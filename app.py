import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import time

# --- 1. Configuration & Styling ---
st.set_page_config(page_title="Tokyo 2026 Expense", page_icon="🗼", layout="centered")

# Custom CSS for a cleaner look
st.markdown("""
    <style>
    .stButton>button { width: 100%; border-radius: 10px; }
    div[data-testid="stMetricValue"] { font-size: 24px; color: #38bdf8; }
    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] { 
        height: 50px; white-space: pre-wrap; background-color: #1e293b; 
        border-radius: 8px; color: white;
    }
    </style>
    """, unsafe_allow_html=True)

USERS = ['Christen', 'Bill']
EXCHANGE_RATE = 0.2075  # JPY to TWD
SHEET_URL = ""

# --- 2. Connection & Data Fetching ---
conn = st.connection("gsheets", type=GSheetsConnection)

@st.cache_data(ttl=30)
def get_data(spreadsheet=SHEET_URL):
    """Fetch data with a 30-second cache."""
    df = conn.read(spreadsheet=spreadsheet)
    if df is not None and not df.empty:
        # Basic cleaning to prevent KeyError: np.float64
        df = df.dropna(subset=['Payer', 'Amount'])
        df['Payer'] = df['Payer'].astype(str).str.strip()
    return df

# --- 3. Header & Force Refresh ---
header_col1, header_col2 = st.columns([3, 1])

with header_col1:
    st.title("2026 東京記帳 🗼")
    if 'last_sync' not in st.session_state:
        st.session_state.last_sync = datetime.now().strftime("%H:%M:%S")
    st.caption(f"匯率: {EXCHANGE_RATE} | 最後更新: {st.session_state.last_sync}")


if 'last_sync_time' not in st.session_state:
    st.session_state.last_sync_time = 0.0
if 'last_sync_display' not in st.session_state:
    st.session_state.last_sync_display = "尚未同步"
with header_col2:
    st.write("##") # Vertical alignment
    if st.button("🔄 刷新"):
        current_time = time.time()
        time_since_last = current_time - st.session_state.last_sync_time
        
        if time_since_last < 30:
            wait_time = int(30 - time_since_last)
            st.warning(f"請稍候 {wait_time} 秒再刷新")
        else:
            with st.spinner("同步中..."):
                st.cache_data.clear()
                st.session_state.last_sync_time = current_time
                st.session_state.last_sync_display = datetime.now().strftime("%H:%M:%S")
                st.rerun()

# --- 4. Main Tabs ---
tabs = st.tabs(["➕ 新增", "📜 明細", "💰 結算"])

# --- TAB 1: Input Form ---
with tabs[0]:
    with st.form("add_expense", clear_on_submit=True):
        date = st.date_input("日期", datetime.now())
        item = st.text_input("項目名稱", placeholder="例如：一蘭拉麵")
        
        c1, c2 = st.columns(2)
        amount = c1.number_input("金額", min_value=0.0, step=1.0)
        currency = c2.radio("幣別", ["TWD", "JPY"], horizontal=True)
        
        payer = st.selectbox("誰先墊付？", USERS)
        involved = st.multiselect("誰要分攤？", USERS, default=USERS)
        
        submit = st.form_submit_button("新增到 Google Sheets", use_container_width=True)
        
        if submit:
            if not item or amount <= 0 or not involved:
                st.error("⚠️ 請填寫完整內容（項目、金額、分攤人）")
            else:
                with st.spinner("正在同步至 Google..."):
                    # IMPORTANT: Read fresh data with TTL=0 before writing to prevent data loss
                    fresh_data = conn.read(spreadsheet=SHEET_URL, ttl=0)
                    
                    new_row = pd.DataFrame([{
                        "Date": date.strftime("%Y-%m-%d"),
                        "Item": item,
                        "Amount": amount,
                        "Currency": currency,
                        "Payer": payer,
                        "Involved": ", ".join(involved)
                    }])
                    
                    updated_df = pd.concat([fresh_data, new_row], ignore_index=True)
                    conn.update(spreadsheet=SHEET_URL, data=updated_df)
                    
                    # Clear cache so the new item shows up in List/Summary immediately
                    st.cache_data.clear()
                    st.session_state.last_sync = datetime.now().strftime("%H:%M:%S")
                    st.success(f"✅ 已成功紀錄：{item}")
                    st.balloons()
                    st.rerun()

# --- Load Data for other tabs ---
df = get_data()

# --- TAB 2: Expense List ---
with tabs[1]:
    if df is not None and not df.empty:
        # Display as a table sorted by most recent
        st.dataframe(
            df.sort_index(ascending=False), 
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("目前尚無記帳資料")

# --- TAB 3: Summary & Settlement ---
with tabs[2]:
    if df is not None and not df.empty:
        user_stats = {u: {"paid": 0.0, "fair_share": 0.0} for u in USERS}
        total_twd = 0.0

        for _, row in df.iterrows():
            try:
                # Currency conversion
                amt = float(row['Amount'])
                amt_twd = amt * EXCHANGE_RATE if row['Currency'] == 'JPY' else amt
                total_twd += amt_twd
                
                # Payer credit
                p_name = str(row['Payer'])
                if p_name in user_stats:
                    user_stats[p_name]["paid"] += amt_twd
                
                # Split cost
                inv_list = [name.strip() for name in str(row['Involved']).split(",")]
                share = amt_twd / len(inv_list)
                for person in inv_list:
                    if person in user_stats:
                        user_stats[person]["fair_share"] += share
            except:
                continue

        # Metrics display
        m1, m2 = st.columns(2)
        for i, u in enumerate(USERS):
            balance = user_stats[u]["paid"] - user_stats[u]["fair_share"]
            color = "normal" if balance >= 0 else "inverse"
            (m1 if i == 0 else m2).metric(
                label=f"{u} 墊付總額", 
                value=f"NT$ {int(user_stats[u]['paid'])}", 
                delta=f"{int(balance)} (淨額)",
                delta_color=color
            )

        st.divider()
        st.subheader("💡 結算建議")
        
        # Two-person logic: Difference between balances
        diff = user_stats[USERS[0]]["paid"] - user_stats[USERS[0]]["fair_share"]
        
        if abs(diff) < 1:
            st.success("🎉 目前帳目完全平衡！")
        elif diff > 0:
            st.warning(f"👉 **{USERS[1]}** 應支付給 **{USERS[0]}**： **NT$ {int(abs(diff))}**")
        else:
            st.warning(f"👉 **{USERS[0]}** 應支付給 **{USERS[1]}**： **NT$ {int(abs(diff))}**")
            
        st.info(f"📊 旅程總支出： NT$ {int(total_twd)}")
    else:
        st.info("請先新增資料以計算結算結果")