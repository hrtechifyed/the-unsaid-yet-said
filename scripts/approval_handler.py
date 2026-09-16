#!/usr/bin/env python3
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = os.environ.get("GITHUB_REPOSITORY", "hrtechifyed/the-unsaid-yet-said")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
EVENT_PATH = os.environ.get("GITHUB_EVENT_PATH", "")


def api(url, method="GET", payload=None):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Bearer {GITHUB_TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8")) if response.status != 204 else {}


def gemini(prompt):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required for /revise commands")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(GEMINI_MODEL)}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.6}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("x-goog-api-key", GEMINI_API_KEY)
    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))
    return result["candidates"][0]["content"]["parts"][0]["text"].strip()


def extract_proposal(body, number):
    pattern = rf"(^## {number}\. .*?)(?=\n---\n|\Z)"
    match = re.search(pattern, body, flags=re.M | re.S)
    return match.group(1).strip() if match else None


def proposal_title(block):
    m = re.match(r"## \d+\.\s*(.+)", block or "")
    return m.group(1).strip() if m else "Untitled"


def comment(issue_number, text):
    return api(f"https://api.github.com/repos/{REPO}/issues/{issue_number}/comments", "POST", {"body": text})


def main():
    if not EVENT_PATH or not Path(EVENT_PATH).exists():
        raise RuntimeError("Missing GitHub event payload")
    event = json.loads(Path(EVENT_PATH).read_text(encoding="utf-8"))
    issue = event.get("issue", {})
    user_comment = (event.get("comment", {}).get("body") or "").strip()
    issue_number = issue.get("number")
    issue_title = issue.get("title", "")
    issue_body = issue.get("body") or ""

    if not issue_number or not issue_title.startswith("Topic Proposals —"):
        print("Ignoring non-topic-proposal issue")
        return

    cmd = re.match(r"^/(approve|reject|revise)\s+(\d+)(?:\s+(.*))?$", user_comment, flags=re.I | re.S)
    if not cmd:
        print("No supported command found")
        return

    action = cmd.group(1).lower()
    number = int(cmd.group(2))
    instruction = (cmd.group(3) or "").strip()
    block = extract_proposal(issue_body, number)
    if not block:
        comment(issue_number, f"I couldn't find proposal **{number}**. Please use a number shown in this issue.")
        return

    title = proposal_title(block)

    if action == "approve":
        approved_body = f"""# Approved Topic Record

**Status:** APPROVED FOR RESEARCH — no script or video is approved yet.  
**Source proposal issue:** #{issue_number}

{block}

---

## Next mandatory gate

The next stage will create a research pack and draft script. **That output must be explicitly approved before any voice/video production begins.**
"""
        created = api(
            f"https://api.github.com/repos/{REPO}/issues",
            "POST",
            {"title": f"Approved Topic — {title}", "body": approved_body}
        )
        comment(issue_number, f"✅ Proposal **{number}** approved for **research only**. Created #{created['number']}. Nothing beyond research/script may advance without your next approval.")
        api(f"https://api.github.com/repos/{REPO}/issues/{issue_number}", "PATCH", {"state": "closed", "state_reason": "completed"})
        print(f"Approved proposal {number}")
        return

    if action == "reject":
        reason = instruction if instruction else "No reason supplied."
        comment(issue_number, f"❌ Proposal **{number}** rejected. It will not advance.\n\n**Reason:** {reason}")
        print(f"Rejected proposal {number}")
        return

    if action == "revise":
        if not instruction:
            comment(issue_number, f"Please add a revision instruction, e.g. `/revise {number} strengthen the employee perspective`.")
            return
        prompt = f"""
You are revising a single topic proposal for THE UNSAID, YET SAID — Powered by HRTechify.

EDITOR'S INSTRUCTION:
{instruction}

CURRENT PROPOSAL:
{block}

Revise the proposal while preserving the exact Markdown field structure already used. Keep the heading exactly `## {number}. <title>`. Do not invent facts, studies, URLs, trends or statistics. Retain only source links already present unless removing them. Decode signals without mind-reading or deterministic conclusions. Return only the revised Markdown proposal block, with no code fence or explanation.
""".strip()
        revised = gemini(prompt)
        revised = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", revised, flags=re.I | re.S).strip()
        if not revised.startswith(f"## {number}."):
            raise RuntimeError("Revision did not preserve proposal heading")
        new_body = issue_body.replace(block, revised, 1)
        api(f"https://api.github.com/repos/{REPO}/issues/{issue_number}", "PATCH", {"body": new_body})
        comment(issue_number, f"✏️ Proposal **{number}** revised using your instruction: _{instruction}_\n\nReview the updated proposal above. It still requires `/approve {number}` to advance.")
        print(f"Revised proposal {number}")


if __name__ == "__main__":
    main()
