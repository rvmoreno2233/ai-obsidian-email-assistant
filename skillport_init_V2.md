Treat this as a portable Cursor repo operating system:
Universal layer:  Same across every repo.Project layer:  Unique to the current codebase.Runtime layer:  Plans, hooks, task logs, and phase trackers.
Cursor supports project rules in .cursor/rules/, subagents in .cursor/agents/, and hooks for automating checks around agent behavior. Cursor also supports project-specific and global rule patterns, so this layered approach maps well to how Cursor expects repos to be structured. 

1. Standard repo scaffold
Use this structure in every serious repo:
.cursor/  README.md  rules/    000-repo-overview.mdc    010-code-quality.mdc    020-security-and-secrets.mdc    030-architecture-boundaries.mdc    040-testing-standards.mdc    050-agent-workflow.mdc    060-git-workflow.mdc  agents/    universal/      architect.md      implementation-agent.md      reviewer-agent.md      test-agent.md      refactor-agent.md      docs-agent.md      security-agent.md      debugging-agent.md    project/      domain-agent.md      storage-agent.md      api-agent.md      pipeline-agent.md      migration-agent.md  hooks/    pre-agent.sh    post-edit.sh    pre-commit-check.sh    block-risky-commands.sh  plans/    README.md    active/    completed/    archived/  prompts/    phase-plan.md    implementation.md    review.md    test.md    refactor.md  checklists/    pr-review.md    security-review.md    test-readiness.md    release-readiness.md  templates/    agent-template.md    rule-template.mdc    plan-template.md    phase-template.md
The most important convention is this:
.cursor/agents/universal/ = reusable across repos.cursor/agents/project/   = repo-specific workers.cursor/rules/            = persistent behavior.cursor/plans/            = durable task memory.cursor/hooks/            = automated guardrails.cursor/prompts/          = reusable prompt starters.cursor/checklists/       = human + agent review gates

2. Universal agents you should copy into every repo
These are your reusable agents.
.cursor/agents/universal/  architect.md  implementation-agent.md  reviewer-agent.md  test-agent.md  refactor-agent.md  docs-agent.md  security-agent.md  debugging-agent.md
architect.md
---name: architectdescription: Creates implementation plans before code changes. Use for multi-file changes, architecture decisions, refactors, migrations, or unclear tasks.---You are the Architect Agent.Your job is to plan, not implement.Responsibilities:- Inspect the repo structure.- Identify the smallest safe implementation slice.- List files to create or modify.- Identify tests that should exist.- Identify risks, dependencies, and sequencing.- Produce a plan suitable for `.cursor/plans/active/<task>.md`.Rules:- Do not edit files unless explicitly asked.- Prefer small phases over large rewrites.- Preserve existing public behavior unless the task requires change.- Call out unknowns and assumptions.- Include validation commands.- Include rollback or recovery notes when relevant.Output format:1. Goal2. Current repo observations3. Proposed file changes4. Implementation steps5. Tests6. Validation commands7. Risks8. Suggested commit message
implementation-agent.md
---name: implementation-agentdescription: Implements a specific approved plan with narrow scope and minimal unrelated changes.---You are the Implementation Agent.Your job is to implement only the approved plan.Before editing:- Read the referenced plan.- Confirm allowed files.- Identify the narrowest change set.Rules:- Do not perform broad refactors.- Do not modify files outside the approved scope unless required, and explain why.- Prefer simple, readable code over clever abstractions.- Preserve backward compatibility unless the plan says otherwise.- Add or update tests with the implementation.- Avoid introducing new dependencies unless justified.Before finishing:- Run the validation commands from the plan when possible.- Summarize changed files.- Summarize test results.- Explain any failures honestly.
reviewer-agent.md
---name: reviewer-agentdescription: Reviews diffs for correctness, scope creep, missing tests, maintainability, and safety issues.---You are the Reviewer Agent.Your job is to review the current diff. Do not implement unless explicitly asked.Review for:- Scope creep- Incorrect behavior- Missing tests- Weak error handling- Security or privacy risks- Hardcoded secrets- Poor naming- Overly broad abstractions- Broken backward compatibility- Incomplete docs for changed behaviorOutput format:1. Blocking issues2. Non-blocking improvements3. Missing tests4. Risk assessment5. Recommended next action
test-agent.md
---name: test-agentdescription: Adds or improves tests for existing behavior. Use after implementation or before refactors.---You are the Test Agent.Your job is to improve test coverage without changing production behavior unless a bug is clearly exposed.Responsibilities:- Identify critical paths.- Add focused unit tests.- Add fixture-based tests where needed.- Add regression tests for bugs.- Avoid brittle tests.- Avoid real network, real secrets, or production data.Rules:- Do not rewrite production code unless necessary to make it testable.- Prefer small tests with clear assertions.- Use temporary directories and synthetic fixtures.- Keep tests deterministic.Before finishing:- Run the relevant test command.- Summarize added coverage.- Explain any failing tests.
security-agent.md
---name: security-agentdescription: Reviews secrets, data exposure, authentication, authorization, logging, and privacy risks.---You are the Security Agent.Review for:- Hardcoded secrets- Unsafe logging- Sensitive data exposure- Weak file permissions- Unsafe shell commands- Missing input validation- Insecure defaults- Risky dependency usage- Authentication or authorization gapsDo not make cosmetic comments.Prioritize concrete, exploitable, or compliance-relevant risks.Output:1. Critical risks2. High risks3. Medium/low risks4. Suggested remediations5. Tests or hooks to prevent recurrence

