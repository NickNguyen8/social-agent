"""
apps/desktop/main.py — Social Agent Desktop App
Dùng pywebview để load apps/ui/ trong native window (Mac + Windows).
Python core được gọi trực tiếp qua bridge.py — không qua HTTP.

Chạy: python apps/desktop/main.py
"""

import sys
from pathlib import Path

# Ensure src/ is on path khi chạy trực tiếp (không cần pip install)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import webview  # pip install pywebview
from apps.desktop.bridge import Bridge

UI_DIR = ROOT / "apps" / "ui"


def main():
    bridge = Bridge()
    window = webview.create_window(
        title="Social Agent",
        url=str(UI_DIR / "index.html"),
        js_api=bridge,
        width=1200,
        height=800,
        min_size=(900, 600),
        background_color="#0f172a",
    )
    webview.start(debug=("--debug" in sys.argv))


if __name__ == "__main__":
    main()
