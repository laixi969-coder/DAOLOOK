"""提交前的单问题追问（内容效果升级·第一优先）。

同一次只问真正阻止成稿的一个问题；能省略的缺失信息就省略。
规则完全确定性、透明可测：不调用模型、不产生费用、不进入任务队列。
判断只看本次所选文字资料与临时资料，图片资料不参与。
"""

import re

# 价格写法：¥12 / ￥12.5 / 12 元 / 12.5块（RMB 前缀或中文单位）。
_PRICE = re.compile(r"(?:¥|￥|RMB)\s*(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?)\s*[元块]")
# 联系与购买路径的关键词，命中任意一个即认为资料写明了转化方式。
_CONTACT = re.compile(
    r"(微信|加微|VX|V信|wx|wechat|私信|评论区|留言|电话|手机号|联系|咨询|扫码|二维码|店铺|小店|链接|下单|购买|预约|到店)",
    re.IGNORECASE,
)
_PURCHASE = re.compile(r"(购买|下单|拍下|拍单|链接|店铺|小店|微店|淘宝|天猫|京东|拼多多|抖音小店|预约|到店|扫码|二维码)")

MAX_ANSWER = 500

QUESTIONS = {
    "price_conflict": "资料里出现了多个不同的价格。以哪个为准？请直接回答价格和对应的产品或规格。",
    "sales_missing": "这批内容的目标是引导下单，但所选资料里没有价格或购买方式。价格是多少、在哪里下单？",
    "leads_missing": "这批内容的目标是带来咨询，但所选资料里没有写用户怎么联系你。咨询方式是什么（如微信、私信或到店）？",
}


def texts(assets, temporary=""):
    values = []
    for asset in assets or []:
        content = asset.get("content")
        if isinstance(content, str) and content.strip():
            values.append(content)
    if isinstance(temporary, str) and temporary.strip():
        values.append(temporary)
    return values


def blocking_question(goal, assets, temporary=""):
    """返回 {id, question} 或 None。一次最多一个问题；冲突优先于缺失。"""
    corpus = "\n".join(texts(assets, temporary))
    if not corpus.strip():
        return None  # 完全没有资料时不追问，由接口层必填校验兜底
    prices = {m.group(1) or m.group(2) for m in _PRICE.finditer(corpus)}
    if len(prices) > 1:
        return {
            "id": "price_conflict",
            "question": QUESTIONS["price_conflict"].replace("多个不同的价格", f"多个不同的价格（{'、'.join(sorted(prices, key=float))}）"),
        }
    if goal == "sales" and not prices and not _PURCHASE.search(corpus):
        return {"id": "sales_missing", "question": QUESTIONS["sales_missing"]}
    if goal == "leads" and not _CONTACT.search(corpus):
        return {"id": "leads_missing", "question": QUESTIONS["leads_missing"]}
    return None


def apply_answer(payload, question_id, answer):
    """把用户对追问的回答并入临时资料；回答进入生成为可引用事实。"""
    if not isinstance(answer, str):
        raise ValueError("回答格式不正确")
    answer = answer.strip()
    if not answer:
        raise ValueError("请填写回答，或选择跳过直接生成")
    if len(answer) > MAX_ANSWER:
        raise ValueError(f"回答最多 {MAX_ANSWER} 字")
    suffix = f"用户补充回答（{question_id}）：{answer}"
    payload["temporary"] = f"{payload['temporary']}\n{suffix}".strip() if payload.get("temporary", "").strip() else suffix
    return payload
