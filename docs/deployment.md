# Putting Sportive Circle online

A checklist for launching to UW students. It takes about an hour the first time.

## 1. Before you launch

- [ ] Tests pass: `.venv/bin/python -m pytest -q` (GitHub Actions also runs them on every push).
- [ ] Pick a name and domain (optional). A free host address like `sportive-circle.onrender.com` works too.
- [ ] Set up an email provider (see step 3). Without one, nobody can sign up, because codes can't be sent.
- [ ] Have a friend (or a UW law clinic or ASUW office) read the [Privacy](../sportive/templates/pages/privacy.html)
      and [Terms](../sportive/templates/pages/terms.html) pages.
- [ ] Decide who the admins are (your UW email, maybe a co-founder's).
- [ ] Don't use UW logos (the "W" or the Husky dog marks). Purple, gold and place names are fine.

## 2. Host the app (example: Render)

Any host that runs Python works (Render, Railway, Fly.io, a UW-provided server...). On Render:

1. Push the code to GitHub.
2. Render → **New → Web Service** → pick the repository.
3. **Build command:** `pip install -r requirements.txt`
4. **Start command:** `gunicorn wsgi:app --workers 2 --bind 0.0.0.0:$PORT`
5. **Disk:** add a persistent disk mounted at `/data` (the database lives there; without a disk it's
   erased on every deploy).
6. **Environment variables** (copy from [`.env.example`](../.env.example)):

   | Variable | Value |
   |---|---|
   | `SECRET_KEY` | run `python3 -c "import secrets; print(secrets.token_hex(32))"` |
   | `PUBLIC_URL` | `https://your-app.onrender.com` (your real address, with https) |
   | `BEHIND_PROXY` | `1` |
   | `DATABASE` | `/data/sportive_circle.db` |
   | `ADMIN_EMAILS` | `you@uw.edu` |
   | `MAIL_SERVER`, `MAIL_PORT`, `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_FROM` | from your email provider |

7. Deploy, then open the site and sign up with your own UW email.

## 3. Email

Pick any SMTP provider. Good free or cheap options: **Brevo**, **SendGrid**, **Mailgun**, **Amazon SES**.

- Verify a sender address or domain with the provider, so emails don't land in spam.
- UW email filters are strict: send a test code to your `@uw.edu` address and check Junk.

## 4. Reminders (every 10 minutes)

Add a scheduled job (Render → **New → Cron Job**, same repository and environment variables):

- **Schedule:** `*/10 * * * *`
- **Command:** `flask --app wsgi send-reminders`

It emails everyone going to a game that starts within the next hour.

## 5. Backups

The whole app is one file: `sportive_circle.db`. Back it up daily, for example with a cron job:

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
