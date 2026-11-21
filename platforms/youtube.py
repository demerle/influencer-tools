"""Upload a vertical video to YouTube. YouTube makes it a Short on its own (vertical and 3 minutes or less)."""

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from common import PROJECT_FOLDER, build_caption, load_tokens, save_tokens

# Downloaded from Google Cloud Console (see README).
CLIENT_SECRET_FILE = PROJECT_FOLDER / "client_secret.json"

# Permission to upload videos and nothing else.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

MUSIC_CATEGORY_ID = "10"
MAX_TITLE_LENGTH = 100


def connect():
    """Opens your browser so you can log in to Google, then saves the login."""
    if not CLIENT_SECRET_FILE.exists():
        raise RuntimeError("client_secret.json is missing. See the YouTube steps in README.md.")

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
    credentials = flow.run_local_server(port=0)

    save_tokens("youtube", json.loads(credentials.to_json()))
    print("YouTube is connected.")


def load_credentials():
    """Load the saved Google login, renewing it first if it has expired."""
    saved_login = load_tokens("youtube")
    if saved_login is None:
        raise RuntimeError("YouTube is not connected yet. Run: uv run connect.py youtube")

    credentials = Credentials.from_authorized_user_info(saved_login, SCOPES)

    if credentials.expired:
        credentials.refresh(Request())
        save_tokens("youtube", json.loads(credentials.to_json()))

    return credentials


def make_title(description, video_path):
    """YouTube needs a title. Use the first line of the description, or the file name if there is no description."""
    lines = description.strip().splitlines()

    if len(lines) > 0:
        title = lines[0]
    else:
        title = Path(video_path).stem

    return title[:MAX_TITLE_LENGTH]


def post(video_path, description, hashtags, is_private):
    credentials = load_credentials()
    youtube = build("youtube", "v3", credentials=credentials)

    if is_private:
        privacy = "private"
    else:
        privacy = "public"

    # YouTube's tags are the hashtags without the "#".
    tags = []
    for hashtag in hashtags:
        tags.append(hashtag.removeprefix("#"))

    video_details = {
        "snippet": {
            "title": make_title(description, video_path),
            "description": build_caption(description, hashtags),
            "tags": tags,
            "categoryId": MUSIC_CATEGORY_ID,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    video_file = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    upload_request = youtube.videos().insert(part="snippet,status", body=video_details, media_body=video_file)

    # next_chunk() keeps uploading until YouTube sends back the finished video's details.
    finished_video = None
    while finished_video is None:
        upload_progress, finished_video = upload_request.next_chunk()

    video_id = finished_video["id"]
    return f"https://youtube.com/shorts/{video_id}"
