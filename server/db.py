import os, sqlite3, json, uuid, datetime
from contextlib import contextmanager
from .defaults import ENDPOINTS

DB_PATH = os.environ.get("DAOLOOK_DB", "data/daolook.db")


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with db() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password TEXT,role TEXT NOT NULL DEFAULT 'user',created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),name TEXT NOT NULL,description TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS assets(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),name TEXT,kind TEXT,content TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS source_contents(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),platform TEXT,url TEXT,data TEXT,saved INTEGER DEFAULT 0,created_at TEXT);
        CREATE TABLE IF NOT EXISTS analysis_outputs(id TEXT PRIMARY KEY,source_id TEXT REFERENCES source_contents(id),data TEXT,skill_version TEXT,task_id TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS creation_outputs(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),source_id TEXT REFERENCES source_contents(id),task_id TEXT,data TEXT,skill_version TEXT,saved INTEGER DEFAULT 0,deleted_at TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS generated_images(id TEXT PRIMARY KEY,project_id TEXT REFERENCES projects(id),creation_id TEXT REFERENCES creation_outputs(id),data TEXT,task_id TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),project_id TEXT REFERENCES projects(id),kind TEXT,state TEXT,payload TEXT,result TEXT,error TEXT,cost INTEGER,model TEXT,skill_version TEXT,created_at TEXT,updated_at TEXT);
        CREATE TABLE IF NOT EXISTS credit_accounts(user_id TEXT PRIMARY KEY REFERENCES users(id),balance INTEGER NOT NULL CHECK(balance>=0),frozen INTEGER NOT NULL DEFAULT 0 CHECK(frozen>=0));
        CREATE TABLE IF NOT EXISTS credit_ledger(id TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),task_id TEXT,kind TEXT,amount INTEGER,description TEXT,created_at TEXT);
        CREATE TABLE IF NOT EXISTS model_providers(id TEXT PRIMARY KEY,name TEXT,base_url TEXT,api_key TEXT,enabled INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS model_routes(kind TEXT PRIMARY KEY,config TEXT);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
        CREATE TABLE IF NOT EXISTS skill_versions(id TEXT PRIMARY KEY,name TEXT,version INTEGER,prompt TEXT,status TEXT,created_at TEXT);
        CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id,created_at);
        CREATE INDEX IF NOT EXISTS idx_creation_project ON creation_outputs(project_id,deleted_at);
        """)
        defaults = {
            "mode": os.environ.get("DAOLOOK_MODE", "demo"),
            "rules": {"analyze": 5, "create": 15, "cover": 8},
            "limits": {
                "batch": 10,
                "timeout": 60,
                "retries": 1,
                "temporary_ttl_hours": 24,
            },
            "provider": {
                "base_url": "https://api.openai.com/v1",
                "api_key": "",
                "model": "",
                "backup_model": "",
                "image_model": "",
                "enabled": True,
            },
            "tikhub": {
                "base_url": "https://api.tikhub.io",
                "api_key": "",
                "endpoints": ENDPOINTS,
            },
            "ranking": {
                "engagement": 0.3,
                "efficiency": 0.25,
                "account_lift": 0.2,
                "category_lift": 0.15,
                "freshness": 0.05,
                "reusability": 0.05,
            },
        }
        for k, v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, dumps(v)))
        # One-time configuration migration for early V1.1 local databases.
        if not c.execute(
            "SELECT 1 FROM settings WHERE key='schema_version'"
        ).fetchone():
            current = json.loads(
                c.execute("SELECT value FROM settings WHERE key='tikhub'").fetchone()[0]
            )
            for key, endpoint in ENDPOINTS.items():
                old = current.setdefault("endpoints", {}).get(key)
                if not old or old == endpoint["path"]:
                    current["endpoints"][key] = endpoint
            c.execute(
                "UPDATE settings SET value=? WHERE key='tikhub'", (dumps(current),)
            )
            c.execute("INSERT INTO settings VALUES ('schema_version','1')")
        for kind in ("analyze", "create", "cover"):
            c.execute(
                "INSERT OR IGNORE INTO model_routes VALUES (?,?)",
                (
                    kind,
                    dumps(
                        {
                            "primary": {"provider": "default", "model": ""},
                            "backup": {"provider": "default", "model": ""},
                        }
                    ),
                ),
            )
        for name in [
            "xhs_analysis",
            "douyin_analysis",
            "xhs_creation",
            "douyin_creation",
        ]:
            if not c.execute(
                "SELECT 1 FROM skill_versions WHERE name=?", (name,)
            ).fetchone():
                c.execute(
                    "INSERT INTO skill_versions VALUES (?,?,?,?,?,?)",
                    (
                        uid(),
                        name,
                        1,
                        "你是专业内容策划。只依据提供的参考与资料，事实缺失时明确标注待补充。分析平台特有结构；创作三个机制一致但表达不同的原创方案，禁止编造数据、经历、产品功效。返回指定 JSON。",
                        "Published",
                        now(),
                    ),
                )


def setting(key):
    with db() as c:
        return json.loads(
            c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()[0]
        )


def ledger(c, user, task, kind, amount, description):
    c.execute(
        "INSERT INTO credit_ledger VALUES (?,?,?,?,?,?,?)",
        (uid(), user, task, kind, amount, description, now()),
    )
