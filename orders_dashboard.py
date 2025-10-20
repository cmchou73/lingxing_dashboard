# orders_dashboard.py
import json
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, timezone

from lx_client import fetch_with_range, now_ts

API_PATH = "/pb/mp/order/v2/list"  # 訂單列表 API
st.set_page_config(page_title="LingXing 訂單面板", layout="wide")

st.title("🧾 LingXing 訂單查詢面板")
st.caption("自訂天數 / 進階篩選 / 勾選訂單後續處理（預留接口）")

# ============ 側邊欄：查詢參數 ============
with st.sidebar:
    st.header("查詢條件")

    days = st.number_input("最近 N 天（1~31）", min_value=1, max_value=31, value=7, step=1)

    date_type = st.selectbox(
        "日期類型 (date_type)",
        ["update_time", "global_purchase_time", "global_delivery_time", "global_payment_time", "delivery_time"],
        index=0
    )

    store_ids_str = st.text_input("店鋪 ID，多個以逗號分隔", "")
    store_ids = [s.strip() for s in store_ids_str.split(",") if s.strip()] or None

    platform_codes_str = st.text_input("平台代碼（多個逗號分隔，如 10008,10011）", "")
    platform_codes = [int(x.strip()) for x in platform_codes_str.split(",") if x.strip()] or None

    include_delete = st.checkbox("包含已刪除訂單", value=False)

    order_status_str = st.text_input("訂單狀態 (order_status，例如 1,2,3)", "")
    shipping_status_str = st.text_input("出貨狀態 (platform_shipping_status，例如 partial,fulfilled)", "")
    payment_status_str  = st.text_input("付款狀態 (platform_payment_status，例如 pending,paid)", "")

    page_size = st.slider("每頁筆數 (1~500)", 1, 500, 200)

def build_extra_filters():
    extra = {}
    if order_status_str.strip():
        try:
            extra["order_status"] = int(order_status_str.strip())
        except:
            st.warning("order_status 必須是整數，已忽略該條件。")
    if shipping_status_str.strip():
        extra["platform_shipping_status"] = [s.strip() for s in shipping_status_str.split(",") if s.strip()]
    if payment_status_str.strip():
        extra["platform_payment_status"]  = [s.strip() for s in payment_status_str.split(",") if s.strip()]
    return extra

def fetch_orders(days: int, date_type: str, store_ids, platform_codes, include_delete: bool, extra_filters: dict, page_size: int):
    # 時間區間（以 UTC 時間戳；雙開區間）
    end = now_ts()
    start = end - days * 86400
    base_body = {"date_type": date_type, "length": page_size, "offset": 0}
    if store_ids:       base_body["store_id"] = store_ids
    if platform_codes:  base_body["platform_code"] = platform_codes
    if include_delete is not None:
        base_body["include_delete"] = include_delete
    if extra_filters:
        base_body.update(extra_filters)
    return fetch_with_range(API_PATH, start_time=start, end_time=end, base_body=base_body, page_size=page_size)

