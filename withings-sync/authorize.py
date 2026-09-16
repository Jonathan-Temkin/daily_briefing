"""
One-time OAuth2 authorization for the Withings API (official flow, per
Withings' own sample: https://github.com/withings-sas/api-oauth2-python).
Run this once to get a refresh token -- after that, withings_sync.py
refreshes it automatically forever (Withings rotates the refresh token on
every use and this script's sibling handles that).

Prerequisites:
  1. Register a developer app at https://account.withings.com/partner/add_oauth2
     - Environment: dev
     - Callback URL: http://localhost:5000/get_token
  2. Copy .env.example to .env in this folder and fill in WITHINGS_CLIENT_ID
     and WITHINGS_CLIENT_SECRET from the app you just registered.
  3. Run: python authorize.py
     Your browser opens to Withings' login page -- log in with your own
     Withings account (the one your watch is paired to) and approve access.
     This script catches the redirect automatically and saves a refresh
     token to .env. Never share that file.
"""
import os
import secrets
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs

import requests
from dotenv import load_dotenv, set_key

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"
ACCOUNT_URL = "https://account.withings.com"
WBSAPI_URL = "https://wbsapi.withings.net"
CALLBACK_PORT = 5000
CALLBACK_URI = f"http://localhost:{CALLBACK_PORT}/get_token"
SCOPES = "user.info,user.metrics,user.activity"

captured = {}


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        captured["code"] = params.get("code", [None])[0]
        captured["state"] = params.get("state", [None])[0]
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Withings authorization complete. "
            b"You can close this tab and return to the terminal.</h2></body></html>"
        )

    def log_message(self, format, *args):
        pass


def main():
    load_dotenv(ENV_PATH)
    client_id = os.environ.get("WITHINGS_CLIENT_ID")
    client_secret = os.environ.get("WITHINGS_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise SystemExit(
            "Set WITHINGS_CLIENT_ID and WITHINGS_CLIENT_SECRET in .env first "
            "(copy .env.example to .env and fill them in)."
        )

    state = secrets.token_urlsafe(16)
    auth_url = f"{ACCOUNT_URL}/oauth2_user/authorize2?" + urlencode({
        "response_type": "code",
        "client_id": client_id,
        "state": state,
        "scope": SCOPES,
        "redirect_uri": CALLBACK_URI,
    })

    print(f"Opening browser for Withings authorization...\n{auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)
    print(f"Waiting for the redirect on {CALLBACK_URI} ...")
    server.handle_request()

    if not captured.get("code") or captured.get("state") != state:
        raise SystemExit("Authorization failed or state mismatch -- try again.")

    # NOTE: Withings deprecated the old account.withings.com/oauth2/token
    # endpoint -- token exchange now goes through the same wbsapi "action"
    # pattern every other Withings API call uses.
    resp = requests.post(f"{WBSAPI_URL}/v2/oauth2", data={
        "action": "requesttoken",
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": captured["code"],
        "redirect_uri": CALLBACK_URI,
    }).json()

    if resp.get("status") != 0:
        raise SystemExit(f"Token exchange failed: {resp}")

    body = resp.get("body", resp)
    set_key(str(ENV_PATH), "WITHINGS_REFRESH_TOKEN", body["refresh_token"])
    print("Success -- refresh token saved to .env.")
    print("You can now run withings_sync.py (and the daily briefing task will do this automatically).")


if __name__ == "__main__":
    main()
