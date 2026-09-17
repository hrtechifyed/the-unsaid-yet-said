#!/usr/bin/env python3
import json, os, re, sys, time, random, urllib.parse, urllib.request, urllib.error
from pathlib import Path
REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said'); TOKEN=os.environ.get('GITHUB_TOKEN',''); GEMINI=os.environ.get('GEMINI_API_KEY',''); MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); EVENT=os.environ.get('GITHUB_EVENT_PATH',''); TRANSIENT_HTTP={429,500,502,503,504}
def gh(url,method='GET',payload=None):
 data=None if payload is None else json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,method=method)
 for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
 with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode()) if r.status!=204 else {}
def gemini(prompt,max_attempts=5):
 if not GEMINI: raise RuntimeError('GEMINI_API_KEY missing')
 url=f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(MODEL)}:generateContent'; payload={'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.35}}; data=json.dumps(payload).encode()
 for attempt in range(1,max_attempts+1):
  req=urllib.request.Request(url,data=data,method='POST'); req.add_header('Content-Type','application/json'); req.add_header('x-goog-api-key',GEMINI)
  try:
   with urllib.request.urlopen(req,timeout=90) as r: out=json.loads(r.read().decode())
   return out['candidates'][0]['content']['parts'][0]['text'].strip()
  except urllib.error.HTTPError as e:
   body=e.read().decode(errors='replace')[:1000]
   if e.code not in TRANSIENT_HTTP or attempt==max_attempts: raise RuntimeError(f'Gemini HTTP {e.code} after {attempt} attempt(s): {body}') from e
   delay=min(60,2**attempt+random.uniform(0,2)); print(f'Gemini transient HTTP {e.code}; retry {attempt}/{max_attempts} in {delay:.1f}s',file=sys.stderr); time.sleep(delay)
  except (urllib.error.URLError,TimeoutError) as e:
   if attempt==max_attempts: raise RuntimeError(f'Gemini network failure after {attempt} attempts: {e}') from e
   delay=min(60,2**attempt+random.uniform(0,2)); print(f'Gemini network error; retry {attempt}/{max_attempts} in {delay:.1f}s',file=sys.stderr); time.sleep(delay)
 raise RuntimeError('Gemini request exhausted retries')
def comment(n,text): gh(f'https://api.github.com/repos/{REPO}/issues/{n}/comments','POST',{'body':text})
def dispatch_production(n): gh(f'https://api.github.com/repos/{REPO}/actions/workflows/production.yml/dispatches','POST',{'ref':'main','inputs':{'issue_number':str(n)}})
def main():
 event=json.loads(Path(EVENT).read_text()); issue=event.get('issue',{}); n=issue.get('number'); title=issue.get('title',''); body=issue.get('body') or ''
 if not title.startswith('Research + Script — '): print('Ignoring non-research issue'); return
 text=(event.get('comment',{}).get('body') or '').strip()
 if text=='/approve-script':
  topic=title.replace('Research + Script — ','',1); created=gh(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Script Approved — {topic}','body':f'''# Production Authorization\n\n**Status:** SCRIPT APPROVED.\n\n**Source:** #{n}\n\nApproval authorizes the next stage to generate voice, visuals, captions, thumbnail and metadata. It does **not** authorize public publishing until the final preview gate is approved.\n'''})
  dispatch_production(created['number']); comment(n,f"✅ Script approved. Production authorization recorded in #{created['number']} and production dispatched. Public publishing remains blocked behind the final preview gate."); gh(f'https://api.github.com/repos/{REPO}/issues/{n}','PATCH',{'state':'closed','state_reason':'completed'}); return
 m=re.match(r'^/revise-script\s+(.+)$',text,flags=re.S|re.I)
 if m:
  instruction=m.group(1).strip(); prompt=f'''Revise the following research dossier + YouTube script for THE UNSAID, YET SAID.\n\nEDITOR INSTRUCTION:\n{instruction}\n\nCURRENT DOCUMENT:\n{body}\n\nPreserve the source ledger and never invent new sources, data, quotes or factual claims. Preserve calibrated language and multiple plausible interpretations. Update the script and any affected checklist sections. Keep the Mandatory Gate 2 instructions at the end. Return complete revised Markdown only.'''; revised=re.sub(r'^```(?:markdown)?\s*|\s*```$','',gemini(prompt),flags=re.I|re.S).strip(); gh(f'https://api.github.com/repos/{REPO}/issues/{n}','PATCH',{'body':revised}); comment(n,f'✏️ Revised using your instruction: _{instruction}_\n\nThe script still requires `/approve-script`.'); return
 m=re.match(r'^/reject-script(?:\s+(.+))?$',text,flags=re.S|re.I)
 if m:
  reason=(m.group(1) or 'No reason supplied.').strip(); comment(n,f'❌ Script rejected. It will not advance.\n\n**Reason:** {reason}'); gh(f'https://api.github.com/repos/{REPO}/issues/{n}','PATCH',{'state':'closed','state_reason':'not_planned'}); return
 print('No Gate 2 command found')
if __name__=='__main__': main()
