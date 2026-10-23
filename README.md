# Centralized Database Resort

## Folder layout

- `API/` contains external services, including SMS.
- `models/` contains shared helpers and model files.
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
3. For Supabase PostgreSQL, run `schema/supabase.sql` in the Supabase SQL Editor and set `DATABASE_URL`. For local MySQL, leave `DATABASE_URL` blank and configure the `DB_*` settings.
4. Start the site with `python app.py`.

## Deploy to Render and Supabase

1. Create a Supabase project and run `schema/supabase.sql` in its SQL Editor. This file creates the schema only; it does not contain customer or reservation records.
2. In Supabase, copy the **Session pooler** connection string and set it as `DATABASE_URL` in Render. The app uses a persistent web process, and Supabase recommends session pooling for persistent backends on IPv4 networks.
3. Connect this GitHub repository to Render as a Blueprint. Render reads `render.yaml`; enter the prompted secrets in the Render dashboard. Use newly rotated mail and OpenAI credentials.
4. The Blueprint uses a Render Starter web service and a 1 GB persistent disk mounted at `static/uploads`, so uploaded photos and payment proofs survive deploys. Render disks are available only at their mount path and cannot be shared by multiple service instances.

To migrate all rows from the configured local MySQL database, set `DATABASE_URL` in your ignored local `.env` to the Supabase Session pooler URL, run `python scripts/migrate_mysql_to_supabase.py`, and keep the MySQL server available during the transfer. The script checks the expected tables and columns, refuses to copy into non-empty target tables, copies in batches inside one transaction, and leaves MySQL unchanged. It reports row counts only. The current MySQL data contains caretaker and reservation rows referencing resort IDs that no longer exist, so the Supabase schema intentionally omits those two resort foreign-key constraints to preserve the source rows. Repair the orphaned references before adding those constraints if you want strict enforcement. The migration does not transfer uploaded files, so copy any media you need to retain into the Render disk after deployment. Do not commit database dumps, connection strings, or uploaded proofs to GitHub.

## Resort photo moderation

Resort gallery uploads are sent to OpenAI's moderation endpoint and checked with `omni-moderation-latest` before being written to disk or added to the customer gallery. Set `OPENAI_API_KEY` in `.env` or Render to enable uploads. If the key is missing, the moderation service is unavailable, or an image is flagged, the upload is rejected. JPG, PNG, and WEBP images up to 8 MB each are supported; GIF uploads are not accepted.
