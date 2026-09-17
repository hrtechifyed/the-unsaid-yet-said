# THE UNSAID, YET SAID

**What isn’t said often says the most.**  
**Powered by HRTechify**

An approval-gated, AI-assisted YouTube content engine for decoding the signals, behaviours, choices, silences and decisions through which people and organisations communicate at work.

## Operating model

1. The topic engine scans current workplace/career signals.
2. It proposes 5 content ideas in a GitHub Issue.
3. **Nothing advances automatically.** The Editor-in-Chief must approve a topic.
4. An approved topic moves to research + script generation.
5. The script requires a second approval before video production.
6. Production creates narration, captions, a branded 16:9 render, thumbnail and metadata, then uploads the video to the verified YouTube channel as **PRIVATE**.
7. The finished package requires a third approval before any public publishing capability is allowed.

## Approval commands

Gate 1 — Topic Proposals:
- `/approve 3`
- `/reject 3 reason`
- `/revise 3 make the employee perspective stronger`

Gate 2 — Research + Script:
- `/approve-script`
- `/revise-script <instruction>`
- `/reject-script <reason>`

Gate 3 — Final Preview commands are reserved for the publishing handler:
- `/approve-publish`
- `/revise-production <instruction>`
- `/reject-production <reason>`

## Current MVP

- [x] Editorial constitution
- [x] Topic discovery + proposal workflow
- [x] Mandatory human topic approval gate
- [x] Research pack generation
- [x] Script generation + approval gate
- [x] Phase 1 voice / captions / branded render pipeline
- [x] Thumbnail + metadata generation
- [x] Verified PRIVATE YouTube API upload
- [x] Mandatory Final Preview issue creation
- [ ] Gate 3 publishing/revision handler
- [ ] Rich B-roll / scene generation
- [ ] Analytics learning loop

## Required repository secrets

- `GEMINI_API_KEY`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

No API key, OAuth credential or token should ever be committed to this public repository.
