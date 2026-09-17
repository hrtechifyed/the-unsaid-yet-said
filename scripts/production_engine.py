#!/usr/bin/env python3
"""Gate 3 production orchestrator.
Triggered only by a Script Approved issue. Renders an MVP video, uploads it PRIVATE,
and opens a mandatory Final Preview issue. Public publishing is never performed here.
"""
import json, os, re, subprocess, sys, urllib.request
from pathlib import Path

REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said')
TOKEN=os.environ.get('GITHUB_TOKEN','')
EVENT=os.environ.get('GITHUB_EVENT_PATH','')
OUT=Path('/tmp/production')


def gh(url,method='GET',payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(url,data=data,method=method)
    for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
    with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode())


def extract(document, heading):
    m=re.search(rf'##\s+{re.escape(heading)}\s*(.*?)(?=\n##\s|\Z)',document,re.S|re.I)
    return m.group(1).strip() if m else ''


def main():
    ev=json.loads(Path(EVENT).read_text()); issue=ev.get('issue',{})
    title=issue.get('title',''); body=issue.get('body') or ''
    if not title.startswith('Script Approved — '): print('Ignoring'); return
    topic=title.replace('Script Approved — ','',1).strip()
    m=re.search(r'\*\*Source:\*\* #(\d+)',body); source=int(m.group(1)) if m else None
    if not source: raise RuntimeError('Missing research/script source issue')
    src=gh(f'https://api.github.com/repos/{REPO}/issues/{source}')
    document=src.get('body') or ''
    script=extract(document,'Draft script')
    if not script: raise RuntimeError('Could not find ## Draft script in approved source issue')
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'script.txt').write_text(script)

    subprocess.run([sys.executable,'scripts/render_video.py','--topic',topic,'--script',str(OUT/'script.txt')],check=True)
    metadata=json.loads((OUT/'metadata.json').read_text())

    # Reuse the already-tested OAuth/channel safety code. Upload remains PRIVATE.
    sys.path.insert(0,str(Path('scripts').resolve()))
    from youtube_upload import access_token, verify_channel, upload
    token=access_token(); channel=verify_channel(token)
    result=upload(token,str(OUT/'video.mp4'),metadata['title'],metadata['description'],'private')
    video_id=result['id']
    watch=f'https://www.youtube.com/watch?v={video_id}'

    manifest={'topic':topic,'source_issue':source,'production_authorization_issue':issue.get('number'),
              'script_approved':True,'public_publish_authorized':False,'youtube_video_id':video_id,
              'youtube_privacy':'private','channel_id':channel['id'],
              'stages_completed':['voice','captions','branded_visuals','thumbnail','metadata','render','private_youtube_upload'],
              'phase':'MVP branded renderer; richer B-roll/scene generation is the next production enhancement.'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))

    preview=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Final Preview — {topic}','body':f'''# Final Production Gate

**Status:** PRIVATE PREVIEW READY — PUBLIC PUBLISHING BLOCKED

**Approved script source:** #{source}
**Production authorization:** #{issue.get('number')}
**YouTube privacy:** PRIVATE
**Private preview:** {watch}
**Rendered duration:** {metadata['duration_seconds']} seconds

## Production package
- Narration generated
- Captions generated and burned into the video
- Branded 16:9 visual render generated
- Thumbnail generated
- Metadata generated
- Video uploaded to the verified TheUnsaidYetSaid channel as PRIVATE
- Workflow artifact contains the render package for review/debugging

## Gate 3
Nothing may be made public until you explicitly approve the finished package. Public publishing is intentionally not implemented in this production job.

Commands reserved for the Gate 3 handler:
- `/approve-publish`
- `/revise-production <instruction>`
- `/reject-production <reason>`
'''})
    print('PRIVATE_UPLOAD_VIDEO_ID='+video_id)
    print('Opened final preview gate issue',preview['number'])

if __name__=='__main__': main()
