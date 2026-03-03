"""OAK Hub — Page 01: Submit a new problem."""
import streamlit as st
import httpx

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="OAK Hub", page_icon="🌳", layout="wide")
st.title("🌳 OAK — Orchestrated Agent Kernel")
st.subheader("Submit a New Problem")

with st.form("new_problem"):
    title = st.text_input("Problem title", placeholder="e.g. Sales forecast Q4 2025")
    description = st.text_area("Description", placeholder="Describe the problem and expected output")
    data_path = st.text_input("Data path (optional)", placeholder="/mnt/oak-data/my-dataset.csv")
    submitted = st.form_submit_button("Submit Problem")

if submitted and title:
    with st.spinner("Submitting..."):
        try:
            resp = httpx.post(
                f"{API_BASE}/api/problems",
                json={"title": title, "description": description, "data_path": data_path or None},
                timeout=10.0,
            )
            if resp.status_code == 201:
                data = resp.json()
                st.success(f"Problem submitted! UUID: `{data.get('uuid', data.get('id', '?'))}`")
                st.json(data)
            else:
                st.error(f"API error {resp.status_code}: {resp.text}")
        except httpx.ConnectError:
            st.error("Cannot connect to OAK API at http://localhost:8000. Is the stack running?")

st.divider()
st.caption("Navigate using the sidebar pages →")
