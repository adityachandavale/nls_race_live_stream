import streamlit as st
import pandas as pd
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

URL = "https://livetiming.azurewebsites.net/events/50/results/"

st.set_page_config(layout="wide")
st.title("🏁 NLS Telemetry Dashboard")

refresh_rate = st.sidebar.slider("Refresh (sec)", 5, 60, 10)

# --- SESSION STATE ---
if "prev_df" not in st.session_state:
    st.session_state.prev_df = None

# --- FETCH DATA ---
@st.cache_data(ttl=5)
def fetch_data():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(URL, timeout=60000)

            # Ensure rows actually load
            page.wait_for_selector("tbody tr", timeout=20000)

            html = page.content()
            browser.close()

        tables = pd.read_html(html)
        return tables[0] if tables else pd.DataFrame()

    except Exception as e:
        st.error(f"Error: {e}")
        return pd.DataFrame()

# --- CLEAN DATA ---
def clean_data(df):
    df.columns = [str(c).strip() for c in df.columns]
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

    rename_map = {
        'Pos': 'Position',
        'No': 'Car',
        'No.': 'Car',
        'Entrant / Driver': 'Driver',
        'Cls': 'Class',
        'Category': 'Class'
    }

    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    return df

# --- GAP PARSER ---
def parse_gap(g):
    try:
        return float(str(g).replace("+", "").replace("s", ""))
    except:
        return None

# --- MAIN LOOP ---
placeholder = st.empty()

while True:
    with placeholder.container():
        df = fetch_data()

        if df.empty:
            st.warning("No data")
        else:
            df = clean_data(df)

            # --- FILTER SP9 + PRO ---
            if "Class" in df.columns:
                df = df[
                    df["Class"]
                    .astype(str)
                    .str.replace(" ", "", regex=False)
                    .str.upper()
                    .str.contains("SP9", na=False)
                ]

            if "Pro" in df.columns:
                df = df[
                    df["Pro"]
                    .astype(str)
                    .str.replace(" ", "", regex=False)
                    .str.upper()
                    .isin(["PRO", "PROAM"])
                ]

            # --- GAP ---
            if "Gap" in df.columns:
                df["Gap_s"] = df["Gap"].apply(parse_gap)

            # --- POSITION CHANGE ---
            if st.session_state.prev_df is not None and "Position" in df.columns:
                prev = st.session_state.prev_df.set_index("Car")
                curr = df.set_index("Car")

                df["ΔPos"] = [
                    prev.loc[c]["Position"] - curr.loc[c]["Position"] if c in prev.index else 0
                    for c in curr.index
                ]
            else:
                df["ΔPos"] = 0

            # --- BATTLES ---
            if "Gap_s" in df.columns:
                df["Battle"] = df["Gap_s"].diff().abs() < 1
            else:
                df["Battle"] = False

            # =========================
            # 🧩 FINAL CLEAN LAYOUT
            # =========================

            # --- METRICS ---
            top1, top2, top3 = st.columns(3)

            with top1:
                st.metric("Leader", df.iloc[0]["Driver"] if "Driver" in df.columns else "N/A")

            with top2:
                st.metric("Cars", len(df))

            with top3:
                st.metric("Time", datetime.now().strftime("%H:%M:%S"))

            st.divider()

            # --- STREAMS (TOP) ---
            st.subheader("🔴 Live Streams")

            left, right = st.columns(2)

            with left:
                st.markdown("### 🟣 Twitch")
                st.components.v1.iframe(
                    "https://player.twitch.tv/?channel=verstappensimracing&parent=localhost",
                    height=400
                )

            with right:
                st.markdown("### 🔴 YouTube")
                st.video("https://www.youtube.com/watch?v=N39NJK3G75Q")

            st.divider()

            # --- LEADERBOARD (BOTTOM) ---
            st.subheader("🏎️ Leaderboard")

            def color_rows(row):
                return ["background-color: #2a2a2a"] * len(row) if row.get("Battle", False) else [""] * len(row)

            st.dataframe(
                df.style.apply(color_rows, axis=1),
                use_container_width=True,
                hide_index=True,
                height=700
            )

            # Save snapshot
            st.session_state.prev_df = df.copy()

    time.sleep(refresh_rate)