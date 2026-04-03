"""
fb_oauth.py - Local OAuth server để lấy Facebook User Token tự động.
Chạy: python -m social_agent.platforms.fb_oauth

Flow:
  1. Mở browser → Facebook login + grant permissions
  2. Facebook redirect về localhost:8765/callback
  3. Server tự exchange → Page Token vĩnh viễn
  4. Lưu vào .env tự động
"""

import http.server
import json
import os
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import requests
from dotenv import dotenv_values, set_key

APP_ID = "976792168038686"
APP_SECRET = "064259bff686f2d5b3b9518cef5a88b8"
REDIRECT_URI = "http://localhost:8765/callback"
PERMISSIONS = [
    "pages_manage_posts",
    "pages_read_engagement",
    "pages_show_list",
    "pages_read_user_content",
]

ROOT = Path(__file__).resolve().parents[4]
ENV_PATH = ROOT / ".env"

_token_result = {}
_server_done = threading.Event()


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self._respond(404, "Not found")
            return

        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            self._respond(400, f"<h2>Lỗi: {error}</h2>")
            _token_result["error"] = error
            _server_done.set()
            return

        if not code:
            self._respond(400, "<h2>Không nhận được code</h2>")
            _server_done.set()
            return

        # Exchange code → short-lived user token
        resp = requests.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "client_id": APP_ID,
                "client_secret": APP_SECRET,
                "redirect_uri": REDIRECT_URI,
                "code": code,
            },
            timeout=15,
        )
        data = resp.json()
        if "error" in data:
            self._respond(400, f"<h2>Exchange error: {data['error']['message']}</h2>")
            _token_result["error"] = data["error"]["message"]
            _server_done.set()
            return

        short_token = data["access_token"]

        # Exchange short-lived → long-lived user token
        resp2 = requests.get(
            "https://graph.facebook.com/v20.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": APP_ID,
                "client_secret": APP_SECRET,
                "fb_exchange_token": short_token,
            },
            timeout=15,
        )
        long_token = resp2.json().get("access_token", short_token)

        # Lấy danh sách pages
        pages_resp = requests.get(
            "https://graph.facebook.com/v20.0/me/accounts",
            params={"access_token": long_token, "fields": "id,name,access_token"},
            timeout=15,
        )
        pages = pages_resp.json().get("data", [])

        _token_result["user_token"] = long_token
        _token_result["pages"] = pages

        # Build HTML result
        html_pages = ""
        for p in pages:
            html_pages += f"""
            <div style="background:#1e293b;border:1px solid #334155;border-radius:8px;padding:16px;margin:8px 0">
              <b>{p['name']}</b><br>
              <small style="color:#94a3b8">ID: {p['id']}</small><br>
              <code style="font-size:11px;word-break:break-all;color:#22c55e">{p['access_token'][:40]}...</code>
            </div>
            """

        self._respond(200, f"""
        <html><body style="background:#0f172a;color:#f1f5f9;font-family:sans-serif;padding:32px">
          <h2 style="color:#22c55e">✅ Lấy token thành công!</h2>
          <p>Tìm thấy <b>{len(pages)}</b> Page(s). Token đã được lưu vào terminal.</p>
          {html_pages}
          <p style="color:#94a3b8;margin-top:24px">Bạn có thể đóng tab này.</p>
        </body></html>
        """)
        _server_done.set()

    def _respond(self, code, body):
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass  # suppress access logs


def run():
    auth_url = (
        "https://www.facebook.com/v20.0/dialog/oauth?"
        + urllib.parse.urlencode({
            "client_id": APP_ID,
            "redirect_uri": REDIRECT_URI,
            "scope": ",".join(PERMISSIONS),
            "response_type": "code",
        })
    )

    server = http.server.HTTPServer(("localhost", 8765), _CallbackHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    print("\n" + "="*60)
    print("Facebook OAuth — Lấy Page Token tự động")
    print("="*60)
    print(f"\nMở browser và đăng nhập Facebook...")
    print(f"URL: {auth_url}\n")

    webbrowser.open(auth_url)
    print("Đang chờ callback từ Facebook...")
    _server_done.wait(timeout=120)
    server.shutdown()

    if "error" in _token_result:
        print(f"\n❌ Lỗi: {_token_result['error']}")
        return

    pages = _token_result.get("pages", [])
    if not pages:
        print("\n⚠️  Không tìm thấy Page nào. Kiểm tra lại permissions.")
        return

    print(f"\n✅ Tìm thấy {len(pages)} Page(s):\n")
    updates = {}
    for p in pages:
        name = p["name"]
        pid = p["id"]
        token = p["access_token"]
        print(f"  📄 {name} (ID: {pid})")
        print(f"     Token: {token[:40]}...")

        # Map page ID → env var name
        env_map = {
            "1004575376074629": "FASTDX_PAGE_TOKEN",
            "793789520455674": "GTEMAS_JSC_TOKEN",
        }
        env_key = env_map.get(pid)
        if env_key:
            updates[env_key] = token
            print(f"     → Sẽ lưu vào .env: {env_key}")
        print()

    if updates:
        print("Lưu tokens vào .env...")
        for key, value in updates.items():
            set_key(str(ENV_PATH), key, value)
        print(f"✅ Đã lưu {len(updates)} token(s) vào {ENV_PATH}")
    else:
        print("⚠️  Không map được Page ID nào. Tokens:")
        for p in pages:
            print(f"  {p['name']} ({p['id']}): {p['access_token']}")


if __name__ == "__main__":
    run()
