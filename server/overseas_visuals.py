"""Public source references and conservative caption matches for shootable shorts."""
import json
import re
from pathlib import Path


def _load_cases():
    resources = Path(__file__).parent / 'resources/hiccai-pop'
    profiles = {p['publisher']:p for p in json.loads((resources / 'visual-sources.json').read_text())}
    cases = {}
    for item in json.loads((resources / 'visual-references.json').read_text()):
        video = {k: item[k] for k in ('url', 'title', 'publisher')}
        platform = item.get('platform', 'instagram')
        if platform=='youtube':
            video['url']=item['url'].replace('https://www.youtube.com/watch?v=','https://www.youtube.com/shorts/')
        profile = profiles.get(item['publisher'], {})
        cases[item['id']] = {
            **item, 'platform': platform, 'source_kind': 'visual_case',
            'industry': item.get('industry', profile.get('industry','')),
            'publisher_type': item.get('publisher_type', profile.get('publisher_type','')),
            'reference_video': {**video, 'platform': platform, 'relation': '来源视频'},
            'source': item.get('filming_basis', '原片画面参考'), 'category': '', 'category_name': '', 'metrics': {},
        }
    return cases


CASES = _load_cases()
BY_URL = {case['url']: case for case in CASES.values()}

# The post must describe both a practical action and the message it delivers.
# The suggested setup is ours. A match is not a claim about the original crew or budget.
MESSAGE = re.compile(
    r"\b(?:invit\w*|event|worship night|match\s?day|opening (?:day|night|hours)|open soon|grand opening|"
    r"we(?:[’']re| are) open|(?:our|store|holiday|business) hours|save the date|sale|discount|offer|menu|"
    r"bookings?|book (?:now|your|a table)|launch|logo|brand|team|price|announcement|address|new arrivals?|specials?|"
    r"(?:join us|see you) (?:on |this )?(?:sunday|saturday|friday)|come to (?:church|our store)|"
    r"(?:our|the new|introducing (?:the|our)) (?:collection|bag|shoe|kit|product|shade|exhibition|jersey)|colourways?|colorways?)\b"
    r"|邀请|活动|报名|营业|时间|折扣|优惠|菜单|预约|上新|品牌|店名|团队|价格|开业|地址|摊位", re.I,
)
EXCLUDE = re.compile(r'\b(?:unbox\w*|reviews?|giveaway|sweepstakes|stunts?|explosions?|pyrotechnics|blockbuster|CGI|3D render\w*|crane shots?|aerial rig|behind the scenes of a movie)\b|开箱|测评|抽奖|爆破|高空特技|大型特效', re.I)
PHONE_SHADOW = re.compile(r'\bshadows?\b.{0,180}\b(?:shot|filmed) (?:on|with) (?:a |my )?phone\b', re.I | re.S)
METHODS = (
    ('遮镜换物', r'(?:cover|block|palm)\w*.{0,30}(?:lens|camera).{0,72}(?:switch|reveal|chang\w*)|(?:手掌|手指).{0,8}遮镜.{0,15}(?:换色|换装|露出)',
     '固定机位，手掌遮满镜头时换上第二件物品或换一个颜色。用两段全黑画面对剪，手移开后停在新造型。'),
    ('轮廓对位', r'(?:sketch|drawing|outline|silhouette).{0,55}(?:becomes?|turns? into|match.cut|align\w* with).{0,40}(?:bag|shoe|bottle|jersey|product|outfit)|(?:线稿|剪影|轮廓).{0,18}(?:变成|接到|对齐).{0,10}(?:实物|球衣|鞋|瓶|包)',
     '先正对手机拍纸上的轮廓，标好纸角和物品的中心。将实物放到同一位置再拍一遍，在两个轮廓重合处硬切。'),
    ('桌面定格', r'(?:stop.motion|frame by frame).{0,70}(?:paper cutouts?|sticky notes?|shoelaces?|paper clips?|price tags?)|(?:paper cutouts?|sticky notes?|shoelaces?).{0,60}(?:stop.motion|frame by frame)',
     '固定手机和桌面光线，每移动一点道具就拍一张照片，依次拼成短动画。最后定住产品或活动信息。'),
    ('刷痕显字', r'(?:paint|brush).{0,48}(?:wip\w*|reveal|smooth across)|(?:wip\w*|smooth).{0,35}paint.{0,40}(?:reveal|message|frame)|(?:刷|刮).{0,8}(?:颜料|油漆).{0,14}(?:邀请|显字|露出)',
     '手机固定俯拍，在两张同构图的纸上分别拍刷子扫过和信息露出，沿刷毛边缘接一刀。'),
    ('甩物接镜', r'(?:flick\w*|toss\w*|fling\w*|throw\w*).{0,35}(?:the |a |our )?menus?\b|\bmenu\b.{0,45}(?:lands? open|flips? open)|(?:甩|抛|掷).{0,10}菜单',
     '拍菜单从手里甩出画面，再拍它沿相同方向落到桌上。对齐运动方向剪接，最后让观众看清菜单。'),
    ('机位错觉', r'(?:throw\w*|toss\w*|drop\w*).{0,22}straws?.{0,55}(?:cup|glass)|吸管.{0,15}(?:投进|落入|扔进).{0,6}杯',
     '将杯子靠近手机，一人在远处投，一人在镜头旁放入备用吸管。补拍一个侧面镜头揭开错觉。'),
    ('投中揭晓', r'(?:basketball|hoop).{0,22}(?:shot|shoot|toss)|(?:shoot|sink|mak\w*).{0,20}(?:basket|hoop)|投篮.{0,12}(?:命中|邀请)',
     '把投篮动作和篮筐拍在同一镜头。起手时给出条件，球落进篮筐时亮出活动邀请。'),
    ('屏幕接字', r'(?:swip\w*|tap\w*|stack\w*|light up).{0,45}(?:phones?|screens?)|(?:phones?|screens?).{0,45}(?:swip\w*|in turn|one by one|light up)|(?:手机|屏幕).{0,16}(?:依次|逐个|接力|拼字)',
     '固定手机机位，把一句信息分在几块屏幕上，按顺序切换画面，最后留出读字时间。'),
    ('剪绳落字', r'(?:cut|snip|pull|clip).{0,35}(?:strings?|ribbons?)|(?:翻|剪|抽|拉).{0,12}(?:线绳|绳子|细绳|细线|字卡|纸条)',
     '把信息分行写在纸卡上，在同一机位抽开或放下一张，露出下一行。'),
    ('翻牌指路', r'(?:flip\w*|turn\w*|bit(?:e|ing)|cutout|cut.out|fram\w*).{0,42}(?:cardboard|sign|paper frame|card\b)|(?:cardboard|paper frame|paper sign).{0,42}(?:flip|turn|bite|cutout|frame)|(?:纸板|纸框|纸牌).{0,16}(?:缺口|翻面|取景|镂空)',
     '用一张纸板作遮挡、取景框或双面招牌。固定构图，让翻面或换人自然带出店里的信息。'),
    ('擦镜显字', r'(?:wip\w*|writ\w*|swip\w*).{0,40}(?:lens|glass|mirror)|(?:lens|mirror).{0,35}(?:wipe|writ\w*)|(?:擦|写).{0,10}(?:镜头|玻璃|镜面)',
     '把手机固定在透明片后，在手指划过时用一次擦除或文字遮罩显字。'),
    ('纸飞机送信', r'paper (?:plane|airplane|aeroplane).{0,55}(?:unfold|open|message|fly|land)|(?:unfold|throw|toss|catch).{0,30}paper (?:plane|airplane|aeroplane)|纸飞机.{0,14}(?:飞入|接住|展开|打开)',
     '让纸飞机从画外入镜，在柜台上接住并展开。沿纸的运动方向剪接，消息写在纸内侧。'),
    ('叠盒亮标', r'stack\w*.{0,35}(?:pizza |branded |empty )?boxes|(?:packaging|boxes).{0,30}(?:tower|stacked)|(?:叠|摞).{0,12}(?:包装盒|纸盒|披萨盒)',
     '在固定机位叠放轻质空盒，把品牌字样朝向镜头，最后落到盒面上的信息。'),
    ('拨开关切景', r'(?:tap\w*|flip\w*|press\w*|reach\w*).{0,35}(?:toggle|switch)|(?:拨|点|碰).{0,12}(?:开关|按钮).{0,18}(?:画面|海报|活动)',
     '在固定画面中留出开关的位置，人物轻点时硬切画面或切换两张文字图层。'),
    ('动作拟音', r'(?:foley|sound effects?).{0,45}(?:ice|cup|drink|pour)|(?:stir|ice|pour\w*).{0,45}(?:foley|sound of summer)|(?:杯|冰块|倒饮料).{0,15}(?:拟音|卡点)',
     '在同一张桌面录下放冰、倒入、搅拌的声音，逐个动作剪到对应声点，最后停在成品。'),
)
METHODS = tuple((name, re.compile(pattern, re.I), note) for name, pattern, note in METHODS)


