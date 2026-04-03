"""
images.py - Generate ảnh minh họa bằng Gemini + Pillow overlay
Pipeline:
  1. Gemini gemini-2.5-flash-image tạo ảnh cinematic với text/visual tích hợp
  2. Pillow overlay: logo FastDX nhỏ góc dưới phải

Style reference: dark neon cinematic — light trails, 3D elements, glowing text
integrated into scene (không phải flat background + overlay riêng biệt).
"""

import base64
import logging
import sys
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("social_agent.image")

GEMINI_IMG_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.5-flash-image:generateContent"
)

# Cross-platform font paths
if sys.platform == "darwin":
    FONT_PATHS = [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
elif sys.platform == "win32":
    FONT_PATHS = [
        "C:/Windows/Fonts/arialuni.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
else:
    FONT_PATHS = [
        "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
    ]


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    paths = FONT_PATHS if not bold else [FONT_PATHS[1]] + FONT_PATHS
    for path in paths:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _build_prompt(content_dict: dict) -> str:
    """
    Tạo prompt cinematic dựa trên content — visual metaphor theo format và topic.
    Inspired by: dark neon tech imagery với text/labels tích hợp vào scene.
    """
    title = (
        content_dict.get("title")
        or content_dict.get("hook")
        or content_dict.get("question")
        or content_dict.get("opening_hook")
        or "FastDX Digital Transformation"
    )
    key_points = content_dict.get("key_points", [])

    # Rút ra 2-3 keywords nổi bật từ key_points để đưa vào scene
    scene_labels = []
    for kp in key_points[:3]:
        # Lấy ~3 từ đầu của mỗi key point làm label ngắn
        words = kp.split()[:4]
        scene_labels.append(" ".join(words).upper())

    labels_str = " | ".join(scene_labels) if scene_labels else "AI · DATA · AUTOMATION"

    # Detect visual theme từ title/keywords
    title_lower = title.lower()
    if any(w in title_lower for w in ["agentic", "ai agent", "tự động", "automation"]):
        visual_theme = (
            "Futuristic AI pipeline: glowing autonomous agents as luminous nodes connected "
            "by electric blue data streams, each node pulsing with cyan light, "
            "dark circuit board floor, holographic task cards floating in 3D space"
        )
    elif any(w in title_lower for w in ["doanh nghiệp", "sme", "business", "chi phí", "cost"]):
        visual_theme = (
            "Dramatic business transformation: one side dark crumbling legacy systems "
            "with red warning labels, other side gleaming neon-lit modern tech stack, "
            "speed lines and light trails showing the transition, cinematic depth"
        )
    elif any(w in title_lower for w in ["data", "dữ liệu", "analytics", "insight"]):
        visual_theme = (
            "Dark command center: massive holographic data dashboard with glowing charts, "
            "flowing data rivers of cyan particles, 3D bar graphs rising dramatically, "
            "neon grid floor perspective shot"
        )
    elif any(w in title_lower for w in ["digital", "chuyển đổi", "transformation", "dx"]):
        visual_theme = (
            "Speed transformation: electric blue and orange neon light trails racing forward "
            "on dark circuit board landscape, OLD labels fading behind, "
            "FAST FORWARD energy, cinematic motion blur"
        )
    else:
        visual_theme = (
            "Epic tech landscape: dark navy environment with electric blue (#2563EB) "
            "and cyan accent glows, interconnected network nodes as luminous spheres, "
            "flowing data streams as light trails, dramatic perspective, "
            "futuristic Vietnamese tech company aesthetic"
        )

    prompt = f"""Create a cinematic dark neon tech social media image (1:1 square format, 1080x1080px).

STYLE: Professional tech company post. Dark backgrounds (#0A1628 navy/black).
Neon glowing elements in electric blue (#2563EB), cyan, and orange accents.
3D perspective shots. Dramatic lighting. High detail. Photorealistic + stylized hybrid.

VISUAL CONCEPT: {visual_theme}

FLOATING LABELS IN SCENE (short English only, render as holographic panels or neon signs):
{labels_str}

STRICT RULES:
- NO Vietnamese text anywhere in the image
- NO brand names, NO logos, NO "FastDX" text — leave bottom-right corner empty
- NO plain white backgrounds, NO flat designs
- Labels must be short English words only (max 3 words each)

COMPOSITION:
- Cinematic wide-angle perspective with depth
- Key visual elements in foreground, mid, background layers
- Dramatic contrast between dark background and glowing elements
- Bottom 15% of image: keep relatively dark/clear for text overlay

QUALITY: Ultra-detailed, 8K quality render, professional social media ready."""

    return prompt


def _overlay_logo(image_path: str, brand: str = "FastDX") -> str:
    """
    Minimal overlay: chỉ logo nhỏ góc dưới phải.
    Không che ảnh chính — ảnh đã có text tích hợp từ Gemini.
    """
    img = Image.open(image_path).convert("RGBA")
    W, H = img.size

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Logo nhỏ góc dưới phải — semi-transparent pill
    font_size = int(H * 0.032)
    font = _get_font(font_size, bold=True)
    bbox = draw.textbbox((0, 0), brand, font=font)
    # bbox = (left, top, right, bottom) — top/left có thể != 0 tuỳ font
    bx0, by0, bx1, by1 = bbox
    tw, th = bx1 - bx0, by1 - by0

    pad_x, pad_y = int(font_size * 0.8), int(font_size * 0.5)
    pill_w = tw + pad_x * 2
    pill_h = th + pad_y * 2
    margin = int(H * 0.025)

    x0 = W - pill_w - margin
    y0 = H - pill_h - margin
    x1 = W - margin
    y1 = H - margin

    # Pill background
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=pill_h // 2,
                            fill=(10, 22, 40, 120))
    # Blue border
    draw.rounded_rectangle([(x0, y0), (x1, y1)], radius=pill_h // 2,
                            outline=(37, 99, 235, 140), width=1)

    # Căn chữ đúng giữa pill — trừ offset bbox để compensate font descender
    text_x = x0 + (pill_w - tw) // 2 - bx0
    text_y = y0 + (pill_h - th) // 2 - by0
    draw.text((text_x, text_y), brand, font=font, fill=(37, 99, 235, 160))

    result = Image.alpha_composite(img, overlay).convert("RGB")

    out = tempfile.NamedTemporaryFile(suffix=".jpg", prefix="fastdx_post_", delete=False)
    result.save(out.name, "JPEG", quality=95)
    out.close()
    return out.name


def generate_image(content_dict: dict, api_key: str) -> str:
    """
    Generate cinematic social media image từ content dict.
    Trả về đường dẫn file ảnh JPEG.
    """
    prompt = _build_prompt(content_dict)
    title_preview = (content_dict.get("title") or "")[:40]
    logger.info(f"Generating cinematic image for: {title_preview}...")

    resp = requests.post(
        GEMINI_IMG_URL,
        headers={"x-goog-api-key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
        },
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()

    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    image_bytes = None
    for part in parts:
        if "inlineData" in part:
            image_bytes = base64.b64decode(part["inlineData"]["data"])
            break

    if not image_bytes:
        raise ValueError(f"Gemini không trả về ảnh: {data}")

    tmp_bg = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_bg.write(image_bytes)
    tmp_bg.close()
    logger.info(f"Raw image: {tmp_bg.name} ({len(image_bytes)//1024}KB)")

    result_path = _overlay_logo(tmp_bg.name)
    logger.info(f"Final image: {result_path}")

    Path(tmp_bg.name).unlink(missing_ok=True)
    return result_path
