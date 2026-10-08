"""Free, versioned manual edits. Generated claims are never re-certified by editing."""
import copy
import json
from .db import db, dumps, now
from . import content_quality

FIELDS = {"title": 300, "body": 30000, "cover_text": 300, "hook": 2000, "cta": 2000}


class EditError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def creation(c, ident, project):
    row = c.execute(
        "SELECT o.*,s.platform FROM creation_outputs o JOIN source_contents s ON s.id=o.source_id "
        "WHERE o.id=? AND o.project_id=? AND o.deleted_at IS NULL", (ident, project),
    ).fetchone()
    if not row:
        raise EditError("稿件不存在", 404)
    return row


def revision(c, ident):
    return c.execute("SELECT COALESCE(MAX(revision),0) FROM creation_revisions WHERE creation_id=?", (ident,)).fetchone()[0]


def history(ident, project):
    with db() as c:
        row = creation(c, ident, project)
        rows = c.execute("SELECT revision,data,reason,created_at FROM creation_revisions WHERE creation_id=? ORDER BY revision DESC", (ident,)).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows] or [
            {"revision": 0, "data": json.loads(row["data"]), "reason": "初始稿", "created_at": row["created_at"]}]


def edited_data(original, changes, platform):
    if not isinstance(changes, dict) or not changes or set(changes) - (set(FIELDS) | {"tags", "comments"}):
        raise EditError("请提交标题、正文、话题或发布文案的修改")
    output = copy.deepcopy(original)
    for key, limit in FIELDS.items():
        if key in changes:
            value = changes[key]
            if not isinstance(value, str) or len(value) > limit or (key in ("title", "body") and not value.strip()):
                raise EditError(f"{key} 内容为空或超过 {limit} 字")
            if value.strip() != output.get(key, ""):
                output[key] = value.strip()
    if "tags" in changes:
        tags = changes["tags"]
        if not isinstance(tags, list) or len(tags) > 20 or any(not isinstance(t, str) or not t.strip() or len(t) > 60 for t in tags):
            raise EditError("话题最多 20 个，每个 1–60 字")
        output["tags"] = list(dict.fromkeys(t.strip().lstrip("#") for t in tags))
        if any(not t for t in output["tags"]):
            raise EditError("话题不能为空")
    if "comments" in changes:
        comments = changes["comments"]
        if not isinstance(comments, dict) or set(comments) != {"atmosphere", "knowledge", "pinned"}:
            raise EditError("评论格式不正确")
        if any(not isinstance(v, str) or len(v) > 4000 for v in comments.values()):
            raise EditError("每组评论最多 4000 字")
        if output.get("comment_layout"):
            layout = output["comment_layout"]
            for key in ("atmosphere", "knowledge"):
                layout[key] = [s.strip() for s in comments[key].splitlines() if s.strip()]
            layout.setdefault("pinned", {})["text"] = comments["pinned"].strip()
    if output == original:
        return original
    # Check only the current public copy. Old alternate titles and missing-material
    # notes remain available as context, but are not assertions about an edited draft.
    check = {**output, "titles": [], "missing": []}
    quality = content_quality.assess(check, [], platform)
    quality["issues"] = [s for s in quality["issues"] if s != "业务事实缺少可核对的文字依据，请补充产品或服务资料"]
    quality["status"] = "needs_input" if quality["issues"] else "review"
    quality["note"] = "已手动编辑；原始引用不代表修改后的事实已核验，请核对价格、卖点与购买方式。"
    output["quality"] = quality
    return output


def save(ident, project, expected, changes=None, restore=None):
    if type(expected) is not int or expected < 0:
        raise EditError("缺少有效版本号，请重新打开稿件")
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        row = creation(c, ident, project)
        current = revision(c, ident)
        if current != expected:
            raise EditError("稿件已在其他页面更新，你的修改仍保留在编辑框中。请复制备份后重新打开最新版本。", 409)
        if c.execute("SELECT 1 FROM creation_tracking WHERE creation_id=? AND status='published'", (ident,)).fetchone() or c.execute("SELECT 1 FROM creation_results WHERE creation_id=?", (ident,)).fetchone():
            raise EditError("已发布或已记录效果的稿件保留原文，请另行创作新稿。", 409)
        original = json.loads(row["data"])
        reason = "手动编辑"
        if restore is not None:
            if type(restore) is not int or restore < 0:
                raise EditError("版本号无效")
            saved = c.execute("SELECT data FROM creation_revisions WHERE creation_id=? AND revision=?", (ident, restore)).fetchone()
            if not saved:
                raise EditError("历史版本不存在", 404)
            output = json.loads(saved["data"])
            reason = f"恢复版本 {restore}"
        else:
            output = edited_data(original, changes, row["platform"])
        if output == original:
            return {"data": original, "revision": current}
        c.execute("INSERT OR IGNORE INTO creation_revisions VALUES (?,?,?,?,?)", (ident, 0, row["data"], "初始稿", row["created_at"]))
        timestamp = now()
        c.execute("INSERT INTO creation_revisions VALUES (?,?,?,?,?)", (ident, current + 1, dumps(output), reason, timestamp))
        c.execute("UPDATE creation_outputs SET data=? WHERE id=?", (dumps(output), ident))
        return {"data": output, "revision": current + 1}
