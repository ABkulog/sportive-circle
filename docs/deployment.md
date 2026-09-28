# Putting Sportive Circle online

A checklist for launching to UW students. It takes about an hour the first time.

## 1. Before you launch

- [ ] Tests pass: `.venv/bin/python -m pytest -q` (GitHub Actions also runs them on every push).
- [ ] Pick a name and domain (optional). A free host address like `sportive-circle.onrender.com` works too.
- [ ] Set up an email provider (see step 2). Without one, nobody can sign up, because codes can't be sent.
- [ ] Have a friend (or a UW law clinic or ASUW office) read the [Privacy](../sportive/templates/pages/privacy.html)
      and [Terms](../sportive/templates/pages/terms.html) pages.
- [ ] Decide who the admins are (your UW email, maybe a co-founder's).
- [ ] Don't use UW logos (the "W" or the Husky dog marks). Purple, gold and place names are fine.

## 2. Email (Brevo, free)

1. Make a separate email just for the app (e.g. a new Gmail), so your UW and personal inboxes stay separate.
   Then sign up at [brevo.com](https://www.brevo.com) (free plan: 300 emails a day).
2. **Senders, domains & dedicated IPs → Senders → Add a sender**: use the email you want codes to come from,
   and confirm it from your inbox.
3. **SMTP & API → SMTP**: note the **SMTP server** (`smtp-relay.brevo.com`), **login**, and create an
   **SMTP key** (that's the password).

## 3. Put it online (Render, one Blueprint)

The repository has a [`render.yaml`](../render.yaml) Blueprint that sets up everything: the website, a disk for
the database, a random secret key, and the reminder job that runs every 10 minutes.

1. Sign up at [render.com](https://render.com) with **GitHub**, and add a payment method (the disk needs a
   paid plan: about $7/month for the website plus about $1/month for the reminder job).
2. **New → Blueprint →** pick `sportive-circle` → Render reads `render.yaml`.
3. It asks for the email settings from step 2:

   | Setting | Value |
   |---|---|
   | `MAIL_SERVER` | `smtp-relay.brevo.com` |
   | `MAIL_USERNAME` | your Brevo SMTP login |
   | `MAIL_PASSWORD` | your Brevo SMTP key |
   | `MAIL_FROM` | `Sportive Circle <the sender email you confirmed>` |
   | `CONTACT_EMAIL` | the app's own email (shown on Privacy and Terms), not a personal or UW one |

4. **Apply**. The first build takes a few minutes. Your site is at `https://sportive-circle.onrender.com`
   (or the name Render shows).
5. Open it, sign up with your UW email (`ADMIN_EMAILS` in `render.yaml` makes that account an admin), and
   check the code email arrives (look in Junk too).

Every push to `main` on GitHub redeploys automatically. The database stays on the disk.

## 4. Reminders

Already done by the Blueprint: the `sportive-circle-reminders` cron job calls the site every 10 minutes
(`POST /tasks/send-reminders` with a secret token) and it emails everyone whose game starts within the hour.

## 5. Backups

The whole app is one file: `sportive_circle.db` on the disk. Render snapshots paid disks every day
automatically (Dashboard → your service → Disks). For an extra copy, from the service's **Shell** tab:

```bash
sqlite3 /data/sportive_circle.db ".backup '/data/backups/sportive-$(date +%F).db'"
```

Keep a few days of copies, and copy them somewhere off the server now and then.

## 6. After launch

- Check **Reports** and **Club requests** (the shield and flag icons) every day or two.
- To approve a club: open its HuskyLink or UW Recreation page, check it's active this quarter and the
  applicant is an officer, then tap Approve.
- Run `flask --app wsgi sport-stats` after a few weeks to see if player caps need changing
  (`sportive/constants.py`).
- Watch your host's logs for errors (emails that fail are logged, not shown to users).

## Running it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py      # optional demo data
.venv/bin/python main.py      # http://localhost:5050
```
