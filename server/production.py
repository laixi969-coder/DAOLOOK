"""内容生产线（PRD 9.5）：稿件工序、第一小时评论清单、数据回填与投放判断。

投放判断只给建议，不接投放后台：先看自然流数据，点击率达标才建议小额保护性投放，
投放只放大已经被市场验证的结果。
"""

import json

STATUSES = ("draft", "published")
METRICS = ("impressions", "clicks", "likes", "saves", "comments")
CHECKLIST = ("pinned", "knowledge", "atmosphere")


def thresholds(limits):
    ctr = limits.get("promote_ctr", 0.2)
    floor = limits.get("promote_min_impressions", 500)
    return (
        ctr if isinstance(ctr, (int, float)) and 0 < ctr < 1 else 0.2,
        floor if type(floor) is int and floor >= 0 else 500,
    )


def evaluate(metrics, limits):
    """返回点击率、互动率与投放建议；没有回填数据时返回 None。"""
    metrics = metrics or {}
    if not any(metrics.get(k) is not None for k in METRICS):
        return None
    ctr_line, floor = thresholds(limits)
    imp, clicks = metrics.get("impressions"), metrics.get("clicks")
    engaged = sum(metrics.get(k) or 0 for k in ("likes", "saves", "comments"))
    ctr = clicks / imp if imp and clicks is not None else None
    base = clicks or imp
    engagement = engaged / base if base else None
    if not imp:
        code, text = "unknown", "请先回填曝光和点击，才能判断是否值得投放"
    elif imp < floor:
        code, text = "insufficient", f"曝光不足 {floor}，数据量还不够，继续自然流观察"
    elif ctr is None:
        code, text = "unknown", "缺少点击数，无法计算点击率"
    elif ctr >= ctr_line:
        code, text = (
            "promote",
            f"点击率 {ctr:.0%} 达到 {ctr_line:.0%}：可以考虑小额保护性投放，放大已被验证的结果",
        )
    else:
        code, text = (
            "hold",
            f"点击率 {ctr:.0%} 未到 {ctr_line:.0%}：不建议投放，先换标题 / 封面或换切角再测",
        )
    return {
        "ctr": round(ctr, 4) if ctr is not None else None,
        "engagement": round(engagement, 4) if engagement is not None else None,
        "advice": code,
        "advice_text": text,
    }


def clean_metrics(value):
    if not isinstance(value, dict):
        raise ValueError("数据格式不正确")
    out = {}
    for key in METRICS:
        v = value.get(key)
        if v in (None, ""):
            continue
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v != int(v):
            raise ValueError("数据必须是非负整数")
        v = int(v)
        if not 0 <= v <= 10_000_000_000:
            raise ValueError("数据必须是非负整数")
        out[key] = v
    if (
        out.get("clicks") is not None
        and out.get("impressions") is not None
        and out["clicks"] > out["impressions"]
    ):
        raise ValueError("点击数不能大于曝光数")
    return out


def clean_checklist(value):
    if not isinstance(value, dict):
        raise ValueError("清单格式不正确")
    return {k: bool(value.get(k)) for k in CHECKLIST}


def row_view(row, limits):
    if not row:
        return {"status": "draft", "metrics": {}, "checklist": {}, "evaluation": None}
    metrics = json.loads(row["metrics"] or "{}")
    return {
        "status": row["status"],
        "account_id": row["account_id"],
        "published_at": row["published_at"],
        "metrics": metrics,
        "checklist": json.loads(row["checklist"] or "{}"),
        "evaluation": evaluate(metrics, limits),
        "updated_at": row["updated_at"],
    }