3. Project-specific agents for your Match Guard repo
For your current repo, keep these under:
.cursor/agents/project/
Recommended project agents:
schema-agent.mdruntime-agent.mdstorage-agent.mdreconciliation-agent.mdvendor-adapter-agent.mdscheduler-agent.mdmigration-agent.mdhipaa-agent.md
Example: reconciliation-agent.md
---name: reconciliation-agentdescription: Implements and reviews Match Guard vendor-neutral reconciliation logic, idempotency, coverage checks, and changelog behavior.---You are the Match Guard Reconciliation Agent.Primary responsibilities:- Implement vendor-neutral reconciliation.- Preserve idempotency.- Enforce the change-detection truth table.- Maintain facility-level partitioning.- Ensure coverage equation checks pass.- Write changelog entries through the approved storage API.- Add tests for ADD, UPDATE, STATUS_CHANGE, MISSING_IN_CURRENT_EXPORT, REAPPEARED, EXCLUDED_PRE_OPA, and VALIDATION_EXCEPTION.Allowed areas:- scripts/orchestrator/reconciliation.py- scripts/orchestrator/schemas.py when needed for reconciliation types- tests/test_reconciliation_*.py- tests/fixtures/Do not:- Modify Verity browser automation.- Modify scheduler behavior.- Modify migration code.- Log PHI.- Change legacy CSV shape unless explicitly requested.Before finishing:- Run reconciliation tests.- Summarize changed files.- Explain any failures.
Example: hipaa-agent.md
---name: hipaa-agentdescription: Reviews Match Guard changes for PHI handling, logging safety, secrets, retention, auditability, and operational controls.---You are the Match Guard HIPAA Safety Agent.Review code and docs for:- No PHI in logs.- No raw portal exports committed.- No screenshots in production paths.- No credentials in YAML.- Runtime data stored only in approved ignored paths.- SQLCipher or approved dev fallback behavior.- Run manifests and changelogs preserve auditability.- Cleanup and retention behavior is documented.- Tests use synthetic data only.You are not legal counsel.Provide engineering risk review and concrete remediation steps.Output:1. PHI/logging risks2. Secrets/config risks3. Storage/retention risks4. Auditability gaps5. Required fixes

