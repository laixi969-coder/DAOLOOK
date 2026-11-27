"""Submission cohorts and measured model usage for the project delivery board."""
import datetime
import json
import statistics

from . import production


def record_task(c, ident, kind, execution_mode):
    if kind in ("create", "original", "rewrite"):
        c.execute("INSERT INTO task_model_metrics(task_id,mode,metered) VALUES (?,?,1)", (ident, execution_mode))


def initialize(c):
    c.executescript("""
        CREATE INDEX IF NOT EXISTS idx_creation_task ON creation_outputs(task_id);
        CREATE TABLE IF NOT EXISTS task_model_metrics(
            task_id TEXT PRIMARY KEY REFERENCES tasks(id) ON DELETE CASCADE,
            mode TEXT NOT NULL, metered INTEGER NOT NULL,
            calls INTEGER NOT NULL DEFAULT 0, retries INTEGER NOT NULL DEFAULT 0,
            usage_calls INTEGER NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0, estimated INTEGER NOT NULL DEFAULT 0,
            reserved INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS model_call_rates(
            call_id TEXT PRIMARY KEY REFERENCES external_calls(id) ON DELETE CASCADE,
            input_rate INTEGER NOT NULL, output_rate INTEGER NOT NULL, fixed_fee INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS revision_effort(
            creation_id TEXT NOT NULL, revision INTEGER NOT NULL, minutes REAL NOT NULL,
            PRIMARY KEY(creation_id, revision),
            FOREIGN KEY(creation_id,revision) REFERENCES creation_revisions(creation_id,revision) ON DELETE CASCADE);
    """)
    # Old failures without a recorded execution mode cannot be assigned to either cohort.
    c.execute("""
        INSERT INTO task_model_metrics(task_id,mode,metered)
        SELECT t.id,CASE
          WHEN json_extract(t.payload,'$.execution_mode') IN ('live','demo') THEN json_extract(t.payload,'$.execution_mode')
          WHEN t.model LIKE 'demo%' THEN 'demo'
          WHEN t.model IS NOT NULL AND t.model != '' THEN 'live'
          WHEN EXISTS(SELECT 1 FROM creation_outputs o WHERE o.task_id=t.id AND COALESCE(json_extract(o.data,'$.demo'),0)=0) THEN 'live'
          WHEN EXISTS(SELECT 1 FROM creation_outputs o WHERE o.task_id=t.id) THEN 'demo'
          ELSE 'unknown' END,0
        FROM tasks t WHERE t.kind IN ('create','original','rewrite')
        AND NOT EXISTS(SELECT 1 FROM task_model_metrics m WHERE m.task_id=t.id)
    """)


