#!/usr/bin/env python3
import difflib, html, json, os, random, re, sys, time, urllib.error, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from pathlib import Path

REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said')
TOKEN=os.environ.get('GITHUB_TOKEN','')
GEMINI=os.environ.get('GEMINI_API_KEY','')
MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash')
EVENT=os.environ.get('GITHUB_EVENT_PATH','')
SOURCE_ISSUE=os.environ.get('SOURCE_ISSUE_NUMBER','').strip()
TRANSIENT_HTTP={429,500,502,503,504}
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/152 Safari/537.36 TheUnsaidYetSaidResearch/3.0'
SEARCH_HOSTS={'news.google.com','google.com','www.google.com','bing.com','www.bing.com','api.gdeltproject.org'}
LOW_VALUE_HOSTS={
    'wikipedia.org','simple.wikipedia.org','wiktionary.org','dictionary.com','cambridge.org','dictionary.cambridge.org',
    'merriam-webster.com','collinsdictionary.com','thefreedictionary.com','vocabulary.com','quora.com','pinterest.com'
}
STOP={'about','after','again','against','before','being','could','from','have','into','more','most','other','their','there','these','they','this','those','through','under','what','when','where','which','while','with','without','would','your'}


def gh(url,method='GET',payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    req=urllib.request.Request(url,data=data,method=method)
    for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
    with urllib.request.urlopen(req,timeout=60) as r:
        return json.loads(r.read().decode()) if r.status!=204 else {}


def gemini(prompt,max_attempts=5):
    if not GEMINI: raise RuntimeError('GEMINI_API_KEY missing')
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(MODEL)}:generateContent'
    data=json.dumps({'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.2}}).encode()
    for attempt in range(1,max_attempts+1):
        req=urllib.request.Request(url,data=data,method='POST',headers={'Content-Type':'application/json','x-goog-api-key':GEMINI})
        try:
            with urllib.request.urlopen(req,timeout=90) as r: out=json.loads(r.read().decode())
            return out['candidates'][0]['content']['parts'][0]['text'].strip()
        except urllib.error.HTTPError as e:
            detail=e.read().decode(errors='replace')[:800]
            if e.code not in TRANSIENT_HTTP or attempt==max_attempts:
                raise RuntimeError(f'Gemini HTTP {e.code} after {attempt} attempt(s): {detail}') from e
            retry_after=e.headers.get('Retry-After')
            try: delay=float(retry_after) if retry_after else min(60,2**attempt+random.uniform(0,2))
            except ValueError: delay=min(60,2**attempt+random.uniform(0,2))
            print(f'Gemini transient HTTP {e.code}; retrying in {delay:.1f}s',file=sys.stderr); time.sleep(delay)
        except (urllib.error.URLError,TimeoutError) as e:
            if attempt==max_attempts: raise RuntimeError(f'Gemini network failure after {attempt} attempts: {e}') from e
            delay=min(60,2**attempt+random.uniform(0,2)); print(f'Gemini network error; retrying in {delay:.1f}s',file=sys.stderr); time.sleep(delay)
    raise RuntimeError('Gemini request exhausted retries')


def fetch_bytes(url,timeout=25,limit=1800000,accept='text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':accept,'Accept-Language':'en-US,en;q=0.8'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.geturl(),(r.headers.get('Content-Type') or '').lower(),r.headers.get_content_charset() or 'utf-8',r.read(limit)


def host_of(url): return (urllib.parse.urlparse(url).hostname or '').lower().removeprefix('www.')

def external_url(url):
    h=host_of(url)
    return url.startswith(('http://','https://')) and h not in {x.removeprefix('www.') for x in SEARCH_HOSTS}


def low_value(url):
    h=host_of(url)
    return any(h==x or h.endswith('.'+x) for x in LOW_VALUE_HOSTS)


def normalize_title(text):
    text=html.unescape(text or '')
    text=re.sub(r'\s+[-–—|]\s+[^-–—|]{1,45}$','',text).strip()
    return re.sub(r'\s+',' ',text)


def title_tokens(text):
    return {w.lower() for w in re.findall(r"[A-Za-z][A-Za-z'-]{3,}",normalize_title(text)) if w.lower() not in STOP}


def title_score(a,b):
    a=normalize_title(a); b=normalize_title(b)
    if not a or not b: return 0.0
    seq=difflib.SequenceMatcher(None,a.lower(),b.lower()).ratio()
    ta,tb=title_tokens(a),title_tokens(b)
    overlap=len(ta & tb)/max(1,min(len(ta),len(tb)))
    return max(seq,overlap)


def extract_page_title(raw):
    m=re.search(r'(?is)<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',raw)
    if m: return html.unescape(m.group(1)).strip()
    m=re.search(r'(?is)<title[^>]*>(.*?)</title>',raw)
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',m.group(1)))).strip() if m else ''


def clean_html(raw):
    raw=re.sub(r'(?is)<(script|style|noscript|svg|nav|footer|header|form|aside).*?>.*?</\1>',' ',raw)
    raw=re.sub(r'(?is)<!--.*?-->',' ',raw)
    raw=re.sub(r'(?is)<br\s*/?>','\n',raw); raw=re.sub(r'(?is)</p\s*>','\n',raw); raw=re.sub(r'(?is)</(?:h[1-6]|li|div|section|article)\s*>','\n',raw)
    raw=re.sub(r'(?s)<[^>]+>',' ',raw)
    lines=[]
    for line in html.unescape(raw).splitlines():
        line=re.sub(r'\s+',' ',line).strip()
        if len(line)>=25: lines.append(line)
    return '\n'.join(lines)


def google_news(query,limit=12):
    url=f'https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en'; rows=[]
    try:
        _,_,_,raw=fetch_bytes(url,20,800000,'application/rss+xml,application/xml,text/xml')
        root=ET.fromstring(raw)
        for item in root.findall('.//item')[:limit]:
            src=item.find('source')
            rows.append({'title':(item.findtext('title') or '').strip(),'url':(item.findtext('link') or '').strip(),'published':(item.findtext('pubDate') or '').strip(),'publisher':(src.text or '').strip() if src is not None else '','discovery':'google-news'})
    except Exception as e: print('google-news warning:',e,file=sys.stderr)
    return rows


def bing_rss(query,limit=12):
    url='https://www.bing.com/search?format=rss&q='+urllib.parse.quote(query); rows=[]
    try:
        _,_,_,raw=fetch_bytes(url,20,900000,'application/rss+xml,application/xml,text/xml')
        root=ET.fromstring(raw)
        for item in root.findall('.//item')[:limit]:
            u=(item.findtext('link') or '').strip(); t=(item.findtext('title') or '').strip()
            if external_url(u) and not low_value(u):
                rows.append({'title':t,'url':u,'published':(item.findtext('pubDate') or '').strip(),'publisher':host_of(u),'discovery':'bing-rss'})
    except Exception as e: print('bing-rss warning:',e,file=sys.stderr)
    return rows


def gdelt(query,limit=12,max_attempts=3):
    params={'query':query,'mode':'ArtList','maxrecords':str(limit),'format':'json','sort':'HybridRel'}
    url='https://api.gdeltproject.org/api/v2/doc/doc?'+urllib.parse.urlencode(params); rows=[]
    for attempt in range(1,max_attempts+1):
        try:
            _,_,_,raw=fetch_bytes(url,25,1500000,'application/json,text/plain,*/*')
            text=raw.decode('utf-8','replace').strip()
            if not text.startswith('{'): raise RuntimeError('non-JSON GDELT response')
            data=json.loads(text)
            for a in data.get('articles',[])[:limit]:
                u=(a.get('url') or '').strip(); t=(a.get('title') or '').strip()
                if external_url(u) and not low_value(u):
                    rows.append({'title':t,'url':u,'published':(a.get('seendate') or '').strip(),'publisher':(a.get('domain') or host_of(u)).strip(),'discovery':'gdelt'})
            return rows
        except urllib.error.HTTPError as e:
            if e.code==429 and attempt<max_attempts:
                delay=4*attempt; print(f'gdelt rate limited; retrying in {delay}s',file=sys.stderr); time.sleep(delay); continue
            print('gdelt warning:',e,file=sys.stderr); return []
        except Exception as e:
            print('gdelt warning:',e,file=sys.stderr); return []
    return []


def direct_urls_from_body(body):
    rows=[]
    for u in re.findall(r'https?://[^)\s>`]+',body):
        u=u.rstrip('.,;')
        if external_url(u) and not low_value(u): rows.append({'title':'Editor-provided direct source seed','url':u,'published':'','publisher':host_of(u),'discovery':'approved-topic'})
    return rows


def resolve_google_lead(source):
    title=source.get('title',''); publisher=source.get('publisher','')
    if publisher and title.lower().endswith((' - '+publisher).lower()): title=title[:-(len(publisher)+3)].strip()
    candidates=[]
    for q in [f'"{title}"',f'"{title}" {publisher}'.strip()]:
        candidates.extend(bing_rss(q,8))
        if not candidates: candidates.extend(gdelt(q,8,2))
        if candidates: break
    ranked=sorted(candidates,key=lambda c:title_score(title,c.get('title','')),reverse=True)
    if ranked and title_score(title,ranked[0].get('title',''))>=0.58:
        out=dict(ranked[0]); out['title']=title; out['published']=source.get('published') or out.get('published',''); out['publisher']=publisher or out.get('publisher',''); out['discovery']='resolved-'+out.get('discovery','')
        return out
    return None


def discover_sources(topic,body):
    out=[]; seen=set(); topic_tokens=title_tokens(topic)
    def add(s,force=False):
        u=s.get('url',''); key=(u or s.get('title','')).lower()
        if not key or key in seen or low_value(u): return
        if not force:
            t=title_tokens(s.get('title',''))
            overlap=len(topic_tokens & t)/max(1,min(len(topic_tokens),len(t))) if t else 0
            keywords={'promotion','promotions','management','manager','managers','career','leadership','individual','contributor','workplace','employee','employees'}
            if overlap<0.18 and not (t & keywords): return
        seen.add(key); out.append(s)
    direct=direct_urls_from_body(body)
    for s in direct: add(s,True)
    # Direct publisher seeds are highest quality. Only broaden discovery when we still need redundancy.
    if len(out)<6:
        for g in google_news(topic,12):
            r=resolve_google_lead(g)
            if r: add(r)
            if len(out)>=12: break
    if len(out)<6:
        for q in [f'"{topic}" workplace', 'management promotion individual contributor career survey']:
            for s in bing_rss(q,10): add(s)
            if len(out)<6:
                for s in gdelt(q,8,2): add(s)
            if len(out)>=12: break
    print(f'Discovery produced {len(out)} direct publisher candidate(s).')
    for s in out[:20]: print(f"candidate [{s.get('discovery')}]: {s.get('title','')[:90]} -> {s.get('url')}")
    return out


def fetch_evidence(source):
    target=source.get('url','')
    try:
        final,ctype,charset,raw=fetch_bytes(target,25,1800000)
        if not external_url(final) or low_value(final): print('reject low-value/intermediate:',final); return None
        if 'html' not in ctype and 'text/plain' not in ctype: print('reject non-html:',ctype,final); return None
        doc=raw.decode(charset,errors='replace'); page_title=extract_page_title(doc); text=clean_html(doc)
        if len(text)<900: print('reject too-short:',len(text),final); return None
        expected=source.get('title','')
        if expected and expected!='Editor-provided direct source seed':
            score=max(title_score(expected,page_title),len(title_tokens(expected)&set(re.findall(r"[a-z][a-z'-]{3,}",text.lower())))/max(1,len(title_tokens(expected))))
            if score<0.38: print(f'reject title-mismatch score={score:.2f}: {final}'); return None
        return {**source,'resolved_url':final,'page_title':page_title or expected,'evidence_text':text[:12000]}
    except urllib.error.HTTPError as e:
        print(f'source fetch HTTP {e.code}: {target}',file=sys.stderr); return None
    except Exception as e:
        print(f'source fetch warning {target}: {e}',file=sys.stderr); return None


def validation_errors(md,source_count):
    errors=[]
    required=['## Claim-evidence ledger','## What we can responsibly say','## What we cannot claim yet','## Source ledger','## Draft script','## Editor checklist']
    missing=[h for h in required if h not in md]
    if missing: errors.append('missing section(s): '+', '.join(missing)); return errors
    markers=[int(x) for x in re.findall(r'\[S(\d+)\]',md)]
    if any(x<1 or x>source_count for x in markers): errors.append('source marker references nonexistent source')
    script=md.split('## Draft script',1)[1].split('## Editor checklist',1)[0]
    words=len(re.findall(r"\b[\w’'-]+\b",script))
    if words<850 or words>1800: errors.append(f'draft script has {words} words; expected 850–1800')
    bad=[]
    trigger=re.compile(r'(?:\d+(?:\.\d+)?%|\$\s*\d+|₹\s*\d+|\b\d+\s+(?:percent|per cent|employees|workers|managers|people|hours|days|years)\b|\baccording to\b|\b(?:a |the )?(?:survey|study|research|report)\s+(?:found|finds|shows|showed|suggests|indicates|reveals|reported)\b|\bdata\s+(?:shows|showed|suggests|indicates|reveals|found)\b)',re.I)
    for line in script.splitlines():
        prose=line.strip()
        if not prose or prose.startswith(('#','```','[VISUAL','**[VISUAL')): continue
        if trigger.search(prose) and not re.search(r'\[S\d+\]',prose): bad.append(prose)
    if bad: errors.append('uncited research/numeric claim(s): '+' | '.join(bad[:5]))
    used=set(int(x) for x in re.findall(r'\[S(\d+)\]',script))
    if len(used)<2: errors.append('script does not use at least two verified sources')
    return errors


def build_prompt(body,constitution,evidence):
    return f'''You are the Research Editor and Script Writer for THE UNSAID, YET SAID — Powered by HRTechify.

APPROVED TOPIC RECORD (hypotheses and discovery context, NOT facts):
{body}

EDITORIAL CONSTITUTION:
{constitution}

VERIFIED SOURCE PACKETS (actual fetched publisher-page text):
{evidence}

NON-NEGOTIABLE EVIDENCE RULES:
1. Treat every claim in APPROVED TOPIC RECORD as unverified unless independently supported in FETCHED EVIDENCE.
2. Use only facts explicitly present in FETCHED EVIDENCE. A headline or discovery title alone is not evidence.
3. Every factual assertion, number, percentage, trend, study, historical claim, causal claim, salary/workload figure or statement introduced with research/data/report language must carry [S#] immediately after the claim in both dossier and script.
4. Do not generalise anecdotes, opinions, examples or one population to all workers. Preserve source population, geography, sample and date when available.
5. Interpretations must be labelled as plausible interpretations, not motives or facts.
6. Unsupported ideas go in What we cannot claim yet and must not appear as factual narration.
7. Do not invent quotes. Paraphrase research unless an exact quote is clearly present and necessary.
8. Use the resolved publisher URLs from the packets in Source ledger.
9. Prefer modest, precise language over viral certainty.

Use exactly:
# Research + Script Gate
## Approved topic
## Core thesis
## Claim-evidence ledger
Each item: **Claim:** ... | **Evidence:** exact concise paraphrase of what the source establishes | **Source:** [S#] | **Confidence:** High/Medium. Exclude Low-confidence claims.
## What we can responsibly say
## What we cannot claim yet
## Competing interpretations
## Employee perspective
## Manager perspective
## Peer/team perspective
## HR/people-system perspective
## Organisation/leadership perspective
## Source ledger
List S1... with title, publisher/date where known, and resolved URL.
## Draft script
Write 7–10 minutes of natural narration (roughly 900–1500 spoken words): recognisable workplace moment → tension → multiple plausible interpretations → evidence-backed context → signals that strengthen/weaken interpretations → practical observe/ask/verify/act framework. Visual directions may be included in [VISUAL: ...] lines, but narration must stand alone. Every research-derived factual claim carries [S#].
## Editor checklist
- Claims needing additional verification
- Evidence limitations
- Tone/clickbait risks
- Suggested title
- Thumbnail text (max 5 words)
Return Markdown only.'''


def generate_valid_document(prompt,source_count,evidence,max_repairs=2):
    md=re.sub(r'^```(?:markdown)?\s*|\s*```$','',gemini(prompt),flags=re.I|re.S).strip()
    for repair in range(max_repairs+1):
        errors=validation_errors(md,source_count)
        if not errors: return md
        if repair==max_repairs: raise RuntimeError('RESEARCH QUALITY GATE FAILED after repair attempts: '+' || '.join(errors))
        print('Validation failed; requesting evidence-safe repair:', ' || '.join(errors),file=sys.stderr)
        repair_prompt=f'''Repair the Markdown research dossier and script below. Do not add new facts or sources.

VALIDATION ERRORS:
- '''+'\n- '.join(errors)+f'''

VERIFIED SOURCE PACKETS:
{evidence}

CURRENT DOCUMENT:
{md}

Rules: preserve all required headings; use only the verified source packets; add a valid [S#] only when that source actually supports the claim; otherwise rewrite or remove the unsupported statement. Keep the script between 900 and 1500 spoken words. Return complete Markdown only.'''
        md=re.sub(r'^```(?:markdown)?\s*|\s*```$','',gemini(repair_prompt),flags=re.I|re.S).strip()
    return md


def main():
    issue=gh(f'https://api.github.com/repos/{REPO}/issues/{int(SOURCE_ISSUE)}') if SOURCE_ISSUE else json.loads(Path(EVENT).read_text()).get('issue',{})
    title=issue.get('title','')
    if not title.startswith('Approved Topic — '): raise RuntimeError('Source is not an Approved Topic issue')
    body=issue.get('body') or ''; topic=title.replace('Approved Topic — ','',1).strip()
    candidates=discover_sources(topic,body); verified=[]; hosts=set()
    for s in candidates[:45]:
        ev=fetch_evidence(s)
        if ev:
            h=host_of(ev['resolved_url'])
            if sum(1 for x in verified if host_of(x['resolved_url'])==h)>=2: continue
            verified.append(ev); hosts.add(h); print(f"VERIFIED [{len(verified)}] {ev['page_title'][:100]} -> {ev['resolved_url']}")
        if len(verified)>=6 and len(hosts)>=3: break
    if len(verified)<2 or len(hosts)<2:
        raise RuntimeError(f'RESEARCH QUALITY GATE FAILED: {len(verified)} readable publisher source(s) across {len(hosts)} independent publisher(s); minimum is 2 sources across 2 publishers. No script was generated.')
    packets=[]
    for i,s in enumerate(verified,1):
        packets.append(f"S{i}\nTITLE: {s['page_title']}\nDISCOVERED TITLE: {s.get('title','')}\nDATE: {s.get('published','')}\nPUBLISHER: {host_of(s['resolved_url'])}\nURL: {s['resolved_url']}\nFETCHED EVIDENCE:\n{s['evidence_text']}")
    evidence='\n\n--- SOURCE PACKET ---\n'.join(packets)
    constitution=Path('EDITORIAL_CONSTITUTION.md').read_text()
    md=generate_valid_document(build_prompt(body,constitution,evidence),len(verified),evidence)
    footer='''\n\n---\n## Mandatory Gate 2\nNothing proceeds to voice/video production yet.\n\nComment with:\n- `/approve-script`\n- `/revise-script <instruction>`\n- `/reject-script <reason>`\n'''
    created=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Research + Script — {topic}','body':md+footer})
    gh(f"https://api.github.com/repos/{REPO}/issues/{issue['number']}/comments",'POST',{'body':f"📚 Evidence-grounded research dossier + draft script created in #{created['number']} from {len(verified)} readable publisher sources across {len(hosts)} publishers. Gate 2 approval is mandatory."})
    print(f"Created evidence-grounded research/script issue {created['number']} from {len(verified)} sources across {len(hosts)} publishers")

if __name__=='__main__': main()
