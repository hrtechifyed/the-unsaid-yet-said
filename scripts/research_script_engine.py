#!/usr/bin/env python3
import html, json, os, re, sys, time, random, urllib.parse, urllib.request, urllib.error, xml.etree.ElementTree as ET
from pathlib import Path

REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said'); TOKEN=os.environ.get('GITHUB_TOKEN',''); GEMINI=os.environ.get('GEMINI_API_KEY','')
MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); EVENT=os.environ.get('GITHUB_EVENT_PATH',''); SOURCE_ISSUE=os.environ.get('SOURCE_ISSUE_NUMBER','').strip()
TRANSIENT_HTTP={429,500,502,503,504}; UA='Mozilla/5.0 (compatible; TheUnsaidYetSaidResearch/1.0; +https://github.com/hrtechifyed/the-unsaid-yet-said)'

def gh(url,method='GET',payload=None):
    data=None if payload is None else json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,method=method)
    for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
    with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode()) if r.status!=204 else {}

def gemini(prompt,max_attempts=5):
    if not GEMINI: raise RuntimeError('GEMINI_API_KEY missing')
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(MODEL)}:generateContent'; data=json.dumps({'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.2}}).encode()
    for attempt in range(1,max_attempts+1):
        req=urllib.request.Request(url,data=data,method='POST'); req.add_header('Content-Type','application/json'); req.add_header('x-goog-api-key',GEMINI)
        try:
            with urllib.request.urlopen(req,timeout=90) as r: out=json.loads(r.read().decode())
            return out['candidates'][0]['content']['parts'][0]['text'].strip()
        except urllib.error.HTTPError as e:
            detail=e.read().decode(errors='replace')[:1000]
            if e.code not in TRANSIENT_HTTP or attempt==max_attempts: raise RuntimeError(f'Gemini HTTP {e.code} after {attempt} attempt(s): {detail}') from e
            delay=min(60,2**attempt+random.uniform(0,2)); print(f'Gemini transient HTTP {e.code}; retrying in {delay:.1f}s',file=sys.stderr); time.sleep(delay)
        except (urllib.error.URLError,TimeoutError) as e:
            if attempt==max_attempts: raise RuntimeError(f'Gemini network failure after {attempt} attempts: {e}') from e
            delay=min(60,2**attempt+random.uniform(0,2)); print(f'Gemini network error; retrying in {delay:.1f}s',file=sys.stderr); time.sleep(delay)

def news(query,limit=10):
    url=f'https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en'; rows=[]
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':UA}),timeout=20) as r: root=ET.fromstring(r.read())
        for item in root.findall('.//item')[:limit]:
            src=item.find('source'); rows.append({'title':(item.findtext('title') or '').strip(),'url':(item.findtext('link') or '').strip(),'published':(item.findtext('pubDate') or '').strip(),'publisher':(src.text or '').strip() if src is not None else ''})
    except Exception as e: print('news warning',e,file=sys.stderr)
    return rows

def clean_html(raw):
    raw=re.sub(r'(?is)<(script|style|noscript|svg|nav|footer|header|form).*?>.*?</\1>',' ',raw); raw=re.sub(r'(?is)<!--.*?-->',' ',raw); raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    return re.sub(r'\s+',' ',html.unescape(raw)).strip()

def external_url(url):
    host=(urllib.parse.urlparse(url).hostname or '').lower()
    return bool(host) and not any(x in host for x in ('google.com','googleusercontent.com','gstatic.com','duckduckgo.com'))

def discover_publisher_url(source):
    if external_url(source.get('url','')): return source['url']
    title=source.get('title',''); publisher=source.get('publisher','')
    # Google News titles commonly end in " - Publisher"; remove it before navigation search.
    if publisher and title.lower().endswith((' - '+publisher).lower()): title=title[:-(len(publisher)+3)].strip()
    query=f'"{title}" {publisher}'.strip(); search='https://html.duckduckgo.com/html/?q='+urllib.parse.quote(query)
    try:
        req=urllib.request.Request(search,headers={'User-Agent':UA,'Accept':'text/html'})
        with urllib.request.urlopen(req,timeout=20) as r: raw=r.read(600000).decode('utf-8',errors='replace')
        hrefs=re.findall(r'href=["\']([^"\']+)["\']',raw,re.I)
        for href in hrefs:
            href=html.unescape(href)
            if href.startswith('//'): href='https:'+href
            parsed=urllib.parse.urlparse(href)
            qs=urllib.parse.parse_qs(parsed.query)
            if 'uddg' in qs: href=urllib.parse.unquote(qs['uddg'][0])
            if external_url(href): return href
    except Exception as e: print(f"navigation search warning for {title}: {e}",file=sys.stderr)
    return None

def fetch_evidence(source):
    target=discover_publisher_url(source)
    if not target: return None
    try:
        req=urllib.request.Request(target,headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})
        with urllib.request.urlopen(req,timeout=25) as r: final=r.geturl(); ctype=(r.headers.get('Content-Type') or '').lower(); raw=r.read(1500000)
        if 'html' not in ctype or not external_url(final): return None
        text=clean_html(raw.decode('utf-8',errors='replace'))
        if len(text)<700: return None
        # Require a meaningful overlap with the discovered headline so unrelated search results cannot enter evidence.
        headline_words={w.lower() for w in re.findall(r'[A-Za-z]{5,}',source.get('title','')) if w.lower() not in {'about','their','there','which','after','before','from','with'}}
        page_words=set(re.findall(r'[A-Za-z]{5,}',text.lower()))
        if headline_words and len(headline_words & page_words) < min(3,len(headline_words)): return None
        return {**source,'resolved_url':final,'evidence_text':text[:9000]}
    except Exception as e: print(f"source fetch warning {target}: {e}",file=sys.stderr); return None

