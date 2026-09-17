#!/usr/bin/env python3
"""Final production gate. Only explicit repository-owner commands can change a PRIVATE preview."""
import json, os, re, sys, urllib.request
from pathlib import Path

REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said')
TOKEN=os.environ.get('GITHUB_TOKEN','')
EVENT=os.environ.get('GITHUB_EVENT_PATH','')
OWNER=os.environ.get('GITHUB_REPOSITORY_OWNER','')
MIN_DURATION_SECONDS=360
MIN_NARRATION_WORDS=900


def gh(url,method='GET',payload=None):
    data=None if payload is None else json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,method=method)
    for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
    with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode()) if r.status!=204 else {}


def comment(n,text): gh(f'https://api.github.com/repos/{REPO}/issues/{n}/comments','POST',{'body':text})


def video_id_from(body):
    m=re.search(r'\*\*YouTube video ID:\*\*\s*`([^`]+)`',body)
    if m: return m.group(1).strip()
    m=re.search(r'youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})',body)
    return m.group(1) if m else ''


def quality_metrics(body):
    d=re.search(r'\*\*Rendered duration:\*\*\s*([0-9.]+)\s*seconds',body,re.I)
    w=re.search(r'\*\*Narration words:\*\*\s*(\d+)',body,re.I)
    return (float(d.group(1)) if d else None, int(w.group(1)) if w else None)


def main():
    event=json.loads(Path(EVENT).read_text()); actor=(event.get('comment',{}).get('user',{}).get('login') or '')
    if OWNER and actor.lower()!=OWNER.lower(): raise RuntimeError('SAFETY STOP: Gate 3 actor is not repository owner')
    issue=event.get('issue',{}); n=issue.get('number'); title=issue.get('title',''); body=issue.get('body') or ''; state=issue.get('state')
    if not title.startswith('Final Preview — '): print('Ignoring non-preview issue'); return
    if state!='open': raise RuntimeError('SAFETY STOP: final preview issue is not open')
    command=(event.get('comment',{}).get('body') or '').strip(); video_id=video_id_from(body)
    if not video_id: raise RuntimeError('SAFETY STOP: preview issue has no YouTube video ID')

    sys.path.insert(0,str(Path('scripts').resolve()))
    from youtube_upload import access_token, verify_channel, get_video, set_privacy
    token=access_token(); channel=verify_channel(token); video=get_video(token,video_id)
    if video.get('snippet',{}).get('channelId')!=channel.get('id'): raise RuntimeError('SAFETY STOP: preview video is not on the verified channel')
    privacy=video.get('status',{}).get('privacyStatus')

    if command=='/approve-publish':
        duration,words=quality_metrics(body)
        failures=[]
        if duration is None or duration<MIN_DURATION_SECONDS: failures.append(f'duration {duration if duration is not None else "unknown"}s < {MIN_DURATION_SECONDS}s')
        if words is None or words<MIN_NARRATION_WORDS: failures.append(f'narration words {words if words is not None else "unknown"} < {MIN_NARRATION_WORDS}')
        if failures:
            comment(n,'⛔ Publish blocked by production quality gate: '+ '; '.join(failures)+'. Request a production/script revision before publishing.')
            raise RuntimeError('SAFETY STOP: final preview fails production quality gate: '+'; '.join(failures))
        if privacy!='private': raise RuntimeError(f'SAFETY STOP: expected PRIVATE preview before publishing, got {privacy}')
        set_privacy(token,video_id,'public'); after=get_video(token,video_id); final_privacy=after.get('status',{}).get('privacyStatus')
        if final_privacy!='public': raise RuntimeError(f'Publishing verification failed: privacy is {final_privacy}')
        comment(n,f'✅ Final package approved and published. YouTube video `{video_id}` is now **PUBLIC** on the verified channel.')
        gh(f'https://api.github.com/repos/{REPO}/issues/{n}','PATCH',{'state':'closed','state_reason':'completed'}); return

    m=re.match(r'^/reject-production(?:\s+(.+))?$',command,re.I|re.S)
    if m:
        reason=(m.group(1) or 'No reason supplied.').strip()
        if privacy!='private': raise RuntimeError(f'SAFETY STOP: rejected preview is not private; current privacy={privacy}')
        comment(n,f'❌ Production rejected. The YouTube video remains **PRIVATE** and will not be published.\n\n**Reason:** {reason}')
        gh(f'https://api.github.com/repos/{REPO}/issues/{n}','PATCH',{'state':'closed','state_reason':'not_planned'}); return

    m=re.match(r'^/revise-production\s+(.+)$',command,re.I|re.S)
    if m:
        instruction=m.group(1).strip()
        if privacy!='private': raise RuntimeError(f'SAFETY STOP: revision source preview is not private; current privacy={privacy}')
        topic=title.replace('Final Preview — ','',1).strip()
        revision=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Production Revision Requested — {topic}','body':f'''# Production Revision Request\n\n**Source final preview:** #{n}\n**Existing private YouTube video:** `{video_id}`\n**Status:** PUBLISHING BLOCKED\n\n## Editor instruction\n{instruction}\n\nThe existing preview remains PRIVATE. A revised production package must create a new Final Preview gate before anything can be published.\n'''})
        comment(n,f'✏️ Production revision requested in #{revision["number"]}. Existing video `{video_id}` remains **PRIVATE**. This preview is closed so it cannot be published accidentally.')
        gh(f'https://api.github.com/repos/{REPO}/issues/{n}','PATCH',{'state':'closed','state_reason':'not_planned'}); return

    print('No supported Gate 3 command found')

if __name__=='__main__': main()
