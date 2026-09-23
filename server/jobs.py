import json, queue, threading, traceback
from .db import db, uid, now, dumps, setting, ledger
from . import adapters, covers

Q = queue.Queue()


def submit(user, project, kind, payload):
    return submit_many(user, project, kind, [payload])[0]


def submit_many(user, project, kind, payloads):
    cost = setting("rules").get(kind)
    if type(cost) is not int or cost < 0:
        raise ValueError("任务计费配置无效")
    ids = [uid() for _ in payloads]
    total = cost * len(payloads)
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        if not c.execute(
            "SELECT 1 FROM projects WHERE id=? AND user_id=?", (project, user)
        ).fetchone():
            raise ValueError("项目不存在或无访问权限")
        if not c.execute(
            "UPDATE credit_accounts SET balance=balance-?,frozen=frozen+? WHERE user_id=? AND balance>=?",
            (total, total, user, total),
        ).rowcount:
            raise ValueError("积分不足，请联系管理员补充积分")
        for ident, payload in zip(ids, payloads):
            payload = dict(payload)
            payload["execution_mode"] = setting("mode")
            if kind == "create":
                wanted = payload.get("assets", [])
                rows = [
                    dict(r)
                    for r in c.execute(
                        "SELECT id,name,kind,content FROM assets WHERE project_id=?",
                        (project,),
                    )
                    if r["id"] in wanted
                ]
                if set(wanted) != {r["id"] for r in rows}:
                    raise ValueError("所选资料已删除或不属于当前项目")
                payload["asset_snapshot"] = rows
            c.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ident,
                    user,
                    project,
                    kind,
                    "PENDING",
                    dumps(payload),
                    None,
                    None,
                    cost,
                    None,
                    None,
                    now(),
                    now(),
                ),
            )
            ledger(c, user, ident, "FREEZE", -cost, "冻结：" + kind)
    for ident in ids:
        Q.put(ident)
    return ids


