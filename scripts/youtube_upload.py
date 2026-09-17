#!/usr/bin/env python3
import argparse, json, os, sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN_URL='https://oauth2.googleapis.com/token'
API='https://www.googleapis.com/youtube/v3'
UPLOAD='https://www.googleapis.com/upload/youtube/v3/videos'
EXPECTED_HANDLE=os.environ.get('YOUTUBE_EXPECTED_HANDLE','@TheUnsaidYetSaid').lower()


def request_json(url, method='GET', data=None, headers=None):
    body=None
    if data is not None:
        body = urlencode(data).encode() if isinstance(data,dict) else data
    req=Request(url,data=body,method=method,headers=headers or {})
    with urlopen(req,timeout=120) as r:
        return json.loads(r.read().decode())


def access_token():
    vals={k:os.environ.get(k,'') for k in ['YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','YOUTUBE_REFRESH_TOKEN']}
    missing=[k for k,v in vals.items() if not v]
    if missing: raise RuntimeError('Missing secrets: '+', '.join(missing))
    out=request_json(TOKEN_URL,'POST',{
        'client_id':vals['YOUTUBE_CLIENT_ID'],'client_secret':vals['YOUTUBE_CLIENT_SECRET'],
        'refresh_token':vals['YOUTUBE_REFRESH_TOKEN'],'grant_type':'refresh_token'})
    return out['access_token']


def verify_channel(token):
    url=API+'/channels?'+urlencode({'part':'snippet','mine':'true'})
    out=request_json(url,headers={'Authorization':'Bearer '+token})
    items=out.get('items',[])
    if len(items)!=1: raise RuntimeError(f'Expected exactly one authorized channel, got {len(items)}')
    ch=items[0]; handle=(ch.get('snippet',{}).get('customUrl') or '').lower()
    title=ch.get('snippet',{}).get('title','')
    if EXPECTED_HANDLE and handle != EXPECTED_HANDLE:
        raise RuntimeError(f'SAFETY STOP: OAuth points to {title} ({handle}), expected {EXPECTED_HANDLE}')
    print(f'Authorized channel verified: {title} ({handle}) / {ch["id"]}')
    return ch


def upload(token,path,title,description,privacy):
    metadata={'snippet':{'title':title,'description':description,'categoryId':'22'},'status':{'privacyStatus':privacy,'selfDeclaredMadeForKids':False}}
    boundary='unsaid_boundary_9f3a'
    meta=json.dumps(metadata).encode(); video=Path(path).read_bytes()
    body=(f'--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n'.encode()+meta+
          f'\r\n--{boundary}\r\nContent-Type: video/mp4\r\n\r\n'.encode()+video+
          f'\r\n--{boundary}--\r\n'.encode())
    url=UPLOAD+'?'+urlencode({'part':'snippet,status','uploadType':'multipart','notifySubscribers':'false'})
    return request_json(url,'POST',body,{'Authorization':'Bearer '+token,'Content-Type':f'multipart/related; boundary={boundary}'})


def main():
    p=argparse.ArgumentParser(); p.add_argument('--file',required=True); p.add_argument('--title',required=True); p.add_argument('--description',default=''); p.add_argument('--privacy',choices=['private','unlisted','public'],default='private'); p.add_argument('--verify-only',action='store_true'); a=p.parse_args()
    token=access_token(); verify_channel(token)
    if a.verify_only: return
    if a.privacy!='private' and os.environ.get('ALLOW_NONPRIVATE_UPLOAD','false').lower()!='true':
        raise RuntimeError('SAFETY STOP: non-private upload not authorized')
    out=upload(token,a.file,a.title,a.description,a.privacy)
    print('Upload successful. Video ID:',out['id'],'Privacy:',out.get('status',{}).get('privacyStatus'))

if __name__=='__main__': main()
