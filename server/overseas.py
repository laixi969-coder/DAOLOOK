"""Viral creative production using existing model routing, queue and credits."""
import copy
import re
from . import adapters, content_quality, questions
from .overseas_library import PLATFORMS as SOCIAL_PLATFORMS
from .overseas_prompt import VISUAL_ACTION_EDITION, VISUAL_NAME

LANGUAGES = {'en-zh':'English','es-zh':'Spanish','fr-zh':'French','de-zh':'German'}
PLATFORMS = {'overseas':'TikTok + Reels + Shorts', **SOCIAL_PLATFORMS}
ENDINGS = ('动作传达信息', '故事翻牌', '反转后硬广', '结果先行演示')
CASTING = ('有人', '仅手部', '无人')
SECONDS_UNIT = r'(?:seconds?|secs?|secondes?|segundos?|segs?|sekunden?|sek|s|秒)'
SCREEN_INTERVAL = re.compile(
    r'(?<![\d:])(?:00:[0-5]\d\s*[-–—~～至]\s*(?:00:[0-5]\d|01:00)|'
    rf'\d+(?:\.\d+)?\s*{SECONDS_UNIT}?\s*[-–—~～至]\s*'
    rf'\d+(?:\.\d+)?\s*{SECONDS_UNIT})(?![a-z\d])', re.I,
)
EDITING_TIMECODE = re.compile(
    r'^\s*(?:[\[【(（]\s*)?(' + SCREEN_INTERVAL.pattern + r')(?=\s|[\]】)）：:|]|$)', re.I | re.M,
)


def contains_editing_cue(text, assets):
    """A quoted duration can be valid copy in either language, even at the start of a line."""
    cues = {tuple(re.findall(r'\d+(?:\.\d+)?', match[1])) for match in EDITING_TIMECODE.finditer(text)}
    if not cues:
        return False
    for asset in assets:
        if asset.get('kind') != '图片':
            for match in SCREEN_INTERVAL.finditer(asset.get('content', '')):
                cues.discard(tuple(re.findall(r'\d+(?:\.\d+)?', match[0])))
    return bool(cues)


def string_fields(names):
    return {k:{'type':'string'} for k in names}


OUTPUT_SCHEMA = {
    'type':'object', 'properties':{
        **string_fields(('title','body','cover_text','hook','direction','angle','role','audience','value','cta','script','translation_zh','concept','adaptation','first_second','misread','clue','reveal','product_role','production_method','cost_basis','product_reveal')),
        'ending_type':{'type':'string','enum':list(ENDINGS)},
        'casting':{'type':'string','enum':list(CASTING)},
        'reveal_shot':{'type':'integer','minimum':1,'maximum':6},
        **{k:{'type':'array','items':{'type':'string'}} for k in ('titles','tags','image_suggestions','storyboard','shooting_list','missing','comments')},
        'hooks':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'object','properties':string_fields(('visual','line','translation_zh','sfx')),'required':['visual','line','translation_zh','sfx']}},
        'shots':{'type':'array','minItems':1,'maxItems':6,'items':{'type':'object','properties':{**string_fields(('camera','action','line','translation_zh','screen_text','screen_text_zh','sfx','implementation','ai_prompt')),'start':{'type':'number'},'end':{'type':'number'}},'required':['start','end','camera','action','line','translation_zh','screen_text','screen_text_zh','sfx','implementation','ai_prompt']}},
        'evidence':{'type':'array','items':{'type':'object','properties':string_fields(('asset_id','quote')),'required':['asset_id','quote']}},
        'target_platform':{'type':'string','enum':list(SOCIAL_PLATFORMS)},
    },
}
OUTPUT_SCHEMA['required']=list(OUTPUT_SCHEMA['properties'])
SCHEMA={'type':'object','properties':{'outputs':{'type':'array','minItems':3,'maxItems':3,'items':OUTPUT_SCHEMA}},'required':['outputs']}

