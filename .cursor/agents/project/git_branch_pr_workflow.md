---
title: Git branch + PR workflow (no direct pushes to main)
name: git_branch_pr_workflow
description: Reusable guidance for the Email Assistant Agent repo — every change goes on a fresh branch from origin/main, lands via PR, and never directly to main. Covers naming, PR template, recovery if you already direct-pushed, and stale-branch rehab.
status: active
created: 2026-05-19
updated: 2026-05-29
owner: Ralph Moreno
doc_type: agent
source_of_truth: .cursor/agents/project/git_branch_pr_workflow.md
review_after: 2026-08-19
related:
  - .cursor/rules/060-git-workflow.mdc
  - .cursor/rules/020-security-and-secrets.mdc
  - .cursor/rules/160-privacy-and-pii.mdc
  - .cursor/rules/000-repo-overview.mdc
---

# Git branch + PR workflow

Operational agent for **how every change reaches `main`** in [`rvmoreno2233/ai-obsidian-email-assistant`](https://github.com/rvmoreno2233/ai-obsidian-email-assistant). The single rule: **a feature branch cut from `origin/main`, committed locally, pushed, and merged via a pull request — never a direct push to `main`.**

This workflow prevents unreviewed changes on `main`, keeps team branches aligned with a single source of truth, and makes rollback straightforward (revert one PR at a time).

---

## Scope

- **In scope:** any local change intended to ship to `origin/main` — Python app code, Studio UI, YAML catalogs, vault templates, agents, docs, configs, tests.
- **In scope:** recovery steps if direct-to-main has already happened, and rehab of stale branches that share an old merge-base.
- **Out of scope:** day-to-day pipeline execution, Graph auth setup, catalog scraping runs. This file does not change *what* you ship — only *how* it lands.

---

## The one-line rule

> **Branch from `origin/main`, commit on the branch, open a PR back to `main`. Never commit on `main` and never push to `main` directly.**

If you've already direct-pushed, jump to [Recovery](#recovery-if-you-already-direct-pushed). Do not try to rewrite public history.

---

## The standard loop

Run from the repo root (`Email_Agent/`). Replace `<topic>` with a short kebab-case slug (see [Branch naming](#branch-naming)).

```bash
# 1. Sync your local main to public main BEFORE branching.
git fetch origin
git switch main
git pull --ff-only origin main          # never merge into main from your shell

# 2. Cut a fresh branch from origin/main (not from your previous branch).
git switch -c feat/<topic> origin/main

# 3. Make your changes. Commit small, descriptive units.
git add -p                              # interactive, avoids accidental PII / secrets
git commit -m "feat(<area>): <imperative summary>"

# 4. Push the branch with upstream tracking.
git push -u origin feat/<topic>

# 5. Open the PR.
gh pr create --base main --head feat/<topic> --fill
# or via the GitHub UI; both are fine.

# 6. After merge, clean up locally.
git switch main
git pull --ff-only origin main
git branch -d feat/<topic>
git push origin --delete feat/<topic>   # optional, only if branch is fully merged
```

**Things to never do in this loop:**

- `git switch main && git commit ...` — commits land on `main` immediately, that's the bug.
- `git push origin main` — there is no normal reason to do this.
- `git push --force` or `git push --force-with-lease` to `main`.
- `git merge main` from a feature branch followed by pushing the result *to* `main`.

---

## Branch naming

Use a `<type>/<topic>` prefix so PR lists stay scannable. Match conventional-commit-ish prefixes (`feat`, `fix`, `chore`, `docs`, `refactor`, `dev`).

| Prefix       | When to use                                                | Example                                  |
|--------------|------------------------------------------------------------|------------------------------------------|
| `feat/`      | New capability (pipeline, Studio tab, Graph feature)       | `feat/email-settings-auto-response`      |
| `fix/`       | Bug fix without behavior expansion                         | `fix/graph-draft-reply-threading`        |
| `refactor/`  | Internal restructuring, no behavior change                 | `refactor/catalog-store-loaders`         |
| `chore/`     | Cleanup, dependency bumps, gitignore, secrets hygiene      | `chore/ruff-black-ci`                    |
| `docs/`      | Markdown / runbook / agent updates only                    | `docs/studio-api-guide`                  |
| `dev/`       | Developer scratch / experimental — squash-merge or discard | `dev/local-graph-smoke-test`             |

Do **not** prefix branches with personal names (`ralph/...`) when the change is intended to ship; it makes ownership opaque later. Use `dev/` if it might never merge.

---

## What goes in one branch

Match one branch to **one reviewable intent**. Reviewers can hold ~400 lines of diff in their head without skimming, so:

- Keep each branch focused on one change. If you find yourself touching unrelated areas, stop and cut a second branch.
- Commits within the branch should each compile / pass tests when possible.
- If a branch grows past ~1000 changed lines, split it before opening the PR.

The anti-pattern: mixing unrelated changes (gitignore hardening, a new Studio tab, catalog schema changes, and docs) into one push. That hurts review quality and leaves other branches diverged from `main`.

---

## PR hygiene

Every PR description should answer:

```
## Summary
- What this changes (1–3 bullets)
- Why now / what it unblocks

## Test plan
- [ ] `pytest` (or targeted test file) passes
- [ ] `ruff check .` and `black --check .` pass (if Python changed)
- [ ] `EMAIL_BACKEND=mock` smoke run when pipeline behavior changed
- [ ] Studio UI manually checked when `app/web/` changed
- [ ] Catalog / config diffs reviewed for PII (see data/catalog/, config.json)

## Risk and rollback
- Blast radius if this regresses
- Revert plan (single PR revert is fine for additive work)
```

For catalog or Graph changes, also follow:

- [`.cursor/rules/160-privacy-and-pii.mdc`](../../rules/160-privacy-and-pii.mdc) — review scraped inbox data before commit
- [`.cursor/rules/020-security-and-secrets.mdc`](../../rules/020-security-and-secrets.mdc) — no `.env`, tokens, or MSAL cache
- [`.cursor/rules/040-testing-standards.mdc`](../../rules/040-testing-standards.mdc) — synthetic fixtures only in tests

---

## Recovery if you already direct-pushed

If you committed on `main` and pushed before branch protection was enabled, **do not try to rewrite history.** The damage is bounded; rewriting makes it worse.

1. Tag the current state as a backup so a rollback target exists no matter what:

   ```bash
   git fetch --all --prune
   git tag backup/main-pre-cleanup-$(date +%Y-%m-%d) origin/main
   git push origin backup/main-pre-cleanup-$(date +%Y-%m-%d)
   ```

2. Document what happened: affected SHA range, which branches are now stale, and the forward plan (archive tags, re-cut PRs, enable branch protection).
3. Notify the team in the channel where pushes are announced; list the affected SHA range and merge-base impact.
4. Apply branch protection on `main` (see below) so it cannot recur.
5. For each stale team branch, follow the [stale-branch rehab](#stale-branch-rehab) playbook — do not "fix" them by rebasing the corrupted main on top of theirs.

---

## Diagnosing "my branch is N behind"

When someone reports their branch is "200 commits behind," resist the urge to act on that number. It almost never means "200 commits of lost work." It means the branch was cut from `main` a long time ago and `main` moved forward while the branch stood still. Three numbers matter; they are not the same number.

| Number | Command | What it actually means |
|---|---|---|
| **Behind** | `git rev-list --count origin/<branch>..origin/main` | Commits on `main` not on the branch. Pure calendar drift. No relationship to work-to-preserve. |
| **Ahead** | `git rev-list --count origin/main..origin/<branch>` | Commits on the branch not on `main`. **Upper bound** on work-to-preserve, often inflated. |
| **Unique by patch** | `git log --cherry-pick --right-only --no-merges origin/main...origin/<branch> \| wc -l` | Commits on the branch whose **patch** is not on `main` (uses `git patch-id`, so detects rebased/cherry-picked equivalents). **This is the real work-to-preserve.** |

`--cherry-pick` will still misfire in two predictable ways. Recognize them so you don't chase ghosts:

1. **Shared-base false positives.** Old commits from an early project base may show as "unique by patch" because they were squashed or rebased when they hit `main` (different SHA, different line numbers, patch-id no longer matches). Confirm by `git log origin/main --grep="<subject>"` — if the subject + date match, it's already on `main`.

2. **Cluster-source branches.** When a direct-push incident occurs, the *source* feature branches the work originated on will show enormous "ahead" and "unique by patch" counts even though their content is already on `main` under different SHAs. Tell tale: every such branch shows **identical** `ahead` / `behind` / `last commit date` numbers, and the latest commit date matches the incident date.

The full per-author breakdown for one branch:

```bash
BRANCH=feat/email-settings-auto-response

echo "Raw ahead:        $(git rev-list --count origin/main..origin/$BRANCH)"
echo "Unique by patch:  $(git log --cherry-pick --right-only --no-merges \
                            --format='%h' origin/main...origin/$BRANCH | wc -l)"

# Per author (replace email):
echo "Unique by patch (author):"
git log --cherry-pick --right-only --no-merges \
    --author='[email protected]' \
    --format='  %h %cs %s' origin/main...origin/$BRANCH
```

The reframe in one sentence: **"Behind" is a calendar fact about `main`, not a fact about the developer's work. Always quote the unique-by-patch number, never the raw ahead, when telling someone what they have to deal with.**

---

## Stale-branch rehab

A branch is stale when its merge-base with `origin/main` is more than ~50 commits behind. **Diagnose before you rehab** — run the [Diagnosing](#diagnosing-my-branch-is-n-behind) commands first so you know whether there's any real work to preserve.

### Pre-rehab triage matrix

Before pinging owners, build a one-row-per-branch table. This converts N drive-by Slack/Teams pings into one consolidated conversation per owner:

| Column | How to fill it |
|---|---|
| `branch` | Branch name on `origin` |
| `owner` | `git log -1 --format='%an' origin/<branch>` (or the team-known owner) |
| `last_commit` | `git log -1 --format='%cs' origin/<branch>` |
| `raw_ahead` | `git rev-list --count origin/main..origin/<branch>` |
| `unique_by_patch` | `git log --cherry-pick --right-only --no-merges --format='%h' origin/main...origin/<branch> \| wc -l` |
| `bucket` | A, B, or C — see below |
| `proposed_pr` | Suggested follow-up branch name (or "—" for Bucket A) |

Bucket definitions:

- **Bucket A — Already-shipped or empty.** `unique_by_patch` is 0, or all non-zero entries are shared-base false positives. Archive tag + delete. No owner action needed beyond a courtesy ack.
- **Bucket B — Real work to preserve.** `unique_by_patch` resolves (after subtracting shared-base false positives) to commits whose subjects are not on `main`. Cherry-pick onto a fresh branch from current `main`, group **one PR per intent** (don't bundle unrelated commits even if they came from the same stale branch), open small reviewable PRs.
- **Bucket C — Local-env / scratch.** Branches with self-evident scratchpad commit subjects (`(in-progress)`, `local env setup`, `sync from main`). Courtesy ping the owner, then Bucket A.

Then send **one DM per owner** containing all of their branches' rows, the proposed PRs, and the time ask. See [Team comms templates](#team-comms-templates).

### Path A — Re-cut (preferred for most stale branches)

```bash
git fetch origin

# Archive first, always.
git tag archive/<old-branch>-pre-recut-$(date +%Y-%m-%d) origin/<old-branch>
git push origin archive/<old-branch>-pre-recut-$(date +%Y-%m-%d)

# New branch off current main. Cherry-pick only the commits you actually want.
git switch -c <old-branch>-v2 origin/main
git cherry-pick <sha1> <sha2> ...

git push -u origin <old-branch>-v2
gh pr create --base main --head <old-branch>-v2 --fill

# After merge, retire the original.
git push origin --delete <old-branch>
```

### Path B — Rebase (only for clean, linear branches with the original author available)

```bash
git fetch origin

git tag archive/<branch>-pre-rebase-$(date +%Y-%m-%d) origin/<branch>
git push origin archive/<branch>-pre-rebase-$(date +%Y-%m-%d)

git switch <branch>
git rebase origin/main          # resolve conflicts iteratively
git push --force-with-lease origin <branch>
gh pr create --base main --head <branch> --fill
```

If you don't own a stale branch, **do not rebase or delete it**. Ping the owner. Use the archive tag pattern even when the branch will only be deleted, so the SHAs are recoverable.

---

## Team comms templates

Reusable Teams / Slack / email copy for the human side of an incident or cleanup. Send the team-wide announcement first, then per-owner DMs once you've done the [Pre-rehab triage matrix](#pre-rehab-triage-matrix) and have proposed PR branches ready. **All templates are privacy-safe**: they cite SHAs, paths, counts, and branch names only — never email content, env values, or credentials.

### Team-wide announcement (post in dev channel)

Send after the cleanup plan / workflow doc has merged to `main`, so the doc link resolves.

```
Heads-up: branch cleanup happening this week

Quick context
On <YYYY-MM-DD>, ~<N> commits landed directly on main outside the normal PR
flow. They are good, in-use changes (<one-line summary of the cluster>)
and they are staying. But the side effect was every open branch suddenly
looked <X>-<Y> commits "behind."

Important: that "behind" number is mostly calendar drift, not lost work.
We audited every branch. Out of ~<total apparent stale> commits of apparent
staleness, the actual unshipped work-to-preserve across the whole team is
<real unique-by-patch total> commits.

What's changing this week
1. Every existing branch gets an archive/<name>-pre-cleanup-<YYYY-MM-DD>
   tag before anything is touched. Nothing is unrecoverable.
2. Direct push to main is being turned off. Every change to main goes
   through a PR. No exceptions.
3. Stale branches with no unique work get archived and deleted.
4. Branches with real unique work get re-cut from current main with the
   relevant commits cherry-picked into small, reviewable PRs.

What you do
Nothing yet. I'll DM each of you with your specific list and proposed
PRs. If you have uncommitted local work on any branch, push it now so
it gets captured before archive tags are cut.

Full writeup: <link to incident doc or PR>
```

### Per-owner DM (one per developer, not one per branch)

Sent after Bucket A/B/C classification is done and Bucket B PRs are at least cherry-picked locally. Each DM bundles **all** of the owner's branches so they have one consolidated conversation, not N drive-bys.

```
Hey <name> — branch cleanup audit is done for your work.

Good news first: most of what looks "behind" on your branches is already
on main from the <YYYY-MM-DD> merge, just under different SHAs.

Branches I'm archiving (work is already on main or N/A):
- <branch>     (<reason — e.g. email-settings work shipped under cluster>)
- <branch>     (<reason>)
- <branch>     (<reason>)

Branches I'm bundling into <N> small PRs for you to review:

PR A: <descriptive title>
   from <stale branch>
   <N> commits, <one-line context>

PR B: <descriptive title>
   from <stale branch>
   <N> commits, <one-line context>

PR <X>: <descriptive title> (needs your input first)
   from <stale branch>
   <N> candidate commits — <one-line summary>. Need <X> min of your
   time to confirm which are still wanted vs superseded.

Bigger question — <coherent feature branch with N commits>:
   <one-paragraph context: what's already on main, what's still off main,
    why I can't decide this without you>
   Three options:
     1. Resurrect — re-cut from current main, ship it
     2. Pause — archive behind a safety tag, note in README or docs
     3. Supersede — you note what you'd do differently and we mark
        the plan obsolete pending re-design
   Your call. No action until you weigh in.

Last small one — <N> old local-env branches I'd like to archive:
   <branch>
   <branch>
   These look like <YYYY-MM> local-<thing> bring-up scratchpads.
   Safe to archive? (Each gets a safety tag either way.)

Total time ask: <60–90 min, or whatever the actual estimate is>.
```

### Archive courtesy ping (for ambiguous local-env / scratch branches)

Use when you're confident a branch is dead but the owner hasn't said so out loud. Keeps the "no work deleted without owner sign-off" promise without burning ceremony.

```
Quick ack? I'd like to archive these branches:

  <branch>
  <branch>
  <branch>

They look like <YYYY-MM> local Graph / Studio / catalog scratchpads —
last commit subjects include "(in-progress)" / "sync from main" / etc.

Each one gets an archive/<branch>-pre-cleanup-<YYYY-MM-DD> tag before
deletion, so we can resurrect any of them with one command if I'm wrong.

Reply "ok" / "wait, keep X" / "actually X has WIP I haven't pushed."
```

### What NOT to put in these templates

- Email bodies, scraped catalog rows, or other PII from the branches.
- `.env`, OAuth tokens, MSAL cache paths, or any value from credentials files.
- Full commit diffs. Subjects + SHAs only.
- Speculation about why someone direct-pushed. Stick to the facts and the forward plan.

---

## Branch protection on `main` (one-time setup)

The platform-level enforcement that makes this rule self-policing. On `rvmoreno2233/ai-obsidian-email-assistant` → Settings → Branches → branch protection rule for `main`:

- Require a pull request before merging
- Require at least 1 review approval (raise to 2 once the team grows)
- Disallow direct pushes (no admin bypass, or restrict to one named owner with a documented reason)
- Require status checks to pass (CI, linters, validators when configured)
- Optional: require linear history to block accidental main-into-main merges

Once enabled, a developer who tries `git push origin main` from a feature branch gets a server-side rejection. That is the goal.

---

## Quick reference card

```bash
# Start work
git fetch origin && git switch main && git pull --ff-only && git switch -c feat/<topic> origin/main

# Land work
git push -u origin feat/<topic> && gh pr create --base main --fill

# Sync long-running branch with main without leaving main
git fetch origin && git switch feat/<topic> && git rebase origin/main

# Emergency: I committed on main locally, NOT pushed yet
git switch -c feat/<topic>          # carry the commits to a new branch
git switch main                     # back to main
git reset --hard origin/main        # main now matches public state
# then push feat/<topic> and open the PR

# Emergency: I committed AND pushed to main
# -> stop, do not force-push, follow Recovery section above
```

---

## Privacy and safety

- Never paste email content, scraped catalog rows, env values, OAuth tokens, or MSAL cache contents into commits, PRs, branch descriptions, or agent chat.
- PR descriptions cite **paths and counts**, not message bodies or contact details.
- Use `git add -p` to review hunks before committing — catches accidental PII in `data/catalog/` or test fixtures.
- Do not commit `.env`, MSAL cache, or token files. See [`.cursor/rules/020-security-and-secrets.mdc`](../../rules/020-security-and-secrets.mdc). If a secret was committed, treat it as a security incident and rotate the credential before pushing the cleanup PR.
- Review `data/catalog/` and `config.json` diffs for business-sensitive data before opening a PR. See [`.cursor/rules/160-privacy-and-pii.mdc`](../../rules/160-privacy-and-pii.mdc).

---

## When to update this agent

Bump `updated:` in the frontmatter when you:

- Add or change a branch prefix in the [Branch naming](#branch-naming) table.
- Change the PR template or required CI checks.
- Adopt a new branch protection setting that callers need to know about.
- Document a direct-push incident worth referencing here.
- Change the diagnostic commands in [Diagnosing](#diagnosing-my-branch-is-n-behind) (e.g. a new `git` flag, a different patch-id helper).
- Revise the [Pre-rehab triage matrix](#pre-rehab-triage-matrix) bucket definitions.
- Update any [Team comms templates](#team-comms-templates) — re-audit for email content, secrets, or env values.

Preserve `created:`; only revise `updated:`.

---

## References

- Repo: [`rvmoreno2233/ai-obsidian-email-assistant`](https://github.com/rvmoreno2233/ai-obsidian-email-assistant)
- Git hygiene: [`.cursor/rules/060-git-workflow.mdc`](../../rules/060-git-workflow.mdc)
- Secrets: [`.cursor/rules/020-security-and-secrets.mdc`](../../rules/020-security-and-secrets.mdc)
- PII: [`.cursor/rules/160-privacy-and-pii.mdc`](../../rules/160-privacy-and-pii.mdc)
- Testing: [`.cursor/rules/040-testing-standards.mdc`](../../rules/040-testing-standards.mdc)
- Package overview: [`.cursor/rules/000-repo-overview.mdc`](../../rules/000-repo-overview.mdc)
