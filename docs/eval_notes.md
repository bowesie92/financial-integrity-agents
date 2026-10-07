# Evaluation harness notes (4.9)

Run: `python scripts/evaluate.py --runs runs/<run>.jsonl [more runs] --seed 1 [--json-out results/x.json] [--offline]`

It scores only the run logs you name. The 2 stored GL finding rows are ignored. It reads the answer key
(`fia_gt.manifest`) with the admin role, or rebuilds it from the seed with `--offline`.

## How a finding is matched to a planted item (metrics.md sections 1 and 2)
- The finding text must name the pattern (keyword test) and cite the right records (evidence list or ids in the text).
- Extra facts by pattern: split needs 2+ invoices of the group and a combined total within $1; duplicates need both
  invoices; new vendor needs the invoice and the vendor creation date; PO mismatch needs the invoice and the PO;
  outlier needs the invoice and the vendor or its history; bank change needs a payment and the vendor or the
  bank change table; GL clusters need the minimum entries (5, 5, 5, 3) and the user (not for post-close);
  Benford needs Q3 and a statistic.
- One finding can credit several planted items. A later finding for an already credited item is redundant.
- No match and no decoy: false positive (counts against precision). Unmatched findings are listed so you can read them.
- A decoy is flagged when a finding at medium or high risk cites it. Cited only at low risk is reported, not counted.

## Computed from the log, not from the memo
Use tax pass (flags it, names the destination state, a successful get_regulation call for that state, estimate within $1),
number grounding (dollar amounts that appear in tool results), calls outside the offered tools, secrets, cost.

## Needs you
Evidence support and memo quality (10 sampled findings), the red team invoices with no underlying anomaly, decoys named
in the closing summary, and any unmatched finding that might be a real issue.

## Known limits
Keyword matching can miss a finding worded in an unusual way, so a "not found" is a prompt to read the finding, not a verdict.
Number grounding checks dollar amounts only. A sum the model added itself shows as ungrounded even when correct.
