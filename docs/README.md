# Documentation index

New here? Read the first two in this order, then pick what you need.

## Start here

| Page | Read it for |
| --- | --- |
| [Case study](case_study.md) | The whole project as a story: problem, design, tests, results, limits |
| [Failure catalog](failure_catalog.md) | 20 things that went wrong in real runs, with the evidence and what I did |

## Design and decisions

| Page | Read it for |
| --- | --- |
| [Scope](scope.md) | What the agents do and, just as important, what they never do |
| [Decisions](decisions.md) | Every numbered decision, the reason, and the options I rejected |
| [Metrics](metrics.md) | How success is scored, fixed before any results were seen |
| [Phase 2 amendments](phase2_amendments.md) | Dated changes made to the plan during the baseline phase |
| [Phase 4 amendments](phase4_amendments.md) | Dated changes made to the plan during the agent phase |

## How the agents work

| Page | Read it for |
| --- | --- |
| [Loop walkthrough](loop_walkthrough.md) | Step by step through one review, including the safety caps |
| [Tools](tools.md) | The read-only tools the agents call |
| [AP Guardian notes](ap_guardian_notes.md) | The accounts payable agent: patterns, prompts, behavior |
| [GL Sentinel notes](gl_sentinel_notes.md) | The general ledger agent: patterns, prompts, behavior |
| [Memo template](memo_template.md) | The audit-format layout every finding follows |
| [Notifier notes](notifier_notes.md) | How findings reach Discord and email |

## Data and measurement

| Page | Read it for |
| --- | --- |
| [Data dictionary](data_dictionary.md) | Every table and column in the synthetic company |
| [Baseline notes](baseline_notes.md) | The rules-only comparison the agents have to beat |
| [Eval notes](eval_notes.md) | How runs are scored and what the scorer cannot see |

## Examples

| File | What it is |
| --- | --- |
| [AP Guardian sample memo](sample_memos/ap_guardian_sample.md) | A real review of the synthetic books, 13 findings |
| [GL Sentinel sample memo](sample_memos/gl_sentinel_sample.md) | A real review of the synthetic ledger, 8 findings |

Scored runs and raw numbers are in [`../results/`](../results/). Deployment is in [`../deploy/`](../deploy/README.md).
