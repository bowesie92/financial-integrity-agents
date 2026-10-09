-- Phase 5 (D32): one row per finding per channel once it has been delivered, so a re-run never sends twice.
-- Additive: no existing table changes. Undo with: drop table fia.finding_deliveries;
-- The fia_notifier login must exist before this file runs (scripts/setup_notifier_role.py creates it first).
create table if not exists fia.finding_deliveries (
  finding_id   uuid not null references fia.findings (finding_id),
  channel      text not null check (channel in ('discord', 'email')),
  delivered_at timestamptz not null default now(),
  primary key (finding_id, channel)
);
comment on table fia.finding_deliveries is 'Written by the n8n delivery workflow. A row means that finding was sent to that channel.';

revoke all on fia.finding_deliveries from public;
grant usage on schema fia to fia_notifier;
grant select on fia.findings to fia_notifier;
grant select, insert on fia.finding_deliveries to fia_notifier;
