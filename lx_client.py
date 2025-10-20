# lx_client.py
import os, time, json
from urllib.parse import urljoin
import requests
from dotenv import load_dotenv

from sign_util import build_sign
from token_manager import get_access_token

load_dotenv()

BASE_URL = "https://openapi.lingxing.com"
APP_ID = os.getenv("APP_ID") or "你的AppId或ak_xxx"
RATE_LIMIT_SLEEP_SEC = 0.15

def now_ts() -> int:
    return int(time.time())

def post_signed(api_path: str, body: dict) -> dict:
    access_token = get_access_token()
    url = urljoin(BASE_URL, api_path)

    sys_for_sign = {
        "access_token": access_token,
        "app_key": APP_ID,
        "timestamp": now_ts(),
    }
    sign, _md5, _raw = build_sign(sys_for_sign, body, APP_ID)
    query = {
        "access_token": access_token,
        "app_key": APP_ID,
        "timestamp": sys_for_sign["timestamp"],
        "sign": sign,
    }

    resp = requests.post(
        url,
        params=query,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    try:
        data = resp.json()
    except Exception:
        raise RuntimeError(f"非 JSON 回應：HTTP {resp.status_code} {resp.text[:200]}")
    if data.get("code") != 0:
        raise RuntimeError(f"API error: {json.dumps(data, ensure_ascii=False)}")
    return data

def fetch_with_range(
    api_path: str,
    *,
    start_time: int,
    end_time: int,
    base_body: dict | None = None,
    page_size: int = 500,
) -> list[dict]:
    """通用：帶 start/end 的分頁拉取"""
    assert 1 <= page_size <= 500
    body = {
        "offset": 0,
        "length": page_size,
        **(base_body or {}),
        "start_time": start_time,
        "end_time": end_time,
    }
    first = post_signed(api_path, body)
    data = first["data"]
    total = int(data.get("total", 0))
    items = list(data.get("list") or [])
    print(f"首頁取得 {len(items)} / 總數 {total}")

    got, pages = len(items), 1
    while got < total:
        body["offset"] = got
        time.sleep(RATE_LIMIT_SLEEP_SEC)
        page = post_signed(api_path, body)
        lst = page["data"].get("list") or []
        items.extend(lst)
        got, pages = len(items), pages + 1
        print(f"第 {pages} 頁，累計 {got}/{total}")
    print(f"完成：共 {total} 筆，實收 {len(items)} 筆，頁數 {pages}")
    return items
