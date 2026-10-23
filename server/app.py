import base64
import os, json, re, time, secrets, hashlib, hmac, csv, io, zipfile, html, urllib.parse, socket, threading, http.client
from http.server import BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from .db import db, init, uid, now, dumps, setting, ledger
from . import jobs, adapters, maintenance, covers, catalog, mailer, documents, production, content_quality, editing, overseas, overseas_library, overseas_feed
from .ranking import score
from .skills import SKILL_NAMES
from . import audit, secret_store, spending, resource_limits, workspace, access
from .config import load_env, database_path
from .http_security import BoundedHTTPServer, RateLimiter, StaticCache, Rejected, client_ip, validate_request

ROOT = Path(__file__).resolve().parent.parent
RATE = RateLimiter()
STATIC_CACHE = StaticCache()


def comment_layout_text(layout):
    if not isinstance(layout, dict):
        return ""
    pinned = layout.get("pinned") if isinstance(layout.get("pinned"), dict) else {}
    lines = [f"【气氛】{x}" for x in layout.get("atmosphere") or []]
    lines += [f"【知识】{x}" for x in layout.get("knowledge") or []]
    if pinned.get("text"):
        lines.append(f"【置顶】{pinned['text']}")
    if pinned.get("goal"):
        lines.append(f"置顶目标：{pinned['goal']}")
    if pinned.get("keep_on_top"):
        lines.append(f"保持置顶：{pinned['keep_on_top']}")
    if layout.get("first_hour"):
        lines.append(f"发布后一小时：{layout['first_hour']}")
    return "\n".join(str(x) for x in lines)


def tracking_columns(r):
    return [
        "已发布" if r["track_status"] == "published" else "待发布",
        r["account_name"] or "",
        r["published_at"] or "",
    ]


def reject_nonfinite_json(value):
    raise ValueError("JSON 数字必须有限")


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return (
        salt
        + ":"
        + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()
    )


def signup_allowed(email):
    """白名单开启时，只有名单内邮箱和 .env 里的管理员邮箱可以注册。"""
    rule = setting("signup")
    admin = os.environ.get("DAOLOOK_ADMIN_EMAIL", "").strip().lower()
    return not rule.get("whitelist") or email in rule.get("emails", []) or email == admin


def new_user(email, password=None, role="user", demo=False, verified=False, bootstrap=False):
    ident = uid()
    project = uid()
    welcome = 300 if demo else setting("signup").get("welcome_credits", 100)
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute(
            "INSERT INTO users VALUES (?,?,?,?,?)",
            (ident, email, password_hash(password) if password else None, role, now()),
        )
        if welcome and not demo and role != 'admin' and setting('mode') == 'live':
            day=now()[:10]
            daily=c.execute('SELECT COALESCE(SUM(amount),0) FROM signup_grants WHERE created_at>=?',(day,)).fetchone()[0]
            lifetime=c.execute('SELECT COALESCE(SUM(amount),0) FROM signup_grants').fetchone()[0]
            if daily+welcome>int(os.environ.get('DAOLOOK_SIGNUP_DAILY_CREDITS','1000')) or lifetime+welcome>int(os.environ.get('DAOLOOK_SIGNUP_TOTAL_CREDITS','10000')):
                welcome=0
            else:
                c.execute('INSERT INTO signup_grants VALUES (?,?,?)',(ident,welcome,now()))
        c.execute("INSERT INTO credit_accounts VALUES (?,?,0)", (ident, welcome))
        access.create(c, ident, demo=demo, verified=verified and setting("mode")=="live", role=role)
        if welcome:
            ledger(c, ident, None, "GRANT", welcome, "欢迎积分")
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
        resource_limits.check_storage(c,ident)
        if bootstrap:audit.record(c,ident,'admin.bootstrap',ident)
    return ident


class Error(Exception):
    def __init__(self, message, status=400):
        self.message = message
        self.status = status


