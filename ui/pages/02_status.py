"""OAK Hub — Page 02: Live Agent Status."""
import streamlit as st
import httpx
import time

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Agent Status — OAK Hub", layout="wide")
st.title("🤖 Live Agent Status")

auto_refresh = st.toggle("Auto-refresh (5s)", value=False)

col1, col2 = st.columns(2)
with col1:
    if st.button("Refresh Now"):
        st.rerun()

try:
    resp = httpx.get(f"{API_BASE}/api/agents/status", timeout=5.0)
    if resp.status_code == 200:
        agents = resp.json()
        if not agents:
            st.info("No active agents. Submit a problem to spawn agents.")
        else:
            for agent in agents:
                status = agent.get("status", "unknown")
                color = {"running": "🟢", "idle": "🟡", "terminated": "🔴"}.get(status, "⚪")
                st.metric(
                    label=f"{color} {agent.get('agent_id', '?')}",
                    value=status,
                    delta=f"Problem: {agent.get('problem_uuid', 'N/A')[:8]}",
                )
    else:
        st.error(f"API error {resp.status_code}")
except httpx.ConnectError:
    st.error("Cannot connect to OAK API. Is the stack running?")

if auto_refresh:
    time.sleep(5)
    st.rerun()
