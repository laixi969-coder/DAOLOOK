"""Version-bound, local Xiaohongshu publication artwork; all copy comes from the approved draft."""
import base64
import hashlib
import html
import json
import re

from . import covers, draft_sources, editing


PHOTO_MARKER = "daolook-pack-photo"


def inner_svg(text, index):
    backgrounds = ("#f4efdf", "#253e37")
    foregrounds = ("#282b24", "#fff8e8")
    bg, fg = backgrounds[index % 2], foregrounds[index % 2]
    lines = covers.wrap(text, 23)
    font_size = 40
    if len(lines) > 8:
        lines = covers.wrap(text, 32)
        font_size = 29
    if len(lines) > 16:
        lines = covers.wrap(" ".join(text.split()), 32)
        if len(lines) > 16:
            raise editing.EditError("封面文案超过图片容量，请调整封面文字并确认新版")
    line_height = int(font_size * 1.55)
    block_height = 60 + line_height * len(lines) if lines else 0
    photo_top = 66 if index % 2 == 0 else 66 + block_height
    photo_height = 1308 - block_height
    text_y = (photo_top + photo_height + 58 if index % 2 == 0 else 110)
    words = "".join(f'<text x="76" y="{text_y + i * line_height}">{html.escape(line)}</text>'
                    for i, line in enumerate(lines))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="1080" height="1440" viewBox="0 0 1080 1440"><rect width="1080" height="1440" fill="{bg}"/>'
            f'<image x="66" y="{photo_top}" width="948" height="{photo_height}" preserveAspectRatio="xMidYMid slice" '
            f'xlink:href="{PHOTO_MARKER}"/><g fill="{fg}" font-family="PingFang SC,Microsoft YaHei,sans-serif" '
            f'font-size="{font_size}" font-weight="600">{words}</g></svg>')


# A restriction may follow the price in its own sentence or on the next line.
RESTRICTION = re.compile(r"^(?:[（(]|[但且仅限]|适用|不适用|不含|不叠加|不可|不支持|除外|有效|截至|截止|到期|"
                         r"须|需凭|需满|限购|每人限|每单限|售完|数量有限|活动期间|(?:会员|新客|首单|到店|线下|线上)(?:专享|有效|限定)|"
                         r"(?:该|本次|此)(?:价格|活动|优惠))")
OFFER = re.compile(r"[¥￥]|[0-9零一二三四五六七八九十]\s*(?:元|折|件|份|减)|售价|优惠|活动|购买|下单|试饮|开放")


def info_pages(data):
    def group(parts, separator):
        blocks = []
        prefix = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if RESTRICTION.match(part):
                prefix.append(part)
                continue
            if prefix and blocks:
                # When the next sentence also looks like an offer, keep both
                # neighbours with the condition instead of guessing its owner.
                join_next = not OFFER.search(blocks[-1]) and OFFER.search(part)
                blocks[-1] += separator + separator.join(prefix)
                prefix = []
                if join_next:
                    blocks[-1] += separator + part
                    continue
            blocks.append(separator.join([*prefix, part]))
            prefix = []
        if prefix:
            if blocks:
                blocks[-1] += separator + separator.join(prefix)
            else:
                blocks.append(separator.join(prefix))
        return blocks

    def fits(part):
        return 0 < len(part) <= 1000 and len(covers.wrap(part, 32)) <= 16

    def different(part, picked):
        # A sentence already printed as part of another page is not a second point.
        return all(part not in old and old not in part for old in picked)

    paragraphs = group(data.get("body", "").splitlines(), "\n")
    picked = []
    for part in paragraphs:
        if fits(part) and different(part, picked):
            picked.append(part)
    if len(picked) >= 2:
        return picked[:2]
    # One-paragraph drafts are common. Only cut at sentence boundaries. Keep
    # adjoining qualifier sentences together, along with their punctuation.
    sentences = []
    for p in paragraphs:
        sentences.extend(group(re.split(r"(?<=[。！？!?])\s*|(?<=\.)\s+(?=[A-Z])", p), ""))
    if len(sentences) > len(paragraphs):
        split = []
        for part in sentences:
            if fits(part) and different(part, split):
                split.append(part)
                if len(split) == 2:
                    return split
        if not picked:
            picked = split
    layout = data.get("comment_layout") or {}
    alternatives = [data.get("cta"), data.get("hook"), (layout.get("pinned") or {}).get("text"),
                    *(layout.get("knowledge") or [])]
    for part in alternatives:
        if isinstance(part, str) and fits(part.strip()) and different(part.strip(), picked):
            picked.append(part.strip())
            if len(picked) == 2:
                return picked
    return []


