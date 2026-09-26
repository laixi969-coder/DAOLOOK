"""Purge task-only material after the configured lifetime; never delete saved assets."""

import datetime, json, threading
from .db import db, dumps, setting


def cleanup():
    cutoff = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(hours=setting("limits").get("temporary_ttl_hours", 24))
    ).isoformat()
    with db() as c:
        c.execute("DELETE FROM sessions WHERE expires < strftime('%s','now')")
        for row in c.execute(
            "SELECT id,payload FROM tasks WHERE updated_at<? AND state IN ('SUCCEEDED','PARTIAL','FAILED','CANCELLED')",
            (cutoff,),
        ).fetchall():
            payload = json.loads(row["payload"])
            if payload.get("temporary"):
                payload["temporary"] = ""
                payload["temporary_expired"] = True
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
