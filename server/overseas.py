"""Viral creative production using existing model routing, queue and credits."""
import copy
from . import adapters, content_quality
from .overseas_library import PLATFORMS as SOCIAL_PLATFORMS

LANGUAGES = {'en-zh':'English','es-zh':'Spanish','fr-zh':'French','de-zh':'German'}
PLATFORMS = {'overseas':'TikTok + Reels + Shorts', **SOCIAL_PLATFORMS}
ENDINGS = ('故事翻牌', '反转后硬广', '结果先行演示')


def string_fields(names):
    return {k:{'type':'string'} for k in names}


OUTPUT_SCHEMA = {
    'type':'object', 'properties':{
        **string_fields(('title','body','cover_text','hook','direction','angle','role','audience','value','cta','script','translation_zh','adaptation','first_second','misread','clue','reveal','product_role','ending_type','production_method','cost_basis','casting','product_reveal')),
        'reveal_shot':{'type':'integer','minimum':1,'maximum':6},
        **{k:{'type':'array','items':{'type':'string'}} for k in ('titles','tags','image_suggestions','storyboard','shooting_list','missing','comments')},
        'hooks':{'type':'array','minItems':3,'maxItems':3,'items':{'type':'object','properties':string_fields(('visual','line','translation_zh','sfx')),'required':['visual','line','translation_zh','sfx']}},
        'shots':{'type':'array','items':{'type':'object','properties':{**string_fields(('camera','action','line','translation_zh','screen_text','sfx','implementation')),'start':{'type':'number'},'end':{'type':'number'}},'required':['start','end','camera','action','line','translation_zh','screen_text','sfx','implementation']}},
        'evidence':{'type':'array','items':{'type':'object','properties':string_fields(('asset_id','quote')),'required':['asset_id','quote']}},
        'target_platform':{'type':'string','enum':list(SOCIAL_PLATFORMS)},
    },
}
OUTPUT_SCHEMA['required']=list(OUTPUT_SCHEMA['properties'])
SCHEMA={'type':'object','properties':{'outputs':{'type':'array','minItems':3,'maxItems':3,'items':OUTPUT_SCHEMA}},'required':['outputs']}


def validate(result,brief,assets,previous=None):
    outputs=result.get('outputs') if isinstance(result,dict) else None
    if not isinstance(outputs,list) or len(outputs)!=3: raise ValueError('海外创作需要3个完整创意方案')
    if brief['platform']=='overseas' and {o.get('target_platform') for o in outputs if isinstance(o,dict)}!=set(SOCIAL_PLATFORMS): raise ValueError('三平台创作需要TikTok、Reels、Shorts各一个方案')
    for output in outputs:
        if not isinstance(output,dict): raise ValueError('创意方案格式错误')
        if output.get('target_platform') not in SOCIAL_PLATFORMS or (brief['platform']!='overseas' and output['target_platform']!=brief['platform']): raise ValueError('方案的平台与要求不一致')
        for key in ('title','body','cover_text','hook','direction','angle','role','audience','value','cta','script','translation_zh','first_second','misread','clue','reveal','product_role','ending_type','production_method','cost_basis','casting','product_reveal'):
            if not isinstance(output.get(key),str) or not output[key].strip() or len(output[key])>30000: raise ValueError('创意缺少有效字段：'+key)
        if output['ending_type'] not in ENDINGS: raise ValueError('收尾方式无效')
        if output['casting'] not in ('有人','仅手部','无人'): raise ValueError('请标明有人、仅手部或无人出镜')
        for key in ('titles','tags','image_suggestions','storyboard','shooting_list','missing','comments'):
            value=output.get(key)
            if not isinstance(value,list) or len(value)>60 or any(not isinstance(v,str) or len(v)>6000 for v in value): raise ValueError('创意列表字段无效：'+key)
        if len(output['titles'])!=3 or not output['storyboard'] or not output['shooting_list'] or not output['comments']: raise ValueError('缺少标题、分镜、拍摄清单或评论问题')
        if len(output['tags'])>20: raise ValueError('话题最多20个')
        hooks=output.get('hooks')
        if not isinstance(hooks,list) or len(hooks)!=3: raise ValueError('每个方案必须有3个Hook')
        for hook in hooks:
            if not isinstance(hook,dict) or any(not isinstance(hook.get(k),str) or not hook[k].strip() or len(hook[k])>4000 for k in ('visual','line','translation_zh','sfx')): raise ValueError('Hook缺少画面、台词、中译或音效')
        if len({content_quality.normalized(h['visual']+h['line']) for h in hooks})!=3: raise ValueError('3个Hook不能只是换标点')
        shots=output.get('shots')
        if not isinstance(shots,list) or not 3<=len(shots)<=6: raise ValueError('默认拍摄方案需要3–6镜')
        reveal_shot=output.get('reveal_shot')
        if type(reveal_shot) is not int or not 1<=reveal_shot<=len(shots): raise ValueError('请标明有效的产品首次揭晓镜号')
        if output['ending_type']=='故事翻牌' and reveal_shot!=len(shots): raise ValueError('故事翻牌需要在最后一镜首次揭晓产品')
        cursor=0
        for shot in shots:
            if not isinstance(shot,dict) or any(not isinstance(shot.get(k),str) or len(shot[k])>6000 for k in ('camera','action','line','translation_zh','screen_text','sfx','implementation')): raise ValueError('分镜字段无效')
            start,end=shot.get('start'),shot.get('end')
            if type(start) not in (int,float) or type(end) not in (int,float) or abs(start-cursor)>.01 or not start<end<=brief['duration']: raise ValueError('分镜时间必须从0秒连续覆盖目标时长')
            if not shot['camera'].strip() or not shot['action'].strip() or not shot['implementation'].strip(): raise ValueError('分镜缺少具体画面动作或实现方法')
            cursor=end
        if abs(cursor-brief['duration'])>.01: raise ValueError('分镜总时长与目标时长不一致')
        evidence=output.get('evidence')
        if not isinstance(evidence,list) or (evidence and not content_quality.evidence_valid(output,assets)): raise ValueError('业务事实引用未匹配所选资料')
    for field in ('title','script','body','angle','first_second','misread','reveal'):
        if len({content_quality.normalized(o[field]) for o in outputs})!=3: raise ValueError('方案不能重复：'+field)
    if {content_quality.normalized(o['title']) for o in outputs} & {content_quality.normalized(o.get('title','')) for o in previous or []}: raise ValueError('请避开历史创意标题')


