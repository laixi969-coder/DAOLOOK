"""Resolve the selected text a domestic draft can still use when it is edited."""
import hashlib
import json
from .content_quality import reusable_temporary


def for_creation(c, creation_id, project_id):
    # The original creation task owns the selection, including on later revisions.
    # Read only the needed fields, since a job snapshot can contain full images.
    row = c.execute(
        "SELECT json_extract(t.payload, '$.assets') AS selected, "
        "json_extract(t.payload, '$.temporary') AS temporary, t.updated_at "
        "FROM creation_outputs o JOIN tasks t ON t.id=o.task_id AND t.project_id=o.project_id "
        "WHERE o.id=? AND o.project_id=? AND o.deleted_at IS NULL",
        (creation_id, project_id),
    ).fetchone()
    if not row:
        return []
    # Use the current version of each selected, still existing document.
    assets = [dict(asset) for asset in c.execute(
        "SELECT id,name,kind,content FROM assets WHERE project_id=? AND kind!='图片' "
        "AND id IN (SELECT value FROM json_each(?)) ORDER BY id",
        (project_id, row["selected"]),
    )]
    if row["temporary"]:
        limits = c.execute(
            "SELECT json_extract(value, '$.temporary_ttl_hours') FROM settings WHERE key='limits'"
        ).fetchone()
        ttl_hours = limits[0] if limits and limits[0] is not None else 24
        text = reusable_temporary({"temporary": row["temporary"]}, row["updated_at"], ttl_hours)
        if text:
            assets.append({"id": "temporary", "name": "临时资料", "kind": "文本", "content": text})
    return assets


def signature(c, creation_id, project_id, task_id, cache=None):
    # Include the identity and content of the available sources, including temporary text while valid.
    if cache is not None and task_id in cache:
        return cache[task_id]
    assets = for_creation(c, creation_id, project_id) if task_id else []
    value = hashlib.sha256(json.dumps(assets, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if cache is not None:
        cache[task_id] = value
    return value
