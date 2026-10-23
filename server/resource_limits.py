"""Server-owned bounds; checked inside write transactions, never trusted from forms."""
import os
import shutil
from .db import dumps

MAX_ASSETS_PER_TASK = 12
MAX_TEXT_CHARS = 100000
MAX_INPUT_BYTES = 120000
MAX_IMAGES = 6
MAX_OUTPUT_TOKENS = 8192


def validate_inputs(payload):
    assets = payload.get('asset_snapshot', [])
    if len(assets) > MAX_ASSETS_PER_TASK or len(payload.get('assets', [])) > MAX_ASSETS_PER_TASK:
        raise ValueError('一次最多选择 12 份资料')
    images = [a for a in assets if a.get('kind') == '图片']
    if len(images) > MAX_IMAGES:
        raise ValueError('一次最多选择 6 张图片')
    text = {k: v for k, v in payload.items() if k != 'asset_snapshot'}
    text['asset_snapshot'] = [a for a in assets if a.get('kind') != '图片']
    if len(dumps(text).encode()) > MAX_INPUT_BYTES:
        raise ValueError('本次文字资料合计过大，请精简到约 3 万中文字以内')


def usage(c, user=None):
    total = 0
    for table, column in (('assets','content'),('source_contents','data'),('creation_outputs','data'),
                          ('generated_images','data'),('creation_revisions','data'),('overseas_ideas','data'),
                          ('creation_results','data'),('overseas_searches','ids'),('analysis_outputs','data'),('creation_tracking','checklist')):
        where = ' JOIN projects p ON p.id=t.project_id WHERE p.user_id=?' if user else ''
        if table == 'creation_revisions':
            where = ' JOIN creation_outputs o ON o.id=t.creation_id JOIN projects p ON p.id=o.project_id WHERE p.user_id=?' if user else ''
        if table == 'analysis_outputs':
            where = ' JOIN source_contents s ON s.id=t.source_id JOIN projects p ON p.id=s.project_id WHERE p.user_id=?' if user else ''
        total += c.execute(f'SELECT COALESCE(SUM(length(CAST(t.{column} AS BLOB))),0) FROM {table} t'+where,
                           (user,) if user else ()).fetchone()[0]
    total += c.execute('SELECT COALESCE(SUM(length(CAST(payload AS BLOB))+COALESCE(length(CAST(result AS BLOB)),0)+COALESCE(length(CAST(error AS BLOB)),0)),0) FROM tasks'+(' WHERE user_id=?' if user else ''),
                       (user,) if user else ()).fetchone()[0]
    return total


def check_storage(c, user, extra=0):
    from . import db as database
    if shutil.disk_usage(os.path.dirname(os.path.abspath(database.DB_PATH))).free < int(os.environ.get('DAOLOOK_MIN_FREE_BYTES', 128*1024*1024)):
        raise ValueError('存储空间不足，请联系管理员；未提交新任务')
    if usage(c, user) + max(0,extra) > int(os.environ.get('DAOLOOK_USER_STORAGE_BYTES',100*1024*1024)):
        raise ValueError('账号资料存储额度已满，请清理资料或联系管理员')
    if usage(c) + max(0,extra) > int(os.environ.get('DAOLOOK_TOTAL_STORAGE_BYTES',1024*1024*1024)):
        raise ValueError('服务存储额度已满，请联系管理员')
