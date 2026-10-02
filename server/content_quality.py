"""Outcome brief and conservative delivery checks; never predicts reach or sales."""

import re
import unicodedata
import datetime

GOALS = {
    "reach": ("更多人看到", "让目标人群停下来读，提供一个值得收藏或分享的具体收获；结尾只留一个相关问题。"),
    "leads": ("更多人咨询", "回答购买前的一个真实疑问，以资料里的证据建立信任；结尾邀请读者说明自己的需求，不承诺未提供的资料包或服务。"),
    "sales": ("更多人下单", "说明适合谁、不适合谁，解决一个购买顾虑；仅使用资料中真实存在的价格、优惠、购买入口，不制造库存或限时压力。没有购买入口时邀请读者先咨询。"),
}

CONTRACT = """交付标准（优先于旧版本中冲突的创作规则）：
业务事实只来自 assets。reference、analysis、benchmark 只用于研究表达，不是用户产品、价格、案例、效果或经历的来源。
按 objective 写作；用户不需要看到岗位、原理、拆解方法或提示词。用具体人群和场景开头，正文兑现标题承诺，每条只保留一个容易执行的下一步。
缺少非必要信息就省略，不在可发布文案中放 XX、待补充或方括号占位。确实无法完成时将具体缺项写入 missing，不虚构。
每条额外返回 audience（写给谁）、value（读者得到什么）、cta（一句行动引导，与正文结尾一致）、evidence（业务事实依据数组，每项 asset_id 和 quote 原文短句；只引用文本资料，不引用参考或图片推断，无法引用则空数组并在 missing 说明）。
不把治疗替换成改善来掩盖未经证实的功效；不用虚构亲历、保证效果、假评价。图片只支撑可见外观，不能证明效果、资质或价格。
同批标题与正文须有实质区别。更多流量、有效咨询、成交是不同结果，不能保证爆款。不使用统一点击率阈值给投放建议。
history_results 是用户手动记录的历史表现；只把相同目标和平台的结果当作选题线索，留意发布时间和付费流量，不将单条高数据归因为某种写法必然有效。
"""


def goal(value="leads"):
    if not isinstance(value, str) or value not in GOALS:
        raise ValueError("请选择更多人看到、更多人咨询或更多人下单")
    return value


def reusable_temporary(payload, updated_at, ttl_hours):
    """Expiry is enforced on reuse even before the hourly cleanup has run."""
    try:
        timestamp = datetime.datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=datetime.timezone.utc)
        age = (datetime.datetime.now(datetime.timezone.utc) - timestamp).total_seconds()
        if age >= float(ttl_hours) * 3600:
            return ""
    except (ValueError, TypeError, AttributeError):
        return ""
    return payload.get("temporary", "")


def objective(value):
    label, instruction = GOALS[goal(value)]
    return {"goal": value, "label": label, "instruction": instruction}


def normalized(text):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).casefold())


def public_text(output):
    layout = output.get("comment_layout") or {}
    return "\n".join([
        *(output.get(k, "") for k in ("title", "body", "hook", "cover_text", "cta")),
        *output.get("titles", []), *output.get("tags", []),
        *layout.get("atmosphere", []), *layout.get("knowledge", []),
        (layout.get("pinned") or {}).get("text", ""),
    ])


def evidence_valid(output, assets):
    evidence = output.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        return False
    texts = {a.get("id"): a.get("content", "") for a in assets if a.get("kind") != "图片"}
    return all(
        isinstance(e, dict) and isinstance(e.get("asset_id"), str)
        and isinstance(e.get("quote"), str) and len(e["quote"].strip()) >= 4
        and e["quote"] in texts.get(e["asset_id"], "")
        for e in evidence
    )


def assess(output, assets, p):
    """Checks are observable checks, not semantic fact verification."""
    issues = []
    if output.get("demo"):
        issues.append("这是演示模板，请切换真实服务后生成正式内容")
    if re.search(r"(?<![A-Za-z])X{2,}(?![A-Za-z])|待补充|待填写|请补充|【[^】]*待填", public_text(output), re.I):
        issues.append("文案含未填写内容，请补齐后再发布")
    if len(output.get("title", "")) > (20 if p == "xhs" else 25):
        issues.append("标题偏长，请缩短后发布")
    if not all(isinstance(output.get(k), str) and output[k].strip() for k in ("audience", "value", "cta")):
        issues.append("请确认内容写给谁、具体价值及结尾行动")
    elif normalized(output["cta"]) not in normalized(output.get("body", "")):
        issues.append("正文缺少明确的下一步，请补上结尾的行动引导")
    if not evidence_valid(output, assets):
        issues.append("业务事实缺少可核对的文字依据，请补充产品或服务资料")
    issues.extend(m for m in output.get("missing", []) if m.strip())
    return {"status": "needs_input" if issues else "checked", "issues": list(dict.fromkeys(issues)),
            "note": "发布前仍需核对价格、产品效果和购买方式是否准确。"}


def annotate(outputs, assets, p, selected_goal):
    for output in outputs:
        output["goal"] = selected_goal
        output["quality"] = assess(output, assets, p)
    return outputs


def clean_results(value):
    if not isinstance(value, dict) or set(value) - {"views", "leads", "orders", "spend", "note"}:
        raise ValueError("效果记录格式不正确")
    result = {}
    for key in ("views", "leads", "orders", "spend"):
        number = value.get(key)
        if number is None:
            continue
        if type(number) not in (int, float) or not 0 <= number <= 1_000_000_000:
            raise ValueError("效果数据必须是非负数")
        if key != "spend" and (type(number) is not int):
            raise ValueError("浏览、咨询和订单必须是整数")
        result[key] = number
    note = value.get("note", "")
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError("效果备注最多 1000 字")
    result["note"] = note.strip()
    return result
