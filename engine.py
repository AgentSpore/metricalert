from __future__ import annotations
import math
import httpx
from datetime import datetime, timezone, timedelta
import aiosqlite

SQL_TABLES = """
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    value REAL NOT NULL,
    tags TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    metric_name TEXT NOT NULL,
    condition TEXT NOT NULL,
    threshold REAL NOT NULL,
    window_minutes INTEGER NOT NULL DEFAULT 5,
    notify_url TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts_fired (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    observed_value REAL NOT NULL,
    threshold REAL NOT NULL,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (rule_id) REFERENCES alert_rules(id)
);
CREATE TABLE IF NOT EXISTS baselines (
    metric_name TEXT PRIMARY KEY,
    mean REAL NOT NULL,
    stddev REAL NOT NULL,
    min_val REAL NOT NULL,
    max_val REAL NOT NULL,
    p50 REAL NOT NULL,
    p95 REAL NOT NULL,
    p99 REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    window_hours INTEGER NOT NULL,
    computed_at TEXT NOT NULL
);
"""

COND_MAP = {"gt": lambda v, t: v > t, "lt": lambda v, t: v < t,
            "gte": lambda v, t: v >= t, "lte": lambda v, t: v <= t}

async def init_db(path: str) -> aiosqlite.Connection:
    db = await aiosqlite.connect(path)
    db.row_factory = aiosqlite.Row
    await db.executescript(SQL_TABLES)
    await db.commit()
    return db

def _row(r): return {k: r[k] for k in r.keys()}

