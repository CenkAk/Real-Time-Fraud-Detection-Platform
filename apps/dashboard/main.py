"""Fraud operations dashboard. All data is retrieved through supported API contracts."""

from __future__ import annotations

import os

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="Fraud Command Center", page_icon="🛡️", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem;}
    div[data-testid="stMetric"] {
      background:#111827; border:1px solid #263244;
      padding:1rem; border-radius:12px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=5)
def api_get(path: str) -> object:
    with httpx.Client(timeout=5) as client:
        response = client.get(f"{API_URL}{path}")
        response.raise_for_status()
        return response.json()


st.title("Fraud Command Center")
st.caption("Real-time authorization risk, alerts, model health, and system telemetry")

try:
    overview = api_get("/analytics/overview")
    model = api_get("/model/info")
    alerts = api_get("/alerts?limit=250")
    distribution = api_get("/analytics/risk-distribution")
except Exception as exc:
    st.error(f"API unavailable: {exc}")
    st.stop()

assert isinstance(overview, dict) and isinstance(model, dict) and isinstance(alerts, list)
decisions = overview.get("decisions", {})
left, middle, right, extra = st.columns(4)
left.metric("Transactions · 24h", int(overview.get("transactions_24h", 0)))
middle.metric("Blocked", int(decisions.get("BLOCK", 0)))
right.metric("Manual review", int(decisions.get("MANUAL_REVIEW", 0)))
extra.metric("Model", str(model.get("model_version", "unknown")))

overview_tab, alerts_tab, model_tab, system_tab = st.tabs(
    ["Overview", "Alerts", "Model & drift", "System"]
)
with overview_tab:
    if distribution:
        chart = pd.DataFrame(distribution)
        st.plotly_chart(
            px.bar(
                chart,
                x="risk_score",
                y="count",
                title="Risk score distribution",
                color_discrete_sequence=["#ef4444"],
            ),
            use_container_width=True,
        )
    else:
        st.info("Risk distribution will appear after transactions are processed.")

with alerts_tab:
    if alerts:
        alert_frame = pd.DataFrame(alerts)
        st.dataframe(
            alert_frame[["created_at", "transaction_id", "severity", "status"]],
            use_container_width=True,
            hide_index=True,
        )
        selected = st.selectbox("Inspect transaction", alert_frame["transaction_id"].tolist())
        if selected:
            transaction = api_get(f"/transactions/{selected}")
            prediction = api_get(f"/predictions/{selected}")
            explanation = api_get(f"/predictions/{selected}/explanation")
            one, two = st.columns(2)
            one.json(transaction)
            two.json(prediction)
            st.subheader("Why this decision was made")
            st.json(explanation)
    else:
        st.success("No review or block alerts are currently open.")

with model_tab:
    st.subheader("Active policy")
    st.json(model)
    if model.get("bootstrap_model"):
        st.warning("The bootstrap heuristic is active. Run training before portfolio evaluation.")
    st.info(
        "Delayed-label performance and drift reports appear after enough confirmed outcomes accrue."
    )

with system_tab:
    st.markdown(
        "Operational latency, throughput, errors, consumer health, and outbox "
        "metrics are available in Grafana."
    )
    st.link_button("Open API documentation", f"{API_URL}/docs")
