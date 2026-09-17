#!/usr/bin/env python3
import json, os, re, sys, time, random, urllib.parse, urllib.request, urllib.error, xml.etree.ElementTree as ET
from pathlib import Path

REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said')
TOKEN=os.environ.get('GITHUB_TOKEN','')
GEMINI=os.environ.get('GEMINI_API_KEY','')
MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash')
EVENT=os.environ.get('GITHUB_EVENT_PATH','')
SOURCE_ISSUE=os.environ.get('SOURCE_ISSUE_NUMBER','').strip()
TRANSIENT_HTTP={429,500,502,503,504}

def gh(url, method='GET', payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(url,data=data,method=method)
    for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
    with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode()) if r.status!=204 else {}

def gemini(prompt, max_attempts=5):
    if not GEMINI: raise RuntimeError('GEMINI_API_KEY missing')
    url=f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(MODEL)}:generateContent"
    payload={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.45}}
    data=json.dumps(payload).encode()
    for attempt in range(1,max_attempts+1):
        req=urllib.request.Request(url,data=data,method='POST')
        req.add_header('Content-Type','application/json'); req.add_header('x-goog-api-key',GEMINI)
        try:
            with urllib.request.urlopen(req,timeout=90) as r: out=json.loads(r.read().decode())
            return out['candidates'][0]['content']['parts'][0]['text'].strip()
        except urllib.error.HTTPError as e:
            body=e.read().decode(errors='replace')[:1000]
            if e.code not in TRANSIENT_HTTP or attempt==max_attempts:
                raise RuntimeError(f'Gemini HTTP {e.code} after {attempt} attempt(s): {body}') from e
            delay=min(60, 2**attempt + random.uniform(0,2))
            print(f'Gemini transient HTTP {e.code}; retry {attempt}/{max_attempts} in {delay:.1f}s',file=sys.stderr)
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt==max_attempts: raise RuntimeError(f'Gemini network failure after {attempt} attempts: {e}') from e
            delay=min(60, 2**attempt + random.uniform(0,2))
            print(f'Gemini network error; retry {attempt}/{max_attempts} in {delay:.1f}s',file=sys.stderr)
            time.sleep(delay)
    raise RuntimeError('Gemini request exhausted retries')

def news(query, limit=10):
    q=urllib.parse.quote(query); url=f'https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en'; rows=[]
    try:
        with urllib.request.urlopen(url,timeout=20) as r: root=ET.fromstring(r.read())
        for item in root.findall('.//item')[:limit]: rows.append({'title':(item.findtext('title') or '').strip(),'url':(item.findtext('link') or '').strip(),'published':(item.findtext('pubDate') or '').strip()})
    except Exception as e: print('news warning',e,file=sys.stderr)
    return rows

def main():
    if SOURCE_ISSUE:
        issue=gh(f'https://api.github.com/repos/{REPO}/issues/{int(SOURCE_ISSUE)}')
    else:
        event=json.loads(Path(EVENT).read_text()); issue=event.get('issue',{})
    title=issue.get('title','')
    if not title.startswith('Approved Topic — '): raise RuntimeError('Source is not an Approved Topic issue')
    body=issue.get('body') or ''; topic=title.replace('Approved Topic — ','',1).strip()
    existing=re.findall(r'https?://[^)\s]+',body); signals=news(topic,12)+news(topic+' workplace research',8); seen=set(); sources=[]
    for s in signals:
        if s['url'] and s['url'] not in seen: seen.add(s['url']); sources.append(s)
    for u in existing:
        if u not in seen: seen.add(u); sources.append({'title':'Source carried from approved proposal','url':u,'published':''})
    source_text='\n'.join(f"S{i+1}. {s['title']} | {s['published']} | {s['url']}" for i,s in enumerate(sources[:20]))
    constitution=Path('EDITORIAL_CONSTITUTION.md').read_text()
    prompt=f'''You are the Research Editor and Script Writer for THE UNSAID, YET SAID — Powered by HRTechify.\n\nAPPROVED TOPIC RECORD:\n{body}\n\nEDITORIAL CONSTITUTION:\n{constitution}\n\nPUBLIC SOURCE LEADS:\n{source_text}\n\nCreate a rigorous research dossier and a YouTube script draft. These URLs/titles are source leads, not automatic proof. Never invent a source, statistic, study, quote, company policy, motive, or causal claim. If a claim cannot be adequately supported by the supplied material, place it under Research Gaps and do not state it as fact in the script.\n\nUse this exact structure:\n# Research + Script Gate\n## Approved topic\n## Core thesis\n## What we can responsibly say\n- bullets, each ending with source markers like [S1] where applicable\n## What we cannot claim yet\n## Competing interpretations\n## Employee perspective\n## Manager perspective\n## Peer/team perspective\n## HR/people-system perspective\n## Organisation/leadership perspective\n## Source ledger\nList S1... with title and URL\n## Draft script\nWrite a natural 7–10 minute script. Start with a recognisable workplace moment, reveal the tension, explain multiple interpretations, show what signals strengthen/weaken each interpretation, and end with a practical verification/action framework. Avoid deterministic decoding and generic listicles. Add unobtrusive [S#] markers after factual claims.\n## Editor checklist\n- Claims needing verification\n- Tone/clickbait risks\n- Suggested title\n- Thumbnail text (max 5 words)\n\nReturn Markdown only.'''
    md=gemini(prompt); md=re.sub(r'^```(?:markdown)?\s*|\s*```$','',md,flags=re.I|re.S).strip()
    footer='''\n\n---\n## Mandatory Gate 2\nNothing proceeds to voice/video production yet.\n\nComment with:\n- `/approve-script`\n- `/revise-script <instruction>`\n- `/reject-script <reason>`\n'''
    created=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Research + Script — {topic}','body':md+footer})
    gh(f"https://api.github.com/repos/{REPO}/issues/{issue['number']}/comments",'POST',{'body':f"📚 Research dossier + draft script created in #{created['number']}. Gate 2 approval is mandatory before production."})
    print('Created research/script issue',created['number'])

if __name__=='__main__': main()
