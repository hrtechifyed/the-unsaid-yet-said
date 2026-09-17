#!/usr/bin/env python3
import argparse, json, mimetypes, os
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

TOKEN_URL='https://oauth2.googleapis.com/token'
API='https://www.googleapis.com/youtube/v3'
UPLOAD='https://www.googleapis.com/upload/youtube/v3/videos'
THUMB_UPLOAD='https://www.googleapis.com/upload/youtube/v3/thumbnails/set'
EXPECTED_HANDLE=os.environ.get('YOUTUBE_EXPECTED_HANDLE','@TheUnsaidYetSaid').lower()
CHUNK_SIZE=8*1024*1024


def _safe_google_error(exc):
    try:
        raw=exc.read().decode('utf-8','replace'); payload=json.loads(raw); err=payload.get('error',{})
        message=err.get('message',str(exc)); reasons=[]
        for item in err.get('errors',[]) or []:
            reason=item.get('reason')
            if reason and reason not in reasons: reasons.append(reason)
        status=err.get('status'); parts=[f'Google API HTTP {exc.code}']
        if status: parts.append(f'status={status}')
        if reasons: parts.append('reason='+','.join(reasons))
        parts.append('message='+message); return ' | '.join(parts)
    except Exception:
        return f'Google API HTTP {getattr(exc,"code","unknown")}: {getattr(exc,"reason",str(exc))}'


def request_json(url,method='GET',data=None,headers=None,timeout=180):
    body=None
    if data is not None: body=urlencode(data).encode() if isinstance(data,dict) else data
    req=Request(url,data=body,method=method,headers=headers or {})
    try:
        with urlopen(req,timeout=timeout) as r:
            raw=r.read().decode(); return json.loads(raw) if raw else {}
    except HTTPError as exc:
        raise RuntimeError(_safe_google_error(exc)) from None


def access_token():
    vals={k:os.environ.get(k,'') for k in ['YOUTUBE_CLIENT_ID','YOUTUBE_CLIENT_SECRET','YOUTUBE_REFRESH_TOKEN']}
    missing=[k for k,v in vals.items() if not v]
    if missing: raise RuntimeError('Missing secrets: '+', '.join(missing))
    out=request_json(TOKEN_URL,'POST',{'client_id':vals['YOUTUBE_CLIENT_ID'],'client_secret':vals['YOUTUBE_CLIENT_SECRET'],'refresh_token':vals['YOUTUBE_REFRESH_TOKEN'],'grant_type':'refresh_token'})
    if 'access_token' not in out: raise RuntimeError('OAuth token refresh returned no access token')
    return out['access_token']


def verify_channel(token):
    url=API+'/channels?'+urlencode({'part':'snippet','mine':'true'})
    try: out=request_json(url,headers={'Authorization':'Bearer '+token})
    except RuntimeError as exc: raise RuntimeError('CHANNEL VERIFICATION FAILED: '+str(exc)) from None
    items=out.get('items',[])
    if len(items)!=1: raise RuntimeError(f'Expected exactly one authorized channel, got {len(items)}')
    ch=items[0]; handle=(ch.get('snippet',{}).get('customUrl') or '').lower(); title=ch.get('snippet',{}).get('title','')
    if EXPECTED_HANDLE and handle!=EXPECTED_HANDLE: raise RuntimeError(f'SAFETY STOP: OAuth points to {title} ({handle}), expected {EXPECTED_HANDLE}')
    print(f'Authorized channel verified: {title} ({handle}) / {ch["id"]}'); return ch


def get_video(token,video_id):
    out=request_json(API+'/videos?'+urlencode({'part':'snippet,status','id':video_id}),headers={'Authorization':'Bearer '+token})
    items=out.get('items',[])
    if len(items)!=1: raise RuntimeError(f'Expected one YouTube video for id {video_id}, got {len(items)}')
    return items[0]


