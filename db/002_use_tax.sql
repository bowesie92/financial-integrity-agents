-- Phase 3 (D24): tax charged on each invoice. total_amt already includes tax_amt.
-- Additive and nullable. Undo with: alter table fia.invoices drop column tax_amt;
alter table fia.invoices add column if not exists tax_amt numeric(14,2) check (tax_amt >= 0);
comment on column fia.invoices.tax_amt is 'Sales tax included in total_amt, as charged by the vendor.';
