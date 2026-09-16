# THE UNSAID, YET SAID

**What isn’t said often says the most.**  
**Powered by HRTechify**

An approval-gated, AI-assisted YouTube content engine for decoding the signals, behaviours, choices, silences and decisions through which people and organisations communicate at work.

## Operating model

1. The topic engine scans current workplace/career signals.
2. It proposes 5 content ideas in a GitHub Issue.
3. **Nothing advances automatically.** The Editor-in-Chief must approve a topic.
4. Approved topics later move to research + script generation.
5. The script will require a second approval before video production.
6. Initially, the finished video will require a third approval before publishing.

## Gate 1 commands

Comment on a Topic Proposals issue with:

- `/approve 3` — approve proposal 3
- `/reject 3 reason` — reject proposal 3
- `/revise 3 make the employee perspective stronger` — request a revised proposal

## Current MVP

- [x] Editorial constitution
- [x] Topic proposal schema
- [x] GitHub Actions topic workflow
- [x] Mandatory human topic approval gate
- [ ] Research pack generation
- [ ] Script generation + approval gate
- [ ] Voice / visuals / render pipeline
- [ ] Thumbnail + metadata
- [ ] YouTube upload + analytics loop

## Required secret

The Topic Engine uses a free-tier Gemini API key.

Repository → **Settings → Secrets and variables → Actions → New repository secret**

Create:

`GEMINI_API_KEY`

No API key or credential should ever be committed to this public repository.
