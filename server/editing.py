"""Free, versioned manual edits. Generated claims are never re-certified by editing."""
import copy
import json
from .db import db, dumps, now
from . import content_quality, draft_sources, resource_limits, questions

FIELDS = {"title": 300, "body": 30000, "cover_text": 300, "hook": 2000, "cta": 2000}
REWRITE_LISTS = {"titles": (20, 300), "storyboard": (60, 2000), "shooting_list": (60, 2000),
                 "image_suggestions": (60, 2000)}


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


def confirm_ready(ident, project, expected, expected_sources=None):
    """Confirm the version the editor read. Keep the first confirmation for batch timing."""
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        row = creation(c, ident, project)
        if type(expected) is not int or expected != revision(c, ident):
            raise EditError("稿件版本已变化，请打开最新稿核对", 409)
        digest = draft_sources.signature(c, ident, project, row["task_id"])
        current = c.execute("SELECT revision,confirmed_at,source_digest FROM creation_readiness WHERE creation_id=?", (ident,)).fetchone()
        same_revision = current and current["revision"] == expected
        if expected_sources is not None and expected_sources != digest:
            raise EditError("所选事实资料已变化，请刷新并核对当前资料后再确认", 409)
        if same_revision and current["source_digest"] == digest:
            return {"revision": expected, "confirmed_at": current["confirmed_at"]}
        if expected_sources is None and (row["task_id"] or same_revision):
            raise EditError("所选事实资料需重新核对，请刷新后确认", 409)
        if not same_revision and c.execute("SELECT 1 FROM creation_tracking WHERE creation_id=? AND status='published'", (ident,)).fetchone():
            raise EditError("稿件已经发布，无法补记发布前核对时间", 409)
        stamp = now()
        c.execute("INSERT INTO creation_readiness(creation_id,revision,first_confirmed_at,confirmed_at,source_digest) "
                  "VALUES (?,?,?,?,?) ON CONFLICT(creation_id) DO UPDATE SET revision=excluded.revision,"
                  "confirmed_at=excluded.confirmed_at,source_digest=excluded.source_digest", (ident, expected, stamp, stamp, digest))
        owner = c.execute("SELECT user_id FROM projects WHERE id=?", (project,)).fetchone()[0]
        resource_limits.check_storage(c, owner)
        return {"revision": expected, "confirmed_at": stamp}


def history(ident, project):
    with db() as c:
        row = creation(c, ident, project)
        rows = c.execute("SELECT revision,data,reason,created_at FROM creation_revisions WHERE creation_id=? ORDER BY revision DESC", (ident,)).fetchall()
        return [{**dict(r), "data": json.loads(r["data"])} for r in rows] or [
            {"revision": 0, "data": json.loads(row["data"]), "reason": "初始稿", "created_at": row["created_at"]}]


