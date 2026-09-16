#!/usr/bin/env python3
import json, os, re, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said')
TOKEN=os.environ.get('GITHUB_TOKEN','')
GEMINI=os.environ.get('GEMINI_API_KEY','')
MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash')
EVENT=os.environ.get('GITHUB_EVENT_PATH','')


def gh(url, method='GET', payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(url,data=data,method=method)
    for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
    with urllib.request.urlopen(req,timeout=60) as r:
        return json.loads(r.read().decode()) if r.status!=204 else {}


def gemini(prompt):
    if not GEMINI: raise RuntimeError('GEMINI_API_KEY missing')
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(MODEL)}:generateContent"
    payload={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.45}}
    req=urllib.request.Request(url,data=json.dumps(payload).encode(),method='POST')
    req.add_header('Content-Type','application/json'); req.add_header('x-goog-api-key',GEMINI)
    with urllib.request.urlopen(req,timeout=90) as r: out=json.loads(r.read().decode())
    return out['candidates'][0]['content']['parts'][0]['text'].strip()


def news(query, limit=10):
    q=urllib.parse.quote(query)
    url=f'https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en'
    rows=[]
    try:
        with urllib.request.urlopen(url,timeout=20) as r: root=ET.fromstring(r.read())
        for item in root.findall('.//item')[:limit]:
            rows.append({'title':(item.findtext('title') or '').strip(),'url':(item.findtext('link') or '').strip(),'published':(item.findtext('pubDate') or '').strip()})
    except Exception as e: print('news warning',e,file=sys.stderr)
    return rows


def main():
    event=json.loads(Path(EVENT).read_text())
    issue=event.get('issue',{})
    title=issue.get('title','')
    if not title.startswith('Approved Topic — '):
        print('Ignoring non-approved-topic issue'); return
    body=issue.get('body') or ''
    topic=title.replace('Approved Topic — ','',1).strip()
    existing=re.findall(r'https?://[^)\s]+',body)
    signals=news(topic,12)+news(topic+' workplace research',8)
    seen=set(); sources=[]
    for s in signals:
        if s['url'] and s['url'] not in seen:
            seen.add(s['url']); sources.append(s)
    for u in existing:
        if u not in seen:
            seen.add(u); sources.append({'title':'Source carried from approved proposal','url':u,'published':''})
    source_text='\n'.join(f"S{i+1}. {s['title']} | {s['published']} | {s['url']}" for i,s in enumerate(sources[:20]))
    constitution=Path('EDITORIAL_CONSTITUTION.md').read_text()
    prompt=f'''You are the Research Editor and Script Writer for THE UNSAID, YET SAID — Powered by HRTechify.

APPROVED TOPIC RECORD:
{body}

EDITORIAL CONSTITUTION:
{constitution}

PUBLIC SOURCE LEADS:
{source_text}

Create a rigorous research dossier and a YouTube script draft. These URLs/titles are source leads, not automatic proof. Never invent a source, statistic, study, quote, company policy, motive, or causal claim. If a claim cannot be adequately supported by the supplied material, place it under Research Gaps and do not state it as fact in the script.

Use this exact structure:
# Research + Script Gate
## Approved topic
## Core thesis
## What we can responsibly say
- bullets, each ending with source markers like [S1] where applicable
## What we cannot claim yet
## Competing interpretations
## Employee perspective
## Manager perspective
## Peer/team perspective
## HR/people-system perspective
## Organisation/leadership perspective
## Source ledger
List S1... with title and URL
## Draft script
Write a natural 7–10 minute script. Start with a recognisable workplace moment, reveal the tension, explain multiple interpretations, show what signals strengthen/weaken each interpretation, and end with a practical verification/action framework. Avoid deterministic decoding and generic listicles. Add unobtrusive [S#] markers after factual claims.
## Editor checklist
- Claims needing verification
- Tone/clickbait risks
- Suggested title
- Thumbnail text (max 5 words)

Return Markdown only.''' 
    md=gemini(prompt)
    md=re.sub(r'^```(?:markdown)?\s*|\s*```$','',md,flags=re.I|re.S).strip()
    footer='''\n\n---\n## Mandatory Gate 2\nNothing proceeds to voice/video production yet.\n\nComment with:\n- `/approve-script`\n- `/revise-script <instruction>`\n- `/reject-script <reason>`\n'''
    created=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Research + Script — {topic}','body':md+footer})
    gh(f"https://api.github.com/repos/{REPO}/issues/{issue['number']}/comments",'POST',{'body':f"📚 Research dossier + draft script created in #{created['number']}. Gate 2 approval is mandatory before production."})
    print('Created research/script issue',created['number'])

if __name__=='__main__': main()
