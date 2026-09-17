#!/usr/bin/env python3
import json, os, random, re, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path
REPO=os.environ.get('GITHUB_REPOSITORY','hrtechifyed/the-unsaid-yet-said'); GITHUB_TOKEN=os.environ.get('GITHUB_TOKEN',''); GEMINI_API_KEY=os.environ.get('GEMINI_API_KEY',''); GEMINI_MODEL=os.environ.get('GEMINI_MODEL','gemini-3.6-flash'); EVENT_PATH=os.environ.get('GITHUB_EVENT_PATH',''); OWNER=os.environ.get('GITHUB_REPOSITORY_OWNER',''); TRANSIENT_HTTP={429,500,502,503,504}
def api(url,method='GET',payload=None):
 data=None if payload is None else json.dumps(payload).encode(); req=urllib.request.Request(url,data=data,method=method)
 for k,v in {'Content-Type':'application/json','Authorization':f'Bearer {GITHUB_TOKEN}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}.items(): req.add_header(k,v)
 with urllib.request.urlopen(req,timeout=60) as r: return json.loads(r.read().decode()) if r.status!=204 else {}
def gemini(prompt,max_attempts=5):
 if not GEMINI_API_KEY: raise RuntimeError('GEMINI_API_KEY is required for /revise commands')
 url=f'https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(GEMINI_MODEL)}:generateContent'; data=json.dumps({'contents':[{'parts':[{'text':prompt}]}],'generationConfig':{'temperature':0.6}}).encode()
 for attempt in range(1,max_attempts+1):
  req=urllib.request.Request(url,data=data,method='POST',headers={'Content-Type':'application/json','x-goog-api-key':GEMINI_API_KEY})
  try:
   with urllib.request.urlopen(req,timeout=90) as r: result=json.loads(r.read().decode())
   return result['candidates'][0]['content']['parts'][0]['text'].strip()
  except urllib.error.HTTPError as e:
   detail=e.read().decode(errors='replace')[:800]
   if e.code not in TRANSIENT_HTTP or attempt==max_attempts: raise RuntimeError(f'Gemini HTTP {e.code} after {attempt} attempt(s): {detail}') from e
   delay=min(60,2**attempt+random.uniform(0,2)); print(f'Gemini transient HTTP {e.code}; retrying in {delay:.1f}s',file=sys.stderr); time.sleep(delay)
  except (urllib.error.URLError,TimeoutError) as e:
   if attempt==max_attempts: raise RuntimeError(f'Gemini network failure after {attempt} attempts: {e}') from e
   delay=min(60,2**attempt+random.uniform(0,2)); print(f'Gemini network error; retrying in {delay:.1f}s',file=sys.stderr); time.sleep(delay)
 raise RuntimeError('Gemini request exhausted retries')
def extract_proposal(body,number):
 m=re.search(rf'(^## {number}\. .*?)(?=\n---\n|\Z)',body,flags=re.M|re.S); return m.group(1).strip() if m else None
def proposal_title(block):
 m=re.match(r'## \d+\.\s*(.+)',block or ''); return m.group(1).strip() if m else 'Untitled'
def comment(n,text): return api(f'https://api.github.com/repos/{REPO}/issues/{n}/comments','POST',{'body':text})
def dispatch_research(issue_number): api(f'https://api.github.com/repos/{REPO}/actions/workflows/research-script.yml/dispatches','POST',{'ref':'main','inputs':{'issue_number':str(issue_number)}})
def main():
 event=json.loads(Path(EVENT_PATH).read_text()); actor=(event.get('comment',{}).get('user',{}).get('login') or '')
 if OWNER and actor.lower()!=OWNER.lower(): raise RuntimeError('SAFETY STOP: editor command actor is not repository owner')
 issue=event.get('issue',{}); user_comment=(event.get('comment',{}).get('body') or '').strip(); n=issue.get('number'); title0=issue.get('title',''); body=issue.get('body') or ''
 if not n or not title0.startswith('Topic Proposals —'): print('Ignoring non-topic-proposal issue'); return
 cmd=re.match(r'^/(approve|reject|revise)\s+(\d+)(?:\s+(.*))?$',user_comment,flags=re.I|re.S)
 if not cmd: print('No supported command found'); return
 action=cmd.group(1).lower(); number=int(cmd.group(2)); instruction=(cmd.group(3) or '').strip(); block=extract_proposal(body,number)
 if not block: comment(n,f"I couldn't find proposal **{number}**. Please use a number shown in this issue."); return
 title=proposal_title(block)
 if action=='approve':
  approved_body=f'''# Approved Topic Record\n\n**Status:** APPROVED FOR RESEARCH — no script or video is approved yet.  \n**Source proposal issue:** #{n}\n\n{block}\n\n---\n\n## Next mandatory gate\n\nThe next stage will fetch readable publisher material, create a claim-evidence ledger, and draft a script. **That output must be explicitly approved before any voice/video production begins.**\n'''
  created=api(f'https://api.github.com/repos/{REPO}/issues','POST',{'title':f'Approved Topic — {title}','body':approved_body}); dispatch_research(created['number']); comment(n,f"✅ Proposal **{number}** approved for **research only**. Created #{created['number']} and dispatched the evidence-grounded research/script stage. Nothing beyond research/script may advance without your next approval."); api(f'https://api.github.com/repos/{REPO}/issues/{n}','PATCH',{'state':'closed','state_reason':'completed'}); return
 if action=='reject': comment(n,f"❌ Proposal **{number}** rejected. It will not advance.\n\n**Reason:** {instruction or 'No reason supplied.'}"); return
 if action=='revise':
  if not instruction: comment(n,f'Please add a revision instruction, e.g. `/revise {number} strengthen the employee perspective`.'); return
  prompt=f'''You are revising a single topic proposal for THE UNSAID, YET SAID — Powered by HRTechify.\n\nEDITOR'S INSTRUCTION:\n{instruction}\n\nCURRENT PROPOSAL:\n{block}\n\nRevise the proposal while preserving the exact Markdown field structure already used. Keep the heading exactly `## {number}. <title>`. Do not invent facts, studies, URLs, trends or statistics. Retain only source links already present unless removing them. Decode signals without mind-reading or deterministic conclusions. Return only the revised Markdown proposal block, with no code fence or explanation.'''
  revised=re.sub(r'^```(?:markdown)?\s*|\s*```$','',gemini(prompt),flags=re.I|re.S).strip()
  if not revised.startswith(f'## {number}.'): raise RuntimeError('Revision did not preserve proposal heading')
  api(f'https://api.github.com/repos/{REPO}/issues/{n}','PATCH',{'body':body.replace(block,revised,1)}); comment(n,f'✏️ Proposal **{number}** revised using your instruction: _{instruction}_\n\nReview the updated proposal above. It still requires `/approve {number}` to advance.')
if __name__=='__main__': main()
