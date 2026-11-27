"""Import platform exports into one project's published, version-bound works."""
import csv
import hashlib
import io
import json
import re
from collections import Counter
from decimal import Decimal

from . import production
from .db import dumps, now

PLATFORMS = {'xhs': '小红书', 'douyin': '抖音', 'tiktok': 'TikTok', 'instagram': 'Instagram', 'youtube': 'YouTube'}
TRAFFIC = {'unknown': '未区分', 'organic': '自然', 'paid': '含付费流量'}
PERIODS = {'lifetime': '截至目前', '24h': '24小时', '7d': '7天', '30d': '30天'}
COLUMNS = {'platform': '平台', 'account_id': '账号ID', 'post_id': '作品ID', 'revision': '稿件版本', 'window': '观察期',
           'views': '浏览次数', 'leads': '有效咨询', 'orders': '订单数', 'spend': '投放金额'}
MAX_ROWS = 500
POST = re.compile(r'[A-Za-z0-9_-]{1,128}')


def account(c, project, ident):
    if not isinstance(ident, str) or not c.execute(
        "SELECT 1 FROM assets WHERE project_id=? AND id=? AND kind='账号'", (project, ident)
    ).fetchone():
        raise ValueError('请先在当前项目选择一个发布账号')
    return ident


def binding(c, creation):
    return c.execute('SELECT * FROM publication_bindings WHERE creation_id=?', (creation,)).fetchone()


def validate_spend(traffic, metrics):
    if traffic == 'organic' and (metrics.get('spend') or 0) > 0:
        raise ValueError('自然流量与正数投放金额冲突，请核对发布信息')


def bind(c, creation, project, tracking, fields, previous_tracking):
    old = binding(c, creation)
    row = c.execute('SELECT data FROM creation_results WHERE creation_id=?', (creation,)).fetchone()
    results = json.loads(row[0]) if row else {}
    has_results = any(key in results for key in production.METRICS) or results.get('windows') or results.get('note')
    previous_account = previous_tracking['account_id'] if previous_tracking else None
    if previous_account and previous_account != tracking['account_id'] and has_results:
        raise ValueError('该稿件已记录发布效果，不能将效果转给另一个账号')
    if tracking['status'] != 'published':
        if fields.get('post_id'):
            raise ValueError('请先标记作品已发布')
        return
    post = fields.get('post_id', old['post_id'] if old else '')
    if old and not {'post_id','account_id','traffic_type','status','published_at'}.intersection(fields):
        return
    if not isinstance(post, str) or (post and not POST.fullmatch(post)):
        raise ValueError('请输入平台作品 ID，可使用字母、数字、连字符或下划线，最多 128 位')
    if not old and not post:
        if fields.get('traffic_type') not in (None, 'unknown'):
            raise ValueError('请先绑定作品 ID，再登记这个作品的流量类型')
        return
    account_id = tracking['account_id']
    traffic = fields.get('traffic_type', old['traffic_type'] if old else 'unknown')
    if not isinstance(traffic, str) or traffic not in TRAFFIC:
        raise ValueError('流量类型无效')
    row = c.execute("""
        SELECT COALESCE(json_extract(o.data,'$.target_platform'),s.platform) AS platform,
               COALESCE((SELECT MAX(revision) FROM creation_revisions WHERE creation_id=o.id),0) AS revision
        FROM creation_outputs o JOIN source_contents s ON s.id=o.source_id WHERE o.id=? AND o.project_id=?
    """, (creation, project)).fetchone()
    if not row or row['platform'] not in PLATFORMS:
        raise ValueError('这篇稿件缺少明确的发布平台')
    if old and (old['account_id'], old['post_id'], old['revision']) != (account_id, post, row['revision']):
        if has_results:
            raise ValueError('该作品已记录效果，不能将记录转给另一个作品或版本')
    if not post:
        c.execute('DELETE FROM publication_bindings WHERE creation_id=?', (creation,))
        return
    account(c, project, account_id)
    for snapshot in (results, *production.current_windows(results,tracking['published_at']).values()):
        validate_spend(traffic, snapshot)
    owner = c.execute('SELECT creation_id FROM publication_bindings WHERE project_id=? AND platform=? AND account_id=? AND post_id=?',
                      (project, row['platform'], account_id, post)).fetchone()
    if owner and owner[0] != creation:
        raise ValueError('这个账号的作品 ID 已绑定另一篇稿件')
    c.execute("""INSERT INTO publication_bindings(creation_id,project_id,platform,account_id,post_id,revision,traffic_type)
                 VALUES(?,?,?,?,?,?,?) ON CONFLICT(creation_id) DO UPDATE SET account_id=excluded.account_id,
                 platform=excluded.platform,post_id=excluded.post_id,revision=excluded.revision,traffic_type=excluded.traffic_type""",
              (creation, project, row['platform'], account_id, post, row['revision'], traffic))


