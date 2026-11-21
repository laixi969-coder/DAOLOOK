"""Public source references and conservative caption matches for shootable shorts."""
import json
import re
from pathlib import Path


def _load_cases():
    path = Path(__file__).parent / 'resources/hiccai-pop/visual-references.json'
    cases = {}
    for item in json.loads(path.read_text()):
        video = {k: item[k] for k in ('url', 'title', 'publisher')}
        cases[item['id']] = {
            **item, 'platform': 'instagram', 'source_kind': 'visual_case',
            'reference_video': {**video, 'platform': 'instagram', 'relation': '来源视频'},
            'source': '原片画面参考', 'category': '', 'category_name': '', 'metrics': {},
        }
    return cases


CASES = _load_cases()
BY_URL = {case['url']: case for case in CASES.values()}

# The post must describe both a practical action and the message it delivers.
# The suggested setup is ours. A match is not a claim about the original crew or budget.
MESSAGE = re.compile(
    r"\b(?:invit\w*|event|worship night|match\s?day|opening (?:day|night|hours)|open soon|grand opening|"
    r"we(?:[’']re| are) open|(?:our|store|holiday|business) hours|save the date|sale|discount|offer|menu|"
    r"bookings?|book (?:now|your|a table)|launch|logo|brand|team|price|announcement|address|new arrivals?|specials?)\b"
    r"|邀请|活动|报名|营业|时间|折扣|优惠|菜单|预约|上新|品牌|店名|团队|价格|开业|地址|摊位", re.I,
)
EXCLUDE = re.compile(r'\b(?:unbox\w*|reviews?|tutorial|giveaway|sweepstakes|stunts?|explosions?|pyrotechnics|blockbuster|behind the scenes of a movie)\b|开箱|测评|抽奖|爆破|高空特技|大型特效', re.I)
METHODS = (
    (r'(?:swip\w*|tap\w*|stack\w*|light up).{0,45}(?:phones?|screens?)|(?:phones?|screens?).{0,45}(?:swip\w*|in turn|one by one|light up)|(?:手机|屏幕).{0,16}(?:依次|逐个|接力|拼字)',
     '固定手机机位，把一句信息分在几块屏幕上，按顺序切换画面，最后留出读字时间。'),
    (r'(?:cut|snip|pull|clip).{0,35}(?:strings?|ribbons?)|(?:翻|剪|抽|拉).{0,12}(?:线绳|绳子|细绳|细线|字卡|纸条)',
     '把信息分行写在纸卡上，在同一机位抽开或放下一张，露出下一行。'),
    (r'(?:flip\w*|turn\w*|bit(?:e|ing)|cutout|cut.out|fram\w*).{0,42}(?:cardboard|sign|paper frame|card\b)|(?:cardboard|paper frame|paper sign).{0,42}(?:flip|turn|bite|cutout|frame)|(?:纸板|纸框|纸牌).{0,16}(?:缺口|翻面|取景|镂空)',
     '用一张纸板作遮挡、取景框或双面招牌。固定构图，让翻面或换人自然带出店里的信息。'),
    (r'(?:wip\w*|writ\w*|swip\w*).{0,40}(?:lens|glass|mirror)|(?:lens|mirror).{0,35}(?:wipe|writ\w*)|(?:擦|写).{0,10}(?:镜头|玻璃|镜面)',
     '把手机固定在透明片后，在手指划过时用一次擦除或文字遮罩显字。'),
    (r'paper (?:plane|airplane|aeroplane).{0,55}(?:unfold|open|message|fly|land)|(?:unfold|throw|toss|catch).{0,30}paper (?:plane|airplane|aeroplane)|纸飞机.{0,14}(?:飞入|接住|展开|打开)',
     '让纸飞机从画外入镜，在柜台上接住并展开。沿纸的运动方向剪接，消息写在纸内侧。'),
    (r'stack\w*.{0,35}(?:pizza |branded |empty )?boxes|(?:packaging|boxes).{0,30}(?:tower|stacked)|(?:叠|摞).{0,12}(?:包装盒|纸盒|披萨盒)',
     '在固定机位叠放轻质空盒，把品牌字样朝向镜头，最后落到盒面上的信息。'),
    (r'(?:tap\w*|flip\w*|press\w*|reach\w*).{0,35}(?:toggle|switch)|(?:拨|点|碰).{0,12}(?:开关|按钮).{0,18}(?:画面|海报|活动)',
     '在固定画面中留出开关的位置，人物轻点时硬切画面或切换两张文字图层。'),
    (r'(?:foley|sound effects?).{0,45}(?:ice|cup|drink|pour)|(?:stir|ice|pour\w*).{0,45}(?:foley|sound of summer)|(?:杯|冰块|倒饮料).{0,15}(?:拟音|卡点)',
     '在同一张桌面录下放冰、倒入、搅拌的声音，逐个动作剪到对应声点，最后停在成品。'),
)
METHODS = tuple((re.compile(pattern, re.I), note) for pattern, note in METHODS)


def caption_setup(text):
    text = re.sub(r'[#＃][\w-]+', '', text or '')
    if not text or EXCLUDE.search(text) or not MESSAGE.search(text):
        return ''
    return next((note for pattern, note in METHODS if pattern.search(text)), '')


def with_setup(item):
    case = BY_URL.get(item.get('url'))
    if case:
        return {**case, **item, 'filming': case['filming'], 'filming_basis': '画面参考'}
    if item.get('source_kind') in ('daily_feed', 'data_source', 'manual'):
        # Only the source description is evidence; never use search terms or suggested translations.
        caption = ' '.join(dict.fromkeys(str(item.get(k) or '') for k in ('title','summary')))
        setup = caption_setup(caption)
        if setup:
            return {**item, 'filming': setup, 'filming_basis': '按内容说明匹配'}
    return item