4. Universal rules vs project rules
Your .cursor/rules/ should also have a split in spirit, even if they live in one folder.
Universal rules
Use in every repo:
010-code-quality.mdc020-security-and-secrets.mdc040-testing-standards.mdc050-agent-workflow.mdc060-git-workflow.mdc
Example 050-agent-workflow.mdc:
---description: Standard agent workflow for this repositoryalwaysApply: true---# Agent Workflow- Use planning before multi-file edits.- Keep one agent session focused on one task.- Prefer small diffs.- Do not refactor unrelated code.- Preserve public behavior unless explicitly asked.- Add or update tests with behavior changes.- Run the narrowest relevant validation command first.- Summarize changed files and test results before finishing.- When context becomes noisy, create or update a plan file and start a fresh chat.
Example 040-testing-standards.mdc:
---description: Testing standardsalwaysApply: true---# Testing Standards- Add tests for new behavior.- Prefer deterministic unit tests.- Avoid real network calls in tests.- Avoid production data in tests.- Use fixtures for external inputs.- Test failure paths, not only happy paths.- Keep tests readable and focused.
Project-specific rules
Use only in Match Guard:
000-repo-overview.mdc030-match-guard-architecture.mdc035-hipaa-phi-controls.mdc045-vendor-adapter-contract.mdc
Example 030-match-guard-architecture.mdc:
---description: Match Guard architecture boundariesalwaysApply: true---# Match Guard Architecture Boundaries- The orchestrator is vendor-neutral.- Vendor-specific behavior belongs under `scripts/vendors/`.- Runtime files belong under `runtime/`.- Per-client ledgers belong under `ledger/<client_slug>/`.- Config files belong under `config/clients/` and `config/vendors/`.- Do not rewrite legacy Verity browser automation unless explicitly asked.- Preserve backward-compatible Verity CSV exports.- Use Pydantic schemas for config and canonical records.- Use synthetic fixtures in tests.

5. Hooks directory pattern
Cursor has official hooks docs, and the general idea is to use hooks for automated enforcement around agent actions rather than repeating instructions in every prompt. 
Even before wiring every hook into Cursor, keep your hook scripts in a predictable place:
.cursor/hooks/  pre-agent.sh  post-edit.sh  pre-commit-check.sh  block-risky-commands.sh
Example pre-commit-check.sh:
#!/usr/bin/env bashset -euo pipefailecho "Running repo quality gate..."if command -v ruff >/dev/null 2>&1; then  ruff check .fiif command -v mypy >/dev/null 2>&1; then  mypy scripts || truefiif command -v pytest >/dev/null 2>&1; then  pytestfiif command -v detect-secrets >/dev/null 2>&1; then  detect-secrets scanfi
Example block-risky-commands.sh:
#!/usr/bin/env bashset -euo pipefailCOMMAND="${1:-}"BLOCKED_PATTERNS=(  "rm -rf /"  "rm -rf ledger"  "rm -rf runtime"  "git push --force"  "git reset --hard"  "chmod -R 777")for pattern in "${BLOCKED_PATTERNS[@]}"; do  if [[ "$COMMAND" == *"$pattern"* ]]; then    echo "Blocked risky command: $pattern"    exit 1  fidone
For Match Guard, add PHI-focused scripts later:
.cursor/hooks/check-no-phi-fixtures.sh.cursor/hooks/check-no-db-commit.sh.cursor/hooks/check-no-env-commit.sh

6. Plans directory convention
Use plans as durable context so agents do not need one giant chat.
.cursor/plans/  README.md  active/    phase1a-schemas.md    phase1b-runtime.md  completed/    phase0-foundation.md  archived/
Plan template:
# Plan: <name>## Goal## ScopeAllowed files:- Do not edit:- ## Current observations## Implementation steps## Tests to add/update## Validation commands```bashruff check .mypy scriptspytest
Risks
Rollback notes
Suggested commit message
This is the most important consistency mechanism. When a chat gets stale, save the state to a plan and start fresh.---# 7. Prompts directoryThis is optional but powerful.```text id="7hf5x4".cursor/prompts/  phase-plan.md  implementation.md  review.md  test.md  security-review.md
Example implementation.md:
You are the Implementation Agent.Implement only this plan:@.cursor/plans/active/<PLAN_FILE>.mdRules:- Stay inside the allowed files.- Do not refactor unrelated code.- Add or update tests.- Run the validation commands.- Summarize changed files and test results.
This lets you reuse the same high-quality prompt over and over.

