# Database permission check

Run 2026-10-10 01:53 UTC as database role `fia_agent`, the role both agents use.
Every attempt ran in a transaction that was rolled back. Destructive attempts also used `where false`.
This is a software control test: it shows the database enforces the limits, with no model involved.

| Attempt | Expected | Result | Database message | Matches |
| --- | --- | --- | --- | --- |
| Read invoices (should work) | accepted | accepted | statement was accepted (then rolled back) | yes |
| Insert a proposed finding (should work) | accepted | accepted | statement was accepted (then rolled back) | yes |
| Insert a finding already marked 'accepted' | rejected (rule) | rejected (23514) | new row for relation "findings" violates check constraint "findings_status_check" | yes |
| Update an invoice amount | rejected (permission) | rejected (42501) | permission denied for table invoices | yes |
| Delete an invoice | rejected (permission) | rejected (42501) | permission denied for table invoices | yes |
| Update a payment | rejected (permission) | rejected (42501) | permission denied for table payments | yes |
| Delete a payment | rejected (permission) | rejected (42501) | permission denied for table payments | yes |
| Change a vendor's active flag | rejected (permission) | rejected (42501) | permission denied for table vendors | yes |
| Update a journal entry | rejected (permission) | rejected (42501) | permission denied for table journal_entries | yes |
| Edit one of its own findings | rejected (permission) | rejected (42501) | permission denied for table findings | yes |
| Delete one of its own findings | rejected (permission) | rejected (42501) | permission denied for table findings | yes |
| Read the answer key | rejected (permission) | rejected (42501) | permission denied for schema fia_gt | yes |
| Write to the answer key | rejected (permission) | rejected (42501) | permission denied for schema fia_gt | yes |
| Read the human review decisions | rejected (permission) | rejected (42501) | permission denied for table finding_reviews | yes |
| Create a table | rejected (permission) | rejected (42501) | permission denied for schema fia | yes |

15 of 15 attempts behaved as expected.
