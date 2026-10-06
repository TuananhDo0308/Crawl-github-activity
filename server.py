#!/usr/bin/env python3
"""
GitHub Daily Activity Web App - Backend Server
==============================================
Server phục vụ:
  1. GitHub OAuth Login Flow (Authorize -> Callback -> Token Exchange)
  2. PAT (Personal Access Token) Fallback Login
  3. API lấy Profile User & Daily Activity Report (dựa trên github_activity_crawler.py)
  4. Phục vụ giao diện Web frontend đẹp mắt (Vanilla HTML/CSS/JS)
"""

import sys
import os
import json
import urllib.request
import urllib.error
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from http.cookies import SimpleCookie
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

# Import crawler logic từ file cùng thư mục
import github_activity_crawler as crawler

PORT = int(os.environ.get("PORT", 3000))
ENV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")

# Helper đọc .env đơn giản không cần thư viện ngoài
def load_env() -> Dict[str, str]:
    env_vars = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")
    return env_vars

def save_env_var(key: str, val: str):
    env = load_env()
    env[key] = val
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        for k, v in env.items():
            f.write(f"{k}={v}\n")


class AppHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def _get_cookie(self, name: str) -> Optional[str]:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
            if name in cookie:
                return cookie[name].value
        except Exception:
            pass
        return None

    def _get_auth_token(self) -> Optional[str]:
        # Ưu tiên Authorization header trước, sau đó là cookie
        auth_header = self.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        cookie_token = self._get_cookie("gh_token")
        if cookie_token:
            return cookie_token
        # Hoặc lấy từ biến môi trường nếu có
        env = load_env()
        return env.get("GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN")

    def _send_json(self, status: int, data: Any, cookies: Optional[Dict[str, str]] = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if cookies:
            for k, v in cookies.items():
                self.send_header("Set-Cookie", v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, url: str, cookies: Optional[Dict[str, str]] = None):
        self.send_response(302)
        self.send_header("Location", url)
        if cookies:
            for k, v in cookies.items():
                self.send_header("Set-Cookie", v)
        self.end_headers()

    # =========================================================
    # GET Handlers
    # =========================================================
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API: Cấu hình OAuth
        if path == "/api/config":
            env = load_env()
            client_id = env.get("GITHUB_CLIENT_ID") or os.environ.get("GITHUB_CLIENT_ID", "")
            has_secret = bool(env.get("GITHUB_CLIENT_SECRET") or os.environ.get("GITHUB_CLIENT_SECRET"))
            host = self.headers.get("Host", f"localhost:{PORT}")
            scheme = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
            redirect_uri = f"{scheme}://{host}/callback"
            
            self._send_json(200, {
                "configured": bool(client_id and has_secret),
                "client_id": client_id,
                "redirect_uri": redirect_uri
            })
            return

        # 2. Login Flow: Chuyển hướng sang GitHub OAuth
        if path == "/login" or path == "/api/auth/github":
            env = load_env()
            client_id = env.get("GITHUB_CLIENT_ID") or os.environ.get("GITHUB_CLIENT_ID", "")
            if not client_id:
                self._redirect("/?error=missing_oauth_config")
                return

            host = self.headers.get("Host", f"localhost:{PORT}")
            scheme = "https" if self.headers.get("X-Forwarded-Proto") == "https" else "http"
            redirect_uri = f"{scheme}://{host}/callback"
            # Scopes: 'read:user' để đọc profile, 'repo' để truy cập cả repo private & events private
            scope = "read:user,repo"
            github_auth_url = (
                f"https://github.com/login/oauth/authorize?"
                f"client_id={urllib.parse.quote(client_id)}&"
                f"redirect_uri={urllib.parse.quote(redirect_uri)}&"
                f"scope={urllib.parse.quote(scope)}&"
                f"state=daily_activity_{int(datetime.now().timestamp())}"
            )
            self._redirect(github_auth_url)
            return

        # 3. Callback sau khi người dùng xác thực trên GitHub
        if path == "/callback":
            code = query.get("code", [None])[0]
            error = query.get("error_description", query.get("error", [None]))[0]

            if error:
                self._redirect(f"/?auth_error={urllib.parse.quote(error)}")
                return

            if not code:
                self._redirect("/?auth_error=no_code_provided")
                return

            # Exchange code lấy access token từ GitHub
            env = load_env()
            client_id = env.get("GITHUB_CLIENT_ID") or os.environ.get("GITHUB_CLIENT_ID", "")
            client_secret = env.get("GITHUB_CLIENT_SECRET") or os.environ.get("GITHUB_CLIENT_SECRET", "")

            token_url = "https://github.com/login/oauth/access_token"
            payload = json.dumps({
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code
            }).encode("utf-8")

            token_req = urllib.request.Request(
                token_url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "User-Agent": "GitHub-Daily-Activity-Crawler"
                }
            )

            try:
                with urllib.request.urlopen(token_req) as resp:
                    token_data = json.loads(resp.read().decode("utf-8"))
                    access_token = token_data.get("access_token")
                    if access_token:
                        cookie_str = f"gh_token={access_token}; Path=/; Max-Age=2592000; SameSite=Lax"
                        self._redirect("/?auth=success", {"gh_token": cookie_str})
                        return
                    else:
                        err_msg = token_data.get("error_description", token_data.get("error", "Unknown token error"))
                        self._redirect(f"/?auth_error={urllib.parse.quote(err_msg)}")
                        return
            except Exception as e:
                self._redirect(f"/?auth_error={urllib.parse.quote(str(e))}")
                return

        # 4. API: Lấy thông tin User hiện tại (Profile)
        if path == "/api/user":
            token = self._get_auth_token()
            if not token:
                self._send_json(401, {"error": "unauthorized", "message": "Chưa đăng nhập."})
                return

            client = crawler.GitHubClient(token=token)
            try:
                user_info = client.request("/user")
                self._send_json(200, {
                    "authenticated": True,
                    "user": {
                        "login": user_info.get("login"),
                        "name": user_info.get("name") or user_info.get("login"),
                        "avatar_url": user_info.get("avatar_url"),
                        "html_url": user_info.get("html_url"),
                        "bio": user_info.get("bio"),
                        "public_repos": user_info.get("public_repos", 0),
                        "total_private_repos": user_info.get("total_private_repos", 0),
                    }
                })
            except Exception as e:
                self._send_json(401, {"error": "invalid_token", "message": str(e)})
            return

        # 5. API: Crawl hoạt động trong ngày
        if path == "/api/activity":
            token = self._get_auth_token()
            if not token:
                self._send_json(401, {"error": "unauthorized", "message": "Vui lòng đăng nhập trước khi xem hoạt động."})
                return

            target_date_str = query.get("date", [datetime.now().strftime("%Y-%m-%d")])[0]
            try:
                target_date = crawler.parse_target_date(target_date_str)
            except ValueError as e:
                self._send_json(400, {"error": "bad_request", "message": str(e)})
                return

            tz_offset = int(query.get("tz", [7])[0])
            mode = query.get("mode", ["auto"])[0]

            client = crawler.GitHubClient(token=token)
            try:
                # Lấy username từ token
                user_info = client.request("/user", description="👤 User Profile: Xác thực và lấy thông tin user đang đăng nhập")
                username = user_info.get("login")
            except Exception as e:
                self._send_json(401, {"error": "invalid_token", "message": f"Không thể xác thực user: {e}"})
                return

            # Chọn mode
            days_ago = (datetime.now().date() - target_date).days
            chosen_mode = mode
            if chosen_mode == "auto":
                chosen_mode = "events" if 0 <= days_ago <= 30 else "search"

            try:
                if chosen_mode == "events":
                    result = crawler.crawl_user_events_by_date(client, username, target_date, tz_offset_hours=tz_offset)
                else:
                    result = crawler.crawl_user_activity_via_search(client, username, target_date)

                md_report = crawler.generate_markdown_report(result)
                self._send_json(200, {
                    "success": True,
                    "mode_used": chosen_mode,
                    "data": result,
                    "markdown": md_report,
                    "network_logs": client.network_logs
                })
            except Exception as e:
                self._send_json(500, {
                    "error": "crawler_error",
                    "message": str(e),
                    "network_logs": client.network_logs
                })
            return

        # 6. Mặc định: Phục vụ Static Files trong thư mục public/
        return super().do_GET()

    # =========================================================
    # POST Handlers
    # =========================================================
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except Exception:
            payload = {}

        # 1. API: Lưu cấu hình OAuth (Client ID & Client Secret)
        if path == "/api/config/save":
            client_id = payload.get("client_id", "").strip()
            client_secret = payload.get("client_secret", "").strip()

            if not client_id or not client_secret:
                self._send_json(400, {"error": "Vui lòng nhập đầy đủ Client ID và Client Secret."})
                return

            save_env_var("GITHUB_CLIENT_ID", client_id)
            save_env_var("GITHUB_CLIENT_SECRET", client_secret)
            self._send_json(200, {"success": True, "message": "Đã lưu cấu hình OAuth thành công!"})
            return

        # 2. API: Đăng nhập trực tiếp bằng Personal Access Token (PAT)
        if path == "/api/auth/token":
            token = payload.get("token", "").strip()
            if not token:
                self._send_json(400, {"error": "Vui lòng nhập token."})
                return

            client = crawler.GitHubClient(token=token)
            try:
                user_info = client.request("/user")
                cookie_str = f"gh_token={token}; Path=/; Max-Age=2592000; SameSite=Lax"
                self._send_json(200, {
                    "success": True,
                    "user": {
                        "login": user_info.get("login"),
                        "name": user_info.get("name") or user_info.get("login"),
                        "avatar_url": user_info.get("avatar_url")
                    }
                }, cookies={"gh_token": cookie_str})
            except Exception as e:
                self._send_json(400, {"error": f"Token không hợp lệ hoặc hết hạn: {e}"})
            return

        # 3. API: Đăng xuất
        if path == "/api/auth/logout":
            cookie_str = "gh_token=; Path=/; Max-Age=0; SameSite=Lax"
            self._send_json(200, {"success": True}, cookies={"gh_token": cookie_str})
            return

        self._send_json(404, {"error": "Not Found"})


def run():
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    server_address = ("", PORT)
    httpd = ThreadingHTTPServer(server_address, AppHandler)
    print("=" * 60)
    print(f"🚀 GitHub Daily Activity Web App đang chạy tại:")
    print(f"👉 http://localhost:{PORT}")
    print("=" * 60)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Đang tắt server...")
        httpd.server_close()


if __name__ == "__main__":
    run()
