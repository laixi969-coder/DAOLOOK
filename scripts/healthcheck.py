"""Container/host probe with a matching public Host header, never an environment proxy."""
import os
import urllib.parse
import urllib.request

origin=os.environ.get('DAOLOOK_PUBLIC_ORIGIN','')
host=urllib.parse.urlsplit(origin).netloc or '127.0.0.1'
url='http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health'
request=urllib.request.Request(url,headers={'Host':host})
with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=5) as response:
    if response.status!=200:raise SystemExit(1)
