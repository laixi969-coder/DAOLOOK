"""Conservative daily cost reservations, in integer micro-USD (1 USD = 1,000,000).

Prices are operator supplied upper bounds, not inferred from arbitrary providers.
Every attempted paid request consumes its full reservation even after an error.
Provider usage is kept separately; this is not a provider invoice reconciliation.
"""
import contextvars
import datetime
import json
import os
from contextlib import contextmanager
from .db import db, uid, now

IDENTITY = contextvars.ContextVar('daolook_billing_identity', default=None)


class BudgetExceeded(ValueError):
    pass


@contextmanager
def scope(user=None, task=None, paid=None):
    token = IDENTITY.set({'user':user, 'task':task, 'paid':paid})
    try:
        yield
    finally:
        IDENTITY.reset(token)


def identify(user):
    old = IDENTITY.get() or {}
    IDENTITY.set({**old, 'user':user})


def reserve(operation, payload):
    from . import access, resource_limits
    identity = IDENTITY.get()
    paid = identity.get('paid') if identity else None
    if not operation:
        return None
    if paid is False:
        raise BudgetExceeded('演示任务不能调用真实付费服务')
    if not identity or not identity.get('user'):
        raise BudgetExceeded('付费调用缺少账号归属，已阻止')
    try:
        prices = json.loads(os.environ.get('DAOLOOK_EXTERNAL_PRICES', '{}'))
        if not isinstance(prices, dict):
            raise ValueError()
        price = prices[operation]
        if not isinstance(price, dict):
            raise ValueError()
        numbers = [price.get(k,0) for k in ('per_call','input_per_million','output_per_million','per_image')]
        if any(type(n) is not int or n < 0 for n in numbers):
            raise ValueError()
        inputs = 0
        images = 0
        if isinstance(payload,dict) and 'messages' in payload:
            if not isinstance(payload['messages'], list):
                raise ValueError()
            clean=[]
            for message in payload['messages']:
                if not isinstance(message, dict):
                    raise ValueError()
                message=dict(message)
                if isinstance(message.get('content'),list):
                    parts=[]
                    for part in message['content']:
                        if not isinstance(part, dict):
                            raise ValueError()
                        if part.get('type')=='image_url':images+=1
                        else:parts.append(part)
                    message['content']=parts
                clean.append(message)
            # UTF-8 bytes plus framing is a deliberately conservative text token bound.
            inputs=len(json.dumps(clean,ensure_ascii=False).encode())+64*len(clean)
            if inputs > 140000 or images > 6:
                raise BudgetExceeded('模型输入超出上限，请减少资料或图片')
            if not price.get('input_per_million') or not price.get('output_per_million') or (images and not price.get('per_image')):
                raise ValueError()
        elif not price.get('per_call'):
            raise ValueError()
        output = payload.get('max_tokens',0) if isinstance(payload,dict) else 0
        if type(output) is not int or not 0 <= output <= resource_limits.MAX_OUTPUT_TOKENS or (inputs and not output):
            raise ValueError()
        # Integer rounding keeps large operator supplied prices conservative.
        ceiling = price.get('per_call',0) + (inputs*price.get('input_per_million',0)+999999)//1000000 + (output*price.get('output_per_million',0)+999999)//1000000 + images*price.get('per_image',0)
        if not 0 < ceiling <= 2**63-1:
            raise ValueError()
    except BudgetExceeded:
        raise
    except (KeyError,ValueError,TypeError):
        raise BudgetExceeded('管理员尚未配置此服务的费用上限，付费调用已暂停：'+operation)
    try:
        global_limit=int(os.environ.get('DAOLOOK_DAILY_BUDGET_MICROUSD','20000000'))
        personal_limit=int(os.environ.get('DAOLOOK_USER_DAILY_BUDGET_MICROUSD','2000000'))
        if min(global_limit,personal_limit) < 0 or max(global_limit,personal_limit) > 2**63-1:
            raise ValueError()
    except ValueError:
        raise BudgetExceeded('外部服务费用额度配置无效，付费调用已暂停')
    day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        try:
            access.require_live(c, identity['user'])
        except ValueError as error:
            raise BudgetExceeded(str(error)) from error
        total,personal=c.execute('SELECT COALESCE(SUM(reserved),0),COALESCE(SUM(CASE WHEN user_id=? THEN reserved ELSE 0 END),0) FROM external_calls WHERE day=?',
                                 (identity['user'],day)).fetchone()
        if total+ceiling>global_limit or personal+ceiling>personal_limit:
            raise BudgetExceeded('今日外部服务费用额度已用完，请明天重试或联系管理员')
        ident=uid()
        c.execute('INSERT INTO external_calls VALUES (?,?,?,?,?,?,?,?,?,?)',
                  (ident,identity['user'],identity.get('task'),operation,day,ceiling,'started',None,None,now()))
    return ident


def finish(ident, result=None, failed=False):
    if not ident:return
    usage=(result or {}).get('usage',{}) if isinstance(result,dict) else {}
    if not isinstance(usage,dict):usage={}
    def count(key):
        n=usage.get(key)
        return n if type(n) is int and 0<=n<=2**63-1 else None
    with db() as c:
        c.execute('UPDATE external_calls SET state=?,input_tokens=?,output_tokens=? WHERE id=?',
                  ('failed' if failed else 'responded',count('prompt_tokens'),count('completion_tokens'),ident))