def _start_resumable(token,path,title,description,privacy):
    size=Path(path).stat().st_size
    metadata={'snippet':{'title':title,'description':description,'categoryId':'22'},'status':{'privacyStatus':privacy,'selfDeclaredMadeForKids':False}}
    url=UPLOAD+'?'+urlencode({'part':'snippet,status','uploadType':'resumable','notifySubscribers':'false'})
    req=Request(url,data=json.dumps(metadata).encode(),method='POST',headers={
        'Authorization':'Bearer '+token,'Content-Type':'application/json; charset=UTF-8',
        'X-Upload-Content-Type':'video/mp4','X-Upload-Content-Length':str(size)
    })
    try:
        with urlopen(req,timeout=180) as r:
            location=r.headers.get('Location')
            if not location: raise RuntimeError('YouTube resumable upload did not return an upload URL')
            return location,size
    except HTTPError as exc:
        raise RuntimeError('VIDEO UPLOAD INIT FAILED: '+_safe_google_error(exc)) from None


def upload(token,path,title,description,privacy):
    location,total=_start_resumable(token,path,title,description,privacy)
    offset=0; final=None
    with open(path,'rb') as f:
        while offset<total:
            chunk=f.read(min(CHUNK_SIZE,total-offset))
            if not chunk: break
            end=offset+len(chunk)-1
            req=Request(location,data=chunk,method='PUT',headers={
                'Authorization':'Bearer '+token,'Content-Type':'video/mp4','Content-Length':str(len(chunk)),
                'Content-Range':f'bytes {offset}-{end}/{total}'
            })
            try:
                with urlopen(req,timeout=300) as r:
                    raw=r.read().decode(); final=json.loads(raw) if raw else None
                    offset=end+1
            except HTTPError as exc:
                # 308 Resume Incomplete is expected between chunks.
                if exc.code==308:
                    rng=exc.headers.get('Range','')
                    if rng and '-' in rng:
                        offset=int(rng.rsplit('-',1)[1])+1; f.seek(offset)
                    else:
                        offset=end+1
                    continue
                raise RuntimeError('VIDEO UPLOAD FAILED: '+_safe_google_error(exc)) from None
    if not final or 'id' not in final: raise RuntimeError('VIDEO UPLOAD FAILED: resumable session completed without a video resource')
    return final


def set_thumbnail(token,video_id,path):
    data=Path(path).read_bytes(); ctype=mimetypes.guess_type(path)[0] or 'image/jpeg'
    url=THUMB_UPLOAD+'?'+urlencode({'videoId':video_id,'uploadType':'media'})
    try: return request_json(url,'POST',data,{'Authorization':'Bearer '+token,'Content-Type':ctype,'Content-Length':str(len(data))})
    except RuntimeError as exc: raise RuntimeError('THUMBNAIL UPLOAD FAILED: '+str(exc)) from None


def set_privacy(token,video_id,privacy):
    if privacy not in {'private','unlisted','public'}: raise RuntimeError('Invalid privacy state')
    current=get_video(token,video_id); status=current.get('status',{})
    body=json.dumps({'id':video_id,'status':{'privacyStatus':privacy,'selfDeclaredMadeForKids':status.get('selfDeclaredMadeForKids',False)}}).encode()
    try: return request_json(API+'/videos?'+urlencode({'part':'status'}),'PUT',body,{'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    except RuntimeError as exc: raise RuntimeError('VIDEO STATUS UPDATE FAILED: '+str(exc)) from None


def main():
    p=argparse.ArgumentParser(); p.add_argument('--file'); p.add_argument('--title'); p.add_argument('--description',default=''); p.add_argument('--privacy',choices=['private','unlisted','public'],default='private'); p.add_argument('--thumbnail'); p.add_argument('--verify-only',action='store_true'); a=p.parse_args()
    token=access_token(); verify_channel(token)
    if a.verify_only: return
    if not a.file or not a.title: raise RuntimeError('--file and --title are required unless --verify-only is used')
    if a.privacy!='private' and os.environ.get('ALLOW_NONPRIVATE_UPLOAD','false').lower()!='true': raise RuntimeError('SAFETY STOP: non-private upload not authorized')
    out=upload(token,a.file,a.title,a.description,a.privacy); video_id=out['id']
    if a.thumbnail: set_thumbnail(token,video_id,a.thumbnail)
    print('Upload successful. Video ID:',video_id,'Privacy:',out.get('status',{}).get('privacyStatus'))

if __name__=='__main__': main()