def benchmark(project,brief):
    selected=brief.get('reference_snapshot')
    return {'examples':[selected] if selected else [],'keyword':brief.get('keyword') or brief['topic'],'note':'仅使用用户主动选择的参考；旧版案例仅供启发，不要求套用案例结构、产品事实或复杂拍法。'}


def demo_outputs(brief,assets,batch):
    """Three visibly different demo directions; product facts need live generation."""
    ideas=[
        {
            'name':'放大的影子','angle':'尺度误判','casting':'无人',
            'first_second':'墙面中央一块抽象影子突然变大，观众会问有什么巨物靠近。',
            'misread':'观众以为一个很大的物体正向桌面靠近。',
            'clue':'固定画面右下角始终可见台灯投出的光圈，影子与光圈方向一致。',
            'reveal':'最后同轴宽景露出靠近台灯的小产品实物；先前看似巨物接近的影子其实是近距离投影。',
            'product_role':'产品真实轮廓是影子的来源，不演示或宣称未知性能。',
            'line':'A big shadow. A small surprise.','translation':'一个大影子，一个小惊喜。',
            'props':'台灯、杯子','implementation':'手机固定拍墙面近景，灯和产品在画外；操作者画外调整灯位，末镜同轴切宽景，露出真实产品与灯的位置。',
            'actions':['墙面中央出现一块不完整的抽象影子，杯子影子停在画面左下角','墙面影子变大，仍只拍局部形状，不露可辨认的产品轮廓','右下角的灯光光圈与影子的移动方向同时可见','影子停住，保持杯子和光圈位置；切同轴宽景','最后宽景首次露出真实产品、台灯和杯子的位置关系，解释刚才被放大的影子'],
        },
        {
            'name':'桌面上的秘密检查','angle':'目的误判','casting':'有人',
            'first_second':'一人将桌面中央的空白纸推到一旁，用尺子严肃地比划空位，观众会问他在查什么。',
            'misread':'观众以为人物在寻找一件丢失物品留下的痕迹。',
            'clue':'画面右边的白色反光卡与墙上柔和光斑一直可见，提示这里可能是拍摄布景。',
            'reveal':'最后同角度宽景首次露出真实产品和拍摄手机；前面的测量与检查原来是在为产品照片布置位置。',
            'product_role':'产品是前序布光与定位动作的目的；具体卖点需结合用户资料完善。',
            'line':'Every detail has a purpose.','translation':'每个细节都有它的目的。',
            'props':'尺子、反光纸卡','implementation':'手机固定于桌沿，一名演员从画面左侧进入；产品提前放在近景画外，末镜切到同轴宽景，露出完整布景。',
            'actions':['人物从画面左侧把白纸推开，在桌面中央用尺子比划一个空位','近景拍人物把尺子挪一格，认真观察空位，产品仍在画外','人物调整画面右侧的反光纸卡，墙上光斑移动','人物举起另一部拍摄手机，近景仅拍手机背面，随后切同轴宽景','最后宽景首次露出产品在预留位置、反光卡与拍摄手机，解释之前的测量是在布置产品照片'],
        },
        {
            'name':'缺了一块的图案','angle':'身份误判','casting':'无人',
            'first_second':'桌面中央两张卡片分开一格，露出一段弯曲线条，观众会问这是什么路线图。',
            'misread':'观众以为画面里是正在拼合的一张路线图。',
            'clue':'被露出的局部线条旁始终有真实产品照片的光影渐变，而不是地图标记。',
            'reveal':'最后两张卡片移到两边，首次完整露出用户产品照片；先前的路线其实是产品外形边缘。',
            'product_role':'产品真实外观让图案获得新的含义；使用用户产品照片，不虚构产品效果。',
            'line':'Not the map you expected.','translation':'这不是你想象中的地图。',
            'props':'两张遮挡纸卡','implementation':'使用用户产品照片或实拍打印图；手机俯拍，停机后移动纸卡再拍，操作者始终在画外，末镜完整揭开照片。',
            'actions':['俯拍桌面中央两张遮挡卡片，只露出照片的一小段非识别性线条','停机移动左卡片一格，露出另一段弯曲线条，保持同机位','再露出一小块照片的光影渐变，仍遮住品牌与可辨认部件','两张卡片停在照片中央两侧，保留同一空间线索，切相同机位稍宽景','最后移开全部遮挡，首次完整露出真实产品照片，让之前的线条被理解为产品边缘'],
        },
    ]
    outputs=[]
    duration=brief['duration']
    times=[0,1,round(duration*.25,2),round(duration*.55,2),round(duration*.8,2),duration]
    for index,idea in enumerate(ideas):
        target=list(SOCIAL_PLATFORMS)[index] if brief['platform']=='overseas' else brief['platform']
        shots=[{'start':start,'end':end,'camera':'手机固定，保持主体居中与同轴空间关系','action':idea['actions'][i],
                'line':idea['line'] if i==4 else '', 'translation_zh':idea['translation'] if i==4 else '',
                'screen_text':'', 'sfx':'现场环境音', 'implementation':idea['implementation']}
               for i,(start,end) in enumerate(zip(times,times[1:]))]
        outputs.append({
            'target_platform':target,'title':f"{brief['topic'][:40]} · {idea['name']} {batch}",
            'body':idea['line']+f" Explore {brief['topic'][:60]}.",'cover_text':idea['name'],
            'hook':idea['first_second'],'direction':'原创创意建议','angle':idea['angle'],
            'role':'提供一个独立可选的拍摄方向','audience':brief['market']+'的潜在客户',
            'value':'以'+idea['angle']+'引起对产品的注意','cta':'Look closer.',
            'script':idea['line']+' Look closer.','translation_zh':idea['translation']+'再看仔细一点。',
            'first_second':idea['first_second'],'misread':idea['misread'],'clue':idea['clue'],
            'reveal':idea['reveal'],'product_role':idea['product_role'],'ending_type':'故事翻牌',
            'casting':idea['casting'],'reveal_shot':5,'product_reveal':'最后第5镜首次揭晓产品。'+idea['reveal'],
            'production_method':idea['implementation'],
            'cost_basis':f"{1 if idea['casting']=='有人' else 0}人出镜、1人幕后操作，1处桌面，5镜；道具：{idea['props']}。利用固定机位和现有道具省去额外设备。",
            'adaptation':PLATFORMS[target]+'竖屏，字幕避开界面遮挡。',
            'titles':[idea['line'],idea['name'],'Look closer.'],'tags':['product','creative'],
            'image_suggestions':['使用用户真实产品照片或实物，不改动其外观'],
            'storyboard':[f"{shot['start']}–{shot['end']}s | {shot['action']}" for shot in shots],
            'shooting_list':['手机、产品实物或真实产品照片',idea['props'],idea['implementation']],
            'missing':['演示结构模板，未调用AI或实际翻译；正式创意须用真实资料完善产品因果和卖点。'],
            'comments':['Which detail did you notice?' if index==0 else 'Did you guess the purpose?' if index==1 else 'What did the lines look like to you?'],
            'hooks':[{'visual':visual,'line':idea['line'],'translation_zh':idea['translation'],'sfx':'现场环境音'}
                     for visual in (idea['first_second'],'第一帧从另一侧机位拍摄：'+idea['actions'][0],'第一帧从近景切入：'+idea['actions'][2])],
            'shots':shots,'evidence':[],'demo':True,
        })
    return outputs


def create(brief,bench,assets,requirements,prompt,batch,previous=None,demo=False,history_results=None):
    if demo:
        outputs=demo_outputs(brief,assets,batch);model='demo-hiccai-pop'
    else:
        payload={'brief':brief,'language':LANGUAGES[brief['language']],'assets':assets,'reference':bench,'requirements':requirements,'previous_outputs':previous or [],'history_results':history_results or [],'batch':batch,
                 'objective':content_quality.objective(brief['goal'])}
        result,model=adapters.model_json(payload,SCHEMA,prompt,kind='create',validator=lambda r:validate(r,brief,assets,previous))
        outputs=result['outputs']
    for output in outputs:
        output['storyboard']=[f"{s['start']}–{s['end']}s | {s['camera']} | {s['action']} | {s['line']} / {s['translation_zh']} | {s['screen_text']} | {s['sfx']} | {s['implementation']}" for s in output['shots']]
        output['overseas']={'platform':output['target_platform'],'market':brief['market'],'language':brief['language'],'duration':brief['duration'],'skill':'hiccai-pop v2.2.0'}
        output['goal']=brief['goal']
        output['quality']=content_quality.assess(output,assets,brief['platform'])
    return outputs,model