def extract_summary_rows(orders: list[dict]) -> pd.DataFrame:
    """把原始訂單轉成摘要表格（訂單號、SKU、平台、店鋪、金額、時間等）。
       欄位名稱可能因平台/版本不同，以下做了容錯處理。"""
    rows = []
    for o in orders:
        # 訂單號（常見：platform_order_no 或 order_no 或 platform_order_id）
        order_no = o.get("platform_order_no") or o.get("order_no") or o.get("platform_order_id") or o.get("id")

        # 平台代碼
        platform_code = o.get("platform_code")

        # 店鋪（常見：store_id / store_name）
        store = o.get("store_name") or o.get("store_id")

        # 訂單金額（猜測常見欄位，若無則留空）
        amount = o.get("order_amount") or o.get("amount") or o.get("total_amount")

        # 時間（以 update_time 為例；若有其它時間欄位可加）
        ts = o.get("update_time") or o.get("global_payment_time") or o.get("delivery_time")
        update_time_str = ""
        if isinstance(ts, (int, float)) and ts > 0:
            # 顯示本地時間（若你要顯示 UTC，換 timezone.utc）
            update_time_str = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")

        # SKU：不同平台欄位可能不同；嘗試從 items 取 sku
        sku = ""
        # 常見：list 欄位，如 items/order_items，各 item 內有 sku/merchant_sku
        for key in ("items", "order_items", "list", "details"):
            if isinstance(o.get(key), list) and o.get(key):
                skus = []
                for it in o[key]:
                    skus.append(it.get("sku") or it.get("product_sku") or it.get("merchant_sku") or it.get("seller_sku") or "")
                sku = ",".join([s for s in skus if s])
                break
        # 若在根層
        if not sku:
            sku = o.get("sku") or o.get("product_sku") or ""

        rows.append({
            "select": False,                 # 給使用者勾選
            "order_no": order_no,
            "platform_code": platform_code,
            "store": store,
            "sku": sku,
            "amount": amount,
            "update_time": update_time_str,
            "raw": o,                        # 原始資料保留，後續可用於 API 動作
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        # 讓訂單最新在上
        df = df.sort_values(by="update_time", ascending=False, na_position="last").reset_index(drop=True)
    return df

# ============ 主區域：查詢 & 顯示 ============
extra_filters = build_extra_filters()

col_run, col_dl = st.columns([1, 1])
with col_run:
    run = st.button("🔍 查詢訂單", use_container_width=True)
with col_dl:
    # 留給下載按鈕（查到資料後才啟用）
    pass

if run:
    with st.spinner("查詢中…"):
        try:
            orders = fetch_orders(days, date_type, store_ids, platform_codes, include_delete, extra_filters, page_size)
        except Exception as e:
            st.error(f"查詢失敗：{e}")
            orders = []

    st.success(f"✅ 共取得 {len(orders)} 筆")
    df = extract_summary_rows(orders)

    if df.empty:
        st.info("沒有符合條件的資料。")
    else:
        # 可編輯表格：第一欄 checkbox 讓使用者勾選
        edited = st.data_editor(
            df[["select", "order_no", "sku", "platform_code", "store", "amount", "update_time"]],
            num_rows="fixed",
            use_container_width=True,
            column_config={
                "select": st.column_config.CheckboxColumn("選擇"),
                "order_no": st.column_config.TextColumn("訂單號", width="medium"),
                "sku": st.column_config.TextColumn("SKU", width="large"),
                "platform_code": st.column_config.NumberColumn("平台"),
                "store": st.column_config.TextColumn("店鋪"),
                "amount": st.column_config.NumberColumn("金額"),
                "update_time": st.column_config.TextColumn("更新時間"),
            },
            key="orders_table",
        )

        # 取出使用者勾選的訂單
        selected_rows = edited[edited["select"]].copy()
        st.write(f"已選擇 {len(selected_rows)} 筆")

        # 下載 CSV
        csv = edited.drop(columns=["select"]).to_csv(index=False).encode("utf-8-sig")
        st.download_button("下載目前表格 (CSV)", data=csv, file_name="orders.csv", mime="text/csv", use_container_width=True)

        # ======= 後續操作（預留） =======
        st.divider()
        st.subheader("對已選訂單進行操作（預留）")

        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📦 打出訂單（建立出貨/列印等）", disabled=len(selected_rows)==0, use_container_width=True):
                # TODO: 在這裡串你後續的 API（例如建立出貨、叫貨、列印標籤…）
                # 可從 selected_rows['order_no'] 取得訂單號；selected_rows['raw'] 取得整筆原始資料
                st.info("這裡會調用你的『打出訂單』API（目前為佔位）。")
        with col_b:
            if st.button("🧾 匯出已選訂單 JSON", disabled=len(selected_rows)==0, use_container_width=True):
                payload = [r for r in selected_rows["raw"].tolist()]
                st.code(json.dumps(payload, ensure_ascii=False, indent=2))
