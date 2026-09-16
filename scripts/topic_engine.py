#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "hrtechifyed/the-unsaid-yet-said")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

NEWS_QUERIES = [
    "workplace employee manager career promotion",
    "employee engagement workplace culture leadership",
    "hiring layoffs workforce workplace trends",
    "salary performance review promotion career",
    "AI workplace jobs employees managers",
    "return to office hybrid work employees",
]


def http_json(url, method="GET", payload=None, headers=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def collect_signals():
    items = []
    seen = set()
    for query in NEWS_QUERIES:
        encoded = urllib.parse.quote(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                root = ET.fromstring(response.read())
            for item in root.findall(".//item")[:12]:
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                key = title.lower()
                if title and key not in seen:
                    seen.add(key)
                    items.append({"title": title, "link": link, "published": pub_date})
        except Exception as exc:
            print(f"Warning: could not fetch {query}: {exc}", file=sys.stderr)
    return items[:60]


def call_gemini(prompt):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing. Add it as a GitHub Actions repository secret.")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(GEMINI_MODEL)}:generateContent"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.75,
            "responseMimeType": "application/json"
        }
    }
    result = http_json(url, "POST", payload, {"x-goog-api-key": GEMINI_API_KEY})
    try:
        text = result["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {result}") from exc
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    return json.loads(text)


def build_prompt(signals):
    constitution = Path("EDITORIAL_CONSTITUTION.md").read_text(encoding="utf-8")
    config = json.loads(Path("config/channel.json").read_text(encoding="utf-8"))
    signal_text = "\n".join(
        f"- {x['title']} | {x['published']} | {x['link']}" for x in signals
    )
    return f"""
You are the Topic Editor for THE UNSAID, YET SAID, Powered by HRTechify.

EDITORIAL CONSTITUTION:
{constitution}

CHANNEL CONFIG:
{json.dumps(config, ensure_ascii=False, indent=2)}

CURRENT PUBLIC SIGNALS:
{signal_text}

Create exactly 5 distinct YouTube topic proposals. The source signals are discovery inputs, not automatically facts. Do not invent a trend, statistic, study, source, or company claim. Prefer topics that are timely but still have evergreen value.

Across the five proposals, deliberately vary the primary lens. At least one must focus primarily on what EMPLOYEES communicate indirectly, not just what managers/HR/organisations communicate.

Each proposal must contain these fields:
- working_title
- primary_pillar
- primary_lens
- unsaid_signal
- what_is_observable
- plausible_interpretations (array; at least 2)
- stakeholder_perspectives (object with employee, manager, peer_or_team, hr_or_people_system, leadership_or_organisation; use concise text and 'not central' only when genuinely peripheral)
- why_now
- viewer_value
- opening_hook
- evidence_needed (array)
- source_leads (array of objects with title and url; only URLs supplied in CURRENT PUBLIC SIGNALS)
- risk_or_caveat
- suggested_video_length_minutes

Editorial constraints:
1. Decode signals; never mind-read.
2. Do not use 'this always means', 'HR secretly...', or deterministic conclusions.
3. No unsupported layoff rumours or psychiatric/personality diagnosis.
4. Avoid generic listicles.
5. Make the tension recognisable to working professionals.
6. Give the editor enough information to decide whether the topic deserves research.
7. A proposal is NOT an approved factual claim; explicitly preserve uncertainty.

Return a JSON object with one key: proposals, containing exactly 5 objects. No prose outside JSON.
""".strip()


def proposal_markdown(p, n):
    perspectives = p.get("stakeholder_perspectives", {})
    source_lines = "\n".join(
        f"  - [{s.get('title','Source')}]({s.get('url','')})" for s in p.get("source_leads", [])
    ) or "  - None yet — research required"
    interpretations = "\n".join(f"  - {x}" for x in p.get("plausible_interpretations", []))
    evidence = "\n".join(f"  - {x}" for x in p.get("evidence_needed", []))
    stakeholder = "\n".join(f"  - **{k}:** {v}" for k, v in perspectives.items())
    return f"""
## {n}. {p.get('working_title','Untitled')}

**Primary pillar:** {p.get('primary_pillar','')}  
**Primary lens:** {p.get('primary_lens','')}  
**The unsaid signal:** {p.get('unsaid_signal','')}  
**What is observable:** {p.get('what_is_observable','')}  
**Why now:** {p.get('why_now','')}  
**Viewer value:** {p.get('viewer_value','')}  
**Opening hook:** {p.get('opening_hook','')}  
**Suggested length:** {p.get('suggested_video_length_minutes','')} minutes

**Plausible interpretations**
{interpretations}

**Stakeholder perspectives**
{stakeholder}

**Evidence needed before scripting**
{evidence}

**Current source leads**
{source_lines}

**Risk / caveat:** {p.get('risk_or_caveat','')}
""".strip()


def create_issue(proposals):
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is missing")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = [
        "# Topic Approval Gate",
        "",
        "**Nothing advances until you explicitly approve a proposal.**",
        "",
        "Comment with one of:",
        "- `/approve 3`",
        "- `/reject 3 reason`",
        "- `/revise 3 make the employee perspective stronger`",
        "",
        "---",
        "",
    ]
    for i, p in enumerate(proposals, 1):
        body.append(proposal_markdown(p, i))
        body.extend(["", "---", ""])
    payload = {
        "title": f"Topic Proposals — {today}",
        "body": "\n".join(body),
        "labels": []
    }
    return http_json(
        f"https://api.github.com/repos/{REPO}/issues",
        "POST",
        payload,
        {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    )


def main():
    signals = collect_signals()
    if not signals:
        raise RuntimeError("No public signals were collected; refusing to invent topics without discovery input.")
    result = call_gemini(build_prompt(signals))
    proposals = result.get("proposals", [])
    if len(proposals) != 5:
        raise RuntimeError(f"Expected exactly 5 proposals, got {len(proposals)}")
    issue = create_issue(proposals)
    print(f"Created topic approval issue #{issue['number']}: {issue['html_url']}")


if __name__ == "__main__":
    main()
