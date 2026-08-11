"""Fraud operations dashboard backed only by supported API contracts."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import httpx
import pandas as pd
import plotly.express as px
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
TIME_RANGES = {"Last hour": 1, "Last 24 hours": 24, "Last 7 days": 168, "Last 30 days": 720}

st.set_page_config(page_title="Fraud Command Center", page_icon="🛡️", layout="wide")
st.markdown(
    """
    <style>
    .block-container {padding-top: 1.4rem;}
    div[data-testid="stMetric"] {
      background:#111827; border:1px solid #263244;
      padding:1rem; border-radius:12px;
    }
    .case-heading {margin-top:1rem; padding-top:.5rem; border-top:1px solid #263244;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=5)
def api_get(path: str, params: tuple[tuple[str, str], ...] = ()) -> object:
    with httpx.Client(timeout=5) as client:
        response = client.get(f"{API_URL}{path}", params=dict(params))
        response.raise_for_status()
        return response.json()


def api_patch(path: str, payload: Mapping[str, object]) -> object:
    with httpx.Client(timeout=5) as client:
        response = client.patch(f"{API_URL}{path}", json=dict(payload))
        response.raise_for_status()
        return response.json()


def refresh_dashboard(message: str) -> None:
    st.cache_data.clear()
    st.session_state["case_message"] = message
    st.rerun()


def render_risk_factors(explanation: Mapping[str, Any]) -> None:
    factors = explanation.get("top_risk_factors", [])
    if not factors:
        st.info("No material risk factors were recorded for this transaction.")
        return
    factor_frame = pd.DataFrame(factors)
    factor_frame["impact"] = factor_frame["impact"].map(lambda value: f"{float(value):+.3f}")
    factor_frame["direction"] = factor_frame["direction"].map(
        lambda value: "Increases risk" if value == "increases_risk" else "Decreases risk"
    )
    st.dataframe(
        factor_frame.rename(
            columns={"feature": "Risk factor", "impact": "Impact", "direction": "Direction"}
        ),
        use_container_width=True,
        hide_index=True,
    )


def render_case_workflow(alert: Mapping[str, Any]) -> None:
    alert_id = int(alert["alert_id"])
    status = str(alert["status"])
    st.markdown('<div class="case-heading"></div>', unsafe_allow_html=True)
    st.subheader("Analyst workflow")
    status_col, resolution_col = st.columns(2)
    status_col.metric("Case status", status.replace("_", " ").title())
    resolution_col.metric("Resolution", alert.get("resolution") or "Pending")
    if status == "RESOLVED":
        st.success(
            f"Resolved as {alert.get('resolution')} at {alert.get('resolved_at')}. "
            "The confirmed label is now available to monitoring."
        )
        if alert.get("analyst_note"):
            st.caption(f"Analyst note: {alert['analyst_note']}")
        return

    note = st.text_area(
        "Analyst note",
        value=str(alert.get("analyst_note") or ""),
        max_chars=2000,
        key=f"analyst-note-{alert_id}",
        placeholder="Document evidence and the reason for the disposition.",
    )
    review_col, fraud_col, legitimate_col = st.columns(3)
    try:
        if review_col.button(
            "Start review",
            disabled=status == "IN_REVIEW",
            use_container_width=True,
            key=f"review-{alert_id}",
        ):
            api_patch(
                f"/alerts/{alert_id}",
                {"status": "IN_REVIEW", "analyst_note": note or None},
            )
            refresh_dashboard("Alert moved to in review.")
        if fraud_col.button(
            "Mark fraud", type="primary", use_container_width=True, key=f"fraud-{alert_id}"
        ):
            api_patch(
                f"/alerts/{alert_id}",
                {"status": "RESOLVED", "resolution": "FRAUD", "analyst_note": note or None},
            )
            refresh_dashboard("Alert resolved as confirmed fraud.")
        if legitimate_col.button(
            "Mark legitimate", use_container_width=True, key=f"legitimate-{alert_id}"
        ):
            api_patch(
                f"/alerts/{alert_id}",
                {
                    "status": "RESOLVED",
                    "resolution": "LEGITIMATE",
                    "analyst_note": note or None,
                },
            )
            refresh_dashboard("Alert resolved as legitimate.")
    except httpx.HTTPStatusError as exc:
        st.error(f"Could not update the alert: {exc.response.text}")


def render_investigation(detail: Mapping[str, Any]) -> None:
    transaction = detail["transaction"]
    prediction = detail["prediction"]
    snapshot = detail.get("feature_snapshot")
    st.markdown('<div class="case-heading"></div>', unsafe_allow_html=True)
    st.subheader(f"Transaction investigation · {transaction['transaction_id']}")

    transaction_col, risk_col = st.columns(2)
    with transaction_col:
        st.markdown("#### Transaction")
        amount_col, location_col = st.columns(2)
        amount_col.metric("Amount", f"{transaction['amount']:,.2f} {transaction['currency']}")
        location_col.metric("Country", transaction["country"])
        st.write(
            {
                "timestamp": transaction["timestamp"],
                "user": transaction["user_id"],
                "merchant": transaction["merchant_id"],
                "category": transaction["merchant_category"],
                "device": transaction["device_id"],
                "channel": transaction["channel"],
                "ip_address": transaction["ip_address"],
            }
        )
    with risk_col:
        st.markdown("#### Risk decision")
        score_col, probability_col, decision_col = st.columns(3)
        score_col.metric("Risk score", f"{prediction['risk_score']}/100")
        probability_col.metric("Probability", f"{prediction['fraud_probability']:.1%}")
        decision_col.metric("Decision", prediction["decision"].replace("_", " "))
        st.caption(
            f"Model {prediction['model_version']} · "
            f"{prediction['processing_time_ms']:.2f} ms processing time"
        )
        reasons = prediction.get("rule_reasons") or []
        st.markdown("**Triggered rules:** " + (", ".join(reasons) if reasons else "None"))

    st.markdown("#### Why this decision was made")
    if detail.get("explanation_status") == "unavailable":
        st.warning("Feature snapshot unavailable for this historical transaction.")
    render_risk_factors(detail.get("explanation", {}))

    st.markdown("#### User behavior at authorization time")
    if snapshot is None:
        st.info("Point-in-time behavior features were not stored for this historical prediction.")
    else:
        behavior_one, behavior_two, behavior_three, behavior_four = st.columns(4)
        behavior_one.metric("Normal amount", f"{snapshot['user_average_amount']:,.2f}")
        behavior_two.metric("Amount deviation", f"{snapshot['amount_vs_user_average']:.2f}×")
        behavior_three.metric("Transactions · 5m", int(snapshot["transactions_last_5m"]))
        behavior_four.metric("Transactions · 1h", int(snapshot["transactions_last_1h"]))
        behavior_frame = pd.DataFrame(
            [
                {
                    "Signal": "Transactions in last minute",
                    "Value": int(snapshot["transactions_last_1m"]),
                },
                {"Signal": "New merchant", "Value": bool(snapshot["new_merchant"])},
                {"Signal": "New country", "Value": bool(snapshot["new_country"])},
                {"Signal": "New device", "Value": bool(snapshot["new_device"])},
                {"Signal": "IP changed", "Value": bool(snapshot["ip_changed"])},
                {"Signal": "Travel speed (km/h)", "Value": round(snapshot["travel_speed_kmh"], 1)},
                {"Signal": "Impossible travel", "Value": bool(snapshot["impossible_travel"])},
            ]
        )
        st.dataframe(behavior_frame, use_container_width=True, hide_index=True)

    recent = detail.get("recent_user_transactions", [])
    st.markdown("#### Earlier transactions from this user")
    if recent:
        recent_frame = pd.DataFrame(recent)
        st.dataframe(recent_frame, use_container_width=True, hide_index=True)
    else:
        st.caption("No earlier transactions were available for this user.")

    alert = detail.get("alert")
    if alert:
        render_case_workflow(alert)


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

if message := st.session_state.pop("case_message", None):
    st.success(message)

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

    st.subheader("Recent transactions")
    filter_one, filter_two, filter_three = st.columns(3)
    time_label = filter_one.selectbox("Time range", list(TIME_RANGES), index=1)
    decision_filter = filter_two.selectbox(
        "Decision", ["ALL", "APPROVE", "MANUAL_REVIEW", "BLOCK"]
    )
    risk_range = filter_three.slider("Risk score", min_value=0, max_value=100, value=(0, 100))
    filter_four, filter_five, filter_six = st.columns(3)
    country_filter = filter_four.text_input("Country", max_chars=2, placeholder="US")
    category_filter = filter_five.text_input("Merchant category", placeholder="electronics")
    min_amount = filter_six.number_input("Minimum amount", min_value=0.0, value=0.0, step=25.0)

    query = {
        "hours": str(TIME_RANGES[time_label]),
        "min_risk": str(risk_range[0]),
        "max_risk": str(risk_range[1]),
        "min_amount": str(min_amount),
    }
    if decision_filter != "ALL":
        query["decision"] = decision_filter
    if country_filter:
        query["country"] = country_filter.upper()
    if category_filter:
        query["merchant_category"] = category_filter
    try:
        transaction_page = api_get("/transactions", tuple(sorted(query.items())))
    except httpx.HTTPStatusError as exc:
        st.error(f"Could not load transactions: {exc.response.text}")
        transaction_page = {"items": [], "total": 0}

    transaction_payload = transaction_page if isinstance(transaction_page, dict) else {}
    items = transaction_payload.get("items", [])
    st.caption(f"{transaction_payload.get('total', 0)} matching transactions")
    if items:
        transaction_frame = pd.DataFrame(items)
        display_frame = transaction_frame[
            [
                "timestamp",
                "transaction_id",
                "user_id",
                "merchant_id",
                "amount",
                "currency",
                "country",
                "risk_score",
                "decision",
                "case_status",
            ]
        ].rename(
            columns={
                "timestamp": "Time",
                "transaction_id": "Transaction",
                "user_id": "User",
                "merchant_id": "Merchant",
                "amount": "Amount",
                "currency": "Currency",
                "country": "Country",
                "risk_score": "Risk",
                "decision": "Decision",
                "case_status": "Case status",
            }
        )
        selection = st.dataframe(
            display_frame,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="recent-transactions",
        )
        selection_state = getattr(selection, "selection", None)
        selected_rows: list[int] = list(getattr(selection_state, "rows", []))
        if selected_rows:
            selected_row_id = str(transaction_frame.iloc[selected_rows[0]]["transaction_id"])
            st.session_state["selected_transaction_id"] = selected_row_id
        stored_id = st.session_state.get("selected_transaction_id")
        selected_id: str | None = str(stored_id) if stored_id is not None else None
        visible_ids = set(transaction_frame["transaction_id"].astype(str))
        if selected_id not in visible_ids:
            selected_id = None
            st.session_state.pop("selected_transaction_id", None)
        if selected_id:
            try:
                investigation = api_get(f"/transactions/{selected_id}/investigation")
                assert isinstance(investigation, dict)
                render_investigation(investigation)
            except httpx.HTTPStatusError as exc:
                st.error(f"Could not load investigation: {exc.response.text}")
    else:
        st.info("No transactions match the selected filters.")

with alerts_tab:
    if alerts:
        alert_frame = pd.DataFrame(alerts)
        st.dataframe(
            alert_frame[
                ["created_at", "transaction_id", "severity", "status", "resolution"]
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Select a transaction in Overview to open the complete investigation view.")
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
