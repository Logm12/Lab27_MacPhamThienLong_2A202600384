"""Analytics queries for SQLite audit trail data.

Abstracts all direct raw SQL interactions to prevent app.py tight coupling 
with the persistence layer. Ensures scalability and reusability.
"""

from __future__ import annotations

from typing import Any

from common.database import db_conn


async def get_recent_sessions() -> list[dict[str, Any]]:
    """Query and aggregate latest active thread history sessions."""
    query = """
        SELECT thread_id,
               pr_url,
               MIN(timestamp)        AS started,
               MAX(timestamp)        AS last_event,
               MAX(risk_level)       AS worst_risk,
               COUNT(*)              AS events
          FROM audit_events
         GROUP BY thread_id, pr_url
         ORDER BY MAX(timestamp) DESC
         LIMIT 25
    """
    async with db_conn() as conn:
        async with conn.execute(query) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_analytics_metrics() -> dict[str, float]:
    """Calculate holistic KPIs: Average Confidence and Approval Rates."""
    confidence_query = "SELECT AVG(confidence) FROM audit_events WHERE action='analyze'"
    decisions_query = """
        SELECT 
            COUNT(CASE WHEN decision IN ('approve', 'auto') THEN 1 END) as approved,
            COUNT(CASE WHEN decision = 'reject' THEN 1 END) as rejected
        FROM audit_events
        WHERE action = 'commit'
    """
    
    async with db_conn() as conn:
        # Fetch Average Confidence
        async with conn.execute(confidence_query) as cur:
            row = await cur.fetchone()
            avg_conf = float(row[0]) if row and row[0] is not None else 0.0
            
        # Fetch Finalized Decisions
        async with conn.execute(decisions_query) as cur:
            row = await cur.fetchone()
            if row:
                approved = int(row["approved"])
                rejected = int(row["rejected"])
            else:
                approved = rejected = 0

    total = approved + rejected
    approval_rate = (approved / total) if total > 0 else 0.0
    
    return {
        "avg_confidence": avg_conf,
        "total_sessions": float(total),
        "approval_rate": approval_rate,
    }


async def get_confidence_trend() -> list[dict[str, Any]]:
    """Retrieve incremental confidence scores ordered chronologically for visual plotting."""
    query = """
        SELECT timestamp, confidence, thread_id
        FROM audit_events
        WHERE action = 'analyze'
        ORDER BY timestamp ASC
    """
    async with db_conn() as conn:
        async with conn.execute(query) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_calibration_curve() -> list[dict[str, Any]]:
    """Correlate AI Confidence scores against absolute Human Decisions (approve/reject)."""
    query = """
        SELECT 
            a.confidence,
            c.decision
        FROM audit_events a
        JOIN audit_events c ON a.thread_id = c.thread_id
        WHERE a.action = 'analyze' 
          AND c.action = 'commit'
          AND c.decision IN ('approve', 'reject')
    """
    async with db_conn() as conn:
        async with conn.execute(query) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_top_risk_files() -> list[dict[str, Any]]:
    """Analyze Audit Trail to extract frequently flagged files in low-confidence runs (< 58%)."""
    import re
    from collections import Counter
    
    query = """
        SELECT reason
        FROM audit_events
        WHERE action = 'analyze' AND confidence < 0.58
    """
    async with db_conn() as conn:
        async with conn.execute(query) as cur:
            rows = await cur.fetchall()
            
    counter: Counter[str] = Counter()
    for row in rows:
        reason_txt = row[0] or ""
        # Extract list injected via [Files: a.py, b.py]
        match = re.search(r"\[Files:\s*(.*?)\]", reason_txt)
        if match:
            files = [f.strip() for f in match.group(1).split(",") if f.strip()]
            for f in files:
                counter[f] += 1
                
    return [{"file": k, "flags": v} for k, v in counter.most_common(10)]


async def get_performance_metrics() -> dict[str, float]:
    """Measure Average Latency (in seconds) calculated per logical platform Persona."""
    # Map logical personas back to specific engine actions
    persona_mapping = {
        "AI / System": ["analyze", "route", "fetch_pr", "auto_approve"],
        "QA Specialist": ["escalate", "synthesize"],
        "Lead Developer": ["human_review", "commit"],
    }
    
    query = """
        SELECT action, AVG(execution_time_ms) as avg_ms
        FROM audit_events
        GROUP BY action
    """
    
    async with db_conn() as conn:
        async with conn.execute(query) as cur:
            rows = await cur.fetchall()
            
    action_times = {row["action"]: float(row["avg_ms"]) for row in rows}
    
    persona_times = {}
    for persona, actions in persona_mapping.items():
        subset = [action_times[a] for a in actions if a in action_times]
        # Convert from milliseconds to seconds for dashboard readability
        persona_times[persona] = (sum(subset) / len(subset) / 1000.0) if subset else 0.0
        
    return persona_times

