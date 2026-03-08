from __future__ import annotations
from pydantic import BaseModel


class MetricPush(BaseModel):
    name: str           # e.g. "revenue", "error_rate", "signups"
    value: float
    tags: str | None = None   # e.g. "env=prod,region=us"


class AlertRuleCreate(BaseModel):
    metric_name: str
    condition: str      # gt | lt | gte | lte
    threshold: float
    window_minutes: int = 5
    notify_url: str | None = None   # webhook URL


class MetricPoint(BaseModel):
    id: int
    name: str
    value: float
    tags: str | None
    created_at: str


class AlertRule(BaseModel):
    id: int
    metric_name: str
    condition: str
    threshold: float
    window_minutes: int
    notify_url: str | None
    active: bool
    created_at: str


class AlertFired(BaseModel):
    id: int
    rule_id: int
    metric_name: str
    observed_value: float
    threshold: float
    created_at: str
    resolved_at: str | None
