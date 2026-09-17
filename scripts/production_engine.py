#!/usr/bin/env python3
"""Gate 3 production orchestrator.
Triggered only by a Script Approved issue. Creates a production manifest and a Final Preview issue.
Public publishing is deliberately not performed here.
"""
import json, os, re, subprocess, urllib.request
from pathlib import Path

REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said')
TOKEN=os.environ.get('GITHUB_TOKEN','')
EVENT=os.environ.get('GITHUB_EVENT_PATH','')


def gh(url,method='GET',payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(url,data=data,method=method)
    for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
    with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode())


def main():
    ev=json.loads(Path(EVENT).read_text()); issue=ev.get('issue',{})
    title=issue.get('title',''); body=issue.get('body') or ''
    if not title.startswith('Script Approved — '): print('Ignoring'); return
    topic=title.replace('Script Approved — ','',1)
    m=re.search(r'\*\*Source:\*\* #(\d+)',body); source=int(m.group(1)) if m else None
    if not source: raise RuntimeError('Missing research/script source issue')
    src=gh(f'https://api.github.com/repos/{REPO}/issues/{source}')
    document=src.get('body') or ''
    script_match=re.search(r'## Draft Script\s*(.*?)(?=\n## |\Z)',document,re.S|re.I)
    script=(script_match.group(1).strip() if script_match else document)
    Path('/tmp/production').mkdir(exist_ok=True)
    Path('/tmp/production/script.txt').write_text(script)
    manifest={'topic':topic,'source_issue':source,'script_approved':True,'public_publish_authorized':False,'stages':['voice','visuals','captions','thumbnail','metadata','render','final_preview'],'note':'Rendering integrations are executed only when their required free-provider credentials/assets are configured.'}
    Path('/tmp/production/manifest.json').write_text(json.dumps(manifest,indent=2))
    preview=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Final Preview — {topic}','body':f'''# Final Production Gate\n\n**Status:** PRODUCTION PACKAGE OPENED — PUBLIC PUBLISHING BLOCKED\n\n**Approved script source:** #{source}\n**Production authorization:** #{issue.get('number')}\n\nThe production pipeline is now responsible for voice, visuals, captions, thumbnail, metadata and render.\n\n## Gate 3\nNothing may be published publicly until the rendered video and metadata are attached/reviewable here and you explicitly use `/approve-publish`.\n\nCommands (once preview assets exist):\n- `/approve-publish`\n- `/revise-production <instruction>`\n- `/reject-production <reason>`\n'''})
    print('Opened final preview gate issue',preview['number'])

if __name__=='__main__': main()
