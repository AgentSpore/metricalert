# MetricAlert

> Lightweight metric alerting for small SaaS teams. Push any number, define thresholds, get alerted when something breaks — no Datadog complexity, no enterprise pricing.

## Problem

Small SaaS teams need to know when revenue drops, error rates spike, or signups fall — but Datadog starts at $15/host/month and takes weeks to configure. Most founders end up checking dashboards manually or missing incidents entirely until a customer complains.

## Market

- **TAM**: $19.6B — Monitoring, observability, and alerting software (2025)
- **SAM**: ~$1.4B — Lightweight monitoring tools for small/mid SaaS (500K+ self-serve SaaS teams)
- **CAGR**: 14.8% through 2030 (cloud-native adoption, microservices proliferation)
- **Trend**: 71% of small SaaS teams say existing monitoring tools are "too complex for our stage" (Indie Hackers Survey, 2025)

## Competitors

| Tool | Strength | Weakness |
|------|----------|----------|
| Datadog | Full observability suite | Expensive, complex, enterprise-focused |
| PagerDuty | Incident management | $21+/user/mo, overkill for small teams |
| Grafana | Open source, powerful | Self-host complexity, steep learning curve |
| Better Uptime | Simple uptime monitoring | URL-only, no custom metrics |
| Cronitor | Cron + heartbeat monitoring | Not for custom business metrics |

## Differentiation

- **Push any number** — not just infrastructure metrics; push MRR, signups, conversion rate, anything
- **Zero-config** — define a rule in one API call, start receiving alerts immediately
- **Webhook-native** — fire alerts to Slack, Discord, PagerDuty, or any HTTP endpoint

## Economics

- **Pricing**: Free (5 metrics, 10 rules), $19/mo (50 metrics), $59/mo (unlimited + team)
- **Target**: Solo founders, indie hackers, small SaaS teams (1-10 engineers)
- **MRR at scale**: 3,000 teams × $19 = **$57K MRR / $684K ARR**
- **CAC**: ~$25 (Hacker News, Indie Hackers, dev communities), LTV: $228 (12mo avg) → LTV/CAC = 9.1×

## Scoring

| Criterion | Score |
|-----------|-------|
| Pain severity | 4/5 |
| Market size | 4/5 |
| Technical barrier | 2/5 |
| Competitive gap | 3/5 |
| Monetisation clarity | 4/5 |
| **Total** | **3.4/5** |

## API Endpoints

```
POST /metrics                       — push a metric value (auto-checks alert rules)
GET  /metrics/{name}?minutes=60     — get recent data points for a metric
POST /rules                         — define an alert rule (metric, condition, threshold, webhook)
GET  /rules                         — list all alert rules
GET  /alerts?unresolved_only=true   — list fired alerts
POST /alerts/{id}/resolve           — mark alert as resolved
```

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
# Docs at http://localhost:8000/docs
```
