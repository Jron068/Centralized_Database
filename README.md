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
3. Import `centralize1009.sql` into MySQL if the database is not set up yet.
4. Start the site with `python app.py`.

## Resort photo moderation

Resort gallery uploads are sent to OpenAI's moderation endpoint and checked with `omni-moderation-latest` before being written to disk or added to the customer gallery. Set `OPENAI_API_KEY` in `.env` to enable uploads. If the key is missing, the moderation service is unavailable, or an image is flagged, the upload is rejected. JPG, PNG, and WEBP images up to 8 MB each are supported; GIF uploads are not accepted.
