"""OAK Hub — Page 04: Skill Library."""
import streamlit as st
import httpx

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Skills — OAK Hub", layout="wide")
st.title("🧠 Skill Library")

search_query = st.text_input("Search skills", placeholder="e.g. csv, etl, time-series")
category_filter = st.selectbox(
    "Category", ["all", "etl", "analysis", "ml", "ui", "infra"], index=0
)
status_filter = st.selectbox("Status", ["permanent", "probationary", "all"], index=0)

params: dict = {}
if search_query:
    params["query"] = search_query
if category_filter != "all":
    params["category"] = category_filter
if status_filter != "all":
    params["status"] = status_filter

if st.button("Search") or search_query:
    try:
        resp = httpx.get(f"{API_BASE}/api/skills", params=params, timeout=5.0)
        if resp.status_code == 200:
            skills = resp.json()
            if not skills:
                st.info("No skills found matching your search.")
            else:
                st.success(f"Found {len(skills)} skill(s)")
                for skill in skills:
                    with st.expander(f"🔧 {skill['name']} [{skill['category']}] — {skill['status']}"):
                        st.write(skill["description"])
                        col1, col2 = st.columns(2)
                        with col1:
                            st.caption(f"Use count: {skill['use_count']}")
                            if skill.get("trigger_keywords"):
                                st.caption(f"Keywords: {', '.join(skill['trigger_keywords'])}")
                        with col2:
                            st.caption(f"ID: `{skill['id'][:8]}...`")
                            if skill.get("filesystem_path"):
                                st.caption(f"Path: `{skill['filesystem_path']}`")
        else:
            st.error(f"API error {resp.status_code}")
    except httpx.ConnectError:
        st.error("Cannot connect to OAK API. Is the stack running?")
