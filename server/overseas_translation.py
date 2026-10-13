"""Chinese display translations; originals stay intact and inference stays local."""
import hashlib
import json
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from .db import db, now

ROOT = Path(__file__).resolve().parent.parent
REVIEWED = json.loads((ROOT/'server/resources/hiccai-pop/translations-zh.json').read_text())
RUNTIME = ROOT/'.venv-translation/bin/python'
WORKER = ROOT/'scripts/translate_local.py'
PENDING = queue.Queue(maxsize=1000)
LOCK = threading.Lock()
QUEUED = set()
FAILED = {}
RUNNING = False


def key(text):
    return 'zh-v2:'+hashlib.sha256(text.encode()).hexdigest()


def needs_translation(text):
    return isinstance(text,str) and bool(re.search(r'[A-Za-z]{2}',text)) and not re.search(r'[\u4e00-\u9fff]',text)


def enqueue(text):
    if not RUNNING or not RUNTIME.exists():return
    with LOCK:
        if text in QUEUED or time.monotonic()<FAILED.get(text,0):return
        try:PENDING.put_nowait(text)
        except queue.Full:return
        QUEUED.add(text)


def enrich(item):
    """Read cache only on HTTP paths; never block a request on model inference."""
    value={**item}
    video={**item.get('reference_video',{})}
    targets=[(value,'title'),(value,'summary'),(video,'title')]
    texts={target.get(field,'') for target,field in targets if needs_translation(target.get(field))}
    cached={}
    if texts:
        with db() as c:
            marks=','.join('?' for _ in texts)
            cached={r['key']:r['translated'] for r in c.execute('SELECT key,translated FROM overseas_translations WHERE key IN ('+marks+')',tuple(key(t) for t in texts))}
    for target,field in targets:
        original=target.get(field,'')
        # Always derive from exact original text: an edited caption cannot inherit an old translation.
        target.pop(field+'_zh',None)
        translated=REVIEWED.get(original) or cached.get(key(original))
        if translated:target[field+'_zh']=translated
        elif original in texts:enqueue(original)
    if video:value['reference_video']=video
    return value


def translate_batch(texts):
    result=subprocess.run([str(RUNTIME),str(WORKER)],input=json.dumps(texts,ensure_ascii=False),
                          capture_output=True,text=True,timeout=180,check=True,cwd=str(ROOT))
    values=json.loads(result.stdout)
    if not isinstance(values,list) or len(values)!=len(texts):raise ValueError('Translation response invalid')
    return values


def drain():
    texts=[]
    while len(texts)<16:
        try:texts.append(PENDING.get_nowait())
        except queue.Empty:break
    if not texts:return False
    try:
        values=translate_batch(texts)
    except (OSError,subprocess.SubprocessError,ValueError):
        values=[None]*len(texts)
    with db() as c:
        for original,translated in zip(texts,values):
            valid=isinstance(translated,str) and translated.strip() and len(translated)<=40000 and re.search(r'[\u4e00-\u9fff]',translated)
            if valid:c.execute('INSERT OR REPLACE INTO overseas_translations VALUES (?,?,?)',(key(original),translated.strip(),now()))
            with LOCK:
                QUEUED.discard(original)
                if not valid:FAILED[original]=time.monotonic()+600
            PENDING.task_done()
    return True


def start():
    global RUNNING
    if RUNNING:return
    RUNNING=True
    def loop():
        while True:
            try:
                # Prioritize current TikTok references; also prepare optional archive translations.
                values=public_items()
                videos=json.loads((ROOT/'server/resources/hiccai-pop/reference-videos.json').read_text())
                for item in values:enrich(item)
                for video in videos:enrich({'reference_video':video})
                while drain():pass
            except Exception:
                import traceback
                traceback.print_exc()
            time.sleep(30)
    threading.Thread(target=loop,daemon=True,name='overseas-translation').start()


def public_items():
    with db() as c:
        values=[json.loads(r[0]) for r in c.execute('SELECT data FROM overseas_feed_videos ORDER BY published_at DESC')]
    return sorted(values,key=lambda item:item.get('platform')!='tiktok')


def pending():
    with LOCK:return bool(QUEUED)
