#!/usr/bin/env python3
"""Gate 3 production orchestrator: approved script -> PRIVATE preview -> mandatory final gate."""
import json, os, re, subprocess, sys, urllib.request
from pathlib import Path
REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said'); TOKEN=os.environ.get('GITHUB_TOKEN',''); EVENT=os.environ.get('GITHUB_EVENT_PATH',''); SOURCE_ISSUE=os.environ.get('SOURCE_ISSUE_NUMBER','').strip(); OUT=Path('/tmp/production')
def gh(url,method='GET',payload=None):
 data=None if payload is None else json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,method=method)
 for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
 with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode()) if r.status!=204 else {}
def extract(document,heading):
 m=re.search(rf'##\s+{re.escape(heading)}\s*(.*?)(?=\n##\s|\Z)',document,re.S|re.I); return m.group(1).strip() if m else ''
def main():
 if SOURCE_ISSUE: issue=gh(f'https://api.github.com/repos/{REPO}/issues/{int(SOURCE_ISSUE)}')
 else: issue=json.loads(Path(EVENT).read_text()).get('issue',{})
 title=issue.get('title',''); body=issue.get('body') or ''
 if not title.startswith('Script Approved — '): raise RuntimeError('Source is not a Script Approved issue')
 topic=title.replace('Script Approved — ','',1).strip(); m=re.search(r'\*\*Source:\*\* #(\d+)',body); source=int(m.group(1)) if m else None
 if not source: raise RuntimeError('Missing research/script source issue')
 src=gh(f'https://api.github.com/repos/{REPO}/issues/{source}'); document=src.get('body') or ''; script=extract(document,'Draft script')
 if not script: raise RuntimeError('Could not find ## Draft script in approved source issue')
 OUT.mkdir(parents=True,exist_ok=True); (OUT/'script.txt').write_text(script); subprocess.run([sys.executable,'scripts/render_video.py','--topic',topic,'--script',str(OUT/'script.txt')],check=True); metadata=json.loads((OUT/'metadata.json').read_text())
 sys.path.insert(0,str(Path('scripts').resolve())); from youtube_upload import access_token, verify_channel, upload
 token=access_token(); channel=verify_channel(token); result=upload(token,str(OUT/'video.mp4'),metadata['title'],metadata['description'],'private'); video_id=result['id']; watch=f'https://www.youtube.com/watch?v={video_id}'
 manifest={'topic':topic,'source_issue':source,'production_authorization_issue':issue.get('number'),'script_approved':True,'public_publish_authorized':False,'youtube_video_id':video_id,'youtube_privacy':'private','channel_id':channel['id'],'stages_completed':['voice','captions','branded_visuals','thumbnail','metadata','render','private_youtube_upload']}; (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
 preview=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Final Preview — {topic}','body':f'''# Final Production Gate\n\n**Status:** PRIVATE PREVIEW READY — PUBLIC PUBLISHING BLOCKED\n\n**Approved script source:** #{source}\n**Production authorization:** #{issue.get('number')}\n**YouTube privacy:** PRIVATE\n**Private preview:** {watch}\n**Rendered duration:** {metadata['duration_seconds']} seconds\n\n## Production package\n- Narration generated\n- Captions generated and burned into the video\n- Branded 16:9 visual render generated\n- Thumbnail generated\n- Metadata generated\n- Video uploaded to the verified TheUnsaidYetSaid channel as PRIVATE\n\n## Gate 3\nNothing may be made public until you explicitly approve the finished package.\n\nCommands reserved for Gate 3:\n- `/approve-publish`\n- `/revise-production <instruction>`\n- `/reject-production <reason>`\n'''})
 print('PRIVATE_UPLOAD_VIDEO_ID='+video_id); print('Opened final preview gate issue',preview['number'])
if __name__=='__main__': main()
