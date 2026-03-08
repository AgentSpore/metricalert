from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from models import MetricPush, AlertRuleCreate, MetricPoint, AlertRule, AlertFired
from engine import init_db, push_metric, get_metric_series, create_rule, list_rules, list_alerts, resolve_alert

DB_PATH = "metricalert.db"

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = await init_db(DB_PATH)
    yield
    await app.state.db.close()

app = FastAPI(
    title="MetricAlert",
    description=(
        "Lightweight metric alerting for small SaaS teams. "
        "Push any number, define thresholds, get alerted when something breaks. "
        "No Datadog complexity, no enterprise pricing."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

@app.post("/metrics", response_model=MetricPoint, status_code=201)
async def push(body: MetricPush):
    """
    Push a metric value. Automatically checks all active alert rules
    for this metric and fires alerts if thresholds are breached.
    """
    return await push_metric(app.state.db, body.model_dump())

@app.get("/metrics/{name}")
async def metric_series(name: str, minutes: int = Query(60, description="Lookback window in minutes")):
    """Get recent data points for a metric."""
    return await get_metric_series(app.state.db, name, minutes)

@app.post("/rules", response_model=AlertRule, status_code=201)
async def create_alert_rule(body: AlertRuleCreate):
    """
    Define an alert rule. Example: alert when error_rate > 0.05 over 5 minutes.
    Optionally specify a webhook URL to receive POST notifications.
    """
    if body.condition not in ("gt", "lt", "gte", "lte"):
        raise HTTPException(422, "condition must be: gt | lt | gte | lte")
    return await create_rule(app.state.db, body.model_dump())

@app.get("/rules", response_model=list[AlertRule])
async def get_rules():
    """List all configured alert rules."""
    return await list_rules(app.state.db)

@app.get("/alerts", response_model=list[AlertFired])
async def get_alerts(unresolved_only: bool = Query(False)):
    """List fired alerts. Filter to unresolved_only=true for active incidents."""
    return await list_alerts(app.state.db, unresolved_only)

@app.post("/alerts/{alert_id}/resolve", response_model=AlertFired)
async def resolve(alert_id: int):
    """Mark a fired alert as resolved."""
    result = await resolve_alert(app.state.db, alert_id)
    if not result:
        raise HTTPException(404, "Alert not found")
    return result
