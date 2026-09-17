#!/usr/bin/env python3
import json, os, re, sys, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said'); GITHUB_TOKEN=os.environ.get('GITHUB_TOKEN',''); GEMINI_API_KEY=os.environ.get('GEMINI_API_KEY',''); GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash')
NEWS_QUERIES=['workplace employee manager career promotion','employee engagement workplace culture leadership','hiring layoffs workforce workplace trends','salary performance review promotion career','AI workplace jobs employees managers','return to office hybrid work employees']
def http_json(url,method='GET',payload=None,headers=None):
 data=None if payload is None else json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,method=method); req.add_header('Content-Type','application/json')
 for k,v in (headers or {}).items(): req.add_header(k,v)
 with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode())
def github_headers(): return {'Authorization':f'Bearer {GITHUB_TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
def has_open_topic_gate():
 issues=http_json(f'https://api.github.com/repos/{REPO}/issues?state=open&per_page=100',headers=github_headers())
 for issue in issues:
  if not issue.get('pull_request') and (issue.get('title') or '').startswith('Topic Proposals —'): print(f"Open topic approval gate already exists: #{issue['number']}. Skipping new proposal batch."); return True
 return False
def collect_signals():
 items=[]; seen=set()
 for query in NEWS_QUERIES:
  try:
   url=f'https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en'
   with urllib.request.urlopen(url,timeout=20) as response: root=ET.fromstring(response.read())
   for item in root.findall('.//item')[:12]:
    title=(item.findtext('title') or '').strip(); link=(item.findtext('link') or '').strip(); pub=(item.findtext('pubDate') or '').strip(); key=title.lower()
    if title and key not in seen: seen.add(key); items.append({'title':title,'link':link,'published':pub})
  except Exception as exc: print(f'Warning: could not fetch {query}: {exc}',file=sys.stderr)
 return items[:60]
def call_gemini(prompt):
 if not GEMINI_API_KEY: raise RuntimeError('GEMINI_API_KEY missing')
 url=f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(GEMINI_MODEL)}:generateContent'; payload={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.75,'responseMimeType':'application/json'}}
 result=http_json(url,'POST',payload,{'x-goog-api-key':GEMINI_API_KEY}); text=result['candidates'][0]['content']['parts'][0]['text']; return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',text.strip(),flags=re.I|re.S))
def build_prompt(signals):
 constitution=Path('EDITORIAL_CONSTITUTION.md').read_text(); config=json.loads(Path('config/channel.json').read_text()); signal_text='\n'.join(f"- {x['title']} | {x['published']} | {x['link']}" for x in signals)
 return f'''You are the Topic Editor for THE UNSAID, YET SAID, Powered by HRTechify.\n\nEDITORIAL CONSTITUTION:\n{constitution}\n\nCHANNEL CONFIG:\n{json.dumps(config,ensure_ascii=False,indent=2)}\n\nCURRENT PUBLIC SIGNALS:\n{signal_text}\n\nCreate exactly 5 distinct YouTube topic proposals. IMPORTANT: this is discovery, not research. Headlines are leads only. Do not present a headline, number, trend, motive, prevalence, or causal explanation as established fact. Frame the unsaid signal and interpretations as hypotheses/questions to investigate. Any quantitative statement belongs only in evidence_needed until verified from source content. Prefer timely topics with evergreen value. Vary the primary lens; at least one must focus on employees.\n\nFields: working_title, primary_pillar, primary_lens, unsaid_signal, what_is_observable, plausible_interpretations (array >=2), stakeholder_perspectives (employee, manager, peer_or_team, hr_or_people_system, leadership_or_organisation), why_now, viewer_value, opening_hook, evidence_needed (array), source_leads (only supplied URLs), risk_or_caveat, suggested_video_length_minutes.\n\nConstraints: decode signals, never mind-read; no deterministic conclusions; no unsupported layoff rumours or diagnosis; no generic listicles; distinguish observable behavior from hypotheses; explicitly preserve uncertainty. Return JSON object with key proposals containing exactly 5 objects.'''
def proposal_markdown(p,n):
 perspectives=p.get('stakeholder_perspectives',{}); source_lines='\n'.join(f"  - [{s.get('title','Source')}]({s.get('url','')})" for s in p.get('source_leads',[])) or '  - None yet — research required'; interpretations='\n'.join(f'  - {x}' for x in p.get('plausible_interpretations',[])); evidence='\n'.join(f'  - {x}' for x in p.get('evidence_needed',[])); stakeholder='\n'.join(f'  - **{k}:** {v}' for k,v in perspectives.items())
 return f'''## {n}. {p.get('working_title','Untitled')}\n\n**Primary pillar:** {p.get('primary_pillar','')}  \n**Primary lens:** {p.get('primary_lens','')}  \n**The unsaid signal / hypothesis:** {p.get('unsaid_signal','')}  \n**What is observable:** {p.get('what_is_observable','')}  \n**Why investigate now:** {p.get('why_now','')}  \n**Viewer value:** {p.get('viewer_value','')}  \n**Opening hook:** {p.get('opening_hook','')}  \n**Suggested length:** {p.get('suggested_video_length_minutes','')} minutes\n\n**Plausible interpretations to test**\n{interpretations}\n\n**Stakeholder perspectives**\n{stakeholder}\n\n**Evidence needed before scripting**\n{evidence}\n\n**Discovery source leads — not proof**\n{source_lines}\n\n**Risk / caveat:** {p.get('risk_or_caveat','')}'''
def create_issue(proposals):
 today=datetime.now(timezone.utc).strftime('%Y-%m-%d'); body=['# Topic Approval Gate','','**Nothing advances until you explicitly approve a proposal. Topic proposals are hypotheses for research, not factual findings.**','','Comment with one of:','- `/approve 3`','- `/reject 3 reason`','- `/revise 3 make the employee perspective stronger`','','---','']
 for i,p in enumerate(proposals,1): body.extend([proposal_markdown(p,i),'','---',''])
 return http_json(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Topic Proposals — {today}','body':'\n'.join(body),'labels':[]},github_headers())
def main():
 if has_open_topic_gate(): return
 signals=collect_signals()
 if not signals: raise RuntimeError('No public signals collected; refusing to invent topics')
 proposals=call_gemini(build_prompt(signals)).get('proposals',[])
 if len(proposals)!=5: raise RuntimeError(f'Expected exactly 5 proposals, got {len(proposals)}')
 issue=create_issue(proposals); print(f"Created topic approval issue #{issue['number']}: {issue['html_url']}")
if __name__=='__main__': main()
