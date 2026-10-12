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
    for field in ('title','script','body'):
        if len({content_quality.normalized(o[field]) for o in outputs})!=3: raise ValueError('方案不能重复：'+field)
    if {content_quality.normalized(o['title']) for o in outputs} & {content_quality.normalized(o.get('title','')) for o in previous or []}: raise ValueError('请避开历史创意标题')


def benchmark(project,brief):
    selected=brief.get('reference_snapshot')
    return {'examples':[selected] if selected else [],'keyword':brief.get('keyword') or brief['topic'],'note':'仅使用用户主动选择的参考；旧版案例仅供启发，不要求套用案例结构、产品事实或复杂拍法。'}


def demo_outputs(brief,assets,batch):
    output=[];duration=brief['duration']
    # Explicit demo templates; no fabricated product fact or AI translation.
    for index,angle in enumerate(('便签遮挡','道具放错位置','同一物件的两种用途')):
        target=list(SOCIAL_PLATFORMS)[index] if brief['platform']=='overseas' else brief['platform']
        line='Which detail would you check first?'
        caption=f"A closer look at {brief['topic'][:60]}. {line}"
        times=[0,1,round(duration*.25,2),round(duration*.55,2),round(duration*.8,2),duration]
        casting=('无人','有人','无人')[index]
        actions=['固定近景，桌面中央纸卡突然移动一格，画外操作，不露产品','同轴近景，纸卡旁的空隙保持可见，继续隐藏移动来源','固定近景，纸卡移动后留下位置线索，停顿让观众看见','切同轴稍宽景，保留原桌面位置线索；仍不出现产品或品牌','最后切同轴宽景，首次展示真实产品与道具的完整位置关系；正式反转需结合实际产品设计']
        if casting=='有人': actions[1]='中景，人物站在桌面左侧，低头看纸卡的移动方向，产品仍在画外'
        shots=[{'start':start,'end':end,'camera':'手机固定于桌沿高度，桌面近景，主体在画面中央','action':actions[i],'line':line if i==4 else 'Look at this detail.','translation_zh':'你会先检查哪个细节？' if i==4 else '看看这个细节。','screen_text':'Look closer','sfx':'纸张摩擦声','implementation':'一处桌面、固定手机机位，停机后移动道具再拍，操作者留在画外；检查倒影，最后一镜才加入产品实物。'} for i,(start,end) in enumerate(zip(times,times[1:]))]
        data={'target_platform':target,'title':f"{brief['topic'][:50]} · Concept {batch}-{index+1}",'body':caption+f' #{index+1}', 'cover_text':'Look closer','hook':'把道具放进镜头，环境音Click后切到产品特写',
              'direction':'低成本反转创意','angle':angle+f' {batch}','role':'吸引相关受众并引导真实讨论','audience':brief['market']+'的潜在客户','value':'理解产品在具体场景中的用途', 'cta':line,
              'script':f"Concept {index+1}: Look at this detail. {line}", 'translation_zh':f"方案{index+1}：看看这个细节。你会先检查哪个细节？",'operator':'','innovation':'演示用占位故事，正式方案需围绕真实产品重新设计。','loop':'最后一镜构图可呼应开头，揭晓后不追加剧情。','adaptation':PLATFORMS[target]+'竖屏，字幕避开界面遮挡区域。',
              'casting':casting,'reveal_shot':5,'product_reveal':'最后第5镜首次展示产品及其与道具的位置关系。演示占位，需用产品真实作用重新设计。','first_second':'纸卡在桌面中央移动一格，观众会问是谁移动了它。','misread':'观众以为纸卡由画外的人推动。','clue':'纸卡旁的空隙与运动方向始终可见。','reveal':'最后宽景用产品与道具的位置关系解释先前的移动；这是结构占位，需用真实产品完善因果。','product_role':'产品实物提供谜底；演示模板不宣称具体性能。','ending_type':'故事翻牌','production_method':'实拍：手机固定桌沿，停机移动纸卡后再拍，操作者始终在画外，最后同轴切宽景。','cost_basis':f'{1 if casting=="有人" else 0}人出镜、1人幕后操作，1处桌面，1张纸卡，5镜；固定机位和自然光，无需特效。',
              'titles':[f'Look closer {index+1}','One detail to check','What would you choose?'],'tags':['product','creative'],'image_suggestions':['使用用户提供的真实产品照片'],'storyboard':[f"{s['start']}–{s['end']}s | {s['camera']} | {s['action']} | {s['line']} / {s['translation_zh']} | {s['sfx']}" for s in shots],
              'shooting_list':['产品实物、桌面、便签、手机竖屏机位','确认实际卖点、拍摄假设与购买路径'], 'missing':['演示模板，请在真实服务中生成正式创意'],'comments':[line], 'hooks':[{'visual':v,'line':line,'translation_zh':'你会先检查哪个细节？','sfx':'纸张摩擦声'} for v in ('第一帧便签遮住产品一角','第一帧手指停在便签边缘','第一帧反向掀开便签露出轮廓')], 'shots':shots,'evidence':[], 'demo':True}
        output.append(data)
    return output


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
