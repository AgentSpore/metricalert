from __future__ import annotations
from pydantic import BaseModel, Field
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


class BaselineCompute(BaseModel):
    window_hours: int = Field(24, ge=1, le=168, description="Hours of history to compute baseline from")


class BaselineResponse(BaseModel):
    metric_name: str
    mean: float
    stddev: float
    min: float
    max: float
    p50: float
    p95: float
    p99: float
    sample_size: int
    window_hours: int
    computed_at: str


class AnomalyPoint(BaseModel):
    id: int
    value: float
    deviation_sigma: float
    tags: str | None
    created_at: str


class AutoRuleCreate(BaseModel):
    metric_name: str
    sigma: float = Field(3.0, gt=0, le=10, description="Number of standard deviations for threshold")
    condition: str = Field("gt", description="gt or lt")
    window_minutes: int = Field(5, ge=1)
    notify_url: str | None = None
