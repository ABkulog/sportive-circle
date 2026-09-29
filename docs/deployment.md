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

The repository has a [`render.yaml`](../render.yaml) Blueprint that sets up the website, a disk for the
database, and random secret keys.

1. Sign up at [render.com](https://render.com) with **GitHub**, and add a payment method (the disk needs a
   paid plan: about $7/month for the website plus about $0.25/month for the 1 GB disk).
2. **New → Blueprint →** pick `sportive-circle` → Render reads `render.yaml`.
3. It asks for the email settings from step 2:

   | Setting | Value |
   |---|---|
   | `MAIL_SERVER` | `smtp-relay.brevo.com` |
   | `MAIL_USERNAME` | your Brevo SMTP login |
   | `MAIL_PASSWORD` | your Brevo SMTP key |
   | `MAIL_FROM` | `Sportive Circle <the sender email you confirmed>` |
   | `CONTACT_EMAIL` | the app's own email (shown on Privacy and Terms), not a personal or UW one |
   | `ADMIN_EMAILS` | the admins' UW emails, separated by commas: `you@uw.edu,teammate@uw.edu` |

4. **Apply**. The first build takes a few minutes. Your site is at `https://sportive-circle.onrender.com`
   (or the name Render shows).
5. Open it, sign up with your UW email (being in `ADMIN_EMAILS` makes that account an admin), and
   check the code email arrives (look in Junk too).

Every push to `main` on GitHub redeploys automatically. The database stays on the disk.

## 4. Reminders

Nothing to do: on Render the app checks every 5 minutes by itself and emails everyone whose game starts
within the hour (each person once). To turn it off, set `REMINDER_LOOP` = `0` in Render → Environment.

(`POST /tasks/send-reminders` with the header `X-Task-Token: <TASK_TOKEN>` still works, for an outside
scheduler or a manual test.)

### Adding or removing an admin

Render → **sportive-circle** → **Environment** → edit `ADMIN_EMAILS` (comma-separated UW emails) → **Save**.
The site restarts in about a minute. Each admin signs up in the app with that exact UW email.

## 4b. Your own address (sportivecircle.com)

About $10-15 a year. The site keeps working at the onrender.com address the whole time.

1. **Buy the domain** at a registrar such as [Porkbun](https://porkbun.com) or [Namecheap](https://www.namecheap.com):
   search `sportivecircle.com`, buy it, and turn on **auto-renew** (WHOIS privacy should be free).
2. **Render → sportive-circle → Settings → Custom Domains → Add**: add `sportivecircle.com`, then
   `www.sportivecircle.com`. Render shows the DNS records to create (usually an **A** or **ALIAS** record for
   `sportivecircle.com` and a **CNAME** for `www` pointing to `sportive-circle.onrender.com`).
3. **At the registrar → DNS**: delete the default "parking" records and add exactly what Render shows.
4. Wait until Render says **Verified** (minutes to a few hours). Render adds the HTTPS certificate for free.
5. Nothing to set: on Render the app already uses `https://sportivecircle.com` (the `PUBLIC_URL` in
   `render.yaml`, and `SITE_URL` in `sportive/__init__.py`) for emails, share buttons, calendar files, club QR
   codes and search engines. To use another address, set `PUBLIC_URL` in Render → Environment.
6. Make new flyers: `.venv/bin/python tools/make_qr.py https://sportivecircle.com`.

To show up on Google: [Google Search Console](https://search.google.com/search-console) → add the domain →
verify with the TXT record it gives you (add it in the registrar's DNS) → **Sitemaps** → submit
`https://sportivecircle.com/sitemap.xml`. It can take a few days to a few weeks.

### Email from your own domain (hello@sportivecircle.com)

Codes and reminders are much less likely to land in Junk when they come from your own domain.

1. **Porkbun → sportivecircle.com → Email forwarding**: forward `hello` to your own inbox (free), so replies
   and privacy questions reach you.
2. **Brevo → Settings → Senders, domains & dedicated IPs → Domains → Add a domain** → `sportivecircle.com` →
   authenticate it yourself. Brevo shows a few DNS records (a `brevo-code` TXT, DKIM and DMARC).
3. **Porkbun → DNS**: add each one. The host is the part before `.sportivecircle.com` (empty for the domain
   itself). Keep the existing `v=spf1` TXT. If Brevo asks for SPF, edit that record to
   `v=spf1 include:_spf.porkbun.com include:spf.brevo.com ~all`, because a domain can only have one SPF record.
4. **Brevo → Authenticate** (DNS can take a few minutes). Then **Senders → Add a sender**:
   `Sportive Circle`, `hello@sportivecircle.com`.
5. **Render → Environment**: `MAIL_FROM` = `Sportive Circle <hello@sportivecircle.com>` and
   `CONTACT_EMAIL` = `hello@sportivecircle.com` → Save. Test it: sign up with a new account, or run
   `flask --app wsgi check-email you@uw.edu` in the Render Shell.

### If a secret leaks (SECRET_KEY, TASK_TOKEN)

Render → sportive-circle → **Environment** → **Edit** → give `SECRET_KEY` and `TASK_TOKEN` new random values
→ **Save, rebuild and deploy**. To make a value on a Mac:
`python3 -c "import secrets; print(secrets.token_hex(32))" | pbcopy` (copies it; paste it into Render).
A new `SECRET_KEY` logs everyone out once and turns off invite links that were already shared.

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
- Run `flask --app wsgi sport-stats` after a few weeks to see how big games really are (and adjust each sport's usual size)
  (`sportive/constants.py`).
- Watch your host's logs for errors (emails that fail are logged, not shown to users).

## Running it locally

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python seed.py      # optional demo data
.venv/bin/python main.py      # http://localhost:5050
```
