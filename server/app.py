import os, json, re, time, secrets, hashlib, hmac, csv, io, zipfile, html, urllib.parse
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from .db import db, init, uid, now, dumps, setting, ledger
from . import jobs, adapters, maintenance, covers, catalog
from .ranking import score

ROOT = Path(__file__).resolve().parent.parent
RATE = {}


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()
    )


def new_user(email, password=None, role="user", demo=False):
    ident = uid()
    project = uid()
    with db() as c:
        c.execute(
            "INSERT INTO users VALUES (?,?,?,?,?)",
            (ident, email, password_hash(password) if password else None, role, now()),
        )
        c.execute(
            "INSERT INTO credit_accounts VALUES (?,?,0)", (ident, 300 if demo else 100)
        )
        ledger(c, ident, None, "GRANT", 300 if demo else 100, "欢迎积分")
        c.execute(
            "INSERT INTO projects VALUES (?,?,?,?,?)",
            (project, ident, "我的灵感空间", "从好内容出发，找到自己的表达。", now()),
        )
        if demo:
            for i in range(6):
                sid = uid()
                p = "douyin" if i == 3 else "xhs"
                content = adapters.demo_content(i, p)
                analysis, _ = adapters.analyze(content, "")
                c.execute(
                    "INSERT INTO source_contents VALUES (?,?,?,?,?,?,?)",
                    (sid, project, p, "", dumps(content), 1 if i < 2 else 0, now()),
                )
                c.execute(
                    "INSERT INTO analysis_outputs VALUES (?,?,?,?,?,?)",
                    (uid(), sid, dumps(analysis), "demo-v1", None, now()),
                )
    return ident


