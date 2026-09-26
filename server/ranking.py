"""Relative, transparent ranking. Missing measurements are never fabricated."""

import math
from .db import setting


def engagement(content):
    """互动强度：点赞 + 收藏×2 + 评论×3。账号/赛道基线用同一口径计算。"""
    values = []
    for key in ("likes", "saves", "comments"):
        v = content.get(key)
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            v = None
        values.append(v if v is not None and math.isfinite(v) and v >= 0 else None)
    if all(v is None for v in values):
        return None
    likes, saves, comments = values
    return (likes or 0) + (saves or 0) * 2 + (comments or 0) * 3


def median(values):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    return values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2


def score(content, weights=None):
    weights = weights if weights is not None else setting("ranking")
    components = {}

    def number(key):
        try:
            if content.get(key) is None or isinstance(content[key], bool):
                return None
            value = float(content[key])
            return value if math.isfinite(value) and value >= 0 else None
        except (TypeError, ValueError):
            return None

    likes, saves, comments = [number(k) for k in ("likes", "saves", "comments")]
    if any(x is not None for x in (likes, saves, comments)):
        engagement = (likes or 0) + (saves or 0) * 2 + (comments or 0) * 3
        components["engagement"] = min(1, math.log1p(engagement) / math.log1p(100000))
        for field, key in [
            ("followers", "efficiency"),
            ("account_median", "account_lift"),
            ("category_median", "category_lift"),
        ]:
            denominator = number(field)
            if denominator:
                components[key] = min(
                    1, math.log1p(engagement / denominator) / math.log1p(20)
                )
    age = number("age_days")
    if age is not None:
        components["freshness"] = math.exp(-age / 30)
    reuse = number("reusability")
    if reuse is not None:
        components["reusability"] = min(1, reuse)
    total = sum(weights.get(k, 0) for k in components)
    return {
        "score": round(
            100 * sum(v * weights.get(k, 0) for k, v in components.items()) / total, 1
        )
        if total
        else None,
        "components": components,
        "coverage": len(components),
        "calibrated": False,
    }