def layouts(data, pages):
    title = (data.get("cover_text") or "").strip() or (data.get("title") or "").strip()
    if not title:
        raise editing.EditError("请补充封面文字或标题并确认新版")
    if len(title) <= 36 and len(covers.wrap(title, 10)) <= 4 and title.strip():
        prepared = covers.prepare(data, {"title": title, "style": "brand"}, [])
        rendered = covers.render({**prepared, "photo": PHOTO_MARKER})
        cover = base64.b64decode(rendered["url"].partition(",")[2]).decode()
    else:
        cover = inner_svg(title, 0)
    return [cover, inner_svg(pages[0], 0), inner_svg(pages[1], 1)]


def manifest(c, project, ident, revision, photo, expected):
    row = editing.creation(c, ident, project)
    if row["platform"] != "xhs":
        raise editing.EditError("图文发布包适用于小红书稿件")
    ready = c.execute("SELECT source_digest FROM creation_readiness WHERE creation_id=? AND revision=?", (ident, revision)).fetchone()
    if revision != editing.revision(c, ident) or not ready:
        raise editing.EditError("请打开并确认当前版本后再使用图文发布包", 409)
    digest = draft_sources.signature(c, ident, project, row["task_id"])
    if ready["source_digest"] != digest:
        raise editing.EditError("所选事实资料已变化，请刷新稿件、核对并重新确认", 409)
    data = json.loads(row["data"])
    choices = [dict(a) for a in c.execute(
        "SELECT id,name FROM assets WHERE project_id=? AND kind='图片' ORDER BY created_at DESC,id", (project,))]
    available = {a["id"] for a in choices}
    if photo and photo not in available:
        raise editing.EditError("项目照片已变更，请重新选择", 409)
    selected = [photo] if photo else list(dict.fromkeys(i for i in (data.get("image_asset_ids") or []) if i in available))[:3]
    if not selected:
        if expected:
            raise editing.EditError("所选照片已失效，请重新预览", 409)
        return {"choices": choices, "pages": []}
    paragraphs = info_pages(data)
    if not paragraphs:
        if expected:
            raise editing.EditError("稿件已变更，请重新预览", 409)
        return {"choices": choices, "pages": [], "needs_edit": True,
                "notice": "当前稿件提取不到两段独立的内页文字。可补写两段完整信息，保存并确认新版后再生成。"}
    images = {}
    for aid in selected:
        asset = c.execute("SELECT * FROM assets WHERE id=? AND project_id=? AND kind='图片'", (aid, project)).fetchone()
        if not asset:
            raise editing.EditError("项目照片已变更，请重新预览", 409)
        # Reuse the same size, format and signature validation as the cover studio.
        images[aid] = covers.prepare({"title": "照片"}, {"asset_id": aid}, [asset])["photo"]
    state = hashlib.sha256(json.dumps([project, ident, revision, digest, row["data"], list(images.items())],
                                      ensure_ascii=False).encode()).hexdigest()
    if expected:
        if expected != state:
            raise editing.EditError("稿件或照片已变更，请重新预览", 409)
        return {"ok": True}
    return {"choices": choices, "state": state, "images": images, "demo": bool(data.get("demo")),
            "copy": {k: data.get(k) for k in ("title", "body", "tags")},
            "pages": [{"svg": svg, "photo": selected[index % len(selected)]}
                      for index, svg in enumerate(layouts(data, paragraphs))]}