SHOOT_SETUP = {
    'type':'object', 'required':['people','locations','props','simpler_take'],
    'properties':{
        'people':{'type':'integer','minimum':1,'maximum':100},
        'locations':{'type':'array','minItems':1,'maxItems':12,'items':{'type':'string'}},
        'props':{'type':'array','maxItems':30,'items':{'type':'string'}},
        'simpler_take':{'type':'string','maxLength':600},
    },
}

def check_shoot_setup(setup):
    if not isinstance(setup,dict) or type(setup.get('people')) is not int or not 1 <= setup['people'] <= 100:
        raise ValueError('请写明完成拍摄所需的总人数，含拍摄者')
    for key, least, most in [('locations',1,12),('props',0,30)]:
        values = setup.get(key)
        if (not isinstance(values,list) or not least <= len(values) <= most
                or any(not isinstance(v,str) or not v.strip() or len(v)>150 for v in values)):
            raise ValueError('请列出实际拍摄地点与所需道具')
    simple = setup.get('simpler_take')
    if not isinstance(simple,str) or len(simple)>600:
        raise ValueError('简化拍法格式无效')
    if (setup['people'] > 2 or len(setup['locations']) > 1 or len(setup['props']) > 3) and not simple.strip():
        raise ValueError('请补一个单场地、手边道具就能执行的简化拍法')


