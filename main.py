from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from models import MetricPush, AlertRuleCreate, AlertRuleUpdate, MetricPoint, MetricSummary, AlertRule, AlertFired
from engine import (
    init_db, push_metric, list_metric_names, get_metric_series, get_metric_stats,
    create_rule, list_rules, update_rule, delete_rule, toggle_rule,
    list_alerts, resolve_alert,
)

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
    version="0.3.0",
    lifespan=lifespan,
)

@app.post("/metrics", response_model=MetricPoint, status_code=201)
async def push(body: MetricPush):
    """Push a metric value. Auto-checks active alert rules and fires alerts on breach."""
    return await push_metric(app.state.db, body.model_dump())

@app.get("/metrics", response_model=list[MetricSummary])
async def get_all_metrics():
    """List all known metric names with last value, last seen, and total data point count."""
    return await list_metric_names(app.state.db)

@app.get("/metrics/{name}")
async def metric_series(name: str, minutes: int = Query(60, description="Lookback window in minutes")):
    """Get recent data points for a metric."""
    return await get_metric_series(app.state.db, name, minutes)

@app.get("/metrics/{name}/stats")
async def metric_stats(name: str, minutes: int = Query(60)):
    """Aggregated stats for a metric: min, max, avg, count over the time window."""
    return await get_metric_stats(app.state.db, name, minutes)

@app.post("/rules", response_model=AlertRule, status_code=201)
async def create_alert_rule(body: AlertRuleCreate):
    """Define an alert rule. Condition: gt | lt | gte | lte. Optional webhook URL."""
    if body.condition not in ("gt", "lt", "gte", "lte"):
        raise HTTPException(422, "condition must be: gt | lt | gte | lte")
    return await create_rule(app.state.db, body.model_dump())

@app.get("/rules", response_model=list[AlertRule])
async def get_rules():
    """List all configured alert rules."""
    return await list_rules(app.state.db)

@app.patch("/rules/{rule_id}", response_model=AlertRule)
async def patch_rule(rule_id: int, body: AlertRuleUpdate):
    """Update rule threshold, window, or webhook without deleting and recreating."""
    result = await update_rule(app.state.db, rule_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(404, "Rule not found")
    return result

@app.delete("/rules/{rule_id}", status_code=204)
async def remove_rule(rule_id: int):
    """Delete an alert rule permanently."""
    ok = await delete_rule(app.state.db, rule_id)
    if not ok:
        raise HTTPException(404, "Rule not found")

@app.post("/rules/{rule_id}/toggle")
async def toggle_alert_rule(rule_id: int, active: bool = Query(...)):
    """Enable or disable an alert rule without deleting it."""
    result = await toggle_rule(app.state.db, rule_id, active)
    if not result:
        raise HTTPException(404, "Rule not found")
    return result

@app.get("/alerts", response_model=list[AlertFired])
async def get_alerts(unresolved_only: bool = Query(False)):
    """List fired alerts. unresolved_only=true for active incidents."""
    return await list_alerts(app.state.db, unresolved_only)

@app.post("/alerts/{alert_id}/resolve", response_model=AlertFired)
async def resolve(alert_id: int):
    """Mark a fired alert as resolved."""
    result = await resolve_alert(app.state.db, alert_id)
    if not result:
        raise HTTPException(404, "Alert not found")
    return result
