"""Bounded project reads with stable keyset cursors and lazy private media."""
import base64
import json
from .db import db
from .ranking import score
from . import catalog, production

COLLECTIONS={'sources':'source_contents','creations':'creation_outputs','assets':'assets','images':'generated_images'}


def source_view(c,row):
    value=dict(row)
    value['data']=json.loads(value['data'])
    if value['data'].get('kind')!='brief':
        value['ranking']=score(value['data'])
        value['classification']=catalog.classify(value['data'])
        value['selection_reasons']=catalog.evidence(value['data'],value['ranking'])
        analysis=c.execute('SELECT data FROM analysis_outputs WHERE source_id=? ORDER BY created_at DESC LIMIT 1',(value['id'],)).fetchone()
        value['analysis']=json.loads(analysis[0]) if analysis else {}
    return value


def creation_view(c,row):
    value=dict(row);ident=value['id']
    value['data']=json.loads(value['data'])
    value['revision']=c.execute('SELECT COALESCE(MAX(revision),0) FROM creation_revisions WHERE creation_id=?',(ident,)).fetchone()[0]
    value['tracking']=production.row_view(c.execute('SELECT * FROM creation_tracking WHERE creation_id=?',(ident,)).fetchone())
    results=c.execute('SELECT data,updated_at FROM creation_results WHERE creation_id=?',(ident,)).fetchone()
    value['results']={**json.loads(results[0]),'recorded_at':results[1]} if results else {}
    return value


def image_view(row, project):
    value = dict(row)
    value['data'] = json.loads(value['data']) if isinstance(value['data'], str) else dict(value['data'])
    url = value['data'].get('url', '')
    # Historical provider URLs stay navigable without a cross-origin fetch. Inline
    # media remains private and is only read when the browser displays/exports it.
    if not isinstance(url, str) or not url.startswith('https://') or any(ord(c) <= 32 or ord(c) == 127 for c in url):
        url = f"/api/media/images/{value['id']}?project_id={project}"
    value['data']['url'] = url
    return value


def page(project,raw='',limit=25):
    if type(limit) is not int or not 1<=limit<=50:raise ValueError('每页数量需为 1–50')
    cursors={}
    if raw:
        try:
            if len(raw)>2000:raise ValueError()
            cursors=json.loads(base64.urlsafe_b64decode(raw+'='*(-len(raw)%4)))
            if not isinstance(cursors,dict) or set(cursors)-set(COLLECTIONS):raise ValueError()
            for value in cursors.values():
                if value is not False and (not isinstance(value,list) or len(value)!=2 or any(not isinstance(v,str) or len(v)>100 for v in value)):raise ValueError()
        except Exception:raise ValueError('分页游标无效')
    result={name:[] for name in (*COLLECTIONS,'briefs')};next_cursors={};more=False
    with db() as c:
        for name,table in COLLECTIONS.items():
            previous=cursors.get(name)
            if previous is False:
                next_cursors[name]=False;continue
            query=f'SELECT * FROM {table} WHERE project_id=?'
            if name=='assets':
                query="SELECT id,project_id,name,kind,CASE WHEN kind='图片' THEN '' ELSE substr(content,1,1000) END AS content,length(content)>1000 AND kind!='图片' AS content_truncated,created_at FROM assets WHERE project_id=?"
            if name=='images':
                query="SELECT id,project_id,creation_id,json_set(data,'$.url',CASE WHEN substr(json_extract(data,'$.url'),1,8)='https://' THEN json_extract(data,'$.url') ELSE '' END) AS data,task_id,created_at FROM generated_images WHERE project_id=?"
            values=[project]
            if name=='creations':query+=' AND deleted_at IS NULL'
            if previous:
                query+=' AND (created_at,id)<(?,?)';values.extend(previous)
            query+=' ORDER BY created_at DESC,id DESC LIMIT ?';values.append(limit+1)
            rows=c.execute(query,values).fetchall()
            has_more=len(rows)>limit;rows=rows[:limit]
            next_cursors[name]=[rows[-1]['created_at'],rows[-1]['id']] if has_more else False
            more=more or has_more
            for row in rows:
                if name=='sources':
                    value=source_view(c,row)
                    result['briefs' if value['data'].get('kind')=='brief' else 'sources'].append(value)
                    continue
                if name=='creations':value=creation_view(c,row)
                else:value=dict(row)
                if name=='assets' and value['kind']=='图片':
                    value['content']=f"/api/media/assets/{value['id']}?project_id={project}"
                if name=='images':
                    value=image_view(row,project)
                result[name].append(value)
    result['pagination']={'more':more,'cursor':base64.urlsafe_b64encode(json.dumps(next_cursors).encode()).decode().rstrip('=') if more else None,'limit':limit}
    return result
