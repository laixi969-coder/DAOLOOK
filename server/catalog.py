"""Transparent discovery metadata; keyword labels are suggestions, not platform labels."""

INDUSTRIES = {
    "美食饮品": ("咖啡", "早餐", "美食", "烘焙", "奶茶", "食谱"),
    "家居好物": ("家居", "出租屋", "收纳", "家具", "装修"),
    "旅行记录": ("旅行", "旅游", "周末", "city walk", "徒步", "酒店"),
    "个人成长": ("自律", "成长", "学习", "读书", "效率"),
    "美妆护肤": ("护肤", "美妆", "防晒", "口红", "化妆"),
    "穿搭时尚": ("穿搭", "服饰", "时尚", "搭配"),
    "数码科技": ("数码", "手机", "电脑", "相机", "软件"),
    "职场商业": ("职场", "面试", "创业", "营销", "运营"),
    "生活方式": ("生活", "日常", "日子"),
}
FORMATS = {
    "测评对比": ("测评", "对比", "评测", "实测"),
    "教程方法": ("教程", "方法", "步骤", "如何", "技巧", "攻略"),
    "清单推荐": ("清单", "推荐", "这 3 件", "这3件", "件小事", "必备"),
    "观点表达": ("别再", "停止", "为什么", "我认为"),
    "故事记录": ("记录", "日记", "经历", "周末", "改造"),
}


def classify(content):
    title = str(content.get("title", "")).lower()
    body = str(content.get("body", "")).lower()

    def match(rules):
        results = []
        for label, words in rules.items():
            hits = [w for w in words if w in title or w in body]
            score = sum(3 if w in title else 1 for w in hits)
            if score:
                results.append((score, label, hits))
        if not results:
            return None, []
        results.sort(key=lambda r: -r[0])
        if len(results) > 1 and results[0][0] == results[1][0]:
            return None, []
        return results[0][1], results[0][2]

    industry, hits = match(INDUSTRIES)
    form, form_hits = match(FORMATS)
    # Preserve explicitly marked demo seed industries; never claim they are inferred.
    seeded = content.get("demo") and content.get("category")
    return {
        "industry": seeded or industry or "待分类",
        "format": form or "待判断",
        "basis": (
            "演示样本预设行业"
            if seeded
            else ("行业关键词：" + "、".join(hits) if industry else "未匹配到明确行业")
        )
        + "；"
        + ("形式关键词：" + "、".join(form_hits) if form else "表达形式待判断"),
        "method": "keyword-v1",
        "provisional": True,
    }


def evidence(content, ranking):
    if content.get("demo"):
        return ["演示样本：标题、作者与互动数据为预置示例，不是平台推荐。"]
    origin = content.get("origin", {})
    entry = origin.get("entry", "")
    lines = [
        {
            "single": "来自你提交的内容链接。",
            "batch": "来自你批量提交的内容链接。",
            "creator": "来自指定博主的接口结果，未按爆款筛选。",
            "keyword": "来自关键词搜索的接口结果，未按爆款筛选。",
        }.get(entry, "来自本项目已拆解的参考内容。")
    ]
    if entry == "keyword" and origin.get("query"):
        lines.append("搜索词：" + str(origin["query"])[:100])
    labels = {
        "engagement": "加权互动",
        "efficiency": "粉丝效率",
        "account_lift": "账号基线",
        "category_lift": "同类基线",
        "freshness": "时效",
        "reusability": "可迁移性",
    }
    used = [labels[k] for k in ranking["components"] if k in labels]
    lines.append(
        "排序可用依据：" + "、".join(used)
        if used
        else "互动等数据不足，暂不能计算相对表现。"
    )
    missing = [
        label
        for key, label in (
            ("account_median", "账号历史基线"),
            ("category_median", "同类内容基线"),
            ("age_days", "发布时间"),
        )
        if content.get(key) is None
    ]
    if missing:
        lines.append("缺少：" + "、".join(missing) + "。")
    if ranking.get("score") is not None:
        lines.append(
            f"当前相对评分：{ranking['score']} / 100，仅基于已提供的 {len(used)} 项指标。"
        )
        lines.append(
            "互动按点赞 + 2×收藏 + 3×评论计算，再按管理员配置权重合成；缺失指标不参与。"
        )
    lines.append("相对评分尚未校准，不代表爆款概率或平台推荐。")
    return lines
