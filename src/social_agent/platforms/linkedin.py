"""
linkedin_api.py - Wrapper cho LinkedIn UGC Posts API v2
========================================================
Hỗ trợ:
  - Đăng bài lên Personal Profile (w_member_social)
  - Đăng bài lên Company Page (w_organization_social)
  - Text post và post kèm ảnh (image share)

Setup OAuth 2.0:
  1. Tạo app tại developers.linkedin.com
  2. Products: Share on LinkedIn + Sign In with LinkedIn
  3. Lấy Access Token qua OAuth 2.0 authorization flow
  4. Scopes cần: r_liteprofile, w_member_social (personal), w_organization_social (page)

Token lifetime: 60 ngày (long-lived), cần refresh định kỳ.
"""

import logging
import time
from pathlib import Path
from typing import Optional, Union

import requests

logger = logging.getLogger("social_agent.linkedin")

BASE_URL = "https://api.linkedin.com/v2"

# Error codes có thể retry
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


class LinkedInAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


class LinkedInAPI:
    """
    Client cho LinkedIn UGC Posts API v2.
    Dùng Access Token (OAuth 2.0) để xác thực.
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 2.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.session = requests.Session()

    def _headers(self, access_token: str) -> dict:
        return {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
            "LinkedIn-Version": "202401",
        }

    def get_profile_urn(self, access_token: str) -> str:
        """
        Lấy URN của profile đang dùng token.
        Dùng URN này làm 'author' khi tạo post.
        Trả về dạng: urn:li:person:XXXXXXXX
        """
        url = f"{BASE_URL}/me"
        resp = self._request_with_retry(
            "GET", url,
            headers=self._headers(access_token),
        )
        person_id = resp.get("id")
        if not person_id:
            raise LinkedInAPIError("Không lấy được profile ID từ LinkedIn")
        return f"urn:li:person:{person_id}"

    def post_to_profile(
        self,
        access_token: str,
        text: str,
        image_path: Optional[str] = None,
        visibility: str = "PUBLIC",
    ) -> dict:
        """
        Đăng bài lên LinkedIn Personal Profile.
        visibility: Union[str, None] = "PUBLIC"  # "PUBLIC" or "CONNECTIONS"
        """
        author_urn = self.get_profile_urn(access_token)
        logger.info(f"Đăng lên LinkedIn Profile: {author_urn}")
        return self._create_post(access_token, author_urn, text, image_path, visibility)

    def post_to_company(
        self,
        access_token: str,
        company_id: str,
        text: str,
        image_path: Optional[str] = None,
        visibility: str = "PUBLIC",
    ) -> dict:
        """
        Đăng bài lên LinkedIn Company Page.
        company_id: ID số của Company Page (lấy từ URL linkedin.com/company/XXXXX)
        """
        author_urn = f"urn:li:organization:{company_id}"
        logger.info(f"Đăng lên LinkedIn Company: {author_urn}")
        return self._create_post(access_token, author_urn, text, image_path, visibility)

    def _create_post(
        self,
        access_token: str,
        author_urn: str,
        text: str,
        image_path: Optional[str],
        visibility: str,
    ) -> dict:
        """Tạo UGC post (text-only hoặc kèm ảnh)."""
        if image_path:
            return self._create_image_post(access_token, author_urn, text, image_path, visibility)
        return self._create_text_post(access_token, author_urn, text, visibility)

    def _create_text_post(
        self,
        access_token: str,
        author_urn: str,
        text: str,
        visibility: str,
    ) -> dict:
        """Tạo text-only UGC post."""
        url = f"{BASE_URL}/ugcPosts"
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text
                    },
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            },
        }
        resp = self._request_with_retry(
            "POST", url,
            headers=self._headers(access_token),
            json=payload,
        )
        post_id = resp.get("id", "")
        # Encode URN cho URL
        encoded_id = post_id.replace(":", "%3A") if post_id else ""
        post_url = f"https://www.linkedin.com/feed/update/{encoded_id}/" if encoded_id else ""
        logger.info(f"LinkedIn post thành công: {post_id}")
        return {
            "success": True,
            "post_id": post_id,
            "post_url": post_url,
        }

    def _create_image_post(
        self,
        access_token: str,
        author_urn: str,
        text: str,
        image_path: str,
        visibility: str,
    ) -> dict:
        """
        Tạo post kèm ảnh theo flow 3 bước của LinkedIn:
        1. Register upload → lấy upload URL
        2. Upload ảnh binary lên upload URL
        3. Tạo UGC post với image asset
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Không tìm thấy ảnh: {image_path}")

        # Bước 1: Register upload
        register_url = f"{BASE_URL}/assets?action=registerUpload"
        register_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": author_urn,
                "serviceRelationships": [{
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent",
                }],
            }
        }
        register_resp = self._request_with_retry(
            "POST", register_url,
            headers=self._headers(access_token),
            json=register_payload,
        )
        upload_url = (
            register_resp
            .get("value", {})
            .get("uploadMechanism", {})
            .get("com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest", {})
            .get("uploadUrl", "")
        )
        asset_urn = register_resp.get("value", {}).get("asset", "")

        if not upload_url or not asset_urn:
            raise LinkedInAPIError("LinkedIn không trả về upload URL hợp lệ")

        # Bước 2: Upload ảnh (stream, không load toàn bộ vào memory)
        upload_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/octet-stream",
        }
        with open(image_path, "rb") as f:
            upload_resp = self.session.put(upload_url, data=f, headers=upload_headers, timeout=60)
        if upload_resp.status_code not in (200, 201):
            raise LinkedInAPIError(f"Upload ảnh thất bại: HTTP {upload_resp.status_code}")

        # Bước 3: Tạo post với image asset
        url = f"{BASE_URL}/ugcPosts"
        payload = {
            "author": author_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "IMAGE",
                    "media": [{
                        "status": "READY",
                        "description": {"text": ""},
                        "media": asset_urn,
                        "title": {"text": ""},
                    }],
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": visibility
            },
        }
        resp = self._request_with_retry(
            "POST", url,
            headers=self._headers(access_token),
            json=payload,
        )
        post_id = resp.get("id", "")
        encoded_id = post_id.replace(":", "%3A") if post_id else ""
        post_url = f"https://www.linkedin.com/feed/update/{encoded_id}/" if encoded_id else ""
        logger.info(f"LinkedIn image post thành công: {post_id}")
        return {
            "success": True,
            "post_id": post_id,
            "post_url": post_url,
        }

    def _request_with_retry(
        self,
        method: str,
        url: str,
        headers: dict = None,
        json: dict = None,
        max_retries: int = None,
    ) -> dict:
        retries = max_retries or self.max_retries
        last_error = None

        for attempt in range(1, retries + 1):
            try:
                resp = self.session.request(
                    method, url, headers=headers, json=json, timeout=30
                )
                if resp.status_code in RETRYABLE_HTTP_CODES:
                    wait = self.base_delay * (2 ** (attempt - 1))
                    logger.warning(f"HTTP {resp.status_code}, retry {attempt}/{retries} sau {wait:.1f}s")
                    last_error = LinkedInAPIError(
                        f"HTTP {resp.status_code}", status_code=resp.status_code, retryable=True
                    )
                    time.sleep(wait)
                    continue

                if resp.status_code == 201:
                    # Successful POST - LinkedIn trả 201 cho create
                    try:
                        return resp.json()
                    except Exception:
                        return {"id": resp.headers.get("x-restli-id", "")}

                resp.raise_for_status()
                return resp.json()

            except (requests.ConnectionError, requests.Timeout) as e:
                wait = self.base_delay * (2 ** (attempt - 1))
                logger.warning(f"Network error attempt {attempt}: {e}. Retry sau {wait:.1f}s")
                last_error = e
                time.sleep(wait)

        raise last_error or RuntimeError("LinkedIn request thất bại sau tất cả retries")

    def validate_token(self, access_token: str) -> dict:
        """Kiểm tra token hợp lệ."""
        try:
            url = f"{BASE_URL}/me"
            resp = self.session.get(
                url,
                headers=self._headers(access_token),
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                name = f"{data.get('localizedFirstName', '')} {data.get('localizedLastName', '')}".strip()
                return {"valid": True, "id": data.get("id"), "name": name}
            return {"valid": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"valid": False, "error": str(e)}
