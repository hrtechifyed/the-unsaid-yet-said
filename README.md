# THE UNSAID, YET SAID

**What isn’t said often says the most.**  
**Powered by HRTechify**

An approval-gated, AI-assisted YouTube content engine for decoding the signals, behaviours, choices, silences and decisions through which people and organisations communicate at work.

## Operating model

1. The topic engine proposes current workplace/career ideas.
2. The Editor-in-Chief approves one topic.
3. Research + evidence pack + script are generated.
4. The Editor-in-Chief approves the script.
5. **Before production, choose: Faceless or Face/Hybrid.**
6. Production creates a 7–10 minute episode and uploads it to YouTube as **PRIVATE**.
7. The finished package requires Gate 3 approval before anything can be made public.
8. Analytics and editor feedback feed the learning loop.

## Permanent Face/Hybrid episode template

Target runtime: **8:30** with an allowed range of **7:00–10:00**.

- **00:00–00:25 — Avatar opening**
  - HRTechify-branded avatar
  - Anurag cloned voice
  - Hook, tension and core question

- **00:25–08:00 — Visual storytelling middle**
  - Anurag cloned voice continues from first word to last
  - Avatar is off screen
  - Workplace illustrations/B-roll, animated statistics, charts, frameworks, key phrases, comparison cards and scene changes
  - Subtle HRTechify watermark remains visible

- **08:00–08:30 — Avatar closing**
  - Avatar returns
  - Same cloned voice
  - Synthesis, final thought and channel signature

For episodes that run shorter or longer inside the 7–10 minute range, keep the opening at **25 seconds** and closing at **30 seconds**; only the visual middle expands or contracts.

Canonical configuration: `config/episode_template.json`

## Permanent production rules

- Anurag's cloned voice narrates the **entire episode** in Face/Hybrid mode.
- The avatar appears only in the opening and closing unless the Editor explicitly requests otherwise.
- Use the **exact approved HRTechify logo asset**. Never recreate or approximate the logo.
- Keep HRTechify branding subtle and visible throughout.
- No Siemens name, logo, imagery, colours or references in this channel's production assets.
- Interpretations must be presented as possibilities, not mind-reading.
- Quantitative claims must remain tied to the approved evidence pack.
- All new previews upload as **PRIVATE** by default.

## Approval commands

Gate 1 — Topic Proposals:
- `/approve 3`
- `/reject 3 reason`
- `/revise 3 make the employee perspective stronger`

Gate 2 — Research + Script:
- `/approve-script`
- `/revise-script <instruction>`
- `/reject-script <reason>`

Gate 3 — Final Preview:
- `/approve-publish`
- `/revise-production <instruction>`
- `/reject-production <reason>`

## Current status

- [x] Editorial constitution
- [x] Topic discovery + proposal workflow
- [x] Mandatory human topic approval
- [x] Research pack + script generation
- [x] Script approval gate
- [x] PRIVATE YouTube upload + final approval gate
- [x] Permanent 7–10 minute Face/Hybrid production template
- [x] Topic 1 hybrid scene plan
- [ ] Custom Anurag voice integrated into the production pipeline
- [ ] Avatar opening/closing generation integrated
- [ ] Rich visual middle generation integrated
- [ ] Production revision loop automated
- [ ] Analytics learning loop

## Required repository secrets

- `GEMINI_API_KEY`
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`

No API key, OAuth credential or token should ever be committed to this public repository.
