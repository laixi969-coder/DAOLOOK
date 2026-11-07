"""Purge task-only material after the configured lifetime; never delete saved assets."""

import datetime, json, os, threading
from .db import db, dumps, setting


def cleanup():
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=setting("limits").get("temporary_ttl_hours", 24))
    ).isoformat()
    with db() as c:
        c.execute("DELETE FROM sessions WHERE expires < strftime('%s','now')")
        c.execute("DELETE FROM asset_trash WHERE rowid IN (SELECT rowid FROM asset_trash WHERE deleted_at<? LIMIT 500)", (cutoff,))
        # Never remove today's reservations: they enforce the spending ceiling.
        # Batch deletion avoids monopolizing SQLite's writer lock.
        for table, column, env in (
            ('audit_events', 'created_at', 'DAOLOOK_AUDIT_RETENTION_DAYS'),
            ('external_calls', 'created_at', 'DAOLOOK_EXTERNAL_RETENTION_DAYS'),
        ):
            try:
                days = int(os.environ.get(env, '365'))
                if not 2 <= days <= 36500:
                    raise ValueError()
            except ValueError as exc:
                raise ValueError(env + ' 必须是 2 至 36500 天的整数') from exc
            retention_cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)).isoformat()
            extra = " AND state!='started' AND day<?" if table == 'external_calls' else ''
            args = (retention_cutoff, datetime.datetime.now(datetime.timezone.utc).date().isoformat()) if extra else (retention_cutoff,)
            c.execute(f'DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {column}<?{extra} LIMIT 500)', args)
        for row in c.execute(
            "SELECT id,payload FROM tasks WHERE updated_at<? AND state IN ('SUCCEEDED','PARTIAL','FAILED','CANCELLED')",
            (cutoff,),
        ).fetchall():
            payload = json.loads(row["payload"])
            changed = False
            if payload.get("temporary"):
                payload["temporary"] = ""
                payload["temporary_expired"] = True
                changed = True
            # Snapshots are job inputs, not permanent copies of deleted assets.
            # Subsequent batches select the current saved assets by ID.
            if "asset_snapshot" in payload:
                del payload["asset_snapshot"]
                changed = True
            for field in ("question_context", "observation"):
                if field in payload:
                    del payload[field]
                    changed = True
            if changed:
                c.execute(
                    "UPDATE tasks SET payload=? WHERE id=?", (dumps(payload), row["id"])
                )


def start():
    def loop():
        event = threading.Event()
        while True:
            try:
                cleanup()
            except Exception:
                import traceback

                traceback.print_exc()
            event.wait(3600)

    threading.Thread(target=loop, daemon=True).start()
