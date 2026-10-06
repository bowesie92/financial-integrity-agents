# Decisions

Architecture decisions for Financial Integrity Agents. Each has a reason and the condition that would reopen it.

### D1. Build on the Anthropic API first; verify Bedrock later by switching a config value
- Why: Claude on Bedrock needs a one-way paid-plan upgrade, and build cost is about the same on either provider.
- Revisit if: the Bedrock gate passes early.

### D2. Do not upgrade the AWS plan yet; decide at Gate B0, after Phase 4
- Why: the upgrade cannot be undone, and credits carry over, so waiting costs nothing.
- Revisit if: Bedrock evidence is wanted in the README (decide by Oct 15).

### D3. Hand-built Python loop on the Messages API, no agent framework
- Why: it is the project's differentiator, and the Messages request shape is the same on both providers.
- Revisit if: never.

### D4. One LLMClient interface with a capability profile per model
- Why: Sonnet 5.x rejects settings Haiku 4.5 accepts, and Bedrock lacks some features.
- Revisit if: never.

### D5. Develop on Haiku 4.5; demo on a Sonnet that is open on both providers
- Why: Sonnet 5 is open on Bedrock but in-Region only in us-east-1, so Bedrock verification runs on Haiku 4.5 in Ohio. Sonnet 5.5 is listed "See Access".
- Revisit if: Bedrock access to Sonnet 5.5 is confirmed.

### D6. Python tools compute every number; the model never does arithmetic
- Why: audit credibility and reproducibility, since Sonnet 5.x gives no sampling control.
- Revisit if: never.

### D7. Propose, never act, enforced by a database role
- Decision: the agent role can select on data and insert only on findings.
- Why: a prompt instruction is not a control. Privilege checks prove it (scripts/apply_schema.py).
- Revisit if: never.

### D8. Secrets live in per-project folders on the Beelink
- Decision: Anthropic and Supabase credentials in /etc/financial-integrity-agents-secrets/ (mode 700 folder, mode 600 files); Bedrock in /etc/bedrock-secrets/bedrock.env.
- Why: follows the per-project convention in the infrastructure document.
- Revisit if: secrets move to a vault.

### D9. n8n only schedules and delivers, plus a daily Supabase keep-alive while on Free; the agent runs on the host
- Why: matches the plan, avoids container execution limits, and Free projects pause after low activity over 7 days.
- Revisit if: the bridge proves simpler, or Supabase moves to Pro.

### D10. The author writes or line-by-line reviews the core loop; Claude Code scaffolds around it
- Why: the project's claim is that the reasoning loop is the author's own work.
- Revisit if: never.

### D11. The Master Plan doc is the source of truth
- Decision (updated 2026-10-05): Claude tells the author what to update after each step and syncs the doc only when asked.
- Why: a doc cannot be added to a Project, stored memory is sparse, any new chat must start cold from it, and per-step edits use too much of the session.
- Revisit if: never.

### D12. Supabase stays on the Free plan for now, with a Pro upgrade possible later
- Why: stated by the author on 2026-10-04. Free means pausing after low activity over 7 days, no downloadable backups, 500 MB per project, and any upgrade applies to the whole organization.
- Revisit if: a pause hurts a scheduled run, the database nears 500 MB, or backups are wanted.

### D13. The dedicated Anthropic workspace starts with a $25 monthly spend limit
- Why: the choice was delegated on 2026-10-04. The $45.61 balance is shared with other workloads, and about 75 Haiku runs fit in $25 by estimate.
- Revisit if: measured cost per run says Phase 4 needs more.

### D14. A personal API key scoped to one workspace, with a 90-day expiration, stored only in the secrets file
- Why: Anthropic's docs prefer identity-backed keys over legacy workspace keys, a personal key suits own development, a single-workspace key can only act in the capped workspace, and the expiry matches the 90-day rotation date.
- Revisit if: the agents run unattended for long stretches (use a service account key), or federation becomes practical.

### D15. A dedicated Supabase organization and project (Free, us-west-2, Data API off), with the schema fia and two roles
- Why: its own plan, so a later Pro upgrade does not touch other workloads, and isolation from existing tables and roles. It uses the second and last free project slot.
- Revisit if: a third project is needed, or backups or no pausing are wanted.

### D16. Expand scope per the 2026-10-05 design review, with priority tiers
- Decision: frame GL Sentinel as journal entry testing mapped to AU-C 240, AS 2401, and ISA 240 risk characteristics; add post-close entries, user-account pairing, vendor bank-detail changes, a prompt-injection red-team slice, and a rules-only baseline; mirror the QuickBooks Online bill shape in the AP schema; use the criteria, condition, cause, effect, recommendation memo format.
- Why: stronger audit credibility and a more distinctive project. Must, Should, and Stretch tiers in docs/scope.md say what to cut first if time slips.
- Revisit if: the schedule slips (cut Should items first, last in, first out).

### D17. Metrics, baseline thresholds, and the held-out dataset are fixed before any agent run
- Why: no tuning to results. Seed 1 is for development, seed 2 is held out, and a freeze rule applies once the first seed-2 run starts.
- Revisit if: only through the Amendments section of docs/metrics.md, with a date and a reason.

### D18. Use grants, not row-level security, as the access control in the fia schema
- Why: the Data API is off and the schema is not exposed, so the database roles are the boundary, and eight scripted privilege checks verify it. Ground truth sits in the admin-only schema fia_gt.
- Revisit if: the Data API is enabled or the schema is exposed.
