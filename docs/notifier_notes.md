# Delivery log and the notifier login (Phase 5, D32)

Why: findings cannot be edited and nothing recorded whether one was already sent. Without a record, a second run of
the workflow, or a re-run of the agent, could post the same finding twice (task 5.4).

## What exists
- `fia.finding_deliveries (finding_id, channel, delivered_at)`, primary key (finding_id, channel). A row means that
  finding was sent to that channel ('discord' or 'email'). The key makes a second row for the same pair impossible.
- Login `fia_notifier`: reads `fia.findings`, reads and inserts `fia.finding_deliveries`. It cannot read invoices,
  journal entries, human review decisions or the answer key, and it cannot update or delete anything.
- `fia_agent` has no access to the delivery log, and the agent's tools never see it.
- `scripts/setup_notifier_role.py` creates the login and the table and checks 14 privileges. Safe to re-run.

## What n8n runs
Fetch findings not yet sent to a channel (replace the channel as needed):

    select f.finding_id, f.agent, f.risk, f.title, f.finding_condition, f.recommendation, f.run_id, f.created_at
    from fia.findings f
    where not exists (select 1 from fia.finding_deliveries d
                      where d.finding_id = f.finding_id and d.channel = 'discord')
    order by f.created_at
    limit 25;

After a successful post, record it (the key blocks a duplicate):

    insert into fia.finding_deliveries (finding_id, channel) values ($1, 'discord')
    on conflict do nothing;

If a post fails, nothing is recorded, so the next run tries again. If the insert fails after a post, the next run
posts that finding a second time; that is the one gap, and it is the safer way to fail.

## Undo
    drop table fia.finding_deliveries;
    drop owned by fia_notifier;
    drop role fia_notifier;
The "drop owned" line removes the remaining grants. Then delete the SUPABASE_FIA_NOTIFIER_PASSWORD line from the project secrets file.
