# Deployment: scheduling and delivery

Two small pieces run the agents without anyone at the keyboard. Neither contains any secret.

```
systemd timer  ->  scripts/run_review.py  ->  findings table  ->  n8n workflow  ->  Discord and email
(host)             (Python agent loop)        (Supabase)          (polls, formats)    (human reviewer)
```

| Folder | What it holds |
| --- | --- |
| `systemd/` | One service and one timer per agent (`fia-ap`, `fia-gl`). The timers fire weekly. |
| `n8n/` | The delivery workflow as importable JSON, with placeholders instead of real addresses. |
| `secrets.env.example` | The names of the secret variables the code expects, with no values. |

## systemd (host side)

The unit files use the author's paths (`/home/cass/repos/financial-integrity-agents`). Change `WorkingDirectory` and `ExecStart` to yours first.

```
mkdir -p ~/.config/systemd/user
cp deploy/systemd/fia-*.service deploy/systemd/fia-*.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user start fia-gl.service
```

The last line runs one real review now and takes about four minutes. Check it with `journalctl --user -u fia-gl.service -n 25 --no-pager`. To run unattended after logout, `loginctl enable-linger $USER` must report `Linger=yes`.

The timers are installed and tested but **not enabled by default**. Turn them on with `systemctl --user enable --now fia-ap.timer fia-gl.timer`. Two things to know before you do:

- Each review is a paid run, about $0.40 to $1.00 on Sonnet 5.5, capped at $1.50 by the loop.
- On static data every weekly run proposes the same issues again under a new run id, so the delivery channels would repeat them. With a live ledger that is the right behavior. With the synthetic data it is noise.

To test a timer without waiting for Sunday, add a drop-in that moves it a few minutes ahead (`systemctl --user edit fia-ap.timer`, set `OnCalendar=` to empty and then to a time three minutes from now), start the timer, and remove the drop-in afterwards. This is how the scheduled path was tested.

## n8n (delivery side)

The workflow polls the findings table every two hours. Every unsent finding is posted to a Discord channel, one email digest sorted by risk is sent, and each delivery is recorded in `fia.finding_deliveries` so a re-run never sends the same finding twice.

1. In n8n, create an empty workflow, click the canvas and paste the contents of `n8n/fia_findings_delivery.json`.
2. Create three credentials and attach them to the nodes that need them:
   - **Postgres**, connecting as the read-mostly `fia_notifier` role through the Supabase session pooler. The user is the role name, a dot and your project ref.
   - **Discord webhook** for the channel that should receive findings.
   - **SMTP** for the email node. Replace the placeholder sender and recipient in the "Send digest email" node.
3. Set an error workflow of your own, so a failed run posts an alert. The Error Trigger only fires on published, scheduled runs, not on manual test runs.
4. Publish the workflow.

Honest notes:

- The Postgres credential was set to **Ignore SSL Issues**, because n8n rejected Supabase's certificate chain as self-signed. Traffic is still encrypted, but the server's identity is not verified. A stricter setup would install Supabase's CA certificate.
- The email path was tested with a **Mailgun sandbox domain**, which only delivers to authorized recipients and tends to land in spam. A real deployment would use a verified domain.
- On the Supabase Free plan the poll doubles as the keep-alive that stops the project from pausing after about a week of low activity. If n8n is off and the project pauses, it needs a manual Resume in the Supabase dashboard.
