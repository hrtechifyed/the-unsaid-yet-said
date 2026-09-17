#!/usr/bin/env python3
import html, json, os, re, sys, time, random, urllib.parse, urllib.request, urllib.error, xml.etree.ElementTree as ET
from pathlib import Path

REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said')
TOKEN=os.environ.get('GITHUB_TOKEN',''); GEMINI=os.environ.get('GEMINI_API_KEY','')
MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); EVENT=os.environ.get('GITHUB_EVENT_PATH','')
SOURCE_ISSUE=os.environ.get('SOURCE_ISSUE_NUMBER','').strip(); TRANSIENT_HTTP={429,500,502,503,504}
UA='Mozilla/5.0 (compatible; TheUnsaidYetSaidResearch/1.0; +https://github.com/hrtechifyed/the-unsaid-yet-said)'

def gh(url,method='GET',payload=None):
    data=None if payload is None else json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,method=method)
    for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
    with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode()) if r.status!=204 else {}

def gemini(prompt,max_attempts=5):
    if not GEMINI: raise RuntimeError('GEMINI_API_KEY missing')
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(MODEL)}:generateContent'
    data=json.dumps({'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.25}}).encode()
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
        req=urllib.request.Request(url,headers={'User-Agent':UA})
        with urllib.request.urlopen(req,timeout=20) as r: root=ET.fromstring(r.read())
        for item in root.findall('.//item')[:limit]: rows.append({'title':(item.findtext('title') or '').strip(),'url':(item.findtext('link') or '').strip(),'published':(item.findtext('pubDate') or '').strip()})
    except Exception as e: print('news warning',e,file=sys.stderr)
    return rows

def clean_html(raw):
    raw=re.sub(r'(?is)<(script|style|noscript|svg|nav|footer|header|form).*?>.*?</\1>',' ',raw)
    raw=re.sub(r'(?is)<!--.*?-->',' ',raw); raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    return re.sub(r'\s+',' ',html.unescape(raw)).strip()

def fetch_evidence(source):
    try:
        req=urllib.request.Request(source['url'],headers={'User-Agent':UA,'Accept':'text/html,application/xhtml+xml'})
        with urllib.request.urlopen(req,timeout=25) as r:
            final=r.geturl(); ctype=(r.headers.get('Content-Type') or '').lower(); raw=r.read(1500000)
        if 'html' not in ctype: return None
        text=clean_html(raw.decode('utf-8',errors='replace'))
        if len(text)<700: return None
        return {**source,'resolved_url':final,'evidence_text':text[:9000]}
    except Exception as e:
        print(f"source fetch warning {source.get('url')}: {e}",file=sys.stderr); return None

def main():
    issue=gh(f'https://api.github.com/repos/{REPO}/issues/{int(SOURCE_ISSUE)}') if SOURCE_ISSUE else json.loads(Path(EVENT).read_text()).get('issue',{})
    title=issue.get('title','')
    if not title.startswith('Approved Topic — '): raise RuntimeError('Source is not an Approved Topic issue')
    body=issue.get('body') or ''; topic=title.replace('Approved Topic — ','',1).strip()
    leads=news(topic,12)+news(topic+' workplace research',8); seen=set(); sources=[]
    for s in leads:
        if s['url'] and s['url'] not in seen: seen.add(s['url']); sources.append(s)
    for u in re.findall(r'https?://[^)\s]+',body):
        if u not in seen: seen.add(u); sources.append({'title':'Source carried from approved proposal','url':u,'published':''})
    verified=[]
    for s in sources[:20]:
        ev=fetch_evidence(s)
        if ev: verified.append(ev)
        if len(verified)>=8: break
    if len(verified)<2:
        raise RuntimeError(f'RESEARCH QUALITY GATE FAILED: only {len(verified)} source(s) yielded readable evidence; minimum is 2. No script was generated.')
    packets=[]
    for i,s in enumerate(verified,1):
        packets.append(f"S{i}\nTITLE: {s['title']}\nDATE: {s['published']}\nURL: {s['resolved_url']}\nFETCHED EVIDENCE:\n{s['evidence_text']}")
    evidence='\n\n--- SOURCE PACKET ---\n'.join(packets); constitution=Path('EDITORIAL_CONSTITUTION.md').read_text()
    prompt=f'''You are the Research Editor and Script Writer for THE UNSAID, YET SAID — Powered by HRTechify.

APPROVED TOPIC RECORD:
{body}

EDITORIAL CONSTITUTION:
{constitution}

VERIFIED SOURCE PACKETS (actual fetched page text, not headlines alone):
{evidence}

NON-NEGOTIABLE EVIDENCE RULES:
1. A source title/headline alone is NOT evidence. Use only facts explicitly present in FETCHED EVIDENCE.
2. Every factual assertion, number, percentage, salary figure, trend claim, study result, historical claim or causal claim in the dossier AND script must end with [S#].
3. Never manufacture precision. If the fetched text does not contain a number, you may not introduce that number.
4. Do not convert an example, opinion, anecdote or single-company observation into a general fact.
5. Clearly label interpretations as interpretations. Ordinary illustrative workplace scenarios must not be presented as research findings.
6. If evidence is weak, conflicting or absent, put the point under What we cannot claim yet and omit it as fact from the script.
7. Prefer calibrated language such as 'one survey reported...' over universal language.
8. Source ledger URLs must use the resolved publisher URL supplied above.

Use this exact structure:
# Research + Script Gate
## Approved topic
## Core thesis
## Claim-evidence ledger
For every factual claim proposed for the script, use: **Claim:** ... | **Evidence:** concise paraphrase of what the fetched source actually establishes | **Source:** [S#] | **Confidence:** High/Medium. Do not include Low-confidence claims in the script.
## What we can responsibly say
## What we cannot claim yet
## Competing interpretations
## Employee perspective
## Manager perspective
## Peer/team perspective
## HR/people-system perspective
## Organisation/leadership perspective
## Source ledger
List S1... with title, date if available, and resolved publisher URL.
## Draft script
Write a natural 7–10 minute script. Start with a recognisable workplace moment, reveal the tension, explain multiple plausible interpretations, show what observable signals strengthen/weaken each interpretation, and end with a practical observe/ask/verify/act framework. Avoid deterministic decoding and generic listicles. Every research-derived factual claim must carry [S#]. Do not put unsupported statistics or pseudo-precise examples in narration.
## Editor checklist
- Claims needing additional verification
- Evidence limitations
- Tone/clickbait risks
- Suggested title
- Thumbnail text (max 5 words)

Return Markdown only.'''
    md=re.sub(r'^```(?:markdown)?\s*|\s*```$','',gemini(prompt),flags=re.I|re.S).strip()
    # Deterministic post-generation guard: numeric claims in script require a source marker on the same line.
    script=md.split('## Draft script',1)[1] if '## Draft script' in md else ''
    bad=[]
    for line in script.splitlines():
        if re.search(r'(?<!\w)(?:\d+(?:\.\d+)?%?|\$\d+|₹\s*\d+)',line) and not re.search(r'\[S\d+\]',line): bad.append(line.strip())
    if bad:
        raise RuntimeError('RESEARCH QUALITY GATE FAILED: unsupported numeric claim(s) detected in draft: '+ ' | '.join(bad[:5]))
    footer='''\n\n---\n## Mandatory Gate 2\nNothing proceeds to voice/video production yet.\n\nComment with:\n- `/approve-script`\n- `/revise-script <instruction>`\n- `/reject-script <reason>`\n'''
    created=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Research + Script — {topic}','body':md+footer})
    gh(f"https://api.github.com/repos/{REPO}/issues/{issue['number']}/comments",'POST',{'body':f"📚 Evidence-grounded research dossier + draft script created in #{created['number']}. Gate 2 approval is mandatory before production."})
    print(f"Created evidence-grounded research/script issue {created['number']} from {len(verified)} readable sources")

if __name__=='__main__': main()
