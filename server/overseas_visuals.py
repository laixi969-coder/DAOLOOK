"""Public source references and conservative caption matches for shootable shorts."""
import json
import re
from urllib.parse import parse_qs, urlsplit
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

POSTERS = {p.name for p in (Path(__file__).resolve().parents[1] / 'web/art/overseas').glob('*.webp')}


def daily_poster(item):
    video = item.get('reference_video') or {}
    source = urlsplit(video.get('url') or item.get('url') or '')
    code = source.path.rstrip('/').rsplit('/', 1)[-1]
    if source.path == '/watch':
        code = parse_qs(source.query).get('v', [''])[0]
    name = f"{item.get('platform')}-{code}.webp"
    if name in POSTERS:
        return '/art/overseas/' + name
    if isinstance(video.get('thumbnail'), str) and video['thumbnail'].startswith('https://'):
        return video['thumbnail']
    if item.get('platform') == 'youtube' and re.fullmatch(r'[A-Za-z0-9_-]{11}', code):
        return 'https://i.ytimg.com/vi/' + code + '/hqdefault.jpg'
    return ''


def review_key(url):
    parts = urlsplit(url)
    host = parts.hostname or ''
    path = parts.path.strip('/').split('/')
    if host in ('www.instagram.com','instagram.com') and len(path)==2 and path[0] in ('p','reel','reels'):
        return ('instagram',path[1])
    if host in ('www.tiktok.com','tiktok.com') and len(path)==3 and path[1]=='video':
        return ('tiktok',path[2])
    return url


REVIEWED = {review_key(url):case for url,case in BY_URL.items()}


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
    ('借位悬浮', r'(?:cup|bottle|product).{0,40}(?:float|hover)\w*|(?:float|hover)\w*.{0,32}(?:cup|bottle)|(?:杯|瓶).{0,12}(?:悬空|漂浮)',
     '手机固定，把杯子放在画框边缘的隐蔽支点上。拍人物伸手取杯，补一个侧面镜头交代支点或借位。'),
    ('折纸透视', r'(?:paper|cardstock).{0,40}(?:ladder|staircase)|(?:ladder|staircase).{0,40}(?:paper|cardstock)|纸.{0,12}(?:阶梯|梯子)',
     '沿折痕画出互相接续的梯档，先从线条接齐的位置拍，然后改变视角露出折痕。'),
    ('封面借位接脸', r'(?:book ?cover|bookface).{0,65}(?:align|match|line.?up|complet)\w*.{0,40}(?:face|chin|body)|书封.{0,18}(?:对齐|接上).{0,10}(?:脸|下巴|身体)',
     '手机固定，前后移动封面，直到印刷轮廓和真人接齐。拍合体效果，再放下书露出借位。'),
    ('纸卡循环', r'(?:infinity|never.ending|endless) (?:folding )?card|(?:无限|循环)翻折卡',
     '俯拍连续翻卡，每一面写一段消息，最后翻回第一面。'),
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


