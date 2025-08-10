# streamlit_app/dashboard.py
from __future__ import annotations
import os
import time
import pandas as pd
import streamlit as st

from repositories.monitor_repository import MonitorRepository
from repositories.action_repository import ActionRepository
from repositories.history_repository import HistoryRepository

DB_PATH = os.getenv("DB_PATH") or "./memecoins.db"
monitor_repo = MonitorRepository(db_path=DB_PATH)
action_repo  = ActionRepository(db_path=DB_PATH)
history_repo = HistoryRepository(db_path=DB_PATH)

st.set_page_config(page_title="BNB Sniper", layout="wide")
st.title("📊 BNB Sniper")

# Sidebar
st.sidebar.header("Opciones")
auto_refresh = st.sidebar.checkbox("Auto-refresh", value=True)
interval_s   = st.sidebar.number_input("Intervalo (seg)", min_value=2, max_value=60, value=3, step=1)
limit_rows   = st.sidebar.number_input("Filas a mostrar", min_value=20, max_value=1000, value=200, step=20)

tab1, tab2, tab3 = st.tabs(["Monitor en vivo", "Acciones", "Resultados"])

# --------------------------
# Monitor
# --------------------------
with tab1:
    st.subheader("Monitor (monitor_state)")

    data = monitor_repo.list_monitored(limit=int(limit_rows))
    if data:
        df = pd.DataFrame(data)

        # Filtros
        symbols = sorted(df["symbol"].dropna().unique()) if "symbol" in df.columns else []
        selected_symbol = st.selectbox("Filtrar por símbolo", options=["(Todos)"] + symbols)
        if selected_symbol != "(Todos)":
            df = df[df["symbol"] == selected_symbol]

        min_pnl = st.number_input("PnL mínimo (%)", value=-100.0)
        max_pnl = st.number_input("PnL máximo (%)", value=1000.0)
        if "pnl" in df.columns:
            df = df[df["pnl"].between(min_pnl, max_pnl)]

        cols = [c for c in ["pair_address","symbol","price","entry_price","buy_price_with_fees","pnl","updated_at","history_id"] if c in df.columns]
        df = df[cols] if cols else df
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No hay datos de monitorización aún.")

# --------------------------
# Acciones pendientes
# --------------------------
with tab2:
    st.subheader("Acciones pendientes (Telegram)")
    rows = action_repo.list_all(estado="pendiente", limit=int(limit_rows))
    if rows:
        df = pd.DataFrame(rows)
        cols = [c for c in ["pair_address","tipo","estado","timestamp"] if c in df.columns]
        st.dataframe(df[cols] if cols else df, use_container_width=True)
    else:
        st.info("No hay acciones pendientes.")

# --------------------------
# Resultados (history)
# --------------------------
with tab3:
    st.subheader("Resultados de ciclos cerrados (history)")

    resumen = history_repo.summary()
    c1, c2, c3 = st.columns(3)
    c1.metric("Ciclos cerrados", f"{resumen.get('closed_cycles', 0)}")
    c2.metric("Beneficio total (BNB)", f"{resumen.get('bnb_profit_total', 0.0):.6f}")
    c3.metric("PnL medio ponderado (%)", f"{resumen.get('avg_pnl_percent_tokens', 0.0):.2f}%")

    hist = history_repo.list_recent(limit=300)
    if hist:
        dfh = pd.DataFrame(hist)

        # Filtros
        symbols_h = sorted(dfh["symbol"].dropna().unique()) if "symbol" in dfh.columns else []
        selected_symbol_h = st.selectbox("Filtrar por símbolo (histórico)", options=["(Todos)"] + symbols_h)
        if selected_symbol_h != "(Todos)":
            dfh = dfh[dfh["symbol"] == selected_symbol_h]

        min_pnl_h = st.number_input("PnL mínimo (%) (histórico)", value=-100.0)
        max_pnl_h = st.number_input("PnL máximo (%) (histórico)", value=1000.0)
        if "pnl" in dfh.columns:
            dfh = dfh[dfh["pnl"].between(min_pnl_h, max_pnl_h)]

        pref = [
            "id","pair_address","token_address","symbol","name",
            "buy_entry_price","buy_price_with_fees","buy_real_price","buy_amount","buy_date",
            "sell_entry_price","sell_price_with_fees","sell_real_price","sell_amount","sell_date",
            "pnl","bnb_amount"
        ]
        cols = [c for c in pref if c in dfh.columns] + [c for c in dfh.columns if c not in pref]
        st.dataframe(dfh[cols], use_container_width=True)
    else:
        st.info("Aún no hay ventas registradas.")

# --------------------------
# Auto-refresh
# --------------------------
if auto_refresh:
    time.sleep(float(interval_s))
    st.rerun()
