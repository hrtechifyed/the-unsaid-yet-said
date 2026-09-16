# One-time setup

The repository is public, but credentials must remain private in GitHub Actions Secrets.

## 1. Create a Gemini API key

Use Google AI Studio and create an API key for the Gemini Developer API.

The workflow defaults to:

`gemini-3.6-flash`

If a different free-tier model is available to your account later, set a repository variable named `GEMINI_MODEL` instead of changing code.

## 2. Add the key to GitHub

Repository → **Settings → Secrets and variables → Actions → Secrets → New repository secret**

Name:

`GEMINI_API_KEY`

Value: your API key.

Never paste the key into an Issue, README, workflow file, commit, or chat screenshot.

## 3. Optional model variable

Repository → **Settings → Secrets and variables → Actions → Variables → New repository variable**

Name:

`GEMINI_MODEL`

Suggested value:

`gemini-3.6-flash`

This variable is optional because the workflow already uses that model as its default.

## 4. Run the first test

Repository → **Actions → Topic Discovery → Run workflow**

Expected result:

- The workflow gathers current workplace/career news signals.
- AI generates exactly five topic proposals.
- A GitHub Issue named `Topic Proposals — YYYY-MM-DD` is created.
- The process stops there.

## 5. Review from your phone

Inside the Topic Proposals issue, comment:

- `/approve 2`
- `/reject 2 too generic`
- `/revise 2 show what the employee is communicating too`

Approval creates an **Approved Topic — ...** issue with status **APPROVED FOR RESEARCH** only.

It does not approve a script, video, thumbnail, or publication.

## Automation schedule

Once configured, Topic Discovery runs automatically at **09:00 IST every Monday, Wednesday and Friday**.

If an earlier Topic Proposals issue is still open, a new batch is not created.

## Security model

The built-in GitHub Actions `GITHUB_TOKEN` is used for creating and updating Issues. Only the Gemini key needs to be added manually at this stage.
