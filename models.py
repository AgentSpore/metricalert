from __future__ import annotations
from pydantic import BaseModel
from typing import Optional


class MetricPush(BaseModel):
    name: str
    value: float
    tags: str | None = None


class AlertRuleCreate(BaseModel):
    metric_name: str
    condition: str
    threshold: float
    window_minutes: int = 5
    notify_url: str | None = None


class AlertRuleUpdate(BaseModel):
    threshold: Optional[float] = None
    window_minutes: Optional[int] = None
    notify_url: Optional[str] = None


class MetricPoint(BaseModel):
    id: int
    name: str
    value: float
    tags: str | None
    created_at: str


class MetricSummary(BaseModel):
    name: str
    total_points: int
    last_value: float
    last_seen: str
    first_seen: str


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
