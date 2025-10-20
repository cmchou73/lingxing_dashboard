# sign_util.py
import json, hashlib, base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def to_sign_str(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, dict)):
        return canonical_json(v)
    s = str(v)
    return s if s != "" else None

def build_sign(sys_params: dict, body_params: dict, app_id: str) -> tuple[str, str, str]:
    merged = {}
    merged.update(sys_params or {})
    merged.update(body_params or {})
    items = []
    for k, v in merged.items():
        sv = to_sign_str(v)
        if sv is None:
            continue
        items.append((k, sv))
    items.sort(key=lambda kv: kv[0])
    raw = "&".join(f"{k}={v}" for k, v in items)
    md5_upper = hashlib.md5(raw.encode("utf-8")).hexdigest().upper()
    cipher = AES.new(app_id.encode("utf-8"), AES.MODE_ECB)
    sign_b64 = base64.b64encode(
        cipher.encrypt(pad(md5_upper.encode("utf-8"), AES.block_size))
    ).decode("utf-8")
    return sign_b64, md5_upper, raw
