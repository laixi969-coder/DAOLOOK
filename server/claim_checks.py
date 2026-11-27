"""Conservative checks for concrete commercial claims in domestic public copy."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import os
import re
import unicodedata
from zoneinfo import ZoneInfo

LABELS = {"price": "价格", "spec": "规格", "promotion": "优惠", "validity": "有效期", "channel": "购买入口"}
NUM = r"(?:\d{1,3}(?:,\d{3}){1,2}|\d{1,9})(?:\.\d{1,4})?"
RULES = {
    "promotion": re.compile(rf"满\s*({NUM})\s*元?\s*(?:立|可)?减\s*({NUM})\s*元?|({NUM})\s*折|买\s*([一二三四五六七八九十\d]+)\s*送\s*([一二三四五六七八九十\d]+)|(?:立减|直降|优惠券|优惠)\s*({NUM})\s*元"),
    "price": re.compile(rf"(?:¥|RMB\s*)\s*({NUM})(?:\s*元)?|(?<![\d.])({NUM})\s*(?:元|块钱)|(?:售价|现价|到手价|原价|会员价|券后价|定价)\s*[:：]?\s*({NUM})(?![\d.])", re.I),
    "spec": re.compile(rf"(?<![\d.])({NUM})\s*(毫升|千克|公斤|毫克|克|升|ml|kg|mg|g|l|包|瓶|袋|片|粒|盒|支)(?![a-z])|(?:含有?|添加|无|零|0)\s*(酒精|蔗糖|糖|香精|色素|防腐剂|乳糖|咖啡因|麸质|牛奶|花生)", re.I),
    "validity": re.compile(r"(?:(\d{4})\s*[-/.年]\s*)?(\d{1,2})\s*[-/.月]\s*(\d{1,2})(?:日|号)?|(?:有效期|保质期)\s*[:：为]?\s*(\d+)\s*(天|日|个月|月|年)"),
    "channel": re.compile(r"https?://[^\s，。；！？、<>（）()「」【】]+|淘宝|天猫|京东|拼多多|微信小程序|小程序|官网|小黄车|购物车|抖音小店|小红书店铺|门店|到店|微信|私信|主页链接|商品链接|团购链接", re.I),
}
EXCLUDED_ASSET_KINDS = {"图片", "禁用词"}
STRONG = re.compile(r"[。！？；;\r\n]+(?![。！？；;\r\n]|[ \t]*(?:仅限|仅适用于|截止|截至|有效至|(?:该|本次|此)?(?:活动|优惠)(?:有效|截止|截至|仅限|仅适用于)))")
SOFT = re.compile(r"[，、]+|,(?!\d{3}(?!\d))|(?:和|与|而)(?=(?:[A-Za-z]款|[大中小][份杯号]|非?会员|原价|现价|券后|到店价))")
CHANNEL_ACTION = re.compile(r"下单|购买|买到|订购|拍下|预约|订货|团购|选购|入口|购买渠道|销售渠道|仅限|仅售|付款|发售|有售|有卖|上架")
PERIOD = re.compile(r"有效|保质|到期|截止|截至|起至|限时|活动|促销|优惠|券|结束|至")
NEGATIVE = re.compile(r"(?:不支持|不接受|不提供|不能在?|不可在?|无需|无法|没有|不在|不含|不|不是|并非|不走|未|禁止|严禁|不得|请勿|不要)(?:宣称|宣传|标注|添加|写作|写成|写为|写)?\s*$")
EXPIRED = re.compile(r"已(?:过期|到期|结束|失效)|已下架")
CONDITIONS = {
    "非会员": r"非会员|普通顾客", "会员": r"(?<!非)会员|VIP",
    "新客": r"新客|新用户|首单|新人", "老客": r"老客|老用户",
    "到店": r"到店|门店|堂食", "线上": r"线上|网上|网购",
    "原价": r"原价|划线价|标价", "券后": r"券后|用券|领券|折后券",
    "周末": r"周末|双休日", "工作日": r"工作日", "首月": r"首月|第一个月",
    "起价": rf"{NUM}\s*(?:元|块)起|起售价|起步价",
    "估算": rf"(?:约|大概|大约){NUM}(?:元|块)|{NUM}(?:元|块)左右|参考价",
    "每包": r"每包|一包|/包", "每盒": r"每盒|一盒|/盒", "每瓶": r"每瓶|一瓶|/瓶",
}
CONDITIONS = {k: re.compile(v, re.I) for k, v in CONDITIONS.items()}
WAIVED_PREFIX = re.compile(r"(?:不限于?|不要求|不需要|不必|无需|无须|不用|无论是否|不)(?:先|是|为|成为|注册|开通|办理|使用|到)?$")
WAIVED_SUFFIX = re.compile(r"(?:资格|身份)?(?:均)?不限")
CALENDAR_DATE = re.compile(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})")
VARIANT = re.compile(r"[a-z0-9]{1,24}款|[款型]号[a-z0-9]{1,24}|(?:商品|产品|套餐|型号|款式)[a-z0-9]{1,24}|[大中小][份杯号]|标准版|升级版|基础版|豪华版|家庭装|体验装|正装|试用装", re.I)
CHANNEL_NAMES = {"门店": "到店", "小黄车": "购物车", "微信小程序": "小程序"}
UNITS = {"毫升": ("ml", 1), "升": ("ml", 1000), "l": ("ml", 1000),
         "克": ("g", 1), "千克": ("g", 1000), "公斤": ("g", 1000), "kg": ("g", 1000),
         "毫克": ("g", Decimal(".001")), "mg": ("g", Decimal(".001"))}
GENERIC_LABELS = {"产品", "产品信息", "品牌资料", "临时资料", "说明", "价目表", "本品", "商品", "单品", "套餐", "活动价", "价格为", "本款", "今日", "仅售", "单价", "低至", "最低", "合计", "总计", "总价", "一共"}
BARE_PRICE = re.compile(rf"[\u4e00-\u9fffA-Za-z]{{2,12}}(?:¥{NUM}|{NUM}(?:元|块钱))(?:一[杯份盒包])?")
LIMIT = re.compile(r"(?:仅限于?|仅适用于|只适用于)([^，,。！？、；;!?\n]*)")
GROUP_SIZE = re.compile(r"([一二两三四五六七八九十\d]+)人(?:团购|拼团|成团|团)")
CN_DIGITS = str.maketrans("一二两三四五六七八九", "1223456789")


def compact(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).lower()


def normalize_groups(text):
    def group_name(match):
        number = match[1].translate(CN_DIGITS)
        if number.count("十") == 1:
            tens, ones = number.split("十")
            number = (tens or "1") + (ones or "0")
        return number + "人团购"
    return GROUP_SIZE.sub(group_name, text)


def explicit_limits(text):
    """Keep unfamiliar restrictions verbatim. Known synonyms are checked as conditions."""
    limits = set()
    for match in LIMIT.finditer(text):
        term = re.split(rf"(?:优惠价|售价|价格|现价|可享|享受|享有)|(?=¥|{NUM}元)", match[1], maxsplit=1)[0]
        remainder = term
        for regex in CONDITIONS.values():
            remainder = regex.sub("", remainder)
        remainder = re.sub(r"用户|顾客|客户|购买|使用|下单|适用|参与|专享|享用|及|和|与|的", "", remainder)
        if remainder:
            limits.add(normalize_groups(term))
    return limits


def mentions_limit(text, term):
    # “13人团购” must not supply evidence for a “3人团购” restriction.
    if term[0].isdigit():
        return re.search(r"(?<!\d)" + re.escape(term), text) is not None
    return term in text


def condition_labels(text):
    labels = set()
    for name, pattern in CONDITIONS.items():
        for match in pattern.finditer(text):
            waived = WAIVED_PREFIX.search(text[max(0,match.start()-12):match.start()]) or WAIVED_SUFFIX.match(text[match.end():])
            labels.add("免除" + name if waived else name)
    return labels


def date_role(text, start, end):
    before = text[max(0,start-12):start]
    after = text[end:end+10]
    if re.search(r"(?:截至|截止(?:到|至|日期)?|有效至|到期日?|活动至|优惠至|[至到~～])[:：]?\s*$", before) or re.match(r"(?:日|号)?\s*(?:到期|截止|结束)", after):
        return "end"
    if re.search(r"(?:自|从|起始日期|开始日期|生效日)[:：]?\s*$", before) or re.match(r"(?:日|号)?\s*(?:开始|起|开售|生效|[至到~～])", after):
        return "start"
    return ""


@dataclass
class Claim:
    kind: str
    key: object
    literal: str
    sentence: str
    conditions: set
    subjects: set
    associated: set
    limits: set
    negative: bool
    asset_id: str = ""


def value_key(kind, match):
    groups = tuple(v.replace(",", "") if v else v for v in match.groups())
    if kind == "price":
        return Decimal(next(value for value in groups if value))
    if kind == "spec":
        if groups[2]:
            return "ingredient", groups[2]
        unit = groups[1].lower()
        unit, scale = UNITS.get(unit, (unit, 1))
        return unit, Decimal(groups[0]) * scale
    if kind == "promotion":
        return tuple(Decimal(g) if g and g.replace(".", "").isdigit() else g for g in groups)
    if kind == "validity":
        year, month, day, length, unit = groups
        if length:
            return int(length), {"日": "天", "个月": "月"}.get(unit, unit)
        try:
            date(int(year or 2000), int(month), int(day))
        except ValueError:
            return None
        return (int(year) if year else None, int(month), int(day), date_role(match.string, *match.span()))
    channel = match[0]
    return CHANNEL_NAMES.get(channel, channel)


def recognized(part):
    """Ignore incidental platform mentions, ordinary dates, and recipe quantities."""
    text = unicodedata.normalize("NFKC", part)
    occupied = bytearray(len(text))
    has_route = bool(CHANNEL_ACTION.search(text))
    has_period = bool(PERIOD.search(text))
    found = []
    for kind, pattern in RULES.items():
        for match in pattern.finditer(text):
            if any(occupied[match.start():match.end()]):
                continue
            if kind == "channel" and not (match[0].startswith(("http://", "https://")) or has_route):
                continue
            if kind == "validity" and not has_period:
                continue
            prefix = text[max(0, match.start()-16):match.start()]
            if kind == "price" and re.search(r"预算|如果|假设|比如说|举例", prefix[-12:]):
                continue
            if kind == "spec" and re.search(r"(?:加入|取用|倒入|放入|准备|量取)\s*$", prefix):
                continue
            key = value_key(kind, match)
            if key is not None:
                occupied[match.start():match.end()] = b"\1" * len(match[0])
                negative = NEGATIVE.search(prefix) or (kind == "spec" and match[3] and match[0].startswith(("无", "零", "0"))) or re.match(r"(?:暂不|不)(?:支持|可|能)(?:下单|购买|预约)", text[match.end():])
                found.append((kind, key, match[0], bool(negative)))
    return found


def subject_label(text):
    """A named product heading or a short product immediately before its price/spec."""
    label = re.split(r"[:：]|(?:每[盒包瓶袋]|售价|价格|定价|原价|会员价|到手价|现价|券后|净含量|容量|规格)|(?=\d|¥)", text, maxsplit=1)[0]
    label = compact(label).strip("「」【】“”•*-")
    if not re.fullmatch(r"[\w\u4e00-\u9fff]{2,16}", label):
        return ""
    if label in GENERIC_LABELS or NEGATIVE.search(label) or re.search(r"这|本次|现在|活动|优惠|到店|到手|会员|只需|只要|一共|卖|只卖|每|建议|目前|可选", label):
        return ""
    return label


def extract(text, asset_id="", name=""):
    for sentence in STRONG.split(text):
        bounds = [0, *(pos for m in SOFT.finditer(sentence) for pos in m.span()), len(sentence)]
        offsets = [(a, b) for a, b in zip(bounds[::2], bounds[1::2]) if sentence[a:b].strip()]
        parts = [sentence[a:b].strip() for a, b in offsets]
        parsed = [recognized(part) for part in parts]
        counts = defaultdict(int)
        for items in parsed:
            for kind in {item[0] for item in items}:
                counts[kind] += 1
        for index, facts in enumerate(parsed):
            grouped = defaultdict(list)
            for kind, key, literal, negative in facts:
                grouped[kind].append((key, literal, negative))
            for kind, values in grouped.items():
                # Two neighboring prices must keep their own products and qualifiers.
                if counts[kind] == 1:
                    first, last = 0, len(parts) - 1
                    scope = sentence.strip()
                else:
                    first = index
                    last = index
                    while first > 0 and not parsed[first - 1]:
                        first -= 1
                    while last + 1 < len(parts) and not parsed[last + 1]:
                        last += 1
                    scope = sentence[offsets[first][0]:offsets[last][1]].strip()
                normalized = compact(scope)
                conditions = condition_labels(normalized)
                limits = explicit_limits(normalized)
                pack_units = ("每包", "每盒", "每瓶")
                conditions.difference_update(pack_units)
                if kind in ("price", "spec"):
                    local = compact(parts[index])
                    conditions.update(unit for unit in pack_units if CONDITIONS[unit].search(local))
                if kind in ("price", "promotion"):
                    conditions.update(re.findall(r"满\d+(?:\.\d+)?(?=元?(?:可享|可用|可打|享|打|起用))", normalized))
                subjects = set(VARIANT.findall(normalized))
                # Bind an advertised price to the size appearing with it. When
                # a brief lists 250ml/99 and 500ml/199, both pairs are valid.
                counterpart = {"price": "spec", "spec": "price"}.get(kind)
                associated = {f[1] for group in parsed[first:last + 1] for f in group if f[0] == counterpart and not f[3]}
                if asset_id:
                    for label in (subject_label(parts[index]), subject_label(name)):
                        if label:
                            subjects.add(label)
                for key, literal, negative in values:
                    yield Claim(kind, key, literal, scope, conditions, subjects, associated, limits, negative, asset_id)


def excerpt(text, literal, limit=160):
    if len(text) <= limit:
        return text
    at = max(0, unicodedata.normalize("NFKC", text).find(literal))
    start = max(0, min(at - 40, len(text) - limit))
    return text[start:start + limit]


def dated_bounds(claim):
    text = compact(claim.sentence)
    for match in CALENDAR_DATE.finditer(text):
        try:
            yield date_role(text, *match.span()), date(*(int(v) for v in match.groups()))
        except ValueError:
            continue


def availability_issue(source, claim, today):
    bounds = set(dated_bounds(source))
    if EXPIRED.search(source.sentence) or any(role == "end" and day < today for role,day in bounds):
        if not EXPIRED.search(claim.sentence):
            return "资料中的活动或购买条件已到期"
    future = {b for b in bounds if b[0] == "start" and b[1] > today}
    if future and not future.issubset(dated_bounds(claim)):
        return "资料中的活动尚未开始，请注明开始日期"
    return ""


def check_claims(text, assets, today=None):
    if today is None:
        today = datetime.now(ZoneInfo(os.environ.get("DAOLOOK_DISPLAY_TIMEZONE", "Asia/Shanghai"))).date()
    sources = defaultdict(list)
    names = set()
    for asset in assets:
        if asset.get("kind") in EXCLUDED_ASSET_KINDS or not asset.get("id") or not isinstance(asset.get("content"), str):
            continue
        for source in extract(asset["content"], asset["id"], asset.get("name", "")):
            sources[source.kind].append(source)
            names.update(source.subjects)
    checks = []
    issues = []
    seen = set()
    for claim in extract(text):
        sentence = excerpt(claim.sentence, claim.literal)
        ident = (claim.kind, claim.key, sentence, claim.negative)
        if ident in seen:
            continue
        seen.add(ident)
        if len(checks) >= 60:
            issues.append("具体业务陈述较多，请分段核对剩余内容")
            break
        folded = compact(claim.sentence)
        named = {n for n in names if n in folded} | claim.subjects
        pool = sources[claim.kind]
        named_form = re.search(r"售价|每[包盒瓶]|净含量", folded) or (claim.kind == "price" and BARE_PRICE.fullmatch(folded))
        if not named and named_form and any(s.subjects for s in pool):
            explicit = subject_label(claim.sentence)
            if explicit:
                named.add(explicit)
        scoped = [s for s in pool if not named or named <= s.subjects or
                  all(n in compact(s.sentence) for n in named)]
        if claim.associated and any(s.associated for s in scoped):
            scoped = [s for s in scoped if claim.associated <= s.associated]
        normalized_copy = normalize_groups(folded)
        def has_limits(source):
            # An explicit restriction in the copy can narrow a claim. Broader
            # claims cannot reuse a price offered only under that restriction.
            if claim.limits and not all(mentions_limit(normalize_groups(compact(source.sentence)), term) for term in claim.limits):
                return False
            for term in source.limits - claim.limits:
                if not mentions_limit(normalized_copy, term) or re.search(r"不限|全场|无须|无需|不用|不必|不需要|不支持", normalized_copy):
                    return False
            return True
        matched = [s for s in scoped if s.key == claim.key and s.negative == claim.negative and s.conditions == claim.conditions and has_limits(s)]
        reason = ""
        source = None
        if matched:
            source = next((s for s in matched if not availability_issue(s, claim, today)), matched[0])
            # A second incompatible value for the same product, condition, and
            # measurement calls for human review. Different products may coexist.
            for other in scoped:
                if not has_limits(other) or other.conditions != claim.conditions or (other.key == claim.key and other.negative == claim.negative):
                    continue
                if availability_issue(other, claim, today):
                    continue
                if other.key == claim.key and other.negative != claim.negative:
                    reason = "资料中同时存在肯定与否定说法"
                    source = other
                    break
                if other.key == claim.key or other.negative != claim.negative:
                    continue
                if claim.kind == "price" or (claim.kind == "spec" and source.key[0] != "ingredient" and source.key[0] == other.key[0]):
                    reason = "所选资料有多个数值，请注明对应商品或适用条件"
                    source = other
                    break
            if not reason:
                reason = availability_issue(source, claim, today)
        else:
            source = next((s for s in scoped if s.key == claim.key), next(iter(scoped), None))
            if source and source.negative != claim.negative:
                reason = "资料对该说法的肯定或否定与稿件不同"
            elif source and source.key == claim.key and (source.conditions != claim.conditions or not has_limits(source)):
                reason = "稿件的适用条件与资料不一致"
            else:
                reason = "所选文字资料缺少对应依据"
        check = {"kind": claim.kind, "value": claim.literal, "sentence": sentence,
                 "status": "review" if reason else "matched", "reason": reason}
        if source:
            check["source"] = {"asset_id": source.asset_id, "quote": excerpt(source.sentence, source.literal)}
        if reason:
            issues.append(f"{LABELS[claim.kind]}待核对「{sentence}」。{reason}。")
        checks.append(check)
    return checks, issues
