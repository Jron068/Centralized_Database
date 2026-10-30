import json
from pathlib import Path

from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
CREDENTIALS_FILE = Path(__file__).resolve().parents[1] / "credentials.json"


def main():
    load_dotenv()

    with CREDENTIALS_FILE.open("r", encoding="utf-8") as file:
        client_data = json.load(file)

    client_info = client_data.get("installed") or client_data.get("web")
    if not client_info:
        raise ValueError(
            "Invalid credentials.json: expected an 'installed' or 'web' section."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(CREDENTIALS_FILE),
        SCOPES,
    )
    credentials = flow.run_local_server(
        port=0,
        access_type="offline",
        prompt="consent",
    )

    print("\nOAuth setup completed!")
    print("GOOGLE_OAUTH_CLIENT_ID =", client_info["client_id"])
    print("GOOGLE_OAUTH_CLIENT_SECRET =", client_info["client_secret"])
    print("GOOGLE_OAUTH_REFRESH_TOKEN =", credentials.refresh_token)
    print("MAIL_DEFAULT_SENDER = the Gmail account you authorized")

    if not credentials.refresh_token:
        print("\nNo refresh token was returned. Reauthorize and check your OAuth settings.")


if __name__ == "__main__":
    main()
