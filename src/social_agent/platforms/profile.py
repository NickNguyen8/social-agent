"""
profile_poster.py - Đăng bài lên Facebook Personal Profile qua Playwright/Patchright
======================================================================================
CẢNH BÁO - ĐỌC TRƯỚC KHI DÙNG:
- Facebook ToS nghiêm cấm automation trên personal profile
- Module này vi phạm Facebook Platform Terms of Service
- Risk: account checkpoint, feature restriction, hoặc suspend
- Chỉ dùng ở tần suất thấp (~1-2 bài/ngày) từ máy cá nhân, không phải server
- KHÔNG chạy module này từ VPS/cloud - datacenter IP là red flag ngay lập tức
- Tác giả không chịu trách nhiệm nếu account bị xử lý
======================================================================================
"""

import asyncio
import logging
import random
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fb_agent.profile")


class ProfileCheckpointError(Exception):
    """
    Facebook yêu cầu xác minh danh tính (2FA checkpoint, security check).
    Agent KHÔNG cố automate qua checkpoint - phải xử lý thủ công.
    """
    pass


class ProfilePoster:
    """
    Đăng bài lên Facebook personal profile qua browser automation.
    Dùng real Chrome profile với session thật để giảm khả năng bị detect.

    Setup lần đầu:
    1. Mở Chrome với profile này, đăng nhập Facebook thủ công
    2. Hoàn thành 2FA nếu có
    3. Để Chrome session persist (không đăng xuất)
    4. Sau đó ProfilePoster sẽ tái sử dụng session đó
    """

    # Selectors Facebook (có thể thay đổi khi FB update UI)
    # Luôn dùng aria-label hoặc data-testid thay vì class name (stable hơn)
    SELECTORS = {
        "compose_box": [
            '[aria-label="What\'s on your mind?"]',
            '[aria-label="Bạn đang nghĩ gì vậy?"]',
            '[data-testid="status-attachment-mentions-input"]',
            'div[role="button"]:has-text("What\'s on your mind")',
            'div[role="button"]:has-text("Bạn đang nghĩ gì")',
        ],
        "post_button": [
            '[aria-label="Post"]',
            '[aria-label="Đăng"]',
            'div[aria-label="Post"][role="button"]',
        ],
        "checkpoint_indicators": [
            'text="We noticed unusual login activity"',
            'text="Confirm Your Identity"',
            'text="Security Check"',
            'text="Xác nhận danh tính"',
            'text="Kiểm tra bảo mật"',
            '[data-testid="checkpoint-cta"]',
        ],
        "logged_in_indicator": [
            '[aria-label="Your profile"]',
            '[aria-label="Profile"]',
            'a[href*="/profile.php"]',
            '[data-testid="nav-profile-link"]',
        ],
    }

    def __init__(
        self,
        chrome_profile_path: str,
        chrome_profile_dir: str = "Default",
        headless: bool = False,  # LUÔN để False - headed mode ít bị detect hơn
    ):
        import os
        # P2 Security: explicit opt-in required - automating personal profile violates FB ToS
        if os.environ.get("ALLOW_PROFILE_AUTOMATION", "").lower() != "yes":
            raise RuntimeError(
                "Profile automation vi phạm Facebook ToS.\n"
                "Nếu bạn hiểu rõ rủi ro, set ALLOW_PROFILE_AUTOMATION=yes trong .env để bật."
            )
        self.chrome_profile_path = Path(chrome_profile_path)
        self.chrome_profile_dir = chrome_profile_dir
        self.headless = headless  # Không dùng headless - quá dễ detect

        if headless:
            logger.warning(
                "CẢNH BÁO: headless=True làm tăng nguy cơ bị Facebook detect. "
                "Nên để headless=False."
            )

    async def post(self, text: str, image_path: Optional[str] = None) -> dict:
        """
        Đăng bài lên Facebook personal profile.
        Raise ProfileCheckpointError nếu Facebook yêu cầu xác minh.
        """
        try:
            from patchright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "patchright chưa được cài. Chạy: pip install patchright && "
                "python -m patchright install chromium"
            )

        if not self.chrome_profile_path.exists():
            raise FileNotFoundError(
                f"Không tìm thấy Chrome profile: {self.chrome_profile_path}\n"
                "Kiểm tra lại đường dẫn trong .env (FB_CHROME_PROFILE_PATH)"
            )

        async with async_playwright() as p:
            logger.info("Khởi động Chrome với persistent profile...")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(self.chrome_profile_path),
                headless=self.headless,
                channel="chrome",  # Dùng Chrome thật, không phải Chromium
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    f"--profile-directory={self.chrome_profile_dir}",
                ],
                viewport={"width": 1280, "height": 800},
                locale="vi-VN",
            )

            page = context.pages[0] if context.pages else await context.new_page()

            try:
                # --- Điều hướng về Facebook home ---
                logger.info("Truy cập Facebook...")
                await page.goto("https://www.facebook.com", wait_until="networkidle", timeout=30000)
                await self._human_delay(2000, 4000)

                # --- Kiểm tra checkpoint trước ---
                await self._check_for_checkpoint(page)

                # --- Xác minh đã đăng nhập ---
                if not await self._is_logged_in(page):
                    raise RuntimeError(
                        "Chưa đăng nhập vào Facebook. "
                        "Mở Chrome với profile này và đăng nhập thủ công trước."
                    )

                # --- Scroll nhẹ để giả lập hành vi người dùng ---
                await page.mouse.wheel(0, random.randint(100, 300))
                await self._human_delay(800, 2000)

                # --- Click vào ô soạn bài ---
                compose = await self._find_element(page, self.SELECTORS["compose_box"])
                if not compose:
                    raise RuntimeError("Không tìm thấy ô soạn bài. Facebook có thể đã thay đổi UI.")

                await compose.click()
                await self._human_delay(1000, 2500)

                # --- Gõ nội dung theo từng ký tự (giả lập người gõ thật) ---
                logger.info(f"Bắt đầu gõ nội dung ({len(text)} ký tự)...")
                await self._type_like_human(page, text)
                await self._human_delay(1500, 3000)

                # --- Đính kèm ảnh nếu có ---
                if image_path:
                    await self._attach_image(page, image_path)
                    await self._human_delay(2000, 4000)

                # --- Kiểm tra checkpoint lần nữa trước khi đăng ---
                await self._check_for_checkpoint(page)

                # --- Bấm nút Đăng ---
                post_btn = await self._find_element(page, self.SELECTORS["post_button"])
                if not post_btn:
                    raise RuntimeError("Không tìm thấy nút Đăng. Facebook có thể đã thay đổi UI.")

                await self._human_delay(500, 1500)
                await post_btn.click()
                logger.info("Đã bấm nút Đăng")
                await self._human_delay(3000, 5000)

                # --- Kiểm tra checkpoint sau khi đăng ---
                await self._check_for_checkpoint(page)

                logger.info("Đăng bài lên personal profile thành công")
                return {"success": True, "post_id": None, "post_url": "https://www.facebook.com"}

            finally:
                await context.close()

    async def _check_for_checkpoint(self, page) -> None:
        """
        Kiểm tra có checkpoint/security check không.
        Nếu có, raise ngay thay vì cố tự động hóa tiếp (dễ làm tình huống tệ hơn).
        """
        for selector in self.SELECTORS["checkpoint_indicators"]:
            try:
                element = page.locator(selector)
                if await element.count() > 0:
                    raise ProfileCheckpointError(
                        "Facebook yêu cầu xác minh danh tính (checkpoint). "
                        "Mở Chrome với profile này và hoàn thành xác minh thủ công. "
                        "Agent sẽ bỏ qua lần post này."
                    )
            except ProfileCheckpointError:
                raise
            except Exception:
                continue

    async def _is_logged_in(self, page) -> bool:
        """Kiểm tra đã đăng nhập vào Facebook chưa."""
        for selector in self.SELECTORS["logged_in_indicator"]:
            try:
                element = page.locator(selector)
                if await element.count() > 0:
                    return True
            except Exception:
                continue
        # Fallback: check URL
        return "facebook.com" in page.url and "login" not in page.url

    async def _find_element(self, page, selectors: list):
        """Thử từng selector, trả về element đầu tiên tìm thấy."""
        for selector in selectors:
            try:
                element = page.locator(selector).first
                if await element.count() > 0:
                    return element
            except Exception:
                continue
        return None

    async def _type_like_human(self, page, text: str) -> None:
        """
        Gõ văn bản simulate người dùng thật.
        Dùng Playwright built-in delay thay vì loop per-character (nhanh hơn ~10x).
        """
        # P3 Performance: keyboard.type(..., delay=ms) là cách cổ định của Playwright
        # Trung bình 80ms/char ≈ realistic typing speed, không cần loop
        await page.keyboard.type(text, delay=80)
        # Thỉnh thoảng dừng lạu hơn để giả lập người nghĩ giữa chừng
        if len(text) > 100:
            await asyncio.sleep(random.uniform(0.5, 1.5))

    async def _attach_image(self, page, image_path: str) -> None:
        """Đính kèm ảnh vào bài đăng."""
        image_path = Path(image_path)
        if not image_path.exists():
            logger.warning(f"Không tìm thấy ảnh {image_path}, bỏ qua đính kèm")
            return
        try:
            photo_btn = page.locator('[aria-label*="Photo"]').first
            if await photo_btn.count() > 0:
                await photo_btn.click()
                await self._human_delay(1000, 2000)
                file_input = page.locator('input[type="file"]').first
                await file_input.set_input_files(str(image_path))
                logger.info(f"Đã đính kèm ảnh: {image_path.name}")
        except Exception as e:
            logger.warning(f"Không thể đính kèm ảnh: {e}")

    async def _human_delay(self, min_ms: int = 800, max_ms: int = 3000) -> None:
        """Delay ngẫu nhiên trong khoảng cho trước (giả lập hành vi người dùng)."""
        delay = random.randint(min_ms, max_ms) / 1000
        await asyncio.sleep(delay)

    def post_sync(self, text: str, image_path: Optional[str] = None) -> dict:
        """Wrapper đồng bộ cho post() - dùng khi gọi từ scheduler không async."""
        return asyncio.run(self.post(text, image_path))