# A technique needs an observable payoff in the source itself. These cues also
# explain what a viewer could point out to another person or watch again to spot.
PAYOFF_CUES = {
    '借位悬浮': (r'(?:grab|take|reach|drink|sip)\w* (?:for |from )?(?:it|the cup|the drink)|(?:side|reverse) angle|伸手取|拿起|反打', '先看见悬空的杯子，再看人伸手接住它或换角度揭晓支点。'),
    '折纸透视': (r'anamorphic|changes? (?:the )?angle|fold.{0,25}illusion|透视|换.{0,5}角度', '纸上的线条从特定机位才连成立体梯子，换角度就能揭晓。'),
    '遮镜换物': (r'(?:same|matching) (?:outline|silhouette)|轮廓.{0,8}(?:重合|接齐)', '手遮住的瞬间，两件轮廓吻合的实物在同一位置交接。'),
    '桌面定格': (r'(?:spell out|fold into|form the (?:logo|word))|拼成.{0,8}(?:字|标志)', '散开的道具逐帧移到位，最后拼出一个完整符号。'),
    '叠盒亮标': (r'(?:block|hide|cover).{0,30}(?:face|person)|(?:遮住|挡住).{0,8}(?:脸|人)', '空盒堆到遮住人的脸，品牌信息随这摞盒子一起移动。'),
    '拨开关切景': (r'(?:turns into|transforms into|switches to).{0,30}(?:poster|scene)|变成.{0,8}(?:海报|场景)', '现实中的手碰到开关，整个画面马上变成海报或新场景。'),
    '动作拟音': (r'(?:sounds? like|mimics?).{0,35}(?:waves|ocean|rain|summer)|听起来像.{0,6}(?:海浪|雨声)', '一个日常动作发出让人想到另一个场景的声音，可以猜声源。'),
    '封面借位接脸': (r'face|chin|body|下巴|脸|身体', '封面和真人共用一条轮廓，可以找出两者在哪里接上。'),
    '纸卡循环': (r'back to (?:the )?(?:start|first)|loops? back|回到(?:起点|第一面)', '纸卡翻了一圈，结尾又接回开头。'),
    '轮廓对位': (r'becomes?|turns? into|align|match.cut|变成|对齐|接到', '平面的轮廓和实物对在一起，可以倒回去找接点。'),
    '刷痕显字': (r'reveal|underneath|显字|露出', '消息沿着刷痕出现，手的动作决定读字顺序。'),
    '甩物接镜': (r'lands? open|flips? open|落.{0,4}摊开', '道具飞出镜头，落地时打开成了菜单。'),
    '机位错觉': (r'(?:reverse|other|second|side) angle|hidden hand|spare straws|反打|另一.{0,4}机位|备用吸管', '换到另一机位，才看懂连续命中的秘密。'),
    '屏幕接字': (r'spell|piece together|one word|one by one.{0,40}(?:word|message)|拼字|拼成|接成', '几块屏幕各显示一部分，接在一起才读出完整信息。'),
    '剪绳落字': (r'(?:reveal|drop|uncover).{0,40}(?:next|word|card|time|date)|露出.{0,12}(?:下一|日期|时间)', '剪开一根绳就露出下一行，观众会等到信息完整。'),
    '翻牌指路': (r'(?:reveal|uncover|points? to).{0,50}(?:hours|offer|booking|stall|address|invite|menu|price|team)|(?:露出|指向).{0,14}(?:营业|摊位|预约|菜单|价格|团队)', '牌面翻转前后给出两层信息，观众会等着看另一面。'),
    '擦镜显字': (r'(?:reveal|uncover|appear).{0,50}(?:hours|sale|discount|offer|invite|message)|(?:显出|露出).{0,12}(?:折扣|营业|邀请)', '擦过的地方留下可读的信息，手势和揭晓发生在同一处。'),
    '纸飞机送信': (r'unfold.{0,50}(?:message|invite|date)|展开.{0,16}(?:邀请|时间|消息)', '飞进画面的道具展开后成了一封邀请。'),
}
PAYOFF_CUES = {name:(re.compile(pattern,re.I),reason) for name,(pattern,reason) in PAYOFF_CUES.items()}

# Only assigned after caption_review has matched a physical action and its payoff.
CAPTION_HOOKS = {
    '借影构图':'先只看影子，你能猜到镜头前摆的是什么吗？',
    '刷痕显字':'刷子扫过，下面开始露字。这一整句会是什么？',
    '封面借位接脸':'眼前这张脸，哪里是书封，哪里才是真人？',
    '纸卡循环':'一张卡翻到尽头，怎么又有一面？',
    '借位悬浮':'没有手托着，杯子怎么会停在半空？',
    '折纸透视':'纸上的线条怎么有了高度？',
    '遮镜换物':'手挡住的一瞬间，眼前的东西换了吗？',
    '桌面定格':'桌上的小物件自己移动，最后要拼成什么？',
    '叠盒亮标':'盒子一层层叠高，后面的人快被挡住了。',
    '拨开关切景':'画面里这个开关，手一碰会发生什么？',
    '动作拟音':'闭眼听像在另一个地方，声音是怎么做出来的？',
    '轮廓对位':'刚才还是画出来的轮廓，实物从哪里接了上来？',
    '甩物接镜':'菜单飞出了画面，下一镜会落在哪里？',
    '机位错觉':'站得那么远，吸管怎么每次都能投中？',
    '屏幕接字':'每块屏幕只亮出一部分，拼起来是哪句话？',
    '剪绳落字':'这根绳一剪，下面会露出哪个字？',
    '翻牌指路':'手里的纸牌转过来，背面藏着什么？',
    '擦镜显字':'手刚擦过，玻璃上怎么留下了字？',
    '纸飞机送信':'飞进画面的纸飞机，展开后写了什么？',
    '实物错觉揭晓':'眼前的东西真是第一眼以为的那样吗？',
}

