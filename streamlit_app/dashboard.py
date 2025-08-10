"""
Streamlit dashboard para BNB Sniper
- Monitor en vivo: lee monitor_state (MonitorRepository)
- Acciones: lee acciones pendientes (ActionRepository)
- Resultados: lee history (HistoryRepository) y muestra métricas
"""
from __future__ import annotations
import os
import time
import streamlit as st  # type: ignore

from repositories.monitor_repository import MonitorRepository
from repositories.action_repository import ActionRepository
from repositories.history_repository import HistoryRepository

DB_PATH = os.getenv("DB_PATH") or "./memecoins.db"
monitor_repo = MonitorRepository(db_path=DB_PATH)
action_repo  = ActionRepository(db_path=DB_PATH)
history_repo = HistoryRepository(db_path=DB_PATH)

st.set_page_config(page_title="BNB Sniper", layout="wide")
st.title("📊 BNB Sniper")

tab1, tab2, tab3 = st.tabs(["Monitor en vivo", "Acciones", "Resultados"])

with tab1:
    st.subheader("Monitor (monitor_state)")
    auto_refresh = st.checkbox("Refrescar cada 3s", value=True)
    if auto_refresh:
        st_autorefresh = st.experimental_rerun  # placeholder para compatibilidad
        time.sleep(3)
    rows = monitor_repo.list_monitored(limit=200)
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("No hay datos de monitorización aún.")

with tab2:
    st.subheader("Acciones pendientes (Telegram)")
    rows = action_repo.list_all(estado="pendiente", limit=200)
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("No hay acciones pendientes.")

with tab3:
    st.subheader("Resultados de ciclos cerrados (history)")
    resumen = history_repo.summary()
    c1, c2, c3 = st.columns(3)
    c1.metric("Ciclos cerrados", f"{resumen['closed_cycles']}")
    c2.metric("Beneficio total (BNB)", f"{resumen['bnb_profit_total']:.6f}")
    c3.metric("PnL medio ponderado (%)", f"{resumen['avg_pnl_percent_tokens']:.2f}%")

    rows = history_repo.list_recent(limit=300)
    if rows:
        st.dataframe(rows, use_container_width=True)
    else:
        st.info("Aún no hay ventas registradas.")