async def push_metric(db: aiosqlite.Connection, data: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    cur = await db.execute(
        "INSERT INTO metrics (name, value, tags, created_at) VALUES (?,?,?,?)",
        (data["name"], data["value"], data.get("tags"), now)
    )
    await db.commit()
    rules = await db.execute_fetchall(
        "SELECT * FROM alert_rules WHERE metric_name=? AND active=1", (data["name"],)
    )
    for rule in rules:
        window_start = (datetime.now(timezone.utc) - timedelta(minutes=rule["window_minutes"])).isoformat()
        recent = await db.execute_fetchall(
            "SELECT AVG(value) as avg FROM metrics WHERE name=? AND created_at >= ?",
            (data["name"], window_start)
        )
        avg_val = recent[0]["avg"] if recent and recent[0]["avg"] is not None else data["value"]
        fn = COND_MAP.get(rule["condition"])
        if fn and fn(avg_val, rule["threshold"]):
            await db.execute(
                "INSERT INTO alerts_fired (rule_id, metric_name, observed_value, threshold, created_at) VALUES (?,?,?,?,?)",
                (rule["id"], data["name"], avg_val, rule["threshold"], now)
            )
            if rule["notify_url"]:
                try:
                    async with httpx.AsyncClient(timeout=5) as client:
                        await client.post(rule["notify_url"], json={
                            "metric": data["name"], "value": avg_val,
                            "threshold": rule["threshold"], "condition": rule["condition"]
                        })
                except Exception:
                    pass
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM metrics WHERE id=?", (cur.lastrowid,))
    return _row(rows[0])

async def list_metric_names(db: aiosqlite.Connection) -> list[dict]:
    rows = await db.execute_fetchall("""
        SELECT
            name,
            COUNT(*) AS total_points,
            MAX(value) AS last_value,
            MAX(created_at) AS last_seen,
            MIN(created_at) AS first_seen
        FROM metrics
        GROUP BY name
        ORDER BY last_seen DESC
    """)
    return [
        {
            "name": r["name"],
            "total_points": r["total_points"],
            "last_value": r["last_value"],
            "last_seen": r["last_seen"],
            "first_seen": r["first_seen"],
        }
        for r in rows
    ]

async def get_metric_series(db, name: str, minutes: int = 60) -> list[dict]:
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    rows = await db.execute_fetchall(
        "SELECT * FROM metrics WHERE name=? AND created_at>=? ORDER BY created_at DESC", (name, since)
    )
    return [_row(r) for r in rows]

async def create_rule(db, data: dict) -> dict:
    now = datetime.now(timezone.utc).isoformat()
    cur = await db.execute(
        "INSERT INTO alert_rules (metric_name, condition, threshold, window_minutes, notify_url, created_at) VALUES (?,?,?,?,?,?)",
        (data["metric_name"], data["condition"], data["threshold"],
         data.get("window_minutes", 5), data.get("notify_url"), now)
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM alert_rules WHERE id=?", (cur.lastrowid,))
    return _row(rows[0])

async def update_rule(db: aiosqlite.Connection, rule_id: int, updates: dict) -> dict | None:
    allowed = {"threshold", "window_minutes", "notify_url"}
    fields = {k: v for k, v in updates.items() if k in allowed}
    if not fields:
        rows = await db.execute_fetchall("SELECT * FROM alert_rules WHERE id=?", (rule_id,))
        return _row(rows[0]) if rows else None
    set_clause = ", ".join(f"{k}=?" for k in fields)
    values = list(fields.values()) + [rule_id]
    cur = await db.execute(f"UPDATE alert_rules SET {set_clause} WHERE id=?", values)
    await db.commit()
    if cur.rowcount == 0:
        return None
    rows = await db.execute_fetchall("SELECT * FROM alert_rules WHERE id=?", (rule_id,))
    return _row(rows[0]) if rows else None

async def list_rules(db) -> list[dict]:
    rows = await db.execute_fetchall("SELECT * FROM alert_rules ORDER BY created_at DESC")
    return [_row(r) for r in rows]

async def list_alerts(db, unresolved_only: bool = False) -> list[dict]:
    if unresolved_only:
        rows = await db.execute_fetchall(
            "SELECT * FROM alerts_fired WHERE resolved_at IS NULL ORDER BY created_at DESC LIMIT 100"
        )
    else:
        rows = await db.execute_fetchall("SELECT * FROM alerts_fired ORDER BY created_at DESC LIMIT 100")
    return [_row(r) for r in rows]

async def resolve_alert(db, alert_id: int) -> dict | None:
    now = datetime.now(timezone.utc).isoformat()
    await db.execute("UPDATE alerts_fired SET resolved_at=? WHERE id=?", (now, alert_id))
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM alerts_fired WHERE id=?", (alert_id,))
    return _row(rows[0]) if rows else None

async def delete_rule(db: aiosqlite.Connection, rule_id: int) -> bool:
    cur = await db.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
    await db.commit()
    return cur.rowcount > 0

async def toggle_rule(db: aiosqlite.Connection, rule_id: int, active: bool) -> dict | None:
    await db.execute("UPDATE alert_rules SET active=? WHERE id=?", (1 if active else 0, rule_id))
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM alert_rules WHERE id=?", (rule_id,))
    return _row(rows[0]) if rows else None

async def get_metric_stats(db: aiosqlite.Connection, name: str, minutes: int = 60) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
    rows = await db.execute_fetchall(
        "SELECT MIN(value) as min, MAX(value) as max, AVG(value) as avg, COUNT(*) as count "
        "FROM metrics WHERE name=? AND created_at>=?", (name, since)
    )
    r = rows[0] if rows else {}
    return {
        "metric_name": name,
        "window_minutes": minutes,
        "count": r["count"] or 0,
        "min": round(r["min"] or 0, 4),
        "max": round(r["max"] or 0, 4),
        "avg": round(r["avg"] or 0, 4),
    }


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


async def compute_baseline(db: aiosqlite.Connection, name: str, window_hours: int = 24) -> dict:
    since = (datetime.now(timezone.utc) - timedelta(hours=window_hours)).isoformat()
    rows = await db.execute_fetchall(
        "SELECT value FROM metrics WHERE name=? AND created_at>=? ORDER BY value ASC",
        (name, since),
    )
    values = [r["value"] for r in rows]
    if len(values) < 10:
        raise ValueError(f"Need at least 10 data points, got {len(values)}")

    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    stddev = math.sqrt(variance)

    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO baselines (metric_name, mean, stddev, min_val, max_val, p50, p95, p99, sample_size, window_hours, computed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(metric_name) DO UPDATE SET
             mean=excluded.mean, stddev=excluded.stddev, min_val=excluded.min_val,
             max_val=excluded.max_val, p50=excluded.p50, p95=excluded.p95, p99=excluded.p99,
             sample_size=excluded.sample_size, window_hours=excluded.window_hours, computed_at=excluded.computed_at""",
        (name, mean, stddev, values[0], values[-1],
         _percentile(values, 50), _percentile(values, 95), _percentile(values, 99),
         n, window_hours, now),
    )
    await db.commit()

    return {
        "metric_name": name,
        "mean": round(mean, 4),
        "stddev": round(stddev, 4),
        "min": round(values[0], 4),
        "max": round(values[-1], 4),
        "p50": round(_percentile(values, 50), 4),
        "p95": round(_percentile(values, 95), 4),
        "p99": round(_percentile(values, 99), 4),
        "sample_size": n,
        "window_hours": window_hours,
        "computed_at": now,
    }


async def get_baseline(db: aiosqlite.Connection, name: str) -> dict | None:
    rows = await db.execute_fetchall(
        "SELECT * FROM baselines WHERE metric_name=?", (name,)
    )
    if not rows:
        return None
    r = rows[0]
    return {
        "metric_name": r["metric_name"],
        "mean": round(r["mean"], 4),
        "stddev": round(r["stddev"], 4),
        "min": round(r["min_val"], 4),
        "max": round(r["max_val"], 4),
        "p50": round(r["p50"], 4),
        "p95": round(r["p95"], 4),
        "p99": round(r["p99"], 4),
        "sample_size": r["sample_size"],
        "window_hours": r["window_hours"],
        "computed_at": r["computed_at"],
    }


async def find_anomalies(db: aiosqlite.Connection, name: str, sigma: float = 3.0, hours: int = 1) -> list[dict]:
    baseline = await get_baseline(db, name)
    if not baseline:
        raise ValueError("No baseline computed for this metric. POST /metrics/{name}/baseline first.")

    mean = baseline["mean"]
    stddev = baseline["stddev"]
    if stddev == 0:
        return []

    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = await db.execute_fetchall(
        "SELECT * FROM metrics WHERE name=? AND created_at>=? ORDER BY created_at DESC",
        (name, since),
    )

    anomalies = []
    for r in rows:
        deviation = abs(r["value"] - mean) / stddev
        if deviation >= sigma:
            anomalies.append({
                "id": r["id"],
                "value": r["value"],
                "deviation_sigma": round(deviation, 2),
                "tags": r["tags"],
                "created_at": r["created_at"],
            })
    return anomalies


async def create_auto_rule(db: aiosqlite.Connection, data: dict) -> dict:
    name = data["metric_name"]
    baseline = await get_baseline(db, name)
    if not baseline:
        raise ValueError("No baseline computed. POST /metrics/{name}/baseline first.")

    sigma = data.get("sigma", 3.0)
    condition = data.get("condition", "gt")

    if condition == "gt":
        threshold = baseline["mean"] + sigma * baseline["stddev"]
    elif condition == "lt":
        threshold = baseline["mean"] - sigma * baseline["stddev"]
    else:
        raise ValueError("condition must be 'gt' or 'lt'")

    return await create_rule(db, {
        "metric_name": name,
        "condition": condition,
        "threshold": round(threshold, 4),
        "window_minutes": data.get("window_minutes", 5),
        "notify_url": data.get("notify_url"),
    })
