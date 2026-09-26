import json, queue, threading, traceback
from .db import db, uid, now, dumps, setting, ledger
from . import adapters, covers, discovery

Q = queue.Queue()
TERMINAL = ("SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED")
DISCOVERY = ("creator", "keyword")


def discover_pick():
    value = setting("limits").get("discover_pick", 3)
    return value if type(value) is int and 1 <= value <= 10 else 3


def task_cost(kind, payload, rules=None):
    """博主/关键词入口按精选条数逐条计费：先冻结上限，成功几条结算几条，其余退回。"""
    unit = (rules or setting("rules")).get(kind)
    if type(unit) is not int or unit < 0:
        raise ValueError("任务计费配置无效")
    if kind == "analyze" and payload.get("entry") in DISCOVERY:
        return unit, unit * discover_pick()
    return unit, unit


def submit(user, project, kind, payload):
    return submit_many(user, project, kind, [payload])[0]


def submit_many(user, project, kind, payloads):
    rules = setting("rules")
    costs = [task_cost(kind, payload, rules) for payload in payloads]
    ids = [uid() for _ in payloads]
    total = sum(c for _, c in costs)
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
        for ident, payload, (unit, cost) in zip(ids, payloads, costs):
            payload = dict(payload)
            payload["execution_mode"] = setting("mode")
            payload["unit_cost"] = unit
            if kind == "analyze" and payload.get("entry") in DISCOVERY:
                payload["pick"] = cost // unit if unit else discover_pick()
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
        if not task or task["state"] in TERMINAL:
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
            "UPDATE tasks SET state=?,updated_at=? WHERE id=? AND state NOT IN ('SUCCEEDED','PARTIAL','FAILED','CANCELLED')",
            (s, now(), ident),
        )


def fail(ident, error):
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        task = c.execute("SELECT * FROM tasks WHERE id=?", (ident,)).fetchone()
        if not task or task["state"] in TERMINAL:
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
    failures = []
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
        entry = payload.get("entry", "single")
        if demo:
            indexes = (
                range(payload.get("pick") or discover_pick())
                if entry in DISCOVERY
                else [sum(map(ord, payload["text"])) % 6]
            )
            contents = [
                adapters.demo_content(
                    i, p, payload["text"] if entry != "keyword" else ""
                )
                for i in indexes
            ]
        else:
            adapter = adapters.TikHubAdapter()
            if entry in ("single", "batch"):
                contents = [adapter.getContentDetail(payload["text"], p)]
            else:
                raw = (
                    adapter.listCreatorContents(payload["text"], p)
                    if entry == "creator"
                    else adapter.searchContents(payload["text"], p)
                )
                items = discovery.list_items(raw, p)
                if not items:
                    raise ValueError("数据源未返回可识别的内容 ID，请检查接口返回结构")
                field = "account_median" if entry == "creator" else "category_median"
                base = discovery.baseline(items)
                contents = []
                for item in discovery.pick(
                    items, payload.get("pick") or discover_pick(), field, base
                ):
                    try:
                        content = adapter.getContentDetail(item["url"], p)
                    except Exception as e:
                        failures.append({"url": item["url"], "error": reason(e)})
                        continue
                    if base:
                        content[field] = base
                    for key in ("age_days", "followers"):
                        if content.get(key) is None and item.get(key) is not None:
                            content[key] = item[key]
                    content["selection"] = item["selection"]
                    contents.append(content)
        state(ident, "ANALYZING")
        for content in contents:
            provided = payload.get("transcript", "") if entry == "single" else ""
            if not content.get("demo") and (
                provided or content.get("media_url") or content["platform"] == "douyin"
            ):
                adapters.attach_transcript(content, provided)
            try:
                analysis, model = adapters.analyze(content, version["prompt"])
            except Exception as e:
                if entry not in DISCOVERY:
                    raise
                failures.append({"url": content.get("url", ""), "error": reason(e)})
                continue
            # Model prose must never overwrite platform metrics, identity or demo provenance.
            analysis.pop("source", None)
            content["origin"] = {
                "entry": entry,
                "query": payload["text"] if entry == "keyword" else "",
                "provider": "demo" if demo else "TikHub",
                "fetched_at": now(),
            }
            new_sources.append((uid(), content, analysis))
        if not new_sources:
            raise ValueError(
                "精选内容均未能完成拆解："
                + (failures[0]["error"] if failures else "没有可用内容")
            )
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
            prior = sum(
                1
                for row in c.execute(
                    "SELECT payload FROM tasks WHERE project_id=? AND kind='create' AND state='SUCCEEDED'",
                    (t["project_id"],),
                )
                if json.loads(row["payload"]).get("source_id") == payload["source_id"]
            )
            batch = prior + 1
            row = c.execute(
                "SELECT data FROM analysis_outputs WHERE source_id=? ORDER BY created_at DESC LIMIT 1",
                (payload["source_id"],),
            ).fetchone()
            analysis = json.loads(row["data"]).get("sections", []) if row else []
            # 同一参考再次生成时，把已有稿件的方向与切角告诉模型，避免换词重复。
            previous = [
                {
                    k: d.get(k, "")
                    for k in ("direction", "angle", "title")
                }
                for d in (
                    json.loads(r["data"])
                    for r in c.execute(
                        "SELECT data FROM creation_outputs WHERE source_id=? AND project_id=? AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 40",
                        (payload["source_id"], t["project_id"]),
                    )
                )
            ]
        assets = payload.get("asset_snapshot", assets)
        if payload.get("temporary"):
            assets.append({"name": "临时资料", "content": payload["temporary"]})
        selected_image_ids = [a["id"] for a in assets if a.get("kind") == "图片"]
        outputs, model = adapters.create(
            content,
            assets,
            payload.get("requirements", ""),
            version["prompt"],
            batch,
            analysis=analysis,
            previous=previous,
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
            TERMINAL
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
        charged = t["cost"]
        if kind == "analyze" and payload.get("entry") in DISCOVERY:
            unit = payload.get("unit_cost", t["cost"])
            charged = min(t["cost"], unit * len(new_sources))
        refund = t["cost"] - charged
        c.execute(
            "UPDATE credit_accounts SET frozen=frozen-?,balance=balance+? WHERE user_id=?",
            (t["cost"], refund, t["user_id"]),
        )
        if refund:
            ledger(
                c,
                t["user_id"],
                ident,
                "REFUND",
                refund,
                "逐条结算：未完成或未找到的条目退回",
            )
        ledger(c, t["user_id"], ident, "SETTLE", 0, "结算：" + kind)
        if failures:
            result["failures"] = failures
        result["charged"] = charged
        c.execute(
            "UPDATE tasks SET state=?,result=?,cost=?,model=?,skill_version=?,updated_at=?,error=? WHERE id=?",
            (
                "PARTIAL" if failures else "SUCCEEDED",
                dumps(result),
                charged,
                model,
                version_id,
                now(),
                f"{len(failures)} 条未完成，已退回对应积分" if failures else None,
                ident,
            ),
        )


def reason(e):
    return str(e)[:120] if isinstance(e, ValueError) else "外部服务或任务处理失败"


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
                "SELECT id FROM tasks WHERE state NOT IN ('SUCCEEDED','PARTIAL','FAILED','CANCELLED')"
            )
        ]
    for ident in stale:
        fail(ident, "服务重启，未完成任务已退回积分，可重新提交")
    for _ in range(2):
        threading.Thread(target=worker, daemon=True).start()