def edited_data(original, changes, platform, assets=None, *, rewrite=False):
    allowed = set(FIELDS) | {"tags", "comments"}
    if rewrite:
        allowed.update(REWRITE_LISTS)
        if "script" in original:
            allowed.add("script")
    if not isinstance(changes, dict) or not changes or set(changes) - allowed:
        raise EditError("请提交标题、正文、话题或发布文案的修改")
    output = copy.deepcopy(original)
    for key, limit in FIELDS.items():
        if key in changes:
            value = changes[key]
            required = key in ("title", "body") or (rewrite and (key == "cover_text" or (key == "hook" and platform == "douyin")))
            if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
                raise EditError(f"{key} 内容为空或超过 {limit} 字")
            if value.strip() != output.get(key, ""):
                output[key] = value.strip()
    if "script" in changes:
        script = changes["script"]
        if not isinstance(script, str) or not script.strip() or len(script) > 30000:
            raise EditError("请提供不超过 30000 字的口播脚本")
        output["script"] = script.strip()
    for key, (max_items, max_chars) in REWRITE_LISTS.items():
        if key not in changes:
            continue
        items = changes[key]
        if (not isinstance(items, list) or len(items) > max_items
                or any(not isinstance(v, str) or not v.strip() or len(v) > max_chars for v in items)
                or sum(map(len, items)) > 30000):
            raise EditError(f"{key} 需要使用长度有效的文字列表")
        if key == "titles" and platform == "xhs" and len(items) != 3:
            raise EditError("小红书稿件需要三个标题候选")
        if platform == "douyin" and key in ("storyboard", "shooting_list") and not items:
            raise EditError("抖音脚本需要保留分镜和拍摄清单")
        output[key] = [v.strip() for v in items]
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
            if rewrite and platform == "xhs":
                previous = {**layout, "pinned": (layout.get("pinned") or {}).get("text")}
                if any(previous.get(k) and not v.strip() for k,v in comments.items()):
                    raise EditError("小红书改稿需保留气氛、知识和置顶评论")
            for key in ("atmosphere", "knowledge"):
                layout[key] = [s.strip() for s in comments[key].splitlines() if s.strip()]
            layout.setdefault("pinned", {})["text"] = comments["pinned"].strip()
    if output == original:
        return original
    if isinstance(output.get("redteam_review"), dict):
        output["redteam_review"] = {**output["redteam_review"], "edited_after": True}
    return questions.mark_edited(recheck(output, platform, assets), original)


def recheck(output, platform, assets):
    # Check only the current public copy. Old alternate titles and missing-material
    # notes remain available as context, but are not assertions about an edited draft.
    check = {**output, "titles": [], "missing": []}
    quality = content_quality.assess(check, assets or [], platform, additional_claim_text=output.get("titles", []))
    if not output.get("evidence"):
        # Handwritten copy may have no original citation. Specific unsupported
        # claims still appear, and an edited version always needs human review.
        quality["issues"] = [s for s in quality["issues"] if s != "业务事实缺少可核对的文字依据，请补充产品或服务资料"]
    quality["status"] = "needs_input" if quality["issues"] else "review"
    quality["note"] = "稿件已修改，原始引用不代表新表述已核验。请核对标出的业务事实。"
    return {**output, "quality": quality}


def with_current_facts(c, ident, project, output, platform, revision_number):
    if platform not in ("xhs", "douyin"):
        return output
    assets = draft_sources.for_creation(c, ident, project)
    if revision_number:
        return recheck(output, platform, assets)
    return {**output, "quality": content_quality.assess(output, assets, platform)}


def save(ident, project, expected, changes=None, restore=None, edit_minutes=None):
    if edit_minutes is not None and (type(edit_minutes) not in (float, int) or not 0 <= edit_minutes <= 1440 or restore is not None):
        raise EditError("本次手动编辑用时须为 0 至 1440 分钟")
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
            output = with_current_facts(c, ident, project, json.loads(saved["data"]), row["platform"], restore)
            reason = f"恢复版本 {restore}"
        else:
            output = edited_data(original, changes, row["platform"], draft_sources.for_creation(c, ident, project))
        if output == original:
            return {"data": original, "revision": current}
        user=c.execute("SELECT user_id FROM projects WHERE id=?",(project,)).fetchone()[0]
        c.execute("INSERT OR IGNORE INTO creation_revisions VALUES (?,?,?,?,?)", (ident, 0, row["data"], "初始稿", row["created_at"]))
        timestamp = now()
        c.execute("INSERT INTO creation_revisions VALUES (?,?,?,?,?)", (ident, current + 1, dumps(output), reason, timestamp))
        if edit_minutes is not None:
            c.execute("INSERT INTO revision_effort VALUES (?,?,?)", (ident, current + 1, edit_minutes))
        c.execute("UPDATE creation_outputs SET data=? WHERE id=?", (dumps(output), ident))
        resource_limits.check_storage(c,user)
        return {"data": output, "revision": current + 1}
