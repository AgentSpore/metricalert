from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from models import (
    MetricPush, AlertRuleCreate, AlertRuleUpdate, MetricPoint, MetricSummary,
    AlertRule, AlertFired, BaselineCompute, BaselineResponse, AnomalyPoint, AutoRuleCreate,
)
from engine import (
    init_db, push_metric, list_metric_names, get_metric_series, get_metric_stats,
    create_rule, list_rules, update_rule, delete_rule, toggle_rule,
    list_alerts, resolve_alert,
    compute_baseline, get_baseline, find_anomalies, create_auto_rule,
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
        "Lightweight metric alerting with anomaly detection. "
        "Push metrics, set thresholds or auto-detect anomalies via statistical baselines. "
        "No Datadog complexity, no enterprise pricing."
    ),
    version="0.4.0",
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

@app.post("/metrics/{name}/baseline", response_model=BaselineResponse)
async def create_baseline(name: str, body: BaselineCompute = BaselineCompute()):
    """Compute statistical baseline (mean, stddev, percentiles) from recent data. Min 10 points required."""
    try:
        return await compute_baseline(app.state.db, name, body.window_hours)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/metrics/{name}/baseline", response_model=BaselineResponse)
async def view_baseline(name: str):
    """View the last computed baseline for a metric."""
    result = await get_baseline(app.state.db, name)
    if not result:
        raise HTTPException(404, "No baseline computed. POST /metrics/{name}/baseline first.")
    return result

@app.get("/metrics/{name}/anomalies", response_model=list[AnomalyPoint])
async def detect_anomalies(
    name: str,
    sigma: float = Query(3.0, gt=0, le=10, description="Deviation threshold in standard deviations"),
    hours: int = Query(1, ge=1, le=168, description="Lookback window in hours"),
):
    """Find data points that deviate more than N sigma from the baseline."""
    try:
        return await find_anomalies(app.state.db, name, sigma, hours)
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.post("/rules", response_model=AlertRule, status_code=201)
async def create_alert_rule(body: AlertRuleCreate):
    """Define an alert rule. Condition: gt | lt | gte | lte. Optional webhook URL."""
    if body.condition not in ("gt", "lt", "gte", "lte"):
        raise HTTPException(422, "condition must be: gt | lt | gte | lte")
    return await create_rule(app.state.db, body.model_dump())

@app.post("/rules/auto", response_model=AlertRule, status_code=201)
async def create_auto_alert_rule(body: AutoRuleCreate):
    """Create alert rule with threshold auto-calculated from baseline (mean + sigma * stddev)."""
    if body.condition not in ("gt", "lt"):
        raise HTTPException(422, "condition must be 'gt' or 'lt' for auto rules")
    try:
        return await create_auto_rule(app.state.db, body.model_dump())
    except ValueError as e:
        raise HTTPException(400, str(e))

@app.get("/rules", response_model=list[AlertRule])
async def get_rules():
    return await list_rules(app.state.db)

@app.patch("/rules/{rule_id}", response_model=AlertRule)
async def patch_rule(rule_id: int, body: AlertRuleUpdate):
    result = await update_rule(app.state.db, rule_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(404, "Rule not found")
    return result

@app.delete("/rules/{rule_id}", status_code=204)
async def remove_rule(rule_id: int):
    ok = await delete_rule(app.state.db, rule_id)
    if not ok:
        raise HTTPException(404, "Rule not found")

@app.post("/rules/{rule_id}/toggle")
async def toggle_alert_rule(rule_id: int, active: bool = Query(...)):
    result = await toggle_rule(app.state.db, rule_id, active)
    if not result:
        raise HTTPException(404, "Rule not found")
    return result

@app.get("/alerts", response_model=list[AlertFired])
async def get_alerts(unresolved_only: bool = Query(False)):
    return await list_alerts(app.state.db, unresolved_only)

@app.post("/alerts/{alert_id}/resolve", response_model=AlertFired)
async def resolve(alert_id: int):
    result = await resolve_alert(app.state.db, alert_id)
    if not result:
        raise HTTPException(404, "Alert not found")
    return result
