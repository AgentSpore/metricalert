from __future__ import annotations
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
    # Check alert rules for this metric
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
    """Delete an alert rule by ID."""
    cur = await db.execute("DELETE FROM alert_rules WHERE id=?", (rule_id,))
    await db.commit()
    return cur.rowcount > 0

async def toggle_rule(db: aiosqlite.Connection, rule_id: int, active: bool) -> dict | None:
    """Enable or disable an alert rule without deleting it."""
    await db.execute("UPDATE alert_rules SET active=? WHERE id=?", (1 if active else 0, rule_id))
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM alert_rules WHERE id=?", (rule_id,))
    return _row(rows[0]) if rows else None

async def get_metric_stats(db: aiosqlite.Connection, name: str, minutes: int = 60) -> dict:
    """Aggregated stats for a metric over a time window."""
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