# A recognizable prop can occur inside an otherwise predictable format.
ROUTINE_FORMAT = re.compile(
    r"what(?:['’]s| is) in my bag|bag dump|unpack my bag|client (?:calls?|face)|"
    r"customer.service (?:face|smile)|swipe to (?:make|cook|build|assemble)|"
    r"(?:bake|baking|oven).{0,65}(?:handbag|tote|purse)|(?:handbag|tote|purse).{0,65}(?:oven|baking)|"
    r"翻包|包里有什么|职业假笑|客户来电|滑动.{0,8}(?:做早餐|拼装)|烤出.{0,8}(?:手袋|托特包)", re.I)


# Leave room for a new trick when the post itself describes a specific
# misreading and the physical action that resolves it in the same scene.
PROP = re.compile(r'\b(?:paper|sticker|label|book|poster|receipt|cup|bottle|card|mirror|photo|box|bag|menu|envelope|pencil|frame)\b|纸|书|杯|瓶|卡片|镜子|盒|信封|菜单', re.I)
MISREAD = re.compile(
    r"(?:looks? (?:like|as if)|appears? to be)\s+[^.!?\n]{3,80}?[, ]+(?:until|but then)\s+"
    r"[^.!?\n]{0,35}?(?:peel|unfold|rotate|tilt|turn|slide|lift|pull back)\w*\b[^.!?\n]{0,80}?"
    r"(?:reveal|show|expos)\w*\s+[^.!?\n]{3,75}"
    r"|(?:看似|看起来像|以为)[^。！？\n]{2,32}?(?:撕开|揭开|转动|拉远|移开|展开|掀开)[^。！？\n]{0,20}?"
    r"(?:才发现|原来|露出)[^。！？\n]{2,35}", re.I)


def caption_review(text):
    text = re.sub(r'[#＃][\w-]+', '', text or '')
    text = re.sub(r'\b(?:no|without) (?:CGI|3D rendering|stunts?)\b','',text,flags=re.I)
    if not text or EXCLUDE.search(text) or ROUTINE_FORMAT.search(text):
        return '', '', ''
    if PHONE_SHADOW.search(text) and re.search(r'behind the scenes|how (?:I|we) (?:shot|made)|how to',text,re.I):
        return '借影构图', '找一件轮廓清楚的日用品，用窗光或台灯将影子投到纸上。先拍影子让人猜，再移开物件，露出它和光源的位置。', '先看影子构图，再看幕后摆法，可以让朋友猜它怎么拍出来。'
    if not MESSAGE.search(text):
        return '', '', ''
    for name, pattern, note in METHODS:
        cue, _ = PAYOFF_CUES[name]
        if match := pattern.search(text):
            context = text[max(0,match.start()-50):match.end()+100]
            if cue.search(context):
                return name, note, PAYOFF_CUES[name][1]
    reveal = MISREAD.search(text)
    if reveal and PROP.search(reveal.group()):
        return ('实物错觉揭晓', '先按原帖中的错觉摆好实物，锁定手机拍第一眼。再拍清楚揭晓的那个动作，在同一构图里留出读信息的时间。',
                '原帖描述的误会和揭晓：' + reveal.group().strip())
    return '', '', ''


def caption_setup(text):
    return caption_review(text)[1]


def with_setup(item):
    case = REVIEWED.get(review_key(item.get('url') or ''))
    if case:
        return {**case, **item, 'filming': case['filming'], 'mechanism': case['mechanism'],
                'hook_zh': case.get('hook_zh', ''), 'visual_payoff': case.get('visual_payoff', ''), 'filming_basis': case.get('filming_basis', '画面参考')}
    item = {**item, 'visual_payoff': ''}
    if item.get('source_kind') in ('daily_feed', 'data_source', 'manual'):
        # Only the source description is evidence; never use search terms or suggested translations.
        caption = ' '.join(dict.fromkeys(str(item.get(k) or '') for k in ('title','summary')))
        if item.get('case_review'):
            caption = (item.get('reference_video') or {}).get('title','')
        mechanism,setup,reason = caption_review(caption)
        if setup:
            return {**item, 'mechanism':mechanism, 'hook_zh':CAPTION_HOOKS[mechanism], 'visual_payoff':reason, 'filming': setup, 'filming_basis': '按内容说明匹配'}
    return item