def check_scope(c, project, account_id, platform):
    account(c, project, account_id)
    if not isinstance(platform, str) or platform not in PLATFORMS:
        raise ValueError('请选择作品平台')


def template(c, project, account_id, platform):
    check_scope(c, project, account_id, platform)
    stream = io.StringIO(newline='')
    writer = csv.writer(stream)
    writer.writerow(COLUMNS.values())
    rows = c.execute("""SELECT b.post_id,b.revision FROM publication_bindings b
        JOIN creation_tracking k ON k.creation_id=b.creation_id AND k.account_id=b.account_id AND k.status='published'
        JOIN creation_outputs o ON o.id=b.creation_id AND o.deleted_at IS NULL
        WHERE b.project_id=? AND b.platform=? AND b.account_id=? ORDER BY k.published_at DESC,b.creation_id""",
        (project, platform, account_id))
    for row in rows:
        # A literal text prefix survives spreadsheet auto-formatting and keeps
        # leading signs inert. Quoting CSV cells alone does neither in Excel/WPS.
        writer.writerow([platform, 'id:' + account_id, 'id:' + row['post_id'], row['revision'], '截至目前', '', '', '', ''])
    return stream.getvalue().encode('utf-8-sig')


def read_csv(text):
    if not isinstance(text, str) or len(text.encode('utf-8')) > 512 * 1024:
        raise ValueError('CSV 最多 512 KB，请分批导入')
    reader = csv.reader(io.StringIO(text.lstrip('\ufeff'), newline=''), strict=True)
    try:
        columns = {**{v: k for k, v in COLUMNS.items()}, **{k: k for k in COLUMNS}}
        header = [columns.get(s.strip()) for s in next(reader, [])]
        if not {'platform', 'account_id', 'post_id'} <= set(header) or not set(production.METRICS).intersection(header):
            raise ValueError('CSV 需包含平台、账号ID、作品ID及至少一个指标列')
        if len(header) != len(set(header)) or None in header:
            raise ValueError('CSV 包含重复或未识别的列，请使用模板')
        rows = []
        for line, cells in enumerate(reader, 2):
            if not any(s.strip() for s in cells):
                continue
            if len(cells) != len(header):
                raise ValueError(f'第 {line} 行列数与表头不符')
            record = {k: v.strip() for k, v in zip(header, cells)}
            for key in ('account_id', 'post_id'):
                record[key] = record[key].removeprefix('id:')
            if not any(record.get(k) for k in production.METRICS):
                continue
            rows.append((line, record))
            if len(rows) > MAX_ROWS:
                raise ValueError(f'一次最多导入 {MAX_ROWS} 条有数据的记录')
    except csv.Error as exc:
        raise ValueError('CSV 格式不正确，请检查引号和分隔符') from exc
    if not rows:
        raise ValueError('CSV 中还没有可导入的效果值')
    return rows


def period_of(row):
    value = row.get('window') or 'lifetime'
    return next((period for period, label in PERIODS.items() if value in (period, label)), None)


def metrics(row):
    values = {}
    for key in production.METRICS:
        raw = row.get(key)
        if not raw:
            continue
        pattern = r'[0-9]{1,10}(?:\.[0-9]{1,2})?' if key == 'spend' else r'[0-9]{1,10}'
        if not re.fullmatch(pattern, raw) or Decimal(raw) > 1_000_000_000:
            raise ValueError('请检查' + COLUMNS[key] + '，数量须为非负整数，投放金额最多两位小数')
        values[key] = float(raw) if key == 'spend' else int(raw)
    return values


def lookup(c, project, platform, account_id, post):
    return c.execute("""SELECT b.creation_id,b.revision,b.traffic_type,k.published_at,f.data AS results,f.updated_at,
        json_extract(o.data,'$.title') AS title,
        COALESCE((SELECT MAX(revision) FROM creation_revisions WHERE creation_id=o.id),0) AS current_revision
        FROM publication_bindings b JOIN creation_tracking k ON k.creation_id=b.creation_id AND k.account_id=b.account_id
        JOIN creation_outputs o ON o.id=b.creation_id AND o.project_id=b.project_id
        LEFT JOIN creation_results f ON f.creation_id=b.creation_id
        WHERE b.project_id=? AND b.platform=? AND b.account_id=? AND b.post_id=? AND k.status='published' AND o.deleted_at IS NULL""",
        (project, platform, account_id, post)).fetchone()


