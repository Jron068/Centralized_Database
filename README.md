# Centralized Database Resort

## Folder layout

- `API/` contains external services, including SMS.
- `models/` contains shared helpers and model files.
- `scripts/` contains database/upload migration tools and the Gmail OAuth setup utility.
- `routes/auth/` contains login, registration, and OTP routes.
- `routes/customer/` contains customer pages and reservations.
- `routes/admin/` contains owner and admin pages.
- `routes/caretaker/` contains caretaker pages.
- `routes/public/` contains public pages and resort listings.
- `templates/` contains the pages for those route groups.
- `static/` contains CSS, images, and uploads.
- `archive/` keeps an unfinished booking prototype that the app does not load.

## Run locally

1. Install packages with `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and set your database and SMS settings.
   To create Gmail API credentials, save your OAuth client JSON as the ignored `credentials.json` file in the project root and run `python scripts/generate_gmail_token.py`; copy the printed values into `.env`.
3. For Supabase PostgreSQL, run `schema/supabase.sql` in the Supabase SQL Editor and set `DATABASE_URL`. For local MySQL, leave `DATABASE_URL` blank and configure the `DB_*` settings.
4. Start the site with `python app.py`. When `FLASK_DEBUG=1`, uploads are saved locally for development; production deployments require the Supabase Storage settings below.

## Free deployment with Render and Supabase

1. In Supabase Storage, create a **public** bucket named `resort-media` and a **private** bucket named `payment-proofs`. Public resort galleries, profile pictures, resort logos, and update images use the public bucket. Customer payment screenshots and caretaker walk-in proofs use the private bucket and are served with short-lived signed links.
2. Before deploying, migrate existing upload files while the local `static/uploads` files are available. Set `SUPABASE_URL` and `SUPABASE_STORAGE_SERVICE_ROLE_KEY` in your ignored local `.env`, then run `python scripts/migrate_uploads_to_supabase.py`. The script updates existing Supabase database references in one transaction and refuses to proceed if a referenced local file is missing. It leaves the local files unchanged.
3. In Render, create a Blueprint from this repository and deploy `main`. The Blueprint selects Render's Free web-service plan and does not create a paid persistent disk. Free services may spin down while idle, and local service files are temporary; all new uploads are stored in Supabase Storage.
4. Set the requested secrets in Render's environment settings:
   - `DATABASE_URL`: Supabase PostgreSQL Session pooler connection string.
   - `SUPABASE_URL`: Supabase project URL root, for example `https://<project-ref>.supabase.co` (do not append `/rest/v1/`).
   - `SUPABASE_STORAGE_SERVICE_ROLE_KEY`: Supabase service-role secret key. This key stays server-side; never put it in browser code, `static/`, or Git.
   - `FLASK_SECRET_KEY`, `OPENAI_API_KEY`, and `MAIL_DEFAULT_SENDER` as required by the app.
   - `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, and `GOOGLE_OAUTH_REFRESH_TOKEN` for Gmail API delivery. Grant the OAuth token the `https://www.googleapis.com/auth/gmail.send` scope. Render production sends through Gmail HTTPS API rather than SMTP.
5. Optional bucket overrides are `SUPABASE_PUBLIC_STORAGE_BUCKET` (default `resort-media`) and `SUPABASE_PRIVATE_STORAGE_BUCKET` (default `payment-proofs`). The service-role key must never be exposed to clients.

New image uploads continue to be checked by OpenAI moderation; configure `OPENAI_API_KEY` in Render to enable them.

Customer e-wallet QR images are served from `static/images/payments/gcash-qr.png` and `static/images/payments/maya-qr.png`. Add the genuine account QR images there before accepting payments; the booking form disables proof submission for a wallet whose QR image is missing. Both options display the configured recipient label, which customers should verify before sending money.

To migrate all rows from the configured local MySQL database, set `DATABASE_URL` in your ignored local `.env` to the Supabase Session pooler URL, run `python scripts/migrate_mysql_to_supabase.py`, and keep the MySQL server available during the transfer. The script checks the expected tables and columns, refuses to copy into non-empty target tables, copies in batches inside one transaction, and leaves MySQL unchanged. It reports row counts only. The current MySQL data contains caretaker and reservation rows referencing resort IDs that no longer exist, so the Supabase schema intentionally omits those two resort foreign-key constraints to preserve the source rows. Repair the orphaned references before adding those constraints if you want strict enforcement. Do not commit database dumps, connection strings, service-role keys, or uploaded proofs to GitHub.

## Resort photo moderation

Resort gallery uploads are sent to OpenAI's moderation endpoint and checked with `omni-moderation-latest` before being written to Supabase Storage or added to the customer gallery. Set `OPENAI_API_KEY` in `.env` or Render to enable uploads. If the key is missing, the moderation service is unavailable, or an image is flagged, the upload is rejected. JPG, PNG, and WEBP images up to 8 MB each are supported; GIF uploads are not accepted.