def validate(result,brief,assets,previous=None,require_setup=False,action_edition=False):
    outputs=result.get('outputs') if isinstance(result,dict) else None
    if not isinstance(outputs,list) or len(outputs)!=3: raise ValueError('海外创作需要3个完整创意方案')
    if brief['platform']=='overseas' and {o.get('target_platform') for o in outputs if isinstance(o,dict)}!=set(SOCIAL_PLATFORMS): raise ValueError('三平台创作需要TikTok、Reels、Shorts各一个方案')
    for output in outputs:
        if not isinstance(output,dict): raise ValueError('创意方案格式错误')
        if require_setup or 'shoot_setup' in output:
            check_shoot_setup(output.get('shoot_setup'))
        if output.get('target_platform') not in SOCIAL_PLATFORMS or (brief['platform']!='overseas' and output['target_platform']!=brief['platform']): raise ValueError('方案的平台与要求不一致')
        for key in ('title','body','cover_text','hook','direction','angle','role','audience','value','cta','concept','first_second','reveal','product_role','ending_type','production_method','cost_basis','casting','product_reveal'):
            if not isinstance(output.get(key),str) or not output[key].strip() or len(output[key])>30000: raise ValueError('创意缺少有效字段：'+key)
        for key in ('script','translation_zh'):
            if not isinstance(output.get(key),str) or len(output[key])>30000: raise ValueError('口播格式无效')
        if bool(output['script'].strip()) != bool(output['translation_zh'].strip()): raise ValueError('有口播时须同时提供中文翻译')
        if output['ending_type'] not in ENDINGS: raise ValueError('收尾方式无效')
        for key in ('misread','clue'):
            value = output.get(key)
            if not isinstance(value, str) or len(value) > 30000:
                raise ValueError('误判与伏笔须为文本')
            if output['ending_type'] in ('故事翻牌','反转后硬广') and not value.strip():
                raise ValueError('反转创意需要交代误判和伏笔')
        if output['casting'] not in CASTING: raise ValueError('请标明有人、仅手部或无人出镜')
        for key in ('titles','tags','image_suggestions','storyboard','shooting_list','missing','comments'):
            value=output.get(key)
            if not isinstance(value,list) or len(value)>60 or any(not isinstance(v,str) or len(v)>6000 for v in value): raise ValueError('创意列表字段无效：'+key)
        if len(output['titles'])!=3 or not output['storyboard'] or not output['shooting_list']:
            raise ValueError('请提供三个备选标题、至少一段分镜及拍摄清单')
        if not action_edition and not output['comments']:
            raise ValueError('缺少评论问题')
        if len(output['tags'])>20: raise ValueError('话题最多20个')
        hooks=output.get('hooks')
        if not isinstance(hooks,list) or len(hooks)!=3: raise ValueError('每个方案必须有3个Hook')
        for hook in hooks:
            if not isinstance(hook,dict) or any(not isinstance(hook.get(k),str) or len(hook[k])>4000 for k in ('visual','line','translation_zh','sfx')) or not hook['visual'].strip(): raise ValueError('Hook缺少有效画面或文案')
            if bool(hook['line'].strip()) != bool(hook['translation_zh'].strip()): raise ValueError('Hook口播须同时提供中文翻译')
        if len({content_quality.normalized(h['visual']+h['line']) for h in hooks})!=3: raise ValueError('3个Hook不能只是换标点')
        shots=output.get('shots')
        if not isinstance(shots,list) or not 1<=len(shots)<=6: raise ValueError('拍摄方案需要1–6镜')
        reveal_shot=output.get('reveal_shot')
        if type(reveal_shot) is not int or not 1<=reveal_shot<=len(shots): raise ValueError('请标明有效的产品首次揭晓镜号')
        if output['ending_type']=='故事翻牌' and reveal_shot!=len(shots): raise ValueError('故事翻牌需要在最后一镜首次揭晓产品')
        cursor=0
        for shot in shots:
            if not isinstance(shot,dict) or any(not isinstance(shot.get(k),str) or len(shot[k])>6000 for k in ('camera','action','line','translation_zh','screen_text','screen_text_zh','sfx','implementation','ai_prompt')): raise ValueError('分镜字段无效')
            if bool(shot['line'].strip()) != bool(shot['translation_zh'].strip()): raise ValueError('镜头口播须同时提供中文翻译')
            if bool(shot['screen_text'].strip()) != bool(shot['screen_text_zh'].strip()): raise ValueError('屏幕文案须同时提供中文翻译')
            if action_edition and any(contains_editing_cue(shot[key],assets) for key in ('screen_text','screen_text_zh')):
                raise ValueError('屏幕文案里出现了剪辑时间码。请把时间安排移到 action，只把观众要看的原文和中译留在屏幕文案')
            start,end=shot.get('start'),shot.get('end')
            if type(start) not in (int,float) or type(end) not in (int,float) or abs(start-cursor)>.01 or not start<end<=brief['duration']: raise ValueError('分镜时间必须从0秒连续覆盖目标时长')
            if not shot['camera'].strip() or not shot['action'].strip() or not shot['implementation'].strip(): raise ValueError('分镜缺少具体画面动作或实现方法')
            if not shot['ai_prompt'].strip(): raise ValueError('分镜缺少可复制的AI生成提示词')
            cursor=end
        if abs(cursor-brief['duration'])>.01: raise ValueError('分镜总时长与目标时长不一致')
        evidence=output.get('evidence')
        if not isinstance(evidence,list) or (evidence and not content_quality.evidence_valid(output,assets)): raise ValueError('业务事实引用未匹配所选资料')
    for field in ('title','body','angle','first_second'):
        if len({content_quality.normalized(o[field]) for o in outputs})!=3: raise ValueError('方案不能重复：'+field)
    # A shared invitation can land on exactly the same time and place; compare the filmed action.
    reveals = [content_quality.normalized(o['reveal']) for o in outputs
               if not action_edition or o['ending_type'] in ('故事翻牌','反转后硬广')]
    if len(set(reveals)) != len(reveals): raise ValueError('方案不能重复：reveal')
    if action_edition:
        actions = {content_quality.normalized(' '.join(shot['action'] for shot in o['shots'])) for o in outputs}
        if len(actions) < len(outputs): raise ValueError('方案使用了相同的分镜动作，请换一个实际拍法')
    misreads = [content_quality.normalized(o['misread']) for o in outputs if o['misread'].strip()]
    if len(set(misreads)) != len(misreads): raise ValueError('方案不能重复：misread')
    scripts=[content_quality.normalized(o['script']) for o in outputs if o['script'].strip()]
    if len(set(scripts))!=len(scripts): raise ValueError('方案不能重复：script')
    if {content_quality.normalized(o['title']) for o in outputs} & {content_quality.normalized(o.get('title','')) for o in previous or []}: raise ValueError('请避开历史创意标题')