def plan(c, project, account_id, platform, text):
    check_scope(c, project, account_id, platform)
    rows = read_csv(text)
    counts = Counter((r.get('post_id'), period_of(r)) for _, r in rows)
    preview, pending, stamps = [], {}, {}
    stamp = now()
    for line, row in rows:
        post, period = row['post_id'], period_of(row)
        item = {'line': line, 'post_id': post, 'window': period}
        preview.append(item)
        try:
            if row['platform'] not in (platform, PLATFORMS[platform]) or row['account_id'] != account_id:
                raise ValueError('平台或账号与所选范围不同')
            if not period:
                raise ValueError('观察期无效')
            if counts[post, period] > 1:
                raise ValueError('同一作品和观察期在表内重复')
            found = lookup(c, project, platform, account_id, post)
            if not found:
                raise ValueError('找不到已发布并绑定此作品 ID 的稿件')
            if found['current_revision'] != found['revision'] or row.get('revision') not in (None, '', str(found['revision'])):
                raise ValueError('稿件版本与已绑定版本不符')
            cid = found['creation_id']
            item.update(creation_id=cid, title=found['title'], revision=found['revision'], traffic_type=found['traffic_type'])
            stamps[cid] = (found['updated_at'],found['published_at'],found['traffic_type'],found['revision'])
            previous = pending.get(cid, json.loads(found['results'] or '{}'))
            before = previous if period == 'lifetime' else production.current_windows(previous,found['published_at']).get(period, {})
            supplied = metrics(row)
            validate_spend(found['traffic_type'], supplied)
            combined = {k:before[k] for k in production.METRICS if k in before}
            combined.update(supplied, note=previous.get('note',''))
            merged = production.merge_result(previous, combined, period, found['published_at'], stamp)
            item['changes'] = {k: {'old': before.get(k), 'new': v} for k,v in supplied.items() if before.get(k) != v}
            item['state'] = 'update' if item['changes'] else 'unchanged'
            if item['changes']:
                pending[cid] = merged
        except ValueError as exc:
            item.update(state='error',message=str(exc))
    # A lost response can safely retry the same request when every approved value
    # is now present. Scope that no-op to the same works, publications and versions.
    targets = [(cid, *state[1:]) for cid, state in sorted(stamps.items())]
    identity = hashlib.sha256(dumps([project, account_id, platform, text, targets]).encode()).hexdigest()
    state = hashlib.sha256(dumps([preview, stamps]).encode()).hexdigest()
    fingerprint = identity + '.' + state
    return {'rows': preview, 'token': fingerprint, 'valid': all(item['state']!='error' for item in preview)}, pending, stamp


# Both feedback queries use o (output), k (publication) and r (result).
# A zero counts. Only windows belonging to the current publication qualify.
_GOAL_PATH = """CASE json_extract(o.data,'$.goal')
    WHEN 'sales' THEN '$.orders' WHEN 'leads' THEN '$.leads' WHEN 'reach' THEN '$.views' END"""
HAS_GOAL_METRIC = f"""(json_type(r.data,{_GOAL_PATH})='integer' OR EXISTS (
    SELECT 1 FROM json_each(r.data,'$.windows') w
    WHERE w.key IN ('24h','7d','30d') AND json_extract(w.value,'$.published_at')=k.published_at
      AND json_type(w.value,{_GOAL_PATH})='integer'))"""


def account_summary(c, project):
    accounts = [dict(a) for a in c.execute("SELECT id,name FROM assets WHERE project_id=? AND kind='账号' ORDER BY name,id", (project,))]
    rows = c.execute(f"""
        SELECT k.account_id,COALESCE(b.traffic_type,'unknown') AS traffic_type,
            COALESCE(json_extract(o.data,'$.target_platform'),s.platform) AS platform,
            json_extract(o.data,'$.goal') AS goal,count(*) AS posts
        FROM creation_tracking k JOIN creation_outputs o ON o.id=k.creation_id
        JOIN creation_results r ON r.creation_id=o.id JOIN source_contents s ON s.id=o.source_id
        LEFT JOIN publication_bindings b ON b.creation_id=o.id AND b.account_id=k.account_id
        WHERE o.project_id=? AND o.deleted_at IS NULL AND k.status='published' AND k.account_id IS NOT NULL
          AND COALESCE(json_extract(o.data,'$.demo'),0)=0 AND {HAS_GOAL_METRIC}
        GROUP BY 1,2,3,4
    """,(project,))
    return {'accounts': accounts, 'groups': [dict(r) for r in rows]}