class Error(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server_version = "DAOLOOK"

    def log_message(self, fmt, *args):
        pass

    def send(
        self,
        data,
        status=200,
        headers=None,
        content_type="application/json; charset=utf-8",
    ):
        body = (
            dumps(data).encode()
            if isinstance(data, (dict, list))
            else data
            if isinstance(data, bytes)
            else str(data).encode()
        )
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def session(self, user):
        token = secrets.token_urlsafe(32)
        with db() as c:
            c.execute(
                "INSERT INTO sessions VALUES (?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    user,
                    time.time() + 604800,
                ),
            )
        secure = "; Secure" if os.environ.get("DAOLOOK_SECURE_COOKIE") == "1" else ""
        return {
            "Set-Cookie": f"daolook_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=604800{secure}"
        }

    def user(self):
        cookies = SimpleCookie(self.headers.get("Cookie", ""))
        token = cookies.get("daolook_session")
        with db() as c:
            u = c.execute(
                "SELECT u.id,u.email,u.role FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires>?",
                (
                    hashlib.sha256(token.value.encode()).hexdigest() if token else "",
                    time.time(),
                ),
            ).fetchone()
        if not u:
            raise Error("请先登录", 401)
        return dict(u)

    def project(self, ident, user):
        with db() as c:
            p = c.execute(
                "SELECT * FROM projects WHERE id=? AND user_id=?", (ident, user["id"])
            ).fetchone()
        if not p:
            raise Error("项目不存在或无访问权限", 404)
        return dict(p)

    def do_GET(self):
        self.handle_request("GET")

    def do_POST(self):
        self.handle_request("POST")

    def do_PATCH(self):
        self.handle_request("PATCH")

    def do_DELETE(self):
        self.handle_request("DELETE")

    def handle_request(self, method):
        try:
            path = urllib.parse.urlparse(self.path).path
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            data = {}
            if method != "GET":
                origin = self.headers.get("Origin")
                if origin and urllib.parse.urlparse(origin).netloc != self.headers.get(
                    "Host"
                ):
                    raise Error("跨站请求已拒绝", 403)
                length = int(self.headers.get("Content-Length", 0))
                if length < 0:
                    raise Error("请求长度无效")
                if length > 3_000_000:
                    raise Error("文件过大，请控制在 2 MB 以内", 413)
                if length:
                    data = json.loads(self.rfile.read(length))
            if path.startswith("/api/"):
                return self.api(method, path, query, data)
            if method != "GET":
                raise Error("不支持的操作", 405)
            target = (
                (ROOT / "web" / path.lstrip("/")).resolve()
                if path != "/"
                else ROOT / "web/index.html"
            )
            if not target.is_relative_to(ROOT / "web") or not target.is_file():
                raise Error("页面不存在", 404)
            types = {
                ".html": "text/html; charset=utf-8",
                ".js": "application/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".svg": "image/svg+xml",
            }
            return self.send(
                target.read_bytes(),
                content_type=types.get(target.suffix, "application/octet-stream"),
                headers={
                    "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
                },
            )
        except Error as e:
            self.send({"error": e.message}, e.status)
        except (ValueError, KeyError, TypeError) as e:
            self.send({"error": str(e)}, 400)
        except Exception:
            import traceback

            traceback.print_exc()
            self.send({"error": "服务处理失败，请稍后重试"}, 500)

    def api(self, method, path, q, data):
        if path == "/api/health":
            return self.send({"ok": True, "name": "DAOLOOK", "version": "1.1"})
        if path == "/api/auth/demo" and method == "POST":
            if setting("mode") != "demo":
                raise Error("演示入口已关闭", 403)
            ident = new_user("demo-" + uid()[:12] + "@daolook.local", demo=True)
            return self.send({"ok": True}, headers=self.session(ident))
        if path in ("/api/auth/login", "/api/auth/register") and method == "POST":
            ip = self.client_address[0]
            RATE[ip] = [x for x in RATE.get(ip, []) if x > time.time() - 60]
            if len(RATE[ip]) >= 15:
                raise Error("请求过于频繁，请一分钟后重试", 429)
            RATE[ip].append(time.time())
            email = str(data.get("email", "")).strip().lower()
            password = str(data.get("password", ""))
            if (
                not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
                or len(password) < 8
            ):
                raise Error("请输入有效邮箱和至少 8 位密码")
            with db() as c:
                u = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            if path.endswith("register"):
                if u:
                    raise Error("该邮箱已注册，请直接登录")
                ident = new_user(email, password)
            else:
                if (
                    not u
                    or not u["password"]
                    or not hmac.compare_digest(
                        u["password"],
                        password_hash(password, u["password"].split(":")[0]),
                    )
                ):
                    raise Error("邮箱或密码不正确", 401)
                ident = u["id"]
            return self.send({"ok": True}, headers=self.session(ident))
        if path == "/api/auth/logout" and method == "POST":
            token = SimpleCookie(self.headers.get("Cookie", "")).get("daolook_session")
            if token:
                with db() as c:
                    c.execute(
                        "DELETE FROM sessions WHERE token=?",
                        (hashlib.sha256(token.value.encode()).hexdigest(),),
                    )
            return self.send(
                {"ok": True},
                headers={
                    "Set-Cookie": "daolook_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"
                },
            )
        if path == "/api/public":
            return self.send({"mode": setting("mode")})
        u = self.user()
        if path == "/api/bootstrap":
            with db() as c:
                projects = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM projects WHERE user_id=? ORDER BY created_at",
                        (u["id"],),
                    )
                ]
                credits = dict(
                    c.execute(
                        "SELECT * FROM credit_accounts WHERE user_id=?", (u["id"],)
                    ).fetchone()
                )
            return self.send(
                {
                    "user": u,
                    "projects": projects,
                    "credits": credits,
                    "mode": setting("mode"),
                    "rules": setting("rules"),
                }
            )
        if path.startswith("/api/admin"):
            return self.admin(method, path, data, u, q)
        if path == "/api/projects" and method == "POST":
            name = str(data.get("name", "")).strip()[:60]
            if not name:
                raise Error("请输入项目名称")
            ident = uid()
            with db() as c:
                c.execute(
                    "INSERT INTO projects VALUES (?,?,?,?,?)",
                    (
                        ident,
                        u["id"],
                        name,
                        str(data.get("description", ""))[:500],
                        now(),
                    ),
                )
            return self.send({"id": ident})
        if path == "/api/credits":
            with db() as c:
                rows = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM credit_ledger WHERE user_id=? ORDER BY created_at DESC LIMIT 200",
                        (u["id"],),
                    )
                ]
            return self.send(rows)
        if path == "/api/tasks/cancel" and method == "POST":
            jobs.cancel(data.get("id"), u["id"])
            return self.send({"ok": True})
        if path == "/api/tasks":
            with db() as c:
                rows = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM tasks WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
                        (u["id"],),
                    )
                ]
            return self.send(rows)
        project_id = data.get("project_id") or q.get("project_id", [""])[0]
        self.project(project_id, u)
        if path == "/api/workspace":
            with db() as c:
                sources = []
                for r in c.execute(
                    "SELECT * FROM source_contents WHERE project_id=? ORDER BY created_at DESC",
                    (project_id,),
                ):
                    s = dict(r)
                    s["data"] = json.loads(s["data"])
                    s["ranking"] = score(s["data"])
                    s["classification"] = catalog.classify(s["data"])
                    s["selection_reasons"] = catalog.evidence(s["data"], s["ranking"])
                    a = c.execute(
                        "SELECT data FROM analysis_outputs WHERE source_id=?",
                        (s["id"],),
                    ).fetchone()
                    s["analysis"] = json.loads(a[0]) if a else {}
                    sources.append(s)
                creations = []
                for r in c.execute(
                    "SELECT * FROM creation_outputs WHERE project_id=? AND deleted_at IS NULL ORDER BY created_at DESC",
                    (project_id,),
                ):
                    d = dict(r)
                    d["data"] = json.loads(d["data"])
                    creations.append(d)
                assets = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM assets WHERE project_id=? ORDER BY created_at DESC",
                        (project_id,),
                    )
                ]
                images = [
                    {**dict(r), "data": json.loads(r["data"])}
                    for r in c.execute(
                        "SELECT * FROM generated_images WHERE project_id=?",
                        (project_id,),
                    )
                ]
            return self.send(
                {
                    "sources": sources,
                    "creations": creations,
                    "assets": assets,
                    "images": images,
                }
            )
        if path == "/api/analyze" and method == "POST":
            entry = data.get("entry", "single")
            text = str(data.get("text", "")).strip()
            if entry not in ("single", "batch", "creator", "keyword") or not text:
                raise Error("请输入要拆解的内容")
            texts = (
                [x.strip() for x in text.splitlines() if x.strip()]
                if entry == "batch"
                else [text]
            )
            if len(texts) > setting("limits")["batch"]:
                raise Error("超出批量上限")
            ps = [
                adapters.platform(x)
                if entry != "keyword"
                else data.get("platform", "xhs")
                for x in texts
            ]
            if any(p not in ("xhs", "douyin") for p in ps):
                raise Error("不支持的平台")
            with db() as c:
                balance = c.execute(
                    "SELECT balance FROM credit_accounts WHERE user_id=?", (u["id"],)
                ).fetchone()[0]
            if balance < len(texts) * setting("rules")["analyze"]:
                raise Error("积分不足以执行此批任务")
            ids = jobs.submit_many(
                u["id"],
                project_id,
                "analyze",
                [
                    {"text": text, "entry": entry, "platform": p}
                    for text, p in zip(texts, ps)
                ],
            )
            return self.send({"task_ids": ids}, 202)
        if path == "/api/create" and method == "POST":
            with db() as c:
                source = c.execute(
                    "SELECT * FROM source_contents WHERE id=? AND project_id=?",
                    (data.get("source_id"), project_id),
                ).fetchone()
            if not source:
                raise Error("请先选择参考内容", 404)
            selected = data.get("assets", [])
            if not isinstance(selected, list) or any(
                not isinstance(x, str) for x in selected
            ):
                raise Error("资料选择格式不正确")
            with db() as c:
                available = {
                    r["id"]
                    for r in c.execute(
                        "SELECT id FROM assets WHERE project_id=?", (project_id,)
                    )
                }
            if any(x not in available for x in selected):
                raise Error("所选资料不存在或不属于当前项目")
            payload = {
                k: data.get(k, default)
                for k, default in [
                    ("source_id", ""),
                    ("assets", []),
                    ("requirements", ""),
                    ("temporary", ""),
                ]
            }
            return self.send(
                {"task_ids": [jobs.submit(u["id"], project_id, "create", payload)]}, 202
            )
        if (
            path in ("/api/cover", "/api/cover/plan", "/api/cover/preview")
            and method == "POST"
        ):
            with db() as c:
                output = c.execute(
                    "SELECT * FROM creation_outputs WHERE id=? AND project_id=? AND deleted_at IS NULL",
                    (data.get("creation_id"), project_id),
                ).fetchone()
            if not output:
                raise Error("稿件不存在", 404)
            output_data = json.loads(output["data"])
            if path == "/api/cover/plan":
                plan = covers.plan(output_data)
                with db() as c:
                    available = {
                        r["id"]
                        for r in c.execute(
                            "SELECT id FROM assets WHERE project_id=? AND kind='图片'",
                            (project_id,),
                        )
                    }
                plan["brief"]["asset_id"] = next(
                    (
                        i
                        for i in output_data.get("image_asset_ids", [])
                        if i in available
                    ),
                    "",
                )
                return self.send(plan)
            with db() as c:
                assets = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM assets WHERE project_id=?", (project_id,)
                    )
                ]
            brief = data.get("brief")
            if brief is None:
                if data.get("direction") not in covers.LEGACY:
                    raise Error("请选择封面方向")
                brief = {"style": covers.LEGACY[data["direction"]]}
            prepared = covers.prepare(output_data, brief, assets)
            preview = covers.render(prepared, final=path == "/api/cover")
            if path == "/api/cover/preview":
                return self.send(preview)
            return self.send(
                {
                    "task_ids": [
                        jobs.submit(
                            u["id"],
                            project_id,
                            "cover",
                            {
                                "creation_id": output["id"],
                                "source_id": output["source_id"],
                                "prepared": prepared,
                            },
                        )
                    ]
                },
                202,
            )
        if path == "/api/assets" and method == "POST":
            name = str(data.get("name", "")).strip()
            content = str(data.get("content", ""))
            if not name or not content:
                raise Error("请填写资料名称与内容")
            if data.get("kind") == "图片":
                covers.prepare(
                    {"title": "图片校验"},
                    {"asset_id": "upload"},
                    [
                        {
                            "id": "upload",
                            "kind": "图片",
                            "name": name,
                            "content": content,
                        }
                    ],
                )
            ident = uid()
            with db() as c:
                c.execute(
                    "INSERT INTO assets VALUES (?,?,?,?,?,?)",
                    (
                        ident,
                        project_id,
                        name[:120],
                        data.get("kind", "品牌资料"),
                        content,
                        now(),
                    ),
                )
            return self.send({"id": ident})
        match = re.fullmatch(r"/api/(sources|creations|assets)/([a-f0-9]+)", path)
        if match and method in ("PATCH", "DELETE"):
            kind, ident = match.groups()
            table = {
                "sources": "source_contents",
                "creations": "creation_outputs",
                "assets": "assets",
            }[kind]
            with db() as c:
                if not c.execute(
                    f"SELECT 1 FROM {table} WHERE id=? AND project_id=?",
                    (ident, project_id),
                ).fetchone():
                    raise Error("内容不存在", 404)
                if method == "DELETE":
                    if kind == "creations":
                        c.execute(
                            "UPDATE creation_outputs SET deleted_at=? WHERE id=?",
                            (now(), ident),
                        )
                    elif kind == "assets":
                        c.execute("DELETE FROM assets WHERE id=?", (ident,))
                    else:
                        c.execute(
                            "UPDATE source_contents SET saved=0 WHERE id=?", (ident,)
                        )
                elif kind == "assets":
                    if not data.get("name") or not data.get("content"):
                        raise Error("资料名称和内容不能为空")
                    if data.get("kind") == "图片":
                        covers.prepare(
                            {"title": "图片校验"},
                            {"asset_id": "upload"},
                            [
                                {
                                    "id": "upload",
                                    "kind": "图片",
                                    "name": data["name"],
                                    "content": data["content"],
                                }
                            ],
                        )
                    c.execute(
                        "UPDATE assets SET name=?,kind=?,content=? WHERE id=?",
                        (
                            data["name"],
                            data.get("kind", "品牌资料"),
                            data["content"],
                            ident,
                        ),
                    )
                else:
                    c.execute(
                        f"UPDATE {table} SET saved=? WHERE id=?",
                        (int(bool(data.get("saved"))), ident),
                    )
            return self.send({"ok": True})
        if path == "/api/export":
            return self.export(project_id, q.get("format", ["csv"])[0])
        raise Error("接口不存在", 404)

    def export(self, project, fmt):
        rows = [
            [
                "稿件ID",
                "平台",
                "参考链接",
                "标题",
                "标题候选",
                "封面文案",
                "正文/脚本",
                "标签",
                "前三秒钩子",
                "分镜",
                "拍摄清单",
                "配图建议",
                "素材缺口",
                "Skill版本",
                "创建时间",
            ]
        ]
        with db() as c:
            for r in c.execute(
                "SELECT o.*,s.platform,s.url FROM creation_outputs o JOIN source_contents s ON s.id=o.source_id WHERE o.project_id=? AND o.deleted_at IS NULL ORDER BY o.created_at",
                (project,),
            ):
                d = json.loads(r["data"])
                rows.append(
                    [
                        r["id"],
                        r["platform"],
                        r["url"],
                        d.get("title", ""),
                        " / ".join(d.get("titles", [])),
                        d.get("cover_text", ""),
                        d.get("body", ""),
                        " ".join(d.get("tags", [])),
                        d.get("hook", ""),
                        "\n".join(d.get("storyboard", [])),
                        "\n".join(d.get("shooting_list", [])),
                        "\n".join(d.get("image_suggestions", [])),
                        "\n".join(d.get("missing", [])),
                        r["skill_version"],
                        r["created_at"],
                    ]
                )
        if fmt == "xlsx":
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(
                    "[Content_Types].xml",
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
                )
                z.writestr(
                    "_rels/.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
                )
                z.writestr(
                    "xl/workbook.xml",
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="DAOLOOK" sheetId="1" r:id="rId1"/></sheets></workbook>',
                )
                z.writestr(
                    "xl/_rels/workbook.xml.rels",
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
                )
                sheet = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
                for n, row in enumerate(rows, 1):
                    sheet += (
                        f'<row r="{n}">'
                        + "".join(
                            '<c t="inlineStr"><is><t xml:space="preserve">'
                            + html.escape(
                                re.sub(
                                    r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(v or "")
                                )
                            )
                            + "</t></is></c>"
                            for v in row
                        )
                        + "</row>"
                    )
                z.writestr(
                    "xl/worksheets/sheet1.xml", sheet + "</sheetData></worksheet>"
                )
            return self.send(
                out.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": 'attachment; filename="DAOLOOK.xlsx"'},
            )
        out = io.StringIO()
        writer = csv.writer(out)
        for row in rows:
            writer.writerow(
                [
                    "'" + str(v)
                    if str(v).startswith(("=", "+", "-", "@", "\t", "\r"))
                    else v
                    for v in row
                ]
            )
        return self.send(
            ("\ufeff" + out.getvalue()).encode(),
            content_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="DAOLOOK.csv"'},
        )

    def admin(self, method, path, data, u, q):
        if u["role"] != "admin":
            raise Error("需要超级管理员权限", 403)
        if path == "/api/admin" and method == "GET":
            cfg = {
                k: setting(k)
                for k in ("mode", "rules", "limits", "provider", "tikhub", "ranking")
            }
            for k in ("provider", "tikhub"):
                cfg[k]["api_key"] = "••••••••" if cfg[k].get("api_key") else ""
            with db() as c:
                users = [
                    dict(r)
                    for r in c.execute(
                        "SELECT u.id,u.email,u.role,a.balance,a.frozen FROM users u JOIN credit_accounts a ON a.user_id=u.id"
                    )
                ]
                tasks = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM tasks ORDER BY created_at DESC LIMIT 100"
                    )
                ]
                skills = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM skill_versions ORDER BY name,version DESC"
                    )
                ]
                providers = [
                    {**dict(r), "api_key": "••••••••" if r["api_key"] else ""}
                    for r in c.execute("SELECT * FROM model_providers")
                ]
                routes = {
                    r["kind"]: json.loads(r["config"])
                    for r in c.execute("SELECT * FROM model_routes")
                }
            return self.send(
                {
                    "config": cfg,
                    "users": users,
                    "tasks": tasks,
                    "skills": skills,
                    "providers": providers,
                    "routes": routes,
                }
            )
        if path == "/api/admin/provider" and method == "POST":
            ident = data.get("id") or uid()
            if ident == "default" or not re.fullmatch("[a-zA-Z0-9_-]{1,80}", ident):
                raise Error("供应商 ID 无效")
            if not data.get("name") or not data.get("base_url", "").startswith(
                "https://"
            ):
                raise Error("请输入供应商名称与 HTTPS 地址")
            with db() as c:
                old = c.execute(
                    "SELECT api_key FROM model_providers WHERE id=?", (ident,)
                ).fetchone()
                key = (
                    old["api_key"]
                    if old and data.get("api_key") == "••••••••"
                    else data.get("api_key", "")
                )
                c.execute(
                    "INSERT OR REPLACE INTO model_providers VALUES (?,?,?,?,?)",
                    (
                        ident,
                        data["name"],
                        data["base_url"],
                        key,
                        int(bool(data.get("enabled", True))),
                    ),
                )
            return self.send({"id": ident})
        if path == "/api/admin/routes" and method == "POST":
            if set(data) != {"analyze", "create", "cover"}:
                raise Error("需要拆解、创作、封面三条路由")
            with db() as c:
                providers = {"default"} | {
                    r[0] for r in c.execute("SELECT id FROM model_providers")
                }
                for kind, route in data.items():
                    if not isinstance(route, dict) or set(route) != {
                        "primary",
                        "backup",
                    }:
                        raise Error("每条路由需要主模型和备用模型")
                    for target in route.values():
                        if (
                            not isinstance(target, dict)
                            or target.get("provider") not in providers
                            or not isinstance(target.get("model"), str)
                        ):
                            raise Error("路由供应商或模型无效")
                    c.execute(
                        "UPDATE model_routes SET config=? WHERE kind=?",
                        (dumps(route), kind),
                    )
            return self.send({"ok": True})
        if path == "/api/admin/ledger":
            with db() as c:
                rows = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM credit_ledger WHERE user_id=? ORDER BY created_at DESC LIMIT 200",
                        (q.get("user_id", [""])[0],),
                    )
                ]
            return self.send(rows)
        if path == "/api/admin/config" and method == "POST":
            changes = {}
            for key, value in data.items():
                if key not in (
                    "mode",
                    "rules",
                    "limits",
                    "provider",
                    "tikhub",
                    "ranking",
                ):
                    raise Error("不支持的配置项")
                if key == "mode" and value not in ("demo", "live"):
                    raise Error("模式无效")
                if key == "rules" and (
                    set(value) != {"analyze", "create", "cover"}
                    or any(
                        not isinstance(v, int) or v < 0 or v > 10000
                        for v in value.values()
                    )
                ):
                    raise Error("积分规则无效")
                if key == "limits" and (
                    not 1 <= value.get("batch", 0) <= 50
                    or not 1 <= value.get("timeout", 0) <= 180
                    or not 0 <= value.get("retries", 1) <= 2
                    or not 1 <= value.get("temporary_ttl_hours", 24) <= 168
                ):
                    raise Error("系统限制无效")
                if key == "ranking" and (
                    not isinstance(value, dict)
                    or any(
                        not isinstance(v, (int, float)) or not 0 <= v <= 1
                        for v in value.values()
                    )
                    or sum(value.values()) <= 0
                ):
                    raise Error("排序权重需在 0–1 之间且总和大于 0")
                if key in ("provider", "tikhub"):
                    if not value.get("base_url", "").startswith("https://"):
                        raise Error("服务地址必须使用 HTTPS")
                    if value.get("api_key") == "••••••••":
                        value["api_key"] = setting(key)["api_key"]
                if key == "tikhub":
                    if not isinstance(value.get("endpoints"), dict):
                        raise Error("数据源端点映射必须为 JSON 对象")
                    for endpoint in value["endpoints"].values():
                        if isinstance(endpoint, str):
                            continue
                        if (
                            not isinstance(endpoint, dict)
                            or not endpoint.get("path", "").startswith("/api/")
                            or endpoint.get("method", "GET") not in ("GET", "POST")
                            or not isinstance(endpoint.get("params", {}), dict)
                        ):
                            raise Error("端点需要有效的 path、method 与 params")
                changes[key] = value
            with db() as c:
                for key, value in changes.items():
                    c.execute(
                        "UPDATE settings SET value=? WHERE key=?", (dumps(value), key)
                    )
            return self.send({"ok": True})
        if path == "/api/admin/grant" and method == "POST":
            amount = int(data["amount"])
            if amount <= 0 or amount > 100000:
                raise Error("发放积分必须在 1–100000 之间")
            with db() as c:
                if not c.execute(
                    "UPDATE credit_accounts SET balance=balance+? WHERE user_id=?",
                    (amount, data["user_id"]),
                ).rowcount:
                    raise Error("用户不存在")
                ledger(c, data["user_id"], None, "GRANT", amount, "管理员发放")
            return self.send({"ok": True})
        if path == "/api/admin/test" and method == "POST":
            cfg = setting("provider")
            if data.get("provider_id"):
                with db() as c:
                    provider = c.execute(
                        "SELECT * FROM model_providers WHERE id=?",
                        (data["provider_id"],),
                    ).fetchone()
                if not provider:
                    raise Error("供应商不存在")
                cfg = dict(provider)
            result = adapters.request_json(
                cfg["base_url"].rstrip("/") + "/models", cfg["api_key"], timeout=20
            )
            return self.send(
                {
                    "ok": True,
                    "models": [v["id"] for v in result.get("data", []) if "id" in v],
                }
            )
        if path == "/api/admin/tikhub-test" and method == "POST":
            text = data.get("url", "")
            p = adapters.platform(text)
            adapters.TikHubAdapter().getContentDetail(text, p)
            return self.send({"ok": True})
        if path == "/api/admin/retry" and method == "POST":
            with db() as c:
                t = c.execute(
                    "SELECT * FROM tasks WHERE id=?", (data.get("id"),)
                ).fetchone()
            if not t or t["state"] != "FAILED":
                raise Error("只能重试失败任务")
            if json.loads(t["payload"]).get("temporary_expired"):
                raise Error("本次临时资料已到期清理，请用户补充资料后重新创作")
            return self.send(
                {
                    "task_ids": [
                        jobs.submit(
                            t["user_id"],
                            t["project_id"],
                            t["kind"],
                            json.loads(t["payload"]),
                        )
                    ]
                }
            )
        if path == "/api/admin/skills" and method == "POST":
            name = data.get("name")
            prompt = data.get("prompt", "").strip()
            if (
                name
                not in (
                    "xhs_analysis",
                    "douyin_analysis",
                    "xhs_creation",
                    "douyin_creation",
                )
                or not prompt
            ):
                raise Error("Skill 名称或内容无效")
            with db() as c:
                n = c.execute(
                    "SELECT COALESCE(MAX(version),0)+1 FROM skill_versions WHERE name=?",
                    (name,),
                ).fetchone()[0]
                c.execute(
                    "INSERT INTO skill_versions VALUES (?,?,?,?,?,?)",
                    (uid(), name, n, prompt, "Draft", now()),
                )
            return self.send({"ok": True})
        if path == "/api/admin/skills/state" and method == "POST":
            target = data.get("status")
            if target not in ("Test", "Published"):
                raise Error("状态无效")
            with db() as c:
                skill = c.execute(
                    "SELECT * FROM skill_versions WHERE id=?", (data["id"],)
                ).fetchone()
                if not skill:
                    raise Error("Skill 不存在")
                if target == "Published" and skill["status"] not in (
                    "Test",
                    "Archived",
                ):
                    raise Error("请先测试草稿")
            if target == "Test":
                content = (
                    adapters.demo_content()
                    if setting("mode") == "demo"
                    else {
                        "platform": skill["name"].split("_")[0],
                        "body": data.get(
                            "sample", "这是一份用于测试输出结构的内容样本。"
                        ),
                        "demo": False,
                    }
                )
                if skill["name"].endswith("analysis"):
                    adapters.analyze(content, skill["prompt"])
                else:
                    adapters.create(content, [], "验证结构", skill["prompt"], 1)
            with db() as c:
                if target == "Published":
                    c.execute(
                        "UPDATE skill_versions SET status='Archived' WHERE name=? AND status='Published'",
                        (skill["name"],),
                    )
                c.execute(
                    "UPDATE skill_versions SET status=? WHERE id=?",
                    (target, data["id"]),
                )
            return self.send({"ok": True})
        raise Error("管理接口不存在", 404)


def main():
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, value = line.split("=", 1)
                os.environ.setdefault(
                    key.strip(), value.strip().strip(chr(34)).strip(chr(39))
                )
    # DB path is imported before .env is parsed; apply the configured override here.
    from . import db as database

    database.DB_PATH = os.environ.get("DAOLOOK_DB", str(ROOT / "data/daolook.db"))
    init()
    email = os.environ.get("DAOLOOK_ADMIN_EMAIL")
    password = os.environ.get("DAOLOOK_ADMIN_PASSWORD")
    if email and password:
        if len(password) < 12:
            raise RuntimeError("管理员密码至少 12 位")
        with db() as c:
            existing = c.execute(
                "SELECT id FROM users WHERE email=?", (email.lower(),)
            ).fetchone()
        if not existing:
            new_user(email.lower(), password, "admin")
        else:
            with db() as c:
                c.execute(
                    "UPDATE users SET role='admin',password=? WHERE id=?",
                    (password_hash(password), existing["id"]),
                )
    jobs.start()
    maintenance.start()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"DAOLOOK ready: http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