def caption_match(text):
    text = re.sub(r'[#＃][\w-]+', '', text or '')
    text = re.sub(r'\b(?:no|without) (?:CGI|3D rendering|stunts?)\b','',text,flags=re.I)
    if not text or EXCLUDE.search(text):
        return '', ''
    if PHONE_SHADOW.search(text) and re.search(r'behind the scenes|how (?:I|we) (?:shot|made)|how to',text,re.I):
        return '借影构图', '找一件轮廓清楚的日用品，用窗光或台灯将影子投到纸上。先拍影子让人猜，再移开物件，露出它和光源的位置。'
    if not MESSAGE.search(text):return '', ''
    return next(((name, note) for name, pattern, note in METHODS if pattern.search(text)), ('',''))


def caption_setup(text):
    return caption_match(text)[1]


def with_setup(item):
    case = BY_URL.get(item.get('url'))
    if case:
        return {**case, **item, 'filming': case['filming'], 'mechanism': case['mechanism'],
                'filming_basis': case.get('filming_basis', '画面参考')}
    if item.get('source_kind') in ('daily_feed', 'data_source', 'manual'):
        # Only the source description is evidence; never use search terms or suggested translations.
        caption = ' '.join(dict.fromkeys(str(item.get(k) or '') for k in ('title','summary')))
        mechanism,setup = caption_match(caption)
        if setup:
            return {**item, 'mechanism':item.get('mechanism') or mechanism, 'filming': setup, 'filming_basis': '按内容说明匹配'}
    return item