def cancel(ident, user):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        task = c.execute(
            "SELECT * FROM tasks WHERE id=? AND user_id=?", (ident, user)
        ).fetchone()
        if not task or task["state"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            raise ValueError("任务已结束，无法取消")
        c.execute(
            "UPDATE credit_accounts SET balance=balance+?,frozen=frozen-? WHERE user_id=?",
            (task["cost"], task["cost"], user),
        )
        ledger(c, user, ident, "REFUND", task["cost"], "用户取消，释放冻结积分")
        c.execute(
            "UPDATE tasks SET state='CANCELLED',updated_at=? WHERE id=?", (now(), ident)
        )


def state(ident, s):
    with db() as c:
        c.execute(
            "UPDATE tasks SET state=?,updated_at=? WHERE id=? AND state NOT IN ('SUCCEEDED','FAILED','CANCELLED')",
            (s, now(), ident),
        )


def fail(ident, error):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        task = c.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone()
        if not task or task["state"] in ("SUCCEEDED", "FAILED", "CANCELLED"):
            return
        c.execute(
            "UPDATE credit_accounts SET balance=balance+?,frozen=frozen-? WHERE user_id=?",
            (task["cost"], task["cost"], task["user_id"]),
        )
        ledger(c, task["user_id"], ident, "REFUND", task["cost"], "任务失败，自动退还")
        c.execute(
            "UPDATE tasks SET state='FAILED',error=?,updated_at=? WHERE id=?",
            (error[:300], now(), ident),
        )


def run(ident):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        if not c.execute(
            "UPDATE tasks SET state='PROCESSING',updated_at=? WHERE id=? AND state='PENDING'",
            (now(), ident),
        ).rowcount:
            return
        t = dict(c.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone())
    payload = json.loads(t["payload"])
    kind = t["kind"]
    demo = payload.get("execution_mode", setting("mode")) == "demo"
    p = payload.get("platform", "xhs")
    version = None
    model = "demo"
    new_sources = []
    outputs = []
    image = None
    if kind in ("create", "cover"):
        with db() as c:
            source = c.execute(
                "SELECT * FROM source_contents WHERE id=? AND project_id=?",
                (payload["source_id"], t["project_id"]),
            ).fetchone()
            if not source:
                raise ValueError("参考内容不存在")
            content = json.loads(source["data"])
            p = source["platform"]
    if kind != "cover":
        name = p + "_" + ("analysis" if kind == "analyze" else "creation")
        with db() as c:
            version = c.execute(
                "SELECT * FROM skill_versions WHERE name=? AND status='Published' ORDER BY version DESC LIMIT 1",
                (name,),
            ).fetchone()
        if not version:
            raise ValueError("未找到已发布的拆解/创作 Skill")
    if kind == "analyze":
        state(ident, "FETCHING")
        if demo:
            indexes = (
                range(3)
                if payload.get("entry") in ("creator", "keyword")
                else [sum(map(ord, payload["text"])) % 6]
            )
            contents = [
                adapters.demo_content(
                    i, p, payload["text"] if payload.get("entry") != "keyword" else ""
                )
                for i in indexes
            ]
        else:
            adapter = adapters.TikHubAdapter()
            entry = payload.get("entry", "single")
            if entry in ("single", "batch"):
                contents = [adapter.getContentDetail(payload["text"], p)]
            else:
                raw = (
                    adapter.listCreatorContents(payload["text"], p)
                    if entry == "creator"
                    else adapter.searchContents(payload["text"], p)
                )
                urls = adapters.content_links(raw, p)
                contents = [
                    adapter.getContentDetail(u, adapters.platform(u)) for u in urls
                ]
        state(ident, "ANALYZING")
        for content in contents:
            analysis, model = adapters.analyze(content, version["prompt"])
            # Model prose must never overwrite platform metrics, identity or demo provenance.
            analysis.pop("source", None)
            content["origin"] = {
                "entry": payload.get("entry", "single"),
                "query": payload["text"] if payload.get("entry") == "keyword" else "",
                "provider": "demo" if demo else "TikHub",
                "fetched_at": now(),
            }
            new_sources.append((uid(), content, analysis))
    elif kind == "create":
        state(ident, "GENERATING")
        with db() as c:
            assets = [
                dict(r)
                for r in c.execute(
                    "SELECT id,name,kind,content FROM assets WHERE project_id=?",
                    (t["project_id"],),
                )
                if r["id"] in payload.get("assets", [])
            ]
            batch = (
                c.execute(
                    "SELECT count(*) FROM creation_outputs WHERE source_id=?",
                    (payload["source_id"],),
                ).fetchone()[0]
                // 3
                + 1
            )
        assets = payload.get("asset_snapshot", assets)
        if payload.get("temporary"):
            assets.append({"name": "临时资料", "content": payload["temporary"]})
        selected_image_ids = [a["id"] for a in assets if a.get("kind") == "图片"]
        outputs, model = adapters.create(
            content, assets, payload.get("requirements", ""), version["prompt"], batch
        )
        for output in outputs:
            output["image_asset_ids"] = selected_image_ids
    else:
        state(ident, "GENERATING")
        with db() as c:
            output = c.execute(
                "SELECT data FROM creation_outputs WHERE id=? AND project_id=? AND deleted_at IS NULL",
                (payload["creation_id"], t["project_id"]),
            ).fetchone()
        if not output:
            raise ValueError("稿件已删除或不存在")
        if payload.get("prepared"):
            image = covers.render(payload["prepared"], final=True)
        else:
            image = adapters.cover(json.loads(output["data"]), payload["direction"])
        model = "demo-svg" if image["demo"] else image.get("model", "image")
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute("SELECT state FROM tasks WHERE id=?", (ident,)).fetchone()[0] in (
            "CANCELLED",
            "FAILED",
            "SUCCEEDED",
        ):
            return
        if (
            image
            and not c.execute(
                "SELECT 1 FROM creation_outputs WHERE id=? AND project_id=? AND deleted_at IS NULL",
                (payload["creation_id"], t["project_id"]),
            ).fetchone()
        ):
            raise ValueError("稿件已删除，封面任务已终止")
        result = {}
        version_id = (
            version["id"] if version else (image.get("renderer") if image else None)
        )
        if new_sources:
            for sid, content, analysis in new_sources:
                c.execute(
                    "INSERT INTO source_contents VALUES (?,?,?,?,?,?,?)",
                    (
                        sid,
                        t["project_id"],
                        p,
                        content.get("url", ""),
                        dumps(content),
                        0,
                        now(),
                    ),
                )
                c.execute(
                    "INSERT INTO analysis_outputs VALUES (?,?,?,?,?,?)",
                    (uid(), sid, dumps(analysis), version_id, ident, now()),
                )
            result["source_ids"] = [s[0] for s in new_sources]
        if outputs:
            ids = []
            for output in outputs:
                oid = uid()
                ids.append(oid)
                c.execute(
                    "INSERT INTO creation_outputs VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        oid,
                        t["project_id"],
                        payload["source_id"],
                        ident,
                        dumps(output),
                        version_id,
                        0,
                        None,
                        now(),
                    ),
                )
            result["creation_ids"] = ids
        if image:
            iid = uid()
            c.execute(
                "INSERT INTO generated_images VALUES (?,?,?,?,?,?)",
                (
                    iid,
                    t["project_id"],
                    payload["creation_id"],
                    dumps(image),
                    ident,
                    now(),
                ),
            )
            result["image_id"] = iid
        c.execute(
            "UPDATE credit_accounts SET frozen=frozen-? WHERE user_id=?",
            (t["cost"], t["user_id"]),
        )
        ledger(c, t["user_id"], ident, "SETTLE", 0, "结算：" + kind)
        c.execute(
            "UPDATE tasks SET state='SUCCEEDED',result=?,model=?,skill_version=?,updated_at=? WHERE id=?",
            (dumps(result), model, version_id, now(), ident),
        )


def worker():
    while True:
        ident = Q.get()
        try:
            run(ident)
        except Exception as e:
            traceback.print_exc()
            fail(
                ident,
                str(e)
                if isinstance(e, ValueError)
                else "外部服务或任务处理失败，请重试",
            )
        finally:
            Q.task_done()


def start():
    with db() as c:
        stale = [
            r["id"]
            for r in c.execute(
                "SELECT id FROM tasks WHERE state NOT IN ('SUCCEEDED','FAILED','CANCELLED')"
            )
        ]
    for ident in stale:
        fail(ident, "服务重启，未完成任务已退回积分，可重新提交")
    for _ in range(2):
        threading.Thread(target=worker, daemon=True).start()
