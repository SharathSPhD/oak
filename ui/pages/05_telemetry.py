"""OAK Hub — Page 05: Agent Telemetry."""
import streamlit as st
import httpx

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Telemetry — OAK Hub", layout="wide")
st.title("📊 Agent Telemetry")

try:
    # Health check to show system status
    health_resp = httpx.get(f"{API_BASE}/health", timeout=5.0)
    if health_resp.status_code == 200:
        health = health_resp.json()
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("OAK Mode", health.get("oak_mode", "?"))
        with col2:
            st.metric("Routing Strategy", health.get("routing_strategy", "?"))
        with col3:
            st.metric("API Key Present", "✅" if health.get("api_key_present") else "❌")

        st.subheader("Feature Flags")
        flags = health.get("feature_flags", {})
        cols = st.columns(len(flags))
        for col, (flag, value) in zip(cols, flags.items()):
            col.metric(flag.replace("_", " ").title(), "On" if value else "Off")

        st.subheader("Models")
        models = health.get("models", {})
        for role, model in models.items():
            st.text(f"{role}: {model}")
    else:
        st.error(f"Health check failed: {health_resp.status_code}")
except httpx.ConnectError:
    st.error("Cannot connect to OAK API at http://localhost:8000. Is the stack running?")

st.divider()
# Telemetry data from API (Phase 3+)
try:
    telem_resp = httpx.get(f"{API_BASE}/api/telemetry", timeout=5.0)
    if telem_resp.status_code == 200:
        data = telem_resp.json()
        st.subheader("Recent Telemetry Events")
        st.json(data)
    elif telem_resp.status_code != 501:
        st.warning(f"Telemetry endpoint returned {telem_resp.status_code}")
    else:
        st.info("Telemetry endpoint not yet implemented (Phase 3+)")
except httpx.ConnectError:
    pass