def project_report(c, project, as_of=None):
    as_of = as_of or datetime.datetime.now(datetime.timezone.utc)
    cutoff = (as_of - datetime.timedelta(days=7)).isoformat()
    # An unsuccessful or deleted batch remains in the submission denominator.
    rows = c.execute("""
        SELECT t.id,m.mode,t.created_at FROM tasks t JOIN task_model_metrics m ON m.task_id=t.id
        WHERE t.project_id=? AND t.kind IN ('original','create') AND julianday(t.created_at)<=julianday(?)
    """, (project, cutoff))
    batches = {}
    unknown_batches = 0
    for row in rows:
        if row["mode"] == "live":
            batches[row["id"]] = {"ready": False, "published": False, "submitted_at": production.moment(row["created_at"])}
        elif row["mode"] == "unknown":
            unknown_batches += 1
    seven_day_posts = seven_day_filled = confirmed_drafts = 0
    submitted = c.execute("""
        SELECT o.task_id,json_extract(o.data,'$.goal') AS goal,k.status,k.published_at,
               json_extract(r.data,'$.windows."7d"') AS week,v.first_confirmed_at
        FROM creation_outputs o JOIN task_model_metrics m ON m.task_id=o.task_id
        LEFT JOIN creation_tracking k ON k.creation_id=o.id
        LEFT JOIN creation_results r ON r.creation_id=o.id
        LEFT JOIN creation_readiness v ON v.creation_id=o.id
        WHERE o.project_id=? AND m.mode='live' AND COALESCE(json_extract(o.data,'$.demo'),0)=0
    """, (project,))
    for row in submitted:
        published = row["status"] == "published"
        if row["task_id"] in batches:
            batch = batches[row["task_id"]]
            if published:
                batch["published"] = True
            if row["first_confirmed_at"]:
                batch["ready"] = True
                confirmed_drafts += 1
                first = production.moment(row["first_confirmed_at"])
                if first and batch["submitted_at"] and first >= batch["submitted_at"]:
                    elapsed = (first - batch["submitted_at"]).total_seconds()
                    batch["first_seconds"] = min(elapsed, batch.get("first_seconds", elapsed))
        when = production.moment(row["published_at"])
        if published and when and as_of - when >= datetime.timedelta(days=7):
            seven_day_posts += 1
            snapshot = json.loads(row["week"] or "{}")
            metric = {"reach": "views", "leads": "leads", "sales": "orders"}.get(row["goal"])
            if snapshot.get("published_at") == row["published_at"] and type(snapshot.get(metric)) is int:
                seven_day_filled += 1

    costs = dict.fromkeys(("tasks", "metered_tasks", "calls", "retries", "usage_calls", "input_tokens",
                           "output_tokens", "estimated", "reserved"), 0)
    for row in c.execute("""
        SELECT m.*,CASE WHEN t.kind='rewrite' THEN target.task_id ELSE t.id END AS generation_id
        FROM tasks t JOIN task_model_metrics m ON m.task_id=t.id
        LEFT JOIN creation_outputs target ON t.kind='rewrite' AND target.project_id=t.project_id
            AND target.id=json_extract(t.payload,'$.creation_id')
        WHERE t.project_id=? AND m.mode='live'
    """, (project,)):
        if row["generation_id"] not in batches:
            continue
        costs["tasks"] += 1
        costs["metered_tasks"] += row["metered"]
        for field in ("calls", "retries", "usage_calls", "input_tokens", "output_tokens", "estimated", "reserved"):
            costs[field] += row[field]
    complete_cost = costs["tasks"] == costs["metered_tasks"] and costs["calls"] == costs["usage_calls"]
    costs["per_confirmed_microusd"] = round(costs["estimated"] / confirmed_drafts) if confirmed_drafts and complete_cost else None
    edits = c.execute("""
        SELECT o.task_id,e.minutes FROM creation_revisions v
        JOIN creation_outputs o ON v.creation_id=o.id
        LEFT JOIN revision_effort e ON e.creation_id=v.creation_id AND e.revision=v.revision
        WHERE o.project_id=? AND v.reason='手动编辑' AND COALESCE(json_extract(o.data,'$.demo'),0)=0
    """, (project,))
    minutes = []
    manual_revisions = 0
    for row in edits:
        if row["task_id"] in batches:
            manual_revisions += 1
            if row["minutes"] is not None:
                minutes.append(row["minutes"])
    latencies = [b["first_seconds"] for b in batches.values() if "first_seconds" in b]
    return {
        "batches": len(batches), "unknown_batches": unknown_batches,
        "confirmed_batches": sum(b["ready"] for b in batches.values()),
        "first_confirm_minutes": statistics.median(latencies) / 60 if latencies else None,
        "published_batches": sum(b["published"] for b in batches.values()),
        "confirmed_drafts": confirmed_drafts, "seven_day_posts": seven_day_posts, "seven_day_filled": seven_day_filled,
        "manual_revisions": manual_revisions, "timed_revisions": len(minutes),
        "median_edit_minutes": statistics.median(minutes) if minutes else None, "model": costs,
    }
