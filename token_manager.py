import json
import time
import pathlib
from typing import Optional, Tuple
import os

import requests
from requests import Response
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("APP_ID") or "你的AppId或ak_xxx"
APP_SECRET = os.getenv("APP_SECRET") or "你的AppSecret"

BASE = "https://openapi.lingxing.com"
AUTH_URL = f"{BASE}/api/auth-server/oauth/access-token"
REFRESH_URL = f"{BASE}/api/auth-server/oauth/refresh"

TOKEN_FILE = pathlib.Path("token.json")
EXPIRY_BUFFER = 120  # 剩餘 <=120 秒先刷新

def _now() -> int:
    return int(time.time())

def _load_token_file() -> Optional[dict]:
    if not TOKEN_FILE.exists():
        return None
    try:
        with TOKEN_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _save_token_file(payload: dict) -> None:
    with TOKEN_FILE.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def _calc_expiry(obtained_at: int, expires_in: int) -> int:
    return obtained_at + int(expires_in)

def _is_token_valid(token: Optional[dict]) -> bool:
    if not token or not token.get("access_token"):
        return False
    expires_at = int(token.get("expires_at", 0))
    return _now() < (expires_at - EXPIRY_BUFFER)

def _fetch_new_token() -> dict:
    resp = requests.post(
        AUTH_URL,
        files={"appId": (None, APP_ID), "appSecret": (None, APP_SECRET)},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "200" or "data" not in data:
        raise RuntimeError(f"Auth failed: {data}")

    core = data["data"]
    obtained_at = _now()
    expires_in = int(core.get("expires_in", 0))
    token_blob = {
        "access_token": core.get("access_token"),
        "refresh_token": core.get("refresh_token"),
        "expires_in": expires_in,
        "obtained_at": obtained_at,
        "expires_at": _calc_expiry(obtained_at, expires_in),
        "raw_response": data,
    }
    _save_token_file(token_blob)
    return token_blob

def _refresh_token(app_id: str, refresh_token: str) -> Tuple[bool, Optional[dict]]:
    resp = requests.post(
        REFRESH_URL,
        files={"appId": (None, app_id), "refreshToken": (None, refresh_token)},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != "200" or "data" not in data:
        return False, data

    core = data["data"]
    obtained_at = _now()
    expires_in = int(core.get("expires_in", 0))
    token_blob = {
        "access_token": core.get("access_token"),
        "refresh_token": core.get("refresh_token"),
        "expires_in": expires_in,
        "obtained_at": obtained_at,
        "expires_at": _calc_expiry(obtained_at, expires_in),
        "raw_response": data,
    }
    _save_token_file(token_blob)
    return True, token_blob

def _ensure_fresh_token() -> dict:
    cached = _load_token_file()
    if _is_token_valid(cached):
        return cached
    if cached and cached.get("refresh_token"):
        ok, refreshed = _refresh_token(APP_ID, cached["refresh_token"])
        if ok and _is_token_valid(refreshed):
            return refreshed
    return _fetch_new_token()

def get_access_token(force_renew: bool = False) -> str:
    if force_renew:
        return _fetch_new_token()["access_token"]
    return _ensure_fresh_token()["access_token"]

if __name__ == "__main__":
    print("Access token:", get_access_token())
