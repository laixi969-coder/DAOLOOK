"""内容生产线（PRD 9.5）：稿件工序、发布账号与第一小时评论清单。

不回填平台数据、不给投放建议：点击率等数据由用户在平台后台查看。
"""

import json

STATUSES = ("draft", "published")
CHECKLIST = ("pinned", "knowledge", "atmosphere")


def clean_checklist(value):
    if not isinstance(value, dict):
        raise ValueError("清单格式不正确")
    return {k: bool(value.get(k)) for k in CHECKLIST}


def row_view(row):
    if not row:
        return {"status": "draft", "checklist": {}}
    return {
        "status": row["status"],
        "account_id": row["account_id"],
        "published_at": row["published_at"],
        "checklist": json.loads(row["checklist"] or "{}"),
        "updated_at": row["updated_at"],
    }
