"""OAK Hub — Page 03: Solution Gallery."""
import streamlit as st
import httpx

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Gallery — OAK Hub", layout="wide")
st.title("🖼️ Solution Gallery")
st.caption("Completed problems and their generated apps.")

try:
    resp = httpx.get(f"{API_BASE}/api/problems", timeout=5.0)
    if resp.status_code == 200:
        problems = resp.json()
        if not problems:
            st.info("No problems yet. Submit your first problem on the home page.")
        else:
            for p in problems:
                with st.expander(f"📋 {p.get('title', 'Untitled')} — {p.get('status', 'unknown')}"):
                    col1, col2 = st.columns([2, 1])
                    with col1:
                        st.write(p.get("description", ""))
                    with col2:
                        st.code(str(p.get("uuid", p.get("id", ""))), language=None)
                        st.caption(f"Status: **{p.get('status', '?')}**")
                        if p.get("data_path"):
                            st.caption(f"Data: `{p['data_path']}`")
    else:
        st.error(f"API error {resp.status_code}")
except httpx.ConnectError:
    st.error("Cannot connect to OAK API. Is the stack running?")