class Handler(BaseHTTPRequestHandler):
    server_version = "DAOLOOK"
    sys_version = ""
    request_read_timeout = 15

    def setup(self):
        self.request.settimeout(self.request_read_timeout)
        super().setup()
        # Absolute header/body deadline also stops clients that trickle bytes forever.
        self.read_deadline = threading.Timer(self.request_read_timeout, self.expire_read)
        self.read_deadline.daemon = True
        self.read_deadline.start()

    def expire_read(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def finish(self):
        self.read_deadline.cancel()
        super().finish()

    def parse_request(self):
        original = self.rfile
        class HeaderReader:
            def __init__(self):
                self.remaining = 32768
            def readline(self, limit=-1):
                line = original.readline(min(limit if limit >= 0 else 32769, self.remaining + 1))
                self.remaining -= len(line)
                if self.remaining < 0:
                    raise http.client.LineTooLong('request headers')
                return line
        self.rfile = HeaderReader()
        try:
            return super().parse_request()
        finally:
            self.rfile = original

    def send_error(self, code, message=None, explain=None):
        self.close_connection = True
        messages = {431: "请求头过大", 414: "请求地址过长", 501: "不支持的操作"}
        self.send({"error": messages.get(code, "请求格式不正确")}, code)

    def log_message(self, fmt, *args):
        # BaseHTTPRequestHandler passes raw paths; never log them or query/body data.
        return

    def audit(self, c, actor, action, target='', details=None):
        return audit.record(c, actor, action, target, details, getattr(self,'request_id',''))

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
        if status != 304:
            self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Cache-Control", (headers or {}).get("Cache-Control", "private, no-store"))
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Request-ID", getattr(self,"request_id",""))
        self.response_status = status
        for k, v in (headers or {}).items():
            if k.lower() != "cache-control":
                self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD" and status != 304:
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

    def do_HEAD(self):
        self.handle_request("HEAD")

    def do_POST(self):
        self.handle_request("POST")

    def do_PATCH(self):
        self.handle_request("PATCH")

    def do_DELETE(self):
        self.handle_request("DELETE")

    def handle_request(self, method):
        self.request_id=uid()
        self.response_status=500
        started=time.monotonic()
        try:
            if len(self.path) > 8192:
                raise Error("请求地址过长", 414)
            parsed = urllib.parse.urlsplit(self.path)
            if parsed.scheme or parsed.netloc:
                raise Error("请求地址无效")
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query, max_num_fields=100)
            length = validate_request(self.headers, method)
            self.remote_ip = client_ip(self.client_address[0], self.headers)
            RATE.check(("request", self.remote_ip), 1200)
            if path.startswith("/api/"):
                RATE.check(("api", self.remote_ip), 900)
            if path in ("/api/auth/login", "/api/auth/register", "/api/auth/code", "/api/auth/reset") and method == "POST":
                RATE.check(("auth", self.remote_ip), 15)
            if path == "/api/auth/demo" and method == "POST":
                RATE.check(("demo", self.remote_ip), 30)
            data = {}
            if length:
                body = self.rfile.read(length)
                if len(body) != length:
                    raise Error("请求未接收完整，请重试")
                data = json.loads(body, parse_constant=reject_nonfinite_json)
                if not isinstance(data, dict):
                    raise Error("请求内容必须是 JSON 对象")
            self.read_deadline.cancel()
            if path.startswith("/api/"):
                with spending.scope():
                    return self.api(method, path, query, data)
            if method not in ("GET", "HEAD"):
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
            body, etag = STATIC_CACHE.read(target)
            tags = [tag.strip().removeprefix("W/") for tag in self.headers.get("If-None-Match", "").split(",")]
            return self.send(
                b"" if etag in tags or "*" in tags else body,
                status=304 if etag in tags or "*" in tags else 200,
                content_type=types.get(target.suffix, "application/octet-stream"),
                headers={
                    "Cache-Control": "public, no-cache",
                    "ETag": etag,
                    "Content-Security-Policy": "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
                },
            )
        except (Error, Rejected) as e:
            self.send({"error": e.message}, e.status, headers=getattr(e, "headers", None))
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            self.close_connection = True
        except jobs.TaskAdmissionError as e:
            headers = {"Retry-After": str(e.retry_after)} if e.retry_after is not None else None
            self.send({"error": str(e)}, e.status, headers=headers)
        except editing.EditError as e:
            self.send({"error": str(e)}, e.status)
        except (ValueError, KeyError, TypeError, RecursionError) as e:
            self.send({"error": str(e)}, 400)
        except Exception:
            audit.event('request.error',request_id=self.request_id,error_type=__import__('sys').exc_info()[0].__name__)
            self.send({"error": "服务处理失败，请稍后重试，参考编号："+self.request_id}, 500)
        finally:
            audit.event('request.completed',request_id=self.request_id,method=method,status=self.response_status,
                        elapsed_ms=round((time.monotonic()-started)*1000),user_id=getattr(self,'actor_id',None))

    def api(self, method, path, q, data):
        if path == "/api/health":
            health=jobs.worker_health()
            healthy=not health['settlement_errors'] and health['alive']==health['workers']
            try:
                with db() as c:c.execute('SELECT 1 FROM settings LIMIT 1').fetchone()
            except Exception as exc:
                healthy=False
                audit.event("health.database_unavailable",error_type=type(exc).__name__)
            return self.send({"ok":healthy,"name":"DAOLOOK","version":"1.1"},200 if healthy else 503)
        if path == "/api/auth/demo" and method == "POST":
            if setting("mode") != "demo":
                raise Error("演示入口已关闭", 403)
            ident = new_user("demo-" + uid()[:12] + "@daolook.local", demo=True)
            return self.send({"ok": True}, headers=self.session(ident))
        if path in (
            "/api/auth/login",
            "/api/auth/register",
            "/api/auth/code",
            "/api/auth/reset",
        ) and method == "POST":
            email = str(data.get("email", "")).strip().lower()
            if len(email) > 254 or len(str(data.get("password", ""))) > 1024:
                raise Error("邮箱或密码过长")
            if email:
                RATE.check(("auth-account", hashlib.sha256(email.encode()).hexdigest()), 15)
            if path == "/api/auth/code":
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                    raise Error("请输入有效邮箱")
                purpose = data.get("purpose")
                if purpose == "verify":
                    account = self.user()
                    if account["email"] != email:
                        raise Error("只能验证当前账号的邮箱",403)
                    with db() as c:
                        if c.execute("SELECT 1 FROM demo_accounts WHERE user_id=?",(account["id"],)).fetchone():
                            raise Error("演示账号请注册正式邮箱",403)
                with db() as c:
                    exists = c.execute(
                        "SELECT 1 FROM users WHERE email=?", (email,)
                    ).fetchone()
                if purpose == "register" and exists:
                    raise Error("该邮箱已注册，请直接登录")
                if purpose == "register" and not signup_allowed(email):
                    raise Error("该邮箱不在注册白名单内，请联系管理员开通", 403)
                # 找回密码时不暴露邮箱是否注册：未注册也返回成功，但不发信。
                if purpose == "reset" and not exists:
                    if not mailer.enabled():
                        raise Error("管理员尚未配置邮件服务，请联系管理员重置密码")
                    return self.send({"ok": True})
                mailer.issue(email, purpose)
                return self.send({"ok": True})
            if path == "/api/auth/reset":
                password = str(data.get("password", ""))
                if len(password) < 8:
                    raise Error("新密码至少 8 位")
                mailer.verify(email, "reset", data.get("code"))
                with db() as c:
                    u = c.execute(
                        "SELECT id FROM users WHERE email=?", (email,)
                    ).fetchone()
                    if not u:
                        raise Error("验证码已过期，请重新获取")
                    c.execute(
                        "UPDATE users SET password=? WHERE id=?",
                        (password_hash(password), u["id"]),
                    )
                    c.execute("DELETE FROM sessions WHERE user_id=?", (u["id"],))
                return self.send({"ok": True}, headers=self.session(u["id"]))
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
                if not signup_allowed(email):
                    raise Error("该邮箱不在注册白名单内，请联系管理员开通", 403)
                if setting('mode') == 'live' and not mailer.enabled():
                    raise Error('真实服务注册需验证邮箱，请联系管理员配置邮件服务',403)
                verified=False
                if mailer.enabled():
                    mailer.verify(email, "register", data.get("code"))
                    verified=True
                ident = new_user(email, password, verified=verified)
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
            return self.send(
                {
                    "mode": setting("mode"),
                    "mail": mailer.enabled(),
                    "whitelist": bool(setting("signup").get("whitelist")),
                }
            )
        u = self.user()
        self.actor_id=u["id"]
        spending.identify(u["id"])
        RATE.check(("account", u["id"]), 600)
        if method not in ("GET", "HEAD"):
            RATE.check(("write", u["id"]), 120)
        if path in ("/api/analyze", "/api/create", "/api/original", "/api/cover", "/api/cover/preview", "/api/extract", "/api/export", "/api/admin/test", "/api/admin/tikhub-test", "/api/admin/skills/state", "/api/admin/mail-test", "/api/admin/retry", "/api/overseas/search"):
            RATE.check(("expensive-account", u["id"]), 30)
            RATE.check(("expensive-ip", self.remote_ip), 120)
        if path == "/api/auth/verify" and method == "POST":
            mailer.verify(u['email'], 'verify', data.get('code'))
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                access.approve(c,u['id'],u['id'],'mailbox_verified',request_id=self.request_id)
            return self.send({'ok':True})
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
                u['live_access']=u['role']=='admin' or bool(c.execute('SELECT 1 FROM live_accounts WHERE user_id=?',(u['id'],)).fetchone())
                u['demo_account']=bool(c.execute('SELECT 1 FROM demo_accounts WHERE user_id=?',(u['id'],)).fetchone())
            return self.send(
                {
                    "user": u,
                    "projects": projects,
                    "credits": credits,
                    "mode": setting("mode"),
                    "rules": setting("rules"),
                    "discover_pick": jobs.discover_pick(),
                    "mail": mailer.enabled(),
                }
            )
        if path.startswith("/api/admin"):
            return self.admin(method, path, data, u, q)
        if path == "/api/extract" and method == "POST":
            return self.send(
                {"text": documents.extract(data.get("name"), data.get("data"))}
            )
        if path == "/api/projects" and method == "POST":
            name, description = data.get("name"), data.get("description", "")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
                raise Error("项目名称需要填写 1 到 100 字")
            if not isinstance(description, str) or len(description) > 2000:
                raise Error("项目介绍最多 2000 字")
            name = name.strip()
            ident = uid()
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                if c.execute('SELECT COUNT(*) FROM projects WHERE user_id=?',(u['id'],)).fetchone()[0]>=50:raise Error('最多创建 50 个项目')
                c.execute(
                    "INSERT INTO projects VALUES (?,?,?,?,?)",
                    (
                        ident,
                        u["id"],
                        name,
                        description.strip(),
                        now(),
                    ),
                )
            return self.send({"id": ident})
        project_match = re.fullmatch(r"/api/projects/([a-f0-9]+)", path)
        if project_match and method == "PATCH":
            ident = project_match.group(1)
            self.project(ident, u)
            name, description = data.get("name"), data.get("description", "")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
                raise Error("项目名称需要填写 1 到 100 字")
            if not isinstance(description, str) or len(description) > 2000:
                raise Error("项目介绍最多 2000 字")
            with db() as c:
                c.execute("UPDATE projects SET name=?,description=? WHERE id=? AND user_id=?",
                          (name.strip(), description.strip(), ident, u["id"]))
            return self.send({"ok": True})
        if path == "/api/credits":
            with db() as c:
                rows = [
                    dict(r)
                    for r in c.execute(
                        "SELECT * FROM credit_ledger WHERE user_id=? AND (created_at,id)<(?,?) ORDER BY created_at DESC,id DESC LIMIT 200",
                        (u["id"],q.get("before",["9999"])[0],q.get("before_id",["~"])[0]),
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
                        "SELECT id,user_id,project_id,kind,state,result,error,cost,model,skill_version,created_at,updated_at FROM tasks WHERE user_id=? AND (created_at,id)<(?,?) ORDER BY created_at DESC,id DESC LIMIT 100",
                        (u["id"],q.get("before",["9999"])[0],q.get("before_id",["~"])[0]),
                    )
                ]
            return self.send(rows)
        project_id = data.get("project_id") or q.get("project_id", [""])[0]
        self.project(project_id, u)
        if path == '/api/overseas/ideas' and method == 'GET':
            query = q.get('query', [''])[0]
            if len(query)>100: raise Error('搜索词最多100字')
            saved=q.get('saved',['0'])[0]=='1'
            return self.send({'items':overseas_library.recommendations(project_id, query, q.get('category',[''])[0], saved, q.get('platform',['all' if saved else 'tiktok'])[0]),
                              'categories':overseas_library.CATEGORIES, 'platforms':overseas.PLATFORMS,
                              'search_available':setting('mode')!='demo' and bool(setting('tikhub').get('api_key')),
                              'refresh':overseas_feed.status(),
                              'translation_pending':overseas_library.overseas_translation.pending(),
                              'skill':{'name':'hiccai-pop','version':'2.2.0','legacy_archetypes':60,'reference_videos':len(overseas_library.REFERENCE_VIDEOS)}})
        if path == '/api/overseas/ideas' and method == 'POST':
            return self.send(overseas_library.collect(project_id,data))
        if path == '/api/overseas/refresh' and method == 'POST':
            RATE.check(('overseas-refresh',u['id']),3)
            return self.send(overseas_feed.refresh(force=True))
        overseas_match=re.fullmatch(r'/api/overseas/ideas/([a-f0-9]+)',path)
        if overseas_match and method == 'PATCH':
            ident=overseas_match.group(1)
            if type(data.get('saved')) is not bool: raise Error('收藏状态无效')
            with db() as c:
                if not c.execute('UPDATE overseas_ideas SET saved=?,updated_at=? WHERE id=? AND project_id=? AND deleted_at IS NULL',(int(data['saved']),now(),ident,project_id)).rowcount:
                    raise Error('创意不存在',404)
            return self.send({'ok':True})
        if path == '/api/overseas/search' and method == 'POST':
            RATE.check(('overseas-search',u['id']),20)
            platform=data.get('platform')
            query=overseas_library.text(data.get('query'),'搜索词',100,True)
            if platform not in overseas_library.PLATFORMS:raise Error('请选择海外平台')
            if setting('mode')=='demo' or not setting('tikhub').get('api_key'):raise Error('未启用海外搜索，请管理员配置 TikHub 并启用真实服务')
            return self.send({'task_ids':[jobs.submit(u['id'],project_id,'search',{'platform':platform,'query':query})]},202)
        requested_overseas = path == '/api/overseas/create'
        if requested_overseas and method == 'POST':
            if data.get('platform') not in overseas.PLATFORMS and not data.get('brief_id'):
                raise Error('请选择TikTok、Instagram Reels或YouTube Shorts')
            path='/api/original'
        if path == '/api/workspace':
            return self.send(workspace.page(project_id,q.get('cursor',[''])[0],int(q.get('limit',['25'])[0])))
        media=re.fullmatch(r'/api/media/(assets|images)/([a-f0-9]{32})',path)
        if media and method in ('GET','HEAD'):
            kind,ident=media.groups()
            with db() as c:
                if kind=='assets':
                    row=c.execute("SELECT content FROM assets WHERE id=? AND project_id=? AND kind='图片'",(ident,project_id)).fetchone()
                    url=row[0] if row else ''
                else:
                    row=c.execute('SELECT data FROM generated_images WHERE id=? AND project_id=?',(ident,project_id)).fetchone()
                    url=json.loads(row[0]).get('url','') if row else ''
            if not row:raise Error('图片不存在',404)
            match=re.fullmatch(r'data:image/(png|jpeg|webp|svg\+xml);base64,([A-Za-z0-9+/=]+)',url)
            if match:
                return self.send(base64.b64decode(match[2],validate=True),content_type='image/'+match[1],
                                 headers={'Content-Security-Policy':"default-src 'none'; img-src data:; style-src 'unsafe-inline'; sandbox"})
            if kind=='images' and url.startswith('https://') and not any(ord(ch)<=32 or ord(ch)==127 for ch in url):
                return self.send(b'',302,headers={'Location':url})
            raise Error('图片格式无效')
        creation_images=re.fullmatch(r'/api/creations/([a-f0-9]{32})/images',path)
        single_image=re.fullmatch(r'/api/images/([a-f0-9]{32})',path)
        if method=='GET' and (creation_images or single_image):
            projection="id,project_id,creation_id,json_set(data,'$.url',CASE WHEN substr(json_extract(data,'$.url'),1,8)='https://' THEN json_extract(data,'$.url') ELSE '' END) AS data,task_id,created_at"
            with db() as c:
                if creation_images:
                    ident=creation_images[1]
                    if not c.execute('SELECT 1 FROM creation_outputs WHERE id=? AND project_id=? AND deleted_at IS NULL',(ident,project_id)).fetchone():
                        raise Error('稿件不存在',404)
                    rows=c.execute('SELECT '+projection+' FROM generated_images WHERE creation_id=? AND project_id=? ORDER BY created_at DESC,id DESC LIMIT 50',(ident,project_id)).fetchall()
                    result=[workspace.image_view(r,project_id) for r in rows]
                else:
                    row=c.execute('SELECT '+projection+' FROM generated_images WHERE id=? AND project_id=?',(single_image[1],project_id)).fetchone()
                    if not row:raise Error('图片不存在',404)
                    result=workspace.image_view(row,project_id)
            return self.send(result)
        detail_match=re.fullmatch(r'/api/(sources|creations|assets)/([a-f0-9]{32})',path)
        if detail_match and method=='GET':
            kind,ident=detail_match.groups()
            table={'sources':'source_contents','creations':'creation_outputs','assets':'assets'}[kind]
            with db() as c:
                row=c.execute(f'SELECT * FROM {table} WHERE id=? AND project_id=?'+(' AND deleted_at IS NULL' if kind=='creations' else ''),(ident,project_id)).fetchone()
                if not row:raise Error('内容不存在',404)
                result=workspace.source_view(c,row) if kind=='sources' else workspace.creation_view(c,row) if kind=='creations' else dict(row)
            return self.send(result)
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
            transcript = data.get("transcript", "")
            if not isinstance(transcript, str) or len(transcript) > 20000:
                raise Error("口播文字最多 20000 字")
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
            if balance < sum(
                jobs.task_cost("analyze", {"entry": entry})[1] for _ in texts
            ):
                raise Error("积分不足以执行此批任务")
            ids = jobs.submit_many(
                u["id"],
                project_id,
                "analyze",
                [
                    {
                        "text": text,
                        "entry": entry,
                        "platform": p,
                        "transcript": transcript.strip() if entry == "single" else "",
                    }
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
            if json.loads(source["data"]).get("kind") == "brief":
                raise Error("请从自主创作主题点击再来一批")
            for field in ("requirements", "temporary"):
                if (
                    not isinstance(data.get(field, ""), str)
                    or len(data.get(field, "")) > 100000
                ):
                    raise Error("创作要求与临时资料必须是最多 100000 字的文本")
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
            if data.get("again") and "assets" not in data:
                # 只继承成功任务，临时资料仅在尚未过期时复用。
                with db() as c:
                    last = next(
                        (
                            {**json.loads(r["payload"]), "temporary": content_quality.reusable_temporary(json.loads(r["payload"]), r["updated_at"], setting("limits").get("temporary_ttl_hours", 24))}
                            for r in c.execute(
                                "SELECT payload,updated_at FROM tasks WHERE project_id=? AND kind='create' AND state='SUCCEEDED' ORDER BY created_at DESC,rowid DESC",
                                (project_id,),
                            )
                            if json.loads(r["payload"]).get("source_id") == source["id"]
                        ),
                        {},
                    )
                selected = [a for a in last.get("assets", []) if a in available]
                data = {
                    "source_id": source["id"],
                    "assets": selected,
                    "requirements": data.get("requirements", last.get("requirements", "")),
                    "temporary": data.get("temporary", last.get("temporary", "")),
                    "goal": data.get("goal", last.get("goal", "leads")),
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
                    ("goal", "leads"),
                ]
            }
            payload["goal"] = content_quality.goal(payload["goal"])
            if setting("mode") != "demo" and not selected and not payload["temporary"].strip():
                raise Error("请提供自己的产品或服务资料，参考内容不能代替你的业务事实")
            return self.send(
                {"task_ids": [jobs.submit(u["id"], project_id, "create", payload)]}, 202
            )
        if path == "/api/original" and method == "POST":
            for field in ("requirements", "temporary"):
                if (
                    not isinstance(data.get(field, ""), str)
                    or len(data.get(field, "")) > 100000
                ):
                    raise Error("创作要求与临时资料必须是最多 100000 字的文本")
            brief_id = data.get("brief_id")
            if brief_id is not None and not isinstance(brief_id, str):
                raise Error("自主创作主题格式不正确")
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
                old_brief = None
                if brief_id:
                    row = c.execute(
                        "SELECT data FROM source_contents WHERE id=? AND project_id=?",
                        (brief_id, project_id),
                    ).fetchone()
                    old_brief = json.loads(row["data"]) if row else None
                    if not old_brief or old_brief.get("kind") != "brief":
                        raise Error("自主创作主题不存在", 404)
            if old_brief:
                brief = {
                    k: old_brief.get(k, "") for k in ("platform", "topic", "keyword")
                }
                brief["goal"] = data.get("goal", old_brief.get("goal", "leads"))
                if brief['platform'] in overseas.PLATFORMS:
                    brief.update({k:old_brief[k] for k in ('language','market','duration','reference_snapshot') if k in old_brief})
                if not selected and "assets" not in data:
                    # 再来一批：沿用上次仍然存在的资料选择
                    selected = [a for a in old_brief.get("assets", []) if a in available]
                requirements = data.get("requirements", old_brief.get("requirements", ""))
                if "temporary" not in data:
                    with db() as c:
                        last = next(({**json.loads(r["payload"]), "temporary": content_quality.reusable_temporary(json.loads(r["payload"]), r["updated_at"], setting("limits").get("temporary_ttl_hours", 24))} for r in c.execute(
                            "SELECT payload,updated_at FROM tasks WHERE project_id=? AND kind='original' AND state='SUCCEEDED' ORDER BY created_at DESC,rowid DESC",
                            (project_id,),
                        ) if json.loads(r["payload"]).get("source_id") == brief_id), {})
                    data["temporary"] = last.get("temporary", "")
            else:
                if any(not isinstance(data.get(k, ""), str) for k in ("topic", "keyword")):
                    raise Error("创作主题与搜索词必须是文本")
                brief = {
                    "platform": data.get("platform"),
                    "topic": str(data.get("topic", "")).strip(),
                    "keyword": str(data.get("keyword", "")).strip()[:60],
                    "goal": data.get("goal", "leads"),
                }
                if brief["platform"] not in ("xhs", "douyin", *overseas.PLATFORMS):
                    raise Error("请选择支持的创作平台")
                if not 2 <= len(brief["topic"]) <= 200:
                    raise Error("请填写 2 到 200 字的创作主题")
                requirements = data.get("requirements", "")
            if requested_overseas and brief['platform'] not in overseas.PLATFORMS:
                raise Error('这个主题属于国内创作，请从对应入口继续')
            if brief['platform'] in overseas.PLATFORMS:
                brief['language']=data.get('language',brief.get('language','en-zh'))
                brief['market']=overseas_library.text(data.get('market',brief.get('market','United States')),'目标市场',60,True)
                brief['duration']=data.get('duration',brief.get('duration',24))
                if brief['language'] not in overseas.LANGUAGES: raise Error('请选择支持的台词语言')
                if type(brief['duration']) is not int or not 12<=brief['duration']<=60: raise Error('目标时长须为12–60秒的整数')
                if data.get('reference_id') is not None:
                    ident=overseas_library.text(data['reference_id'],'参考创意ID',80)
                    brief['reference_snapshot']=overseas_library.reference(project_id,ident) if ident else None
                    if ident and not brief['reference_snapshot']: raise Error('参考创意不存在或不属于当前项目',404)
            brief["goal"] = content_quality.goal(brief["goal"])
            if any(x not in available for x in selected):
                raise Error("所选资料不存在或不属于当前项目")
            temporary = data.get("temporary", "")
            if not selected and not temporary.strip() and brief['platform'] not in overseas.PLATFORMS:
                raise Error("自主创作需要依据：请至少选择一份项目资料或填写临时资料")
            payload = {
                "source_id": brief_id or uid(),
                "brief": brief,
                "assets": selected,
                "requirements": requirements,
                "temporary": temporary,
            }
            return self.send(
                {
                    "task_ids": [jobs.submit(u["id"], project_id, "original", payload)],
                    "brief_id": payload["source_id"],
                },
                202,
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
            if not isinstance(data.get('name'),str) or not isinstance(data.get('content'),str):
                raise Error('资料名称和内容必须为文字')
            if data.get('kind','品牌资料') not in ('品牌资料','产品信息','受众画像','禁用词','账号','图片','其他'):
                raise Error('资料类型无效')
            name = data['name'].strip()
            content = data['content']
            if not name or not content:
                raise Error("请填写资料名称与内容")
            if data.get('kind')!='图片' and len(content)>resource_limits.MAX_TEXT_CHARS:
                raise Error('文本资料最多 100000 字')
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
                c.execute('BEGIN IMMEDIATE')
                resource_limits.check_storage(c,u['id'],len(content.encode()))
                if c.execute('SELECT COUNT(*) FROM assets a JOIN projects p ON p.id=a.project_id WHERE p.user_id=?',(u['id'],)).fetchone()[0]>=500:
                    raise Error('账号最多保存 500 份资料，请先清理')
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
        match = re.fullmatch(r"/api/creations/([a-f0-9]+)/(revisions|edit|restore)", path)
        if match:
            ident, operation = match.groups()
            if operation == "revisions" and method == "GET":
                return self.send(editing.history(ident, project_id))
            if operation in ("edit", "restore") and method == "POST":
                if operation == "restore" and type(data.get("restore_revision")) is not int:
                    raise Error("请选择要恢复的版本")
                return self.send(editing.save(ident, project_id, data.get("revision"),
                                             changes=data.get("changes"),
                                             restore=data.get("restore_revision") if operation == "restore" else None))
            raise Error("不支持的操作", 405)
        match = re.fullmatch(r"/api/(sources|creations|assets)/([a-f0-9]+)", path)
        if match and method in ("PATCH", "DELETE"):
            kind, ident = match.groups()
            table = {
                "sources": "source_contents",
                "creations": "creation_outputs",
                "assets": "assets",
            }[kind]
            with db() as c:
                c.execute("BEGIN IMMEDIATE")
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
                    if not isinstance(data.get('name'),str) or not isinstance(data.get('content'),str) or data.get('kind','品牌资料') not in ('品牌资料','产品信息','受众画像','禁用词','账号','图片','其他'):
                        raise Error('资料名称、类型或内容格式无效')
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
                    if not isinstance(data['content'],str) or not isinstance(data['name'],str) or len(data['name'])>120:
                        raise Error('资料名称或内容格式无效')
                    if data.get('kind')!='图片' and len(data['content'])>resource_limits.MAX_TEXT_CHARS:
                        raise Error('文本资料最多 100000 字')
                    old=c.execute('SELECT length(CAST(content AS BLOB)) FROM assets WHERE id=?',(ident,)).fetchone()[0]
                    resource_limits.check_storage(c,u['id'],len(data['content'].encode())-old)
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
        match = re.fullmatch(r"/api/results/([a-f0-9]+)", path)
        if match and method == "POST":
            ident = match.group(1)
            results = content_quality.clean_results(data.get("results"))
            with db() as c:
                c.execute("BEGIN IMMEDIATE")
                if not c.execute("SELECT 1 FROM creation_outputs WHERE id=? AND project_id=? AND deleted_at IS NULL", (ident, project_id)).fetchone():
                    raise Error("稿件不存在", 404)
                c.execute("INSERT OR REPLACE INTO creation_results VALUES (?,?,?,?)", (ident, project_id, dumps(results), now()))
                resource_limits.check_storage(c,u["id"])
            return self.send({"ok": True})
        match = re.fullmatch(r"/api/tracking/([a-f0-9]+)", path)
        if match and method == "POST":
            ident = match.group(1)
            with db() as c:
                c.execute("BEGIN IMMEDIATE")
                if not c.execute(
                    "SELECT 1 FROM creation_outputs WHERE id=? AND project_id=? AND deleted_at IS NULL",
                    (ident, project_id),
                ).fetchone():
                    raise Error("稿件不存在", 404)
                row = c.execute(
                    "SELECT * FROM creation_tracking WHERE creation_id=?", (ident,)
                ).fetchone()
                cur = {
                    "status": row["status"] if row else "draft",
                    "account_id": row["account_id"] if row else None,
                    "published_at": row["published_at"] if row else None,
                    "checklist": json.loads(row["checklist"] or "{}") if row else {},
                }
                if "status" in data:
                    if data["status"] not in production.STATUSES:
                        raise Error("工序状态无效")
                    cur["status"] = data["status"]
                    if data["status"] == "draft":
                        cur["published_at"] = None
                        cur["checklist"] = {}
                    elif not cur["published_at"]:
                        cur["published_at"] = now()
                if "published_at" in data and cur["status"] == "published":
                    value = str(data["published_at"] or "")
                    try:
                        import datetime as _dt

                        _dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
                    except ValueError:
                        raise Error("发布时间格式不正确")
                    cur["published_at"] = value
                if "account_id" in data:
                    account = data["account_id"] or None
                    if account and not c.execute(
                        "SELECT 1 FROM assets WHERE id=? AND project_id=? AND kind='账号'",
                        (account, project_id),
                    ).fetchone():
                        raise Error("账号不存在，请先在项目资料里添加「账号」")
                    cur["account_id"] = account
                if "checklist" in data:
                    cur["checklist"] = production.clean_checklist(data["checklist"])
                c.execute(
                    "INSERT OR REPLACE INTO creation_tracking(creation_id,project_id,status,account_id,published_at,checklist,updated_at) VALUES (?,?,?,?,?,?,?)",
                    (
                        ident,
                        project_id,
                        cur["status"],
                        cur["account_id"],
                        cur["published_at"],
                        dumps(cur["checklist"]),
                        now(),
                    ),
                )
                row = c.execute(
                    "SELECT * FROM creation_tracking WHERE creation_id=?", (ident,)
                ).fetchone()
                resource_limits.check_storage(c,u["id"])
            return self.send(production.row_view(row))
        if path == "/api/export":
            return self.export(project_id, q.get("format", ["csv"])[0])
        raise Error("接口不存在", 404)

    def export(self, project, fmt):
        rows = [
            [
                "稿件ID",
                "平台",
                "参考链接",
                "内容方向",
                "岗位",
                "切角",
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
                "评论布局",
                "投放说明",
                "生成批次",
                "模型",
                "Skill版本",
                "创建时间",
                "工序状态",
                "发布账号",
                "发布时间",
                "创作目标",
                "交付检查",
                "发布前待补充",
                "浏览次数",
                "有效咨询",
                "订单数",
                "推广花费",
                "效果备注",
                "效果记录时间",
                "海外目标市场", "台词语言", "目标时长（秒）", "完整口播", "口播中文翻译", "创新算子", "原创变化", "Hook备选", "循环结尾", "平台适配", "讨论问题",
                "第一秒画面", "观众误判", "公平伏笔", "结尾反转", "产品角色", "收尾方式", "出镜方式", "产品揭晓镜号", "产品揭晓", "制作路径", "成本依据",
                "创意", "AI镜头提示词", "视频屏幕文案", "屏幕文案中文翻译",
            ]
        ]
        with db() as c:
            for r in c.execute(
                "SELECT o.*,s.platform,s.url,s.data AS source_data,t.model,v.name AS skill_name,v.version AS skill_number,k.status AS track_status,k.published_at,a.name AS account_name,f.data AS result_data,f.updated_at AS result_time FROM creation_outputs o JOIN source_contents s ON s.id=o.source_id LEFT JOIN tasks t ON t.id=o.task_id LEFT JOIN skill_versions v ON v.id=o.skill_version LEFT JOIN creation_tracking k ON k.creation_id=o.id LEFT JOIN assets a ON a.id=k.account_id LEFT JOIN creation_results f ON f.creation_id=o.id WHERE o.project_id=? AND o.deleted_at IS NULL ORDER BY o.created_at",
                (project,),
            ):
                d = json.loads(r["data"])
                src = json.loads(r["source_data"] or "{}")
                effect = json.loads(r["result_data"] or "{}")
                rows.append(
                    [
                        r["id"],
                        r["platform"],
                        "自主创作：" + src.get("topic", "")
                        if src.get("kind") == "brief"
                        else r["url"],
                        d.get("direction", ""),
                        d.get("role", ""),
                        d.get("angle", ""),
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
                        comment_layout_text(d.get("comment_layout")),
                        adapters.PROMOTION_NOTE if d.get("direction") else "",
                        r["task_id"],
                        r["model"] or "",
                        f"{r['skill_name']} v{r['skill_number']}"
                        if r["skill_name"]
                        else r["skill_version"] or "",
                        r["created_at"],
                    ]
                    + tracking_columns(r)
                    + [content_quality.GOALS.get(d.get("goal"), ("",))[0],
                       {"checked": "基础检查通过，事实仍需核对", "needs_input": "发布前需补充", "review": "已编辑，事实仍需核对"}.get(d.get("quality", {}).get("status"), "历史稿件未检查"),
                       "\n".join(d.get("quality", {}).get("issues", [])),
                       *(effect.get(k, "") for k in ("views", "leads", "orders", "spend", "note")),
                        r["result_time"] or "",
                        d.get('overseas',{}).get('market',''),d.get('overseas',{}).get('language',''),d.get('overseas',{}).get('duration',''),
                        d.get('script',''),d.get('translation_zh',''),d.get('operator',''),d.get('innovation',''),
                        '\n'.join(f"{h.get('visual','')} | {h.get('line','')} | {h.get('translation_zh','')} | {h.get('sfx','')}" for h in d.get('hooks',[])),
                        d.get('loop',''),d.get('adaptation',''),'\n'.join(d.get('comments',[])),
                        *(d.get(k,'') for k in ('first_second','misread','clue','reveal','product_role','ending_type','casting','reveal_shot','product_reveal','production_method','cost_basis')),
                        d.get('concept',''), '\n\n'.join(f"镜头 {i+1}\n{s.get('ai_prompt','')}" for i,s in enumerate(d.get('shots',[]))),
                        *('\n'.join(f"{s.get('start','')}–{s.get('end','')}s | {s.get(k,'')}" for s in d.get('shots',[]) if s.get(k)) for k in ('screen_text','screen_text_zh'))]
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
        if path == '/api/admin/access' and method == 'POST':
            preserve=data.get('preserve_balance',False)
            if type(preserve) is not bool:raise Error('保留积分选项无效')
            with db() as c:
                c.execute('BEGIN IMMEDIATE')
                access.approve(c,data.get('user_id'),u['id'],'admin_approval',preserve_balance=preserve,request_id=self.request_id)
            return self.send({'ok':True})
        if path == '/api/admin/audit'  and method == 'GET':
            before=q.get('before',['9999'])[0]
            before_id=q.get('before_id',['~'])[0]
            with db() as c:
                rows=[dict(r) for r in c.execute('SELECT * FROM audit_events WHERE (created_at,id)<(?,?) ORDER BY created_at DESC,id DESC LIMIT 100',(before,before_id))]
            return self.send(rows)
        if path == '/api/admin/usage' and method == 'GET':
            with db() as c:
                rows=[dict(r) for r in c.execute('SELECT day,user_id,COUNT(*) AS calls,SUM(reserved) AS reserved_microusd FROM external_calls GROUP BY day,user_id ORDER BY day DESC LIMIT 100')]
            return self.send({'reservations':rows,'basis':'按配置的价格上界预留；不是供应商实际账单'})
        if path == "/api/admin" and method == "GET":
            cfg = {
                k: setting(k)
                for k in (
                    "mode",
                    "rules",
                    "limits",
                    "provider",
                    "tikhub",
                    "ranking",
                    "mail",
                    "signup",
                )
            }
            for k in ("provider", "tikhub"):
                cfg[k]["api_key"] = "••••••••" if cfg[k].get("api_key") else ""
            cfg["mail"]["password"] = "••••••••" if cfg["mail"].get("password") else ""
            with db() as c:
                users = [
                    dict(r)
                    for r in c.execute(
                        "SELECT u.id,u.email,u.role,a.balance,a.frozen,(u.role='admin' OR u.id IN (SELECT user_id FROM live_accounts)) AS live_access,u.id IN (SELECT user_id FROM demo_accounts) AS demo_account FROM users u JOIN credit_accounts a ON a.user_id=u.id"
                    )
                ]
                tasks = [
                    dict(r)
                    for r in c.execute(
                        "SELECT id,user_id,project_id,kind,state,result,error,cost,model,skill_version,created_at,updated_at FROM tasks ORDER BY created_at DESC,id DESC LIMIT 100"
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
                audit_rows=[dict(r) for r in c.execute("SELECT * FROM audit_events ORDER BY created_at DESC,id DESC LIMIT 100")]
                usage_rows=[dict(r) for r in c.execute("SELECT day,user_id,COUNT(*) AS calls,SUM(reserved) AS reserved_microusd FROM external_calls GROUP BY day,user_id ORDER BY day DESC LIMIT 100")]
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
                    "audit": audit_rows,
                    "usage": usage_rows,
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
                        secret_store.write(secret_store.read(key)),
                        int(bool(data.get("enabled", True))),
                    ),
                )
                self.audit(c,u["id"],"provider.save",ident,{"enabled":bool(data.get("enabled",True))})
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
                self.audit(c,u["id"],"routes.update",details={"kinds":list(data)})
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
                    "mail",
                    "signup",
                ):
                    raise Error("不支持的配置项")
                if key == "signup":
                    if not isinstance(value, dict) or not isinstance(
                        value.get("emails", []), list
                    ):
                        raise Error("注册设置格式不正确")
                    emails = []
                    for e in value.get("emails", []):
                        e = str(e).strip().lower()
                        if not e:
                            continue
                        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
                            raise Error("白名单里有无效邮箱：" + e[:60])
                        if e not in emails:
                            emails.append(e)
                    welcome = value.get("welcome_credits", 100)
                    if type(welcome) is not int or not 0 <= welcome <= 100000:
                        raise Error("新用户赠送积分需在 0–100000 之间")
                    if len(emails) > 5000:
                        raise Error("白名单最多 5000 个邮箱")
                    value = {
                        "whitelist": bool(value.get("whitelist")),
                        "emails": emails,
                        "welcome_credits": welcome,
                    }
                if key == "mail":
                    value = {
                        "enabled": bool(value.get("enabled")),
                        "host": str(value.get("host", "")).strip(),
                        "port": value.get("port", 465),
                        "security": value.get("security", "ssl"),
                        "username": str(value.get("username", "")).strip(),
                        "password": str(value.get("password", "")),
                        "sender": str(value.get("sender", "")).strip(),
                    }
                    if (
                        type(value["port"]) is not int
                        or not 1 <= value["port"] <= 65535
                        or value["security"] not in ("ssl", "starttls")
                    ):
                        raise Error("邮件服务端口或加密方式无效")
                    if value["enabled"] and (not value["host"] or not value["sender"]):
                        raise Error("启用邮件服务需要填写 SMTP 地址和发件人")
                    if value["password"] == "••••••••":
                        value["password"] = setting("mail").get("password", "")
                if key != "mode" and not isinstance(value, dict):
                    raise Error("配置项必须为 JSON 对象")
                if key == "mode" and value not in ("demo", "live"):
                    raise Error("模式无效")
                if key == "rules" and (
                    not {"analyze", "create", "cover"} <= set(value)
                    or not set(value) <= {"analyze", "create", "cover", "original", "search"}
                    or any(
                        type(v) is not int or v < 0 or v > 10000 for v in value.values()
                    )
                ):
                    raise Error("积分规则无效")
                if key == "limits" and (
                    any(
                        type(value.get(k, default)) is not int
                        for k, default in (
                            ("batch", 0),
                            ("timeout", 0),
                            ("retries", 1),
                            ("temporary_ttl_hours", 24),
                            ("discover_pick", 3),
                        )
                    )
                    or not 1 <= value.get("discover_pick", 3) <= 10
                    or not 1 <= value.get("batch", 0) <= 50
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
                changes[key] = secret_store.pack(key,value) if key in ("provider","tikhub","mail") else value
            with db() as c:
                for key, value in changes.items():
                    c.execute(
                        "UPDATE settings SET value=? WHERE key=?", (dumps(value), key)
                    )
                self.audit(c,u["id"],"config.update",details={"keys":list(changes)})
            return self.send({"ok": True})
        if path == "/api/admin/mail-test" and method == "POST":
            if not mailer.enabled():
                raise Error("请先保存并启用邮件服务")
            try:
                mailer.send_mail(
                    u["email"], "【DAOLOOK】邮件服务测试", "邮件服务配置可用。"
                )
            except Exception as e:
                raise Error("测试邮件发送失败：" + type(e).__name__)
            return self.send({"ok": True})
        if path == "/api/admin/password" and method == "POST":
            password = str(data.get("password", ""))
            if not 8 <= len(password) <= 1024:
                raise Error("新密码需要 8 到 1024 位")
            with db() as c:
                if not c.execute(
                    "UPDATE users SET password=? WHERE id=?",
                    (password_hash(password), data.get("user_id")),
                ).rowcount:
                    raise Error("用户不存在")
                c.execute("DELETE FROM sessions WHERE user_id=?", (data.get("user_id"),))
                self.audit(c,u["id"],"user.password_reset",data.get("user_id"))
            return self.send({"ok": True})
        if path == "/api/admin/grant" and method == "POST":
            amount = data.get("amount")
            if type(amount) is not int or amount == 0 or abs(amount) > 100000:
                raise Error("调整积分需为 -100000 到 100000 之间的非零整数")
            with db() as c:
                c.execute("BEGIN IMMEDIATE")
                account = c.execute(
                    "SELECT balance FROM credit_accounts WHERE user_id=?",
                    (data.get("user_id"),),
                ).fetchone()
                if not account:
                    raise Error("用户不存在")
                # 扣减只动可用积分，不动任务冻结中的积分。
                if account["balance"] + amount < 0:
                    raise Error(f"可用积分只有 {account['balance']}，不足以扣减")
                c.execute(
                    "UPDATE credit_accounts SET balance=balance+? WHERE user_id=?",
                    (amount, data["user_id"]),
                )
                note = str(data.get("note", "")).strip()[:60]
                ledger(
                    c,
                    data["user_id"],
                    None,
                    "GRANT" if amount > 0 else "DEDUCT",
                    amount,
                    ("管理员发放" if amount > 0 else "管理员扣减") + ("：" + note if note else ""),
                )
                self.audit(c,u["id"],"credits.adjust",data["user_id"],{"amount":amount})
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
                cfg = secret_store.unpack("provider",dict(provider))
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
                            json.loads(t["payload"]), actor=u["id"], request_id=self.request_id,
                        )
                    ]
                }
            )
        if path == "/api/admin/skills" and method == "POST":
            name = data.get("name")
            prompt = data.get("prompt", "").strip()
            if (
                name not in SKILL_NAMES
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
                self.audit(c,u["id"],"skill.draft",name,{"version":n})
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
                if skill["name"].endswith("original"):
                    skill_platform=skill['name'].split('_')[0]
                    producer=overseas.create if skill_platform in overseas.PLATFORMS else adapters.create_original
                    producer(
                        {"platform": skill_platform, "topic": "验证结构", 'duration':24,'market':'United States','language':'en-zh','goal':'leads'},
                        {"examples": [], "note": "结构测试，无赛道参考"},
                        [{"name": "测试资料", "content": data.get("sample", "这是一份用于测试输出结构的资料样本。")}],
                        "验证结构",
                        skill["prompt"],
                        1,
                        demo=setting("mode") == "demo",
                    )
                elif skill["name"].endswith("analysis"):
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
                self.audit(c,u["id"],"skill.state",data["id"],{"status":target})
            return self.send({"ok": True})
        raise Error("管理接口不存在", 404)


def bootstrap_admin():
    email=os.environ.get('DAOLOOK_ADMIN_EMAIL','').strip().lower()
    password=os.environ.get('DAOLOOK_ADMIN_PASSWORD','')
    if not email or not password:return
    with db() as c:
        existing=c.execute('SELECT id,role FROM users WHERE email=?',(email,)).fetchone()
    if existing:
        if existing['role']!='admin':
            raise RuntimeError('引导邮箱已有普通账号，请使用现有管理员明确授权；启动不会提升权限')
        return
    if len(password)<12:raise RuntimeError('管理员初始密码至少 12 位')
    new_user(email,password,'admin',bootstrap=True)


def main():
    os.umask(0o077)
    load_env()
    from . import db as database
    database.DB_PATH = str(database_path())
    init()
    bootstrap_admin()
    jobs.start()
    maintenance.start()
    from . import overseas_translation
    overseas_translation.start()
    overseas_feed.start()
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"DAOLOOK ready: http://{host}:{port}", flush=True)
    BoundedHTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
