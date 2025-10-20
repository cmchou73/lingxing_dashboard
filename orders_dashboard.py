# orders_dashboard.py
import json
import pandas as pd
import streamlit as st
from datetime import datetime, timezone

from lx_client import fetch_with_range, now_ts

st.set_page_config(page_title="LingXing 訂單查詢面板", layout="wide")
st.title("🧾 LingXing 訂單查詢面板")
st.caption("自訂天數 / 多重篩選 / 勾選訂單後續操作（預留）")

API_PATH = "/pb/mp/order/v2/list"  # 訂單列表 API

# ---- 平台代碼/狀態對照 ----
PLATFORM_MAP = {
    10001: "Amazon",
    10008: "Walmart",
    10011: "Wayfair",
    # 需要再補就加在這裡
}

STATUS_MAP = {
    1: "同步中",
    2: "已同步",
    3: "待付款",
    4: "待審核",
    5: "待發貨",
    6: "已發貨",
    7: "已取消/不發貨",
    8: "不顯示",
    9: "平台發貨",
}

ORDER_STATUS_CHOICES = [
    ("不篩選", None),
    ("1 同步中", 1),
    ("2 已同步", 2),
    ("3 待付款", 3),
    ("4 待審核", 4),
    ("5 待發貨", 5),
    ("6 已發貨", 6),
    ("7 已取消/不發貨", 7),
    ("8 不顯示", 8),
    ("9 平台發貨", 9),
]

# ================= 側邊欄：查詢條件 =================
with st.sidebar:
    st.header("查詢條件")
    st.caption("平台代碼：10001=Amazon, 10008=Walmart, 10011=Wayfair …")

    days = st.number_input("最近 N 天（1~31）", min_value=1, max_value=31, value=7, step=1)

    date_type = st.selectbox(
        "日期類型 (date_type)",
        ["update_time", "global_purchase_time", "global_delivery_time", "global_payment_time", "delivery_time"],
        index=0,
    )

    store_ids_str = st.text_input("店鋪 ID（多個以逗號分隔）", "")
    store_ids = [s.strip() for s in store_ids_str.split(",") if s.strip()] or None

    platform_codes_str = st.text_input("平台代碼（多個以逗號分隔）", "")
    try:
        platform_codes = [int(x.strip()) for x in platform_codes_str.split(",") if x.strip()] or None
    except:
        platform_codes = None
        st.warning("平台代碼需為整數（例如 10001,10011），已忽略不合法輸入。")

    include_delete = st.checkbox("包含已刪除訂單", value=False)

    order_status_label = st.selectbox(
        "訂單狀態 (order_status)",
        [x[0] for x in ORDER_STATUS_CHOICES],
        index=0
    )
    order_status_val = dict(ORDER_STATUS_CHOICES)[order_status_label]

    shipping_status_str = st.text_input("出貨狀態 (platform_shipping_status，如 partial,fulfilled)", "")
    payment_status_str  = st.text_input("付款狀態 (platform_payment_status，如 pending,paid)", "")

    page_size = st.slider("每頁筆數 (1~500)", 1, 500, 200)

# ================= 輔助函式 =================
def build_extra_filters() -> dict:
    extra = {}
    if order_status_val is not None:
        extra["order_status"] = int(order_status_val)
    if shipping_status_str.strip():
        extra["platform_shipping_status"] = [s.strip() for s in shipping_status_str.split(",") if s.strip()]
    if payment_status_str.strip():
        extra["platform_payment_status"]  = [s.strip() for s in payment_status_str.split(",") if s.strip()]
    return extra

def fetch_orders(days: int, date_type: str, store_ids, platform_codes, include_delete: bool, extra_filters: dict, page_size: int):
    end = now_ts()
    start = end - days * 86400
    base_body = {"date_type": date_type, "length": page_size, "offset": 0}
    if store_ids:
        base_body["store_id"] = store_ids
    if platform_codes:
        base_body["platform_code"] = platform_codes
    if include_delete is not None:
        base_body["include_delete"] = include_delete
    if extra_filters:
        base_body.update(extra_filters)
    return fetch_with_range(API_PATH, start_time=start, end_time=end, base_body=base_body, page_size=page_size)

