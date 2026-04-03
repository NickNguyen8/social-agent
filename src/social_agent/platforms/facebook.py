"""
facebook_api.py - Wrapper cho Facebook Graph API v20.0
Hỗ trợ đăng bài lên Page và Group, kèm ảnh hoặc không
"""

import logging
import time
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("fb_agent.api")

BASE_URL = "https://graph.facebook.com/v20.0"

# Các error code có thể retry (rate limit, server error tạm thời)
RETRYABLE_FB_CODES = {4, 17, 341, 368, 32, 613}
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


class FacebookAPIError(Exception):
    """Lỗi từ Facebook Graph API."""
    def __init__(self, message: str, code: int = 0, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class FacebookAPI:
    """
    Client cho Facebook Graph API.
    Xử lý retry tự động với exponential backoff cho rate limit.
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "fb-agent/1.0"})

    def post_to_page(
        self,
        page_id: str,
        access_token: str,
        message: str,
        image_path: Optional[str] = None,
    ) -> dict:
        """
        Đăng bài lên Facebook Page.
        Nếu có image_path, dùng /photos endpoint; không thì dùng /feed.
        """
        logger.info(f"Đăng bài lên Page: {page_id}")
        if image_path:
            return self._post_photo(page_id, access_token, message, image_path)
        return self._post_feed(f"{page_id}/feed", access_token, message)

    def post_to_group(
        self,
        group_id: str,
        access_token: str,
        message: str,
        image_path: Optional[str] = None,
    ) -> dict:
        """
        Đăng bài lên Facebook Group.
        Lưu ý: cần permission publish_to_groups và Group admin phải approve app.
        """
        logger.info(f"Đăng bài lên Group: {group_id}")
        if image_path:
            return self._post_photo(group_id, access_token, message, image_path)
        return self._post_feed(f"{group_id}/feed", access_token, message)

    def _post_feed(self, endpoint: str, access_token: str, message: str) -> dict:
        """POST text-only lên /feed endpoint."""
        url = f"{BASE_URL}/{endpoint}"
        # P0 Security: token in Authorization header, not in POST body
        headers = {"Authorization": f"Bearer {access_token}"}
        payload = {"message": message}
        response = self._request_with_retry("POST", url, data=payload, headers=headers)
        post_id = response.get("id", "")
        logger.info(f"Đăng thành công: post_id={post_id}")
        return {
            "success": True,
            "post_id": post_id,
            "post_url": f"https://www.facebook.com/{post_id.replace('_', '/posts/')}",
        }

    def _post_photo(
        self,
        target_id: str,
        access_token: str,
        message: str,
        image_path: str,
    ) -> dict:
        """POST ảnh kèm caption lên /photos endpoint."""
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

        url = f"{BASE_URL}/{target_id}/photos"
        # Facebook /photos với multipart upload không nhận Authorization header —
        # access_token phải nằm trong form data.
        with open(image_path, "rb") as f:
            files = {"source": (image_path.name, f, "image/jpeg")}
            data = {
                "caption": message,
                "published": "true",
                "access_token": access_token,
            }
            response = self._request_with_retry("POST", url, data=data, files=files)

        post_id = response.get("post_id") or response.get("id", "")
        logger.info(f"Đăng ảnh thành công: post_id={post_id}")
        return {
            "success": True,
            "post_id": post_id,
            "post_url": f"https://www.facebook.com/{post_id.replace('_', '/posts/')}",
        }

    def _request_with_retry(
        self,
        method: str,
        url: str,
        data: dict = None,
        files: dict = None,
        headers: dict = None,
        max_retries: int = None,
    ) -> dict:
        """
        Gọi API với exponential backoff retry.
        Phân biệt retryable vs non-retryable errors.
        """
        retries = max_retries or self.max_retries
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                if files:
                    resp = self.session.request(method, url, data=data, files=files,
                                                headers=headers, timeout=30)
                else:
                    resp = self.session.request(method, url, data=data,
                                                headers=headers, timeout=30)

                # Xử lý HTTP error codes
                if resp.status_code in RETRYABLE_HTTP_CODES:
                    wait = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        f"HTTP {resp.status_code}, retry {attempt}/{retries} sau {wait:.1f}s"
                    )
                    last_error = FacebookAPIError(
                        f"HTTP {resp.status_code}", retryable=True
                    )
                    time.sleep(wait)
                    continue

                if not resp.ok:
                    try:
                        err_body = resp.json()
                    except Exception:
                        err_body = resp.text
                    logger.error(f"Facebook API {resp.status_code}: {err_body}")
                resp.raise_for_status()
                response_data = resp.json()

                # Kiểm tra Facebook API error trong response body
                if "error" in response_data:
                    error = response_data["error"]
                    code = error.get("code", 0)
                    msg = error.get("message", "Unknown FB error")
                    retryable = code in RETRYABLE_FB_CODES

                    if retryable and attempt < retries:
                        wait = self.base_delay * (2 ** (attempt - 1))
                        logger.warning(
                            f"FB error {code}: {msg}. Retry {attempt}/{retries} sau {wait:.1f}s"
                        )
                        last_error = FacebookAPIError(msg, code=code, retryable=True)
                        time.sleep(wait)
                        continue
                    else:
                        raise FacebookAPIError(msg, code=code, retryable=False)

                return response_data

            except (requests.ConnectionError, requests.Timeout) as e:
                wait = self.base_delay * (2 ** (attempt - 1))
                logger.warning(f"Network error attempt {attempt}/{retries}: {e}. Retry sau {wait:.1f}s")
                last_error = e
                time.sleep(wait)

        raise last_error or RuntimeError("Request thất bại sau tất cả retries")

    def refresh_page_tokens(self, app_id: str, app_secret: str, user_token: str) -> dict:
        """
        Gia hạn token tự động (không cần vào browser):
        1. Đổi user_token sang long-lived token mới (thêm 60 ngày)
        2. Lấy tất cả Page Tokens từ /me/accounts
        Trả về: {"long_lived_user_token": str, "pages": [{"id", "name", "token"}]}
        """
        # Bước 1: extend user token
        resp = self.session.get(
            f"{BASE_URL}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": app_id,
                "client_secret": app_secret,
                "fb_exchange_token": user_token,
            },
            timeout=15,
        )
        data = resp.json()
        if "error" in data:
            raise FacebookAPIError(data["error"].get("message", "Token exchange failed"))
        long_token = data["access_token"]

        # Bước 2: lấy page tokens
        resp2 = self.session.get(
            f"{BASE_URL}/me/accounts",
            params={"access_token": long_token, "fields": "id,name,access_token"},
            timeout=15,
        )
        data2 = resp2.json()
        if "error" in data2:
            raise FacebookAPIError(data2["error"].get("message", "Cannot fetch pages"))

        pages = [
            {"id": p["id"], "name": p["name"], "token": p["access_token"]}
            for p in data2.get("data", [])
        ]
        return {"long_lived_user_token": long_token, "pages": pages}

    def validate_token(self, access_token: str) -> dict:
        """Kiểm tra token hợp lệ và các permission."""
        url = f"{BASE_URL}/me"
        params = {"access_token": access_token, "fields": "id,name"}
        try:
            resp = self.session.get(url, params=params, timeout=10)
            data = resp.json()
            if "error" in data:
                return {"valid": False, "error": data["error"].get("message")}
            return {"valid": True, "id": data.get("id"), "name": data.get("name")}
        except Exception as e:
            return {"valid": False, "error": str(e)}