def main():
    issue=gh(f'https://api.github.com/repos/{REPO}/issues/{int(SOURCE_ISSUE)}') if SOURCE_ISSUE else json.loads(Path(EVENT).read_text()).get('issue',{})
    title=issue.get('title','')
    if not title.startswith('Approved Topic — '): raise RuntimeError('Source is not an Approved Topic issue')
    body=issue.get('body') or ''; topic=title.replace('Approved Topic — ','',1).strip(); leads=news(topic,12)+news(topic+' workplace research',8); seen=set(); sources=[]
    for s in leads:
        key=s.get('title','').lower()
        if key and key not in seen: seen.add(key); sources.append(s)
    for u in re.findall(r'https?://[^)\s]+',body):
        if u not in seen: seen.add(u); sources.append({'title':'Source carried from approved proposal','url':u,'published':'','publisher':''})
    verified=[]
    for s in sources[:20]:
        ev=fetch_evidence(s)
        if ev: verified.append(ev); print(f"verified source: {ev['resolved_url']}")
        if len(verified)>=8: break
    if len(verified)<2: raise RuntimeError(f'RESEARCH QUALITY GATE FAILED: only {len(verified)} publisher source(s) yielded readable evidence; minimum is 2. No script was generated.')
    packets=[]
    for i,s in enumerate(verified,1): packets.append(f"S{i}\nTITLE: {s['title']}\nDATE: {s['published']}\nURL: {s['resolved_url']}\nFETCHED EVIDENCE:\n{s['evidence_text']}")
    evidence='\n\n--- SOURCE PACKET ---\n'.join(packets); constitution=Path('EDITORIAL_CONSTITUTION.md').read_text()
    prompt=f'''You are the Research Editor and Script Writer for THE UNSAID, YET SAID — Powered by HRTechify.\n\nAPPROVED TOPIC RECORD (contains hypotheses and discovery leads, NOT facts):\n{body}\n\nEDITORIAL CONSTITUTION:\n{constitution}\n\nVERIFIED SOURCE PACKETS (actual fetched publisher page text):\n{evidence}\n\nNON-NEGOTIABLE EVIDENCE RULES:\n1. Treat every claim in APPROVED TOPIC RECORD as an unverified hypothesis unless independently supported in FETCHED EVIDENCE.\n2. A headline alone is not evidence. Use only facts explicitly present in FETCHED EVIDENCE.\n3. Every factual assertion, number, percentage, salary figure, trend/study/historical/causal claim in the dossier AND script must end with [S#].\n4. Never manufacture precision or generalize an anecdote, opinion, example or single-company observation.\n5. Clearly label interpretations as interpretations. Do not mind-read employees, managers or HR.\n6. Unsupported points belong under What we cannot claim yet and must be omitted as facts from narration.\n7. For surveys, state population/sample/geography/date when the source provides them. Do not imply global representativeness.\n8. Use resolved publisher URLs in Source ledger.\n\nUse exactly:\n# Research + Script Gate\n## Approved topic\n## Core thesis\n## Claim-evidence ledger\nEach factual claim: **Claim:** ... | **Evidence:** concise paraphrase of exactly what source establishes | **Source:** [S#] | **Confidence:** High/Medium. Low-confidence claims are excluded.\n## What we can responsibly say\n## What we cannot claim yet\n## Competing interpretations\n## Employee perspective\n## Manager perspective\n## Peer/team perspective\n## HR/people-system perspective\n## Organisation/leadership perspective\n## Source ledger\n## Draft script\nNatural 7–10 minute script: recognisable moment → tension → multiple plausible interpretations → signals that strengthen/weaken each → practical observe/ask/verify/act framework. Every research-derived factual claim carries [S#]. No unsupported statistics or pseudo-precision.\n## Editor checklist\n- Claims needing additional verification\n- Evidence limitations\n- Tone/clickbait risks\n- Suggested title\n- Thumbnail text (max 5 words)\nReturn Markdown only.'''
    md=re.sub(r'^```(?:markdown)?\s*|\s*```$','',gemini(prompt),flags=re.I|re.S).strip()
    if '## Draft script' not in md: raise RuntimeError('RESEARCH QUALITY GATE FAILED: model omitted Draft script section')
    script=md.split('## Draft script',1)[1].split('## Editor checklist',1)[0]; bad=[]
    for line in script.splitlines():
        prose=line.strip()
        if not prose or prose.startswith(('#','**[VISUAL','[VISUAL','```')): continue
        if re.search(r'(?<!\w)(?:\d+(?:\.\d+)?%|\$\s*\d+|₹\s*\d+|\d+\s+(?:percent|per cent|employees|workers|managers|people|hours|days|years))',prose,re.I) and not re.search(r'\[S\d+\]',prose): bad.append(prose)
    if bad: raise RuntimeError('RESEARCH QUALITY GATE FAILED: unsupported numeric factual claim(s): '+' | '.join(bad[:5]))
    footer='''\n\n---\n## Mandatory Gate 2\nNothing proceeds to voice/video production yet.\n\nComment with:\n- `/approve-script`\n- `/revise-script <instruction>`\n- `/reject-script <reason>`\n'''
    created=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Research + Script — {topic}','body':md+footer})
    gh(f"https://api.github.com/repos/{REPO}/issues/{issue['number']}/comments",'POST',{'body':f"📚 Evidence-grounded research dossier + draft script created in #{created['number']} from {len(verified)} readable publisher sources. Gate 2 approval is mandatory."})
    print(f"Created evidence-grounded research/script issue {created['number']} from {len(verified)} readable publisher sources")

if __name__=='__main__': main()
