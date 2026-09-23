"""DAOLOOK original, deterministic cover planning and typography. No third-party prompts."""

import base64
import html
import re
import unicodedata

VERSION = "daolook-cover-1.1"
STYLES = [
    {
        "id": "brand",
        "name": "品牌杂志",
        "reason": "用留白和真实场景突出品牌气质，适合叙事与生活方式。",
    },
    {
        "id": "method",
        "name": "方法清单",
        "reason": "让核心方法和可核实的信息一眼可读，适合教程与测评。",
    },
    {
        "id": "portrait",
        "name": "真人冲击",
        "reason": "让真实照片成为视觉中心，适合人物表达与体验分享。",
    },
]
LEGACY = {"极简文字": "method", "生活杂志": "brand", "大胆撞色": "portrait"}


def plan(output):
    title = str(
        output.get("cover_text") or output.get("title") or "写下你的封面标题"
    ).strip()
    text = title + str(output.get("body", ""))
    recommended = (
        "method" if re.search(r"教程|步骤|方法|清单|测评|技巧", text) else "brand"
    )
    hook = (
        "数字"
        if re.search(r"\d", title)
        else "问题"
        if re.search(r"[？?]|如何|为什么", title)
        else "主题"
    )
    return {
        "styles": STYLES,
        "recommended": recommended,
        "hook": hook,
        "reason": "根据稿件中的方法类关键词推荐。"
        if recommended == "method"
        else "优先突出稿件主题与叙事气质。",
        "brief": {
            "style": recommended,
            "title": title,
            "subtitle": "",
            "points": [],
            "brand": "",
            "asset_id": "",
            "crop": "center",
        },
        "version": VERSION,
        "notice": "标题沿用稿件；请核实数字和效果承诺。方向建议不代表流量预测。",
    }


def units(text):
    return sum(1 if unicodedata.east_asian_width(c) in "WF" else 0.6 for c in text)


def wrap(text, capacity):
    lines, line = [], ""
    for c in text:
        if c == "\n" or (line and units(line + c) > capacity):
            lines.append(line)
            line = "" if c == "\n" else c
        else:
            line += c
    if line:
        lines.append(line)
    return lines


