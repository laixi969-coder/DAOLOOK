"""博主/关键词入口的候选解析、基线计算与按相对表现精选。

只使用数据源返回的指标；缺失的字段保持 None，不做估算。
"""

import datetime, re, time
from . import ranking

TIME_KEYS = ("create_time", "publish_time", "time", "last_update_time", "timestamp")


def parse_count(value):
    """把 1234 / "1,234" / "1.2万" / "3.4w" / "10万+" / "1.1亿" 转成整数。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    text = str(value).strip().replace(",", "").replace("+", "").lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(万|w|亿|k|千)?", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = {"万": 1e4, "w": 1e4, "亿": 1e8, "k": 1e3, "千": 1e3}.get(match.group(2), 1)
    return int(round(number * unit))


def parse_age_days(node, now=None):
    """从 create_time 等字段得到发布距今天数；识别秒、毫秒与 ISO 时间。"""
    now = now or time.time()
    for key in TIME_KEYS:
        value = node.get(key) if isinstance(node, dict) else None
        if value in (None, "", 0):
            continue
        stamp = None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            stamp = float(value)
        elif isinstance(value, str) and value.strip().isdigit():
            stamp = float(value)
        elif isinstance(value, str):
            try:
                stamp = datetime.datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                ).timestamp()
            except ValueError:
                continue
        if stamp is None:
            continue
        if stamp > 1e12:
            stamp /= 1000
        if not 1e9 < stamp <= now + 86400:
            continue
        return round(max(0.0, (now - stamp) / 86400), 2)
    return None


def _walk(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _first(node, keys):
    for n in _walk(node):
        for key in keys:
            if n.get(key) is not None:
                return n[key]
    return None


def _ident(node, p):
    if p == "douyin":
        return node.get("aweme_id")
    if node.get("note_id"):
        return node["note_id"]
    if node.get("id") and any(
        k in node for k in ("title", "display_title", "note_card", "interact_info")
    ):
        return node["id"]
    return None


def list_items(raw, p):
    """从博主作品列表或搜索结果中取出每条内容的公开指标。"""
    items, seen = [], set()
    for node in _walk(raw):
        ident = _ident(node, p)
        if not ident or str(ident) in seen:
            continue
        seen.add(str(ident))
        stats = (
            node.get("statistics")
            or node.get("interact_info")
            or (node.get("note_card") or {}).get("interact_info")
            or node
        )
        author = node.get("author") or node.get("user") or {}
        item = {
            "id": str(ident),
            "url": (
                "https://www.douyin.com/video/"
                if p == "douyin"
                else "https://www.xiaohongshu.com/explore/"
            )
            + str(ident),
            "likes": parse_count(
                _first(stats, ("digg_count", "liked_count", "likes", "like_count"))
            ),
            "saves": parse_count(
                _first(stats, ("collect_count", "collected_count", "collects"))
            ),
            "comments": parse_count(_first(stats, ("comment_count", "comments"))),
            "followers": parse_count(
                _first(author, ("follower_count", "fans", "fans_count"))
            )
            if isinstance(author, dict)
            else None,
            "age_days": parse_age_days(node)
            or parse_age_days(node.get("note_card") or {}),
        }
        items.append(item)
    return items


def baseline(items):
    """这一组内容的互动中位数：博主入口即账号近期中位数，关键词入口即同赛道样本中位数。"""
    return ranking.median([ranking.engagement(i) for i in items])


def pick(items, limit, field, value):
    """按相对表现排序后精选；没有任何指标的内容排在最后，保持数据源原顺序。"""
    scored = []
    for order, item in enumerate(items):
        candidate = dict(item)
        if value:
            candidate[field] = value
        result = ranking.score(candidate)
        candidate["selection"] = {
            "score": result["score"],
            "baseline_field": field,
            "baseline": value,
            "pool": len(items),
            "rank_source": order + 1,
        }
        scored.append((result["score"] is None, -(result["score"] or 0), order, candidate))
    scored.sort(key=lambda x: x[:3])
    return [x[3] for x in scored[:limit]]