8. How to replicate this across repos
Create a separate template repo or local folder:
cursor-repo-template/  .cursor/    rules/    agents/      universal/    hooks/    prompts/    checklists/    templates/  scripts/    init-cursor-repo.sh
Then copy it into a new repo:
cp -R cursor-repo-template/.cursor /path/to/new-repo/.cursor
Or use a small init script:
#!/usr/bin/env bashset -euo pipefailTARGET="${1:-.}"mkdir -p "$TARGET/.cursor"/{rules,plans/{active,completed,archived},agents/{universal,project},hooks,prompts,checklists,templates}touch "$TARGET/.cursor/README.md"touch "$TARGET/.cursor/plans/README.md"echo "Cursor repo scaffold created at $TARGET/.cursor"
For each new repo, customize only these first:
.cursor/rules/000-repo-overview.mdc.cursor/rules/030-architecture-boundaries.mdc.cursor/agents/project/domain-agent.md.cursor/plans/active/phase0-foundation.md
Everything else can stay universal.

9. Naming convention I recommend
Use this everywhere:
Rules:  000-099 = repo identity and universal standards  100-199 = architecture and domain rules  200-299 = framework/language rules  300-399 = testing and validation  400-499 = deployment/ops/securityAgents:  universal/<role>.md  project/<domain-role>.mdPlans:  active/phase<number>-<slug>.md  completed/phase<number>-<slug>.md  archived/<date>-<slug>.md
Example:
.cursor/rules/  000-repo-overview.mdc  010-code-quality.mdc  020-security-and-secrets.mdc  030-architecture-boundaries.mdc  040-testing-standards.mdc  050-agent-workflow.mdc  060-git-workflow.mdc  110-domain-model.mdc  120-data-pipeline-boundaries.mdc

10. What should be global vs committed to repo?
Use global agents/rules for your personal working style.
Use repo committed agents/rules for anything another contributor should inherit.
Global:  personal review style  preferred explanation format  general Python preferences  personal debugging workflowRepo:  architecture boundaries  test commands  security rules  PHI rules  domain terminology  file layout  deployment assumptions
Subagents can exist as project-scoped .cursor/agents/ files or global ~/.cursor/agents/ files according to current Cursor guidance. 
My recommendation: keep universal agents committed inside each repo at first. Once they stabilize across 3–5 repos, promote them to your global Cursor setup.

11. Best default setup for every new repo
Start every repo with this minimum:
.cursor/  rules/    000-repo-overview.mdc    010-code-quality.mdc    020-security-and-secrets.mdc    040-testing-standards.mdc    050-agent-workflow.mdc  agents/    universal/      architect.md      implementation-agent.md      reviewer-agent.md      test-agent.md      security-agent.md    project/      domain-agent.md  plans/    active/    completed/    archived/  hooks/    pre-commit-check.sh  prompts/    phase-plan.md    implementation.md    review.md
Then for Match Guard specifically, add:
.cursor/agents/project/  schema-agent.md  runtime-agent.md  storage-agent.md  reconciliation-agent.md  vendor-adapter-agent.md  scheduler-agent.md  migration-agent.md  hipaa-agent.md.cursor/rules/  030-match-guard-architecture.mdc  035-hipaa-phi-controls.mdc  045-vendor-adapter-contract.mdc

12. The operating principle
Use this as your repeatable system:
Rules = persistent constraints.Agents = reusable roles.Plans = durable task memory.Hooks = automated enforcement.Prompts = repeatable workflows.Checklists = review gates.
For your workflow, the highest-value setup is:
Universal agents:  architect  implementation  reviewer  test  securityProject agents:  domain-specific buildersRules:  universal coding standards  repo-specific architectureHooks:  quality gates and safety blocksPlans:  one task or phase per file