def benchmark(project,brief):
    selected=brief.get('reference_snapshot')
    return {'examples':[selected] if selected else [],'keyword':brief.get('keyword') or brief['topic'],'note':'仅使用用户主动选择的参考；旧版案例仅供启发，不要求套用案例结构、产品事实或复杂拍法。'}


def demo_outputs(brief,assets,batch):
    """Shootable demonstration setups. Only the supplied topic becomes a public claim."""
    topic = brief['topic']
    ideas = [
        {
            'angle':'屏幕接字', 'name':'一划，两块屏幕接成一句话', 'props':'两部展示手机，或两张横向字卡',
            'caption_zh':'顺着箭头看。',
            'caption':{'en-zh':'Follow the arrow.', 'es-zh':'Sigue la flecha.', 'fr-zh':'Suivez la flèche.', 'de-zh':'Folge dem Pfeil.'},
            'camera':'手机固定俯拍，同框拍到上下两块横屏和两屏之间的缝。',
            'actions':[f'上屏的箭头指向下屏。手指顺箭头划过接缝，下屏由空白切到「{topic}」，两屏停住，留出读字时间。'],
            'shoot':'先把箭头和主题字做成相册图片。上屏停在箭头页，手指移到下屏时划到下一张图，一镜录完。手边只有一部手机时用它拍摄，把两部展示机换成可以抽拉的纸卡。',
            'hooks':['箭头的尖端恰好停在两屏接缝处','手指从一块空白屏幕划向另一块','两块横屏先错开，再推齐让箭头接上'],
            'sound':'指尖轻点声',
        },
        {
            'angle':'擦镜显字', 'name':'擦过镜头，把字留在玻璃上', 'props':'一块干布、一张透明片',
            'caption_zh':'擦一下，就出现了。',
            'caption':{'en-zh':'One wipe and it’s there.', 'es-zh':'Una pasada y ahí está.', 'fr-zh':'Un geste et le voilà.', 'de-zh':'Ein Wisch und es ist da.'},
            'camera':'手机固定在柜台前，透明片紧贴镜头前方。第二段保持同机位。',
            'actions':['一只手拿着布从左向右擦过透明片，布在画面中央暂时挡住整个镜头。',
                       f'在布完全遮住镜头的位置接下一段。布移开，透明片上留下「{topic}」，手退出，文字仍停在原位。'],
            'shoot':'先拍空白透明片，布遮满时停机。在透明片贴上正向印好的主题字，从布遮满的位置接拍，一次硬切即可。',
            'hooks':['布从边缘擦向镜头','指尖停在透明片的空白处','布贴满镜头后缓缓移开一角'],
            'sound':'擦过透明片的声音',
        },
        {
            'angle':'翻牌指路', 'name':'缺角的纸牌翻成一块路标', 'props':'一块双面纸板、写有主题的桌牌',
            'caption_zh':'跟着牌子走。',
            'caption':{'en-zh':'The sign points the way.', 'es-zh':'El cartel indica el camino.', 'fr-zh':'Suivez la pancarte.', 'de-zh':'Das Schild zeigt den Weg.'},
            'camera':'固定手机正对柜台，近处的纸板挡住右后方桌牌。',
            'actions':[f'纸板先露出一个向右的缺口，正好框住后面「{topic}」的第一个字。手腕一转，纸板背面的箭头顺势指去；把纸板移到左边，完整桌牌出现在箭头尽头。'],
            'shoot':'在废纸板边缘撕个小缺口，背面画箭头。先对齐缺口和桌牌，锁住机位再翻牌。两件东西在同一张桌前拍完。',
            'hooks':['缺口里只看得见一个字','纸板被推到桌前，缺角刚好对齐桌牌','一根手指沿着缺角探向画外'],
            'sound':'纸板翻面的声音', 'visible':1,
        },
        {
            'angle':'纸框取景', 'name':'同一张纸框，框出两个答案', 'props':'一张挖空的纸、主题字卡',
            'caption_zh':'同一张框，换个视角。',
            'caption':{'en-zh':'Same frame, different view.', 'es-zh':'El mismo marco, otra vista.', 'fr-zh':'Même cadre, autre vue.', 'de-zh':'Gleicher Rahmen, andere Aussicht.'},
            'camera':'手机正对纸框，上边缘的手写主题保持在同一个画面位置。',
            'actions':[f'近处纸框上写着「{topic}」，框内先是一只递出空卡的手。',
                       '在卡片盖住窗口时切一刀，同一位置换成正在展示的实物或主题字卡，纸框边缘始终对齐。'],
            'shoot':'在一张厚纸中间开窗，把主题写在边缘。固定纸框和手机，只换后面的实物或字卡，遮住窗口时剪接两段。',
            'hooks':['一张有洞的纸从画面下方抬起','手从纸框中间递出卡片','空框对着桌面，实物从下沿进入'],
            'sound':'纸张滑过的沙沙声', 'visible':1,
        },
        {
            'angle':'机位错觉', 'name':'纸团怎么每次都能投中', 'props':'一只纸杯、两个小纸团、主题字卡',
            'caption_zh':'看看杯子旁边。',
            'caption':{'en-zh':'Look beside the cup.', 'es-zh':'Mira al lado del vaso.', 'fr-zh':'Regardez à côté du gobelet.', 'de-zh':'Schau neben den Becher.'},
            'camera':'第一段贴近杯沿，第二段从侧面同桌宽景拍摄。',
            'actions':[f'写着「{topic}」的纸杯靠近镜头。远处的手做出投纸团的动作，一颗纸团立即落进前景的杯里。',
                       '切到侧面，同一动作再来一次。这次看到另一只手从杯口正上方松开备用纸团，杯上的主题留在画面中央。'],
            'shoot':'把杯贴近手机，近处的手从取景框上沿放纸团。第二条素材把手机挪到杯侧，拍到两只手的位置。一个人可以双手分工。',
            'hooks':['杯口占据画面下半部，纸团恰好落进来','纸团从画外落入写着主题的杯中','手在远处比出投篮动作，杯口就在镜头旁'],
            'sound':'纸团落杯声', 'visible':1, 'misread':'纸团看起来是远处投进杯里的。', 'clue':'第一段只看得到杯口，投出与落入之间有一小段画外空间。',
        },
        {
            'angle':'纸飞机送信', 'name':'飞到柜台上的一张邀请', 'props':'一张折成飞机的纸',
            'caption_zh':'展开看看。',
            'caption':{'en-zh':'Unfold the message.', 'es-zh':'Despliega el mensaje.', 'fr-zh':'Dépliez le message.', 'de-zh':'Falte die Nachricht auf.'},
            'camera':'固定手机侧拍桌面，把落点留在画面中央。',
            'actions':[f'一架纸飞机从画外滑落桌面。手在原处接住它，沿折痕展开，纸内侧的「{topic}」朝向镜头。'],
            'shoot':'把主题写在纸内侧再折叠。手机靠杯子固定，一只手从画外送入纸飞机，另一只手在桌面展开，简单动作可直接连拍。',
            'hooks':['机头从柜台边缘滑进画面','一只手恰好接住落下的纸飞机','纸飞机的折缝里先露出一小段文字'],
            'sound':'纸飞机落桌和展开的声音',
        },
    ]
    offset = ((batch - 1) * 3) % len(ideas)
    available = ideas[offset:] + ideas[:offset]
    mechanism = (brief.get('reference_snapshot') or {}).get('mechanism')
    available.sort(key=lambda idea: idea['angle'] != mechanism)
    calls_to_action = {
        'reach':{'en-zh':'Share this with a friend.', 'de-zh':'Teile das mit Freunden.', 'es-zh':'Compártelo con alguien.', 'fr-zh':'Partagez avec vos amis.'},
        'leads':{'en-zh':'What would you like to know?', 'de-zh':'Was möchtest du wissen?', 'es-zh':'¿Qué te gustaría saber?', 'fr-zh':'Que voulez-vous savoir ?'},
        'sales':{'en-zh':'Ask us how to order.', 'de-zh':'Frag uns, wie du bestellen kannst.', 'es-zh':'Pregúntanos cómo hacer un pedido.', 'fr-zh':'Demandez-nous comment commander.'},
    }
    tagline = calls_to_action[brief.get('goal','leads')][brief['language']]
    outputs = []
    for index, idea in enumerate(available[:3]):
        target = list(SOCIAL_PLATFORMS)[index] if brief['platform'] == 'overseas' else brief['platform']
        actions = idea['actions']
        caption = idea['caption'][brief['language']]
        shots = []
        for i, action in enumerate(actions):
            shots.append({
                'start':round(brief['duration'] * i / len(actions), 2),
                'end':round(brief['duration'] * (i+1) / len(actions), 2),
                'camera':idea['camera'], 'action':action, 'sfx':idea['sound'],
                'implementation':idea['shoot'], 'line':'', 'translation_zh':'',
                'screen_text':caption if i == 0 else '', 'screen_text_zh':idea['caption_zh'] if i == 0 else '',
                'ai_prompt':f"9:16 竖屏。{idea['camera']}{action} 沿用同一柜台、道具和自然光，按参考素材保持外观一致。保留写字位置，文字后期叠加。",
            })
        visible = idea.get('visible', len(shots))
        title = f"{topic[:40]} · {idea['name']} {batch}"
        output = {
            'target_platform':target, 'title':title, 'body':topic+' · '+caption+' '+tagline,
            'cover_text':idea['name'], 'hook':idea['hooks'][0], 'direction':'实拍短片',
            'angle':idea['angle'], 'role':'用一个画面动作传达主题', 'audience':brief['market']+'的潜在客户',
            'value':'通过'+idea['angle']+'看清主题', 'cta':tagline, 'script':'', 'translation_zh':'',
            'concept':' '.join(actions), 'first_second':idea['hooks'][0], 'misread':idea.get('misread',''), 'clue':idea.get('clue',''),
            'reveal':actions[-1], 'product_role':'主题文字直接出现在道具上。', 'ending_type':'动作传达信息',
            'casting':'仅手部', 'reveal_shot':visible, 'product_reveal':f'第{visible}镜可辨认主题。'+actions[visible-1],
            'production_method':idea['shoot'], 'cost_basis':f"一个人、一个柜台、{len(shots)}镜。准备{idea['props']}。",
            'shoot_setup':{'people':1, 'locations':['柜台旁'], 'props':idea['props'].split('、'), 'simpler_take':''},
            'adaptation':PLATFORMS[target]+'竖屏；文字避开界面遮挡。', 'titles':[idea['name'], topic, tagline],
            'tags':['creative'], 'image_suggestions':['使用项目的实物或主题字卡'], 'storyboard':actions,
            'shooting_list':['拍摄手机',idea['props']], 'missing':['演示拍法，实际对外信息请按项目资料核对。'],
            'comments':[tagline], 'hooks':[{'visual':h,'line':'','translation_zh':'','sfx':idea['sound']} for h in idea['hooks']],
            'shots':shots, 'evidence':[], 'demo':True,
        }
        output['topic_plan'] = {**questions.example(), 'problem':output['concept'], 'approach':'展示'}
        outputs.append(output)
    return outputs


