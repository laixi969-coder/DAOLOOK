"""邮箱验证码：注册时验证邮箱所有权，找回密码时重置。

邮件经管理员配置的 SMTP 发送；验证码只存哈希，10 分钟有效，最多尝试 5 次，
同一邮箱 60 秒内只发一次。
"""

import hashlib, hmac, secrets, smtplib, ssl, time
from email.message import EmailMessage
from .db import db, setting

CODE_TTL = 600
RESEND_SECONDS = 60
MAX_ATTEMPTS = 5
PURPOSES = {"register": "注册 DAOLOOK", "reset": "重置 DAOLOOK 密码"}


def enabled():
    cfg = setting("mail")
    return bool(
        cfg.get("enabled") and cfg.get("host") and cfg.get("sender") and cfg.get("port")
    )


def _digest(email, purpose, code):
    return hashlib.sha256(f"{email}:{purpose}:{code}".encode()).hexdigest()


def send_mail(to, subject, text):
    cfg = setting("mail")
    msg = EmailMessage()
    msg["From"] = cfg["sender"]
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(text)
    port = int(cfg.get("port") or 465)
    context = ssl.create_default_context()
    if cfg.get("security", "ssl") == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], port, timeout=20, context=context)
    else:
        server = smtplib.SMTP(cfg["host"], port, timeout=20)
        server.starttls(context=context)
    try:
        if cfg.get("username"):
            server.login(cfg["username"], cfg.get("password", ""))
        server.send_message(msg)
    finally:
        server.quit()


def issue(email, purpose):
    if purpose not in PURPOSES:
        raise ValueError("验证码用途无效")
    if not enabled():
        raise ValueError("管理员尚未配置邮件服务，暂不能发送验证码")
    code = f"{secrets.randbelow(1000000):06d}"
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT created FROM email_codes WHERE email=? AND purpose=?",
            (email, purpose),
        ).fetchone()
        if row and row["created"] > time.time() - RESEND_SECONDS:
            raise ValueError("验证码已发送，请 60 秒后再试")
        c.execute(
            "INSERT OR REPLACE INTO email_codes VALUES (?,?,?,?,?,?)",
            (
                email,
                purpose,
                _digest(email, purpose, code),
                time.time() + CODE_TTL,
                0,
                time.time(),
            ),
        )
    try:
        send_mail(
            email,
            f"【DAOLOOK】{PURPOSES[purpose]}验证码",
            f"你的验证码是 {code}，10 分钟内有效。\n如果不是你本人操作，请忽略这封邮件。",
        )
    except Exception:
        with db() as c:
            c.execute(
                "DELETE FROM email_codes WHERE email=? AND purpose=?", (email, purpose)
            )
        raise ValueError("验证码邮件发送失败，请稍后重试或联系管理员")


def verify(email, purpose, code):
    """校验并消费验证码；失败计数，超过次数作废。"""
    code = str(code or "").strip()
    with db() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute(
            "SELECT * FROM email_codes WHERE email=? AND purpose=?", (email, purpose)
        ).fetchone()
        if not row or row["expires"] < time.time():
            raise ValueError("验证码已过期，请重新获取")
        if row["attempts"] >= MAX_ATTEMPTS:
            raise ValueError("验证码错误次数过多，请重新获取")
        if not hmac.compare_digest(row["code_hash"], _digest(email, purpose, code)):
            c.execute(
                "UPDATE email_codes SET attempts=attempts+1 WHERE email=? AND purpose=?",
                (email, purpose),
            )
            c.commit()
            raise ValueError("验证码不正确")
        c.execute(
            "DELETE FROM email_codes WHERE email=? AND purpose=?", (email, purpose)
        )
