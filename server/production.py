"""内容生产线（PRD 9.5）：稿件工序、发布账号与第一小时评论清单。

不回填平台数据、不给投放建议：点击率等数据由用户在平台后台查看。
"""

import datetime
import json
import os
from zoneinfo import ZoneInfo

STATUSES = ("draft", "published")
CHECKLIST = ("pinned", "knowledge", "atmosphere")
WINDOWS = {"24h": 24, "7d": 168, "30d": 720}
METRICS = ("views", "leads", "orders", "spend")


def moment(value):
    if not value:
        return None
    try:
        dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=ZoneInfo(os.environ.get('DAOLOOK_DISPLAY_TIMEZONE','Asia/Shanghai')))


def current_windows(result, published_at):
    return {period: entry for period, entry in result.get('windows', {}).items()
            if period in WINDOWS and published_at and entry.get('published_at') == published_at}


def merge_result(previous, values, period, published_at, stamp):
    """A fixed window is a cumulative snapshot for one publication. Never add overlapping snapshots."""
    if period == 'lifetime':
        merged = dict(values)
        if previous.get('windows'):
            merged['windows'] = previous['windows']
        return merged
    if not isinstance(period, str) or period not in WINDOWS:
        raise ValueError('请选择有效的观察期')
    published = moment(published_at)
    if not published or moment(stamp) - published < datetime.timedelta(hours=WINDOWS[period]):
        raise ValueError('请先标记发布时间，并在该观察期结束后填写')
    windows = dict(previous.get('windows', {}))
    metrics = {key:values[key] for key in METRICS if key in values}
    if metrics:
        windows[period] = {**metrics, 'published_at': published_at, 'recorded_at': stamp}
    else:
        windows.pop(period, None)
    return {**previous, 'windows': windows, 'note': values['note']}


def add_goal_window(groups, platform, goal, period, snapshot):
    metric = {'reach':'views', 'leads':'leads', 'sales':'orders'}.get(goal)
    count = snapshot.get(metric)
    if type(count) is not int:
        return
    group = groups.setdefault((platform,goal,period), {
        'platform':platform, 'goal':goal, 'window':period, 'posts':0, 'total':0,
        'paired_posts':0, 'paired_views':0, 'paired_actions':0,
    })
    group['posts'] += 1
    group['total'] += count
    views = snapshot.get('views')
    if type(views) is int and views > 0:
        group['paired_posts'] += 1
        group['paired_views'] += views
        group['paired_actions'] += count


def clean_checklist(value):
    if not isinstance(value, dict):
        raise ValueError("清单格式不正确")
    return {k: bool(value.get(k)) for k in CHECKLIST}


def row_view(row, binding=None):
    if not row:
        return {"status": "draft", "checklist": {}}
    return {
        "status": row["status"],
        "account_id": row["account_id"],
        **({k: binding[k] for k in ('platform', 'post_id', 'revision', 'traffic_type')} if binding and row['account_id']==binding['account_id'] else {}),
        "published_at": row["published_at"],
        "checklist": json.loads(row["checklist"] or "{}"),
        "updated_at": row["updated_at"],
    }