def extract_summary_rows(orders: list[dict]) -> pd.DataFrame:
    """轉成摘要表格：platform_order_no, msku, quantity, platform(含名稱+代碼), store, status(含中文), update_time。"""
    rows = []
    for o in orders:
        # 平台單號 & 平台代碼
        platform_code = o.get("platform_code")
        platform_order_no = o.get("platform_order_no") or o.get("order_no") or o.get("platform_order_id")
        if (not platform_order_no or not platform_code) and isinstance(o.get("platform_info"), list) and o["platform_info"]:
            pi = o["platform_info"][0]
            platform_order_no = platform_order_no or pi.get("platform_order_no") or pi.get("platform_order_name")
            code_raw = pi.get("platform_code")
            try:
                platform_code = int(code_raw) if code_raw is not None else platform_code
            except:
                pass

        platform_name = PLATFORM_MAP.get(int(platform_code)) if platform_code is not None else None
        platform_display = f"{platform_name} ({platform_code})" if platform_name else (str(platform_code) if platform_code is not None else "")

        # SKU 與數量（優先 item_info）
        mskus, qty_total = [], 0
        if isinstance(o.get("item_info"), list) and o["item_info"]:
            for it in o["item_info"]:
                sku_val = it.get("msku") or it.get("sku") or it.get("product_sku") or it.get("seller_sku")
                if sku_val:
                    mskus.append(sku_val)
                try:
                    qty_total += int(it.get("quantity") or 0)
                except:
                    pass
        if not mskus:
            for key in ("items", "order_items", "list", "details"):
                if isinstance(o.get(key), list) and o[key]:
                    for it in o[key]:
                        sku_val = it.get("msku") or it.get("sku") or it.get("product_sku") or it.get("seller_sku")
                        if sku_val:
                            mskus.append(sku_val)
                        try:
                            qty_total += int(it.get("quantity") or 0)
                        except:
                            pass
                    break
        msku_str = ",".join(mskus)

        store = o.get("store_name") or o.get("store_id")
        status_val = o.get("status")
        status_text = STATUS_MAP.get(int(status_val), "") if status_val is not None else ""

        ts = o.get("update_time") or o.get("global_payment_time") or o.get("delivery_time")
        update_time_str = ""
        if isinstance(ts, (int, float, str)):
            try:
                ts_int = int(ts)
                if ts_int > 0:
                    update_time_str = datetime.fromtimestamp(ts_int, tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except:
                pass

        rows.append({
            "select": False,
            "platform_order_no": platform_order_no,
            "msku": msku_str,
            "quantity": qty_total,
            "platform": platform_display,  # 顯示名稱+代碼
            "store": store,
            "status": status_val,          # 原始數字
            "status_name": status_text,    # 中文名稱
            "update_time": update_time_str,
            "raw": o,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(by="update_time", ascending=False, na_position="last").reset_index(drop=True)
    return df

# ================= 主區域：查詢與呈現 =================
extra_filters = build_extra_filters()

col_run, col_info = st.columns([1, 2])
with col_run:
    run = st.button("🔍 查詢訂單", use_container_width=True)
with col_info:
    st.write("")

if run:
    # 簡易護欄：避免無限制大查詢
    if not store_ids and not platform_codes:
        st.warning("建議至少指定『店鋪 ID』或『平台代碼』之一，以避免過寬的查詢。")
    if days > 31:
        st.error("API 限制：單次查詢天數不可超過 31 天。")
        st.stop()

    with st.spinner("查詢中…"):
        try:
            orders = fetch_orders(days, date_type, store_ids, platform_codes, include_delete, extra_filters, page_size)
        except Exception as e:
            st.error(f"查詢失敗：{e}")
            st.stop()

    st.success(f"✅ 共取得 {len(orders)} 筆")
    df = extract_summary_rows(orders)

    if df.empty:
        st.info("沒有符合條件的資料。")
        st.stop()

    # 可編輯表格（第一欄可勾選）
    edited = st.data_editor(
        df[["select", "platform_order_no", "msku", "quantity", "platform", "store", "status", "status_name", "update_time"]],
        num_rows="fixed",
        use_container_width=True,
        column_config={
            "select": st.column_config.CheckboxColumn("選擇"),
            "platform_order_no": st.column_config.TextColumn("平台訂單號", width="medium"),
            "msku": st.column_config.TextColumn("MSKU", width="large"),
            "quantity": st.column_config.NumberColumn("數量"),
            "platform": st.column_config.TextColumn("平台"),
            "store": st.column_config.TextColumn("店鋪"),
            "status": st.column_config.NumberColumn("狀態(數字)", help="對應右欄的中文名稱"),
            "status_name": st.column_config.TextColumn("狀態", help="中文名稱顯示"),
            "update_time": st.column_config.TextColumn("更新時間"),
        },
        key="orders_table",
    )

    selected_rows = edited[edited["select"]].copy()
    st.write(f"已選擇 {len(selected_rows)} 筆")

    # 下載 CSV（只輸出關鍵欄位）
    csv_df = edited.drop(columns=["select"])
    st.download_button(
        "下載目前表格 (CSV)",
        data=csv_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="orders.csv",
        mime="text/csv",
        use_container_width=True,
    )

    # ===== 後續操作占位：針對已選訂單呼叫 API =====
    st.divider()
    st.subheader("對已選訂單進行操作（預留）")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📦 打出訂單（佔位）", disabled=len(selected_rows)==0, use_container_width=True):
            targets = [{"platform_order_no": r["platform_order_no"], "store": r["store"]} for _, r in selected_rows.iterrows()]
            st.info("這裡會呼叫你的『打出訂單』API（目前為佔位）。以下是將傳遞的 payload：")
            st.code(json.dumps(targets, ensure_ascii=False, indent=2))
    with c2:
        if st.button("🧾 輸出已選訂單 JSON", disabled=len(selected_rows)==0, use_container_width=True):
            payload = [raw for raw in df.loc[selected_rows.index, "raw"].tolist()]
            st.code(json.dumps(payload, ensure_ascii=False, indent=2))