def prepare(output, requested, assets):
    if not isinstance(requested, dict):
        raise ValueError("封面参数格式不正确")
    brief = plan(output)["brief"]
    brief.update({k: requested[k] for k in brief if k in requested})
    if not isinstance(brief["style"], str) or brief["style"] not in {
        s["id"] for s in STYLES
    }:
        raise ValueError("请选择有效的封面方向")
    for key, maximum in [("title", 36), ("subtitle", 48), ("brand", 20)]:
        if not isinstance(brief[key], str):
            raise ValueError("封面文案必须是文字")
        brief[key] = brief[key].strip()
        if len(brief[key]) > maximum or any(
            ord(c) < 32 and c != "\n" for c in brief[key]
        ):
            raise ValueError(
                f"{ {'title': '标题', 'subtitle': '副标题', 'brand': '品牌署名'}[key] }最多 {maximum} 字，请精简后预览"
            )
    if not brief["title"]:
        raise ValueError("请填写封面标题")
    if brief["crop"] not in ("top", "center", "bottom"):
        raise ValueError("图片裁切位置不正确")
    points = brief["points"]
    if (
        not isinstance(points, list)
        or len(points) > 3
        or any(not isinstance(p, str) or len(p) > 22 or "\n" in p for p in points)
    ):
        raise ValueError("清单最多 3 项，每项最多 22 字且不能换行")
    brief["points"] = [p.strip() for p in points if p.strip()]
    if len(wrap(brief["title"], 10)) > 4 or len(wrap(brief["subtitle"], 24)) > 2:
        raise ValueError("文案换行过多，请减少手动换行")
    asset = next(
        (a for a in assets if a["id"] == brief["asset_id"] and a["kind"] == "图片"),
        None,
    )
    if brief["asset_id"] and not asset:
        raise ValueError("所选图片不存在，请重新选择项目图片")
    photo = asset["content"] if asset else ""
    if photo:
        match = re.fullmatch(
            r"data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)", photo
        )
        if not match or len(photo) > 3000000:
            raise ValueError("请使用不超过 2 MB 的 PNG、JPEG 或 WebP 图片")
        try:
            raw = base64.b64decode(match[2], validate=True)
        except ValueError:
            raise ValueError("图片编码无效")
        valid = (
            (match[1] == "png" and raw.startswith(b"\x89PNG\r\n\x1a\n"))
            or (match[1] == "jpeg" and raw.startswith(b"\xff\xd8\xff"))
            or (match[1] == "webp" and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP")
        )
        if not valid:
            raise ValueError("图片格式与内容不一致")
    return {
        "brief": brief,
        "photo": photo,
        "asset_name": asset["name"] if asset else "",
        "demo": bool(output.get("demo")),
    }


def render(prepared, final=False):
    b = prepared["brief"]
    photo = prepared["photo"]
    style = b["style"]
    warnings = ["发布前请人工核对文字、事实与图片授权。"]
    if b["points"] and style != "method":
        warnings.append("清单内容仅在方法清单方向显示。")
    if style == "portrait" and not photo:
        if final:
            raise ValueError("真人方向需要选择一张真实照片，请先在项目资料上传图片")
        warnings.append("真人方向尚未选图，生成前请补充真实照片。")
    bg, fg, accent = {
        "brand": ("#f3eee5", "#302d28", "#aa543d"),
        "method": ("#eff2df", "#20281d", "#d4fa47"),
        "portrait": ("#fdffa7", "#22251d", "#f5a6bf"),
    }[style]
    esc = html.escape
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1080" height="1440" viewBox="0 0 1080 1440"><rect width="1080" height="1440" fill="{bg}"/>',
        f'<g fill="{fg}" font-family="PingFang SC,Microsoft YaHei,Noto Sans CJK SC,sans-serif">',
    ]

    def rect(x, y, w, h, fill, rx=0):
        parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"/>'
        )

    def text(content, x, y, size, weight=400, fill=fg):
        parts.append(
            f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}">{esc(content)}</text>'
        )

    def image(x, y, w, h):
        if photo:
            align = {"top": "xMidYMin", "center": "xMidYMid", "bottom": "xMidYMax"}[
                b["crop"]
            ]
            parts.append(
                f'<svg x="{x}" y="{y}" width="{w}" height="{h}" viewBox="0 0 {w} {h}" overflow="hidden"><image width="{w}" height="{h}" xlink:href="{esc(photo, quote=True)}" preserveAspectRatio="{align} slice"/></svg>'
            )
        else:
            rect(x, y, w, h, accent)
            parts.append(
                f'<circle cx="{x + w * 0.72}" cy="{y + h * 0.48}" r="{min(w, h) * 0.32}" fill="{bg}" opacity=".6"/>'
            )
            if style == "portrait":
                text("选择你的真实照片", x + 56, y + h / 2, 40)

    text(b["brand"], 76, 100, 28, 600)
    rect(76, 134, 928, 2, fg)
    lines = wrap(b["title"], 10)
    size = 86 if style == "brand" else 90
    for i, line in enumerate(lines):
        text(line, 76, 264 + i * 112, size, 700)
    subtitle_y = 264 + len(lines) * 112
    for i, line in enumerate(wrap(b["subtitle"], 24)):
        text(line, 78, subtitle_y + i * 44, 34)
    photo_y = max(490, subtitle_y + (100 if b["subtitle"] else 25))
    if style == "brand":
        image(76, photo_y, 928, 1308 - photo_y)
        text("—", 76, 1380, 28, 500, accent)
    elif style == "method":
        if b["points"]:
            if photo:
                image(76, 818, 320, 490)
            offset = 340 if photo else 0
            for i, point in enumerate(b["points"]):
                y = 866 + i * 154
                rect(76 + offset, y - 48, 70, 70, accent, 16)
                text(str(i + 1).zfill(2), 87 + offset, y, 34, 700)
                for j, line in enumerate(wrap(point, 14 if photo else 21)):
                    text(line, 175 + offset, y + j * 40, 34, 600)
        else:
            image(76, photo_y, 928, 1308 - photo_y)
    else:
        image(76, photo_y, 928, 1308 - photo_y)
        rect(76, 1316, 928, 12, fg)
    parts.append("</g></svg>")
    return {
        "url": "data:image/svg+xml;base64,"
        + base64.b64encode("".join(parts).encode()).decode(),
        "mime": "image/svg+xml",
        "width": 1080,
        "height": 1440,
        "demo": prepared["demo"],
        "renderer": VERSION,
        "model": "deterministic-layout",
        "brief": b,
        "asset_name": prepared["asset_name"],
        "style_origin": "DAOLOOK 原创排版",
        "validation": {
            "warnings": warnings,
            "ready": style != "portrait" or bool(photo),
            "checks": [
                "1080 × 1440 · 3:4",
                "标题安全区与自动换行已检查",
                "中文使用字体排版",
            ],
        },
    }
