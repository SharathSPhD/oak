"""OAK Hub — Page 03: Problem Gallery."""
import streamlit as st
import httpx
import pandas as pd

API_BASE = "http://localhost:8000"

st.set_page_config(page_title="Problem Gallery — OAK Hub", layout="wide")
st.title("Problem Gallery")

try:
    resp = httpx.get(f"{API_BASE}/api/problems", timeout=5.0)
    if resp.status_code == 200:
        problems = resp.json()
        if not problems:
            st.info("No problems submitted yet. Go to Submit to create one.")
        else:
            df = pd.DataFrame(problems)
            df["id"] = df["id"].astype(str).str[:8] + "..."
            if "created_at" in df.columns:
                df["created_at"] = pd.to_datetime(df["created_at"]).dt.strftime("%Y-%m-%d %H:%M")
            display_cols = [c for c in ["id", "title", "status", "created_at"] if c in df.columns]
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Details")
            for p in problems:
                with st.expander(f"{p.get('title', 'Untitled')} — {p.get('status', '?')}"):
                    st.json(p)
    else:
        st.error(f"API error {resp.status_code}: {resp.text}")
except httpx.ConnectError:
    st.error("Cannot connect to OAK API. Is the stack running?")
except Exception as e:
    st.error(f"Error: {e}")