def create(brief,bench,assets,requirements,prompt,batch,previous=None,demo=False,history_results=None,observations=None):
    if demo:
        outputs=demo_outputs(brief,assets,batch);model='demo-visual-shorts'
        validate({'outputs':outputs},brief,assets,previous,require_setup=True)
    else:
        action_edition = VISUAL_ACTION_EDITION in prompt
        objective = content_quality.objective(brief['goal'])
        if action_edition and brief['goal'] == 'reach':
            objective['instruction'] = '让目标观众记住一条值得分享的具体信息。正文只留一个贴题的下一步，活动邀请可以直接请人到场。'
        payload={'brief':brief,'language':LANGUAGES[brief['language']],'assets':assets,'reference':bench,'requirements':requirements,'previous_outputs':previous or [],'history_results':history_results or [],'batch':batch,
                 'objective':objective, 'question_observations':observations or []}
        schema=copy.deepcopy(SCHEMA)
        require_setup = VISUAL_NAME in prompt
        if require_setup:
            item_schema = schema['properties']['outputs']['items']
            item_schema['properties']['shoot_setup'] = SHOOT_SETUP
            item_schema['required'].append('shoot_setup')
        if action_edition:
            fields = schema['properties']['outputs']['items']['properties']
            fields['titles'].update(minItems=3, maxItems=3)
            fields['storyboard']['minItems'] = fields['shooting_list']['minItems'] = 1
            fields['comments']['description'] = '可选的发布后讨论问题，没有时返回空数组。'
        schema['properties']['outputs']['items']['properties']['topic_plan']={
            'type':'object','required':['problem','relevance','answer','takeaway','approach','refs'],
            'properties':{**{key:{'type':'string','maxLength':600} for key in ('problem','relevance','answer','takeaway')},
                          'approach':{'enum':['比较','反差','风险说明','判断','答疑','故事','展示']},
                          'refs':{'type':'array','maxItems':3,'items':{'type':'object','required':['id','quote'],'properties':{'id':{'type':'string'},'quote':{'type':'string','maxLength':500}}}}}}
        schema['properties']['outputs']['items']['required'].append('topic_plan')
        def validator(result):
            validate(result,brief,assets,previous,require_setup=require_setup,action_edition=action_edition)
            if observations is not None:
                questions.validate(result['outputs'],observations)
        instructions=questions.INSTRUCTION + "\n海外创作的客户问题仅作场景线索，展示、邀请和故事均可，不强制答疑。内部选题依据用中文。不同市场与平台的需求不能默认相同。history_results 保留实际 platform，只有与当前方案 target_platform 相同的效果可作比较。"
        result,model=adapters.model_json(payload,schema,prompt+'\n'+instructions,kind='create',validator=validator)
        outputs=result['outputs']
        for output in outputs:
            output.pop('demo',None)
    if observations is not None or demo:
        questions.attach(outputs,observations or [],demo=demo)
    method = VISUAL_NAME if demo or VISUAL_NAME in prompt else ('hiccai-pop v2.2.0' if 'hiccai-pop v2.2' in prompt else '海外创作')
    for output in outputs:
        output['storyboard']=[f"{s['start']}–{s['end']}s | {s['camera']} | {s['action']} | {s['line']} / {s['translation_zh']} | {s['screen_text']} | {s['sfx']} | {s['implementation']}" for s in output['shots']]
        output['overseas']={'platform':output['target_platform'],'market':brief['market'],'language':brief['language'],'duration':brief['duration'],'skill':method}
        output['goal']=brief['goal']
        output['quality']=content_quality.assess(output,assets,brief['platform'])
    return outputs,model
