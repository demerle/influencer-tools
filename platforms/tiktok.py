"""Post a video to TikTok with the Content Posting API ("Direct Post")."""

import os
import secrets
import time
from urllib.parse import urlencode

import requests

from common import ask_for_code_from_redirect, build_caption, check_response, load_config, load_tokens, save_tokens

TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
POST_START_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
POST_STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"

# TikTok takes files up to 64 MB in one piece. Bigger files go in 10 MB pieces.
MEGABYTE = 1024 * 1024
BIGGEST_SINGLE_PIECE = 64 * MEGABYTE
PIECE_SIZE = 10 * MEGABYTE

# How long to wait for TikTok to finish processing the video.
SECONDS_BETWEEN_STATUS_CHECKS = 15
MAX_STATUS_CHECKS = 40  # 40 checks x 15 seconds = 10 minutes


# ---------- Connecting your account (one time) ----------

def connect():
    config = load_config()

    login_page_options = {
        "client_key": config["tiktok_client_key"],
        "scope": "user.info.basic,video.publish",
        "response_type": "code",
        "redirect_uri": config["redirect_uri"],
        "state": secrets.token_hex(8),
    }
    login_page = "https://www.tiktok.com/v2/auth/authorize/?" + urlencode(login_page_options)

    print("Open this link, log in to TikTok, and approve the app:")
    print(login_page)
    code = ask_for_code_from_redirect()

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": config["tiktok_client_key"],
            "client_secret": config["tiktok_client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": config["redirect_uri"],
        },
    )
    login = read_login_response(response)

    save_tokens("tiktok", login)
    print("TikTok is connected.")


def get_fresh_access_token():
    """TikTok logins only last 24 hours, so get a new one every time we post.

    The renewal key (refresh_token) lasts a year, and each renewal gives a new one.
    """
    config = load_config()
    old_login = load_tokens("tiktok")
    if old_login is None:
        raise RuntimeError("TikTok is not connected yet. Run: uv run connect.py tiktok")

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": config["tiktok_client_key"],
            "client_secret": config["tiktok_client_secret"],
            "grant_type": "refresh_token",
            "refresh_token": old_login["refresh_token"],
        },
    )
    new_login = read_login_response(response)

    save_tokens("tiktok", new_login)
    return new_login["access_token"]


def read_login_response(response):
    check_response(response, "Getting a TikTok login")
    login = response.json()

    # TikTok sometimes answers "200 OK" but puts an error inside.
    if "access_token" not in login:
        raise RuntimeError(f"TikTok login failed (if it keeps failing, run: uv run connect.py tiktok): {login}")

    return login


# ---------- Posting ----------

def post(video_path, description, hashtags, is_private):
    access_token = get_fresh_access_token()

    if is_private:
        privacy = "SELF_ONLY"
    else:
        privacy = "PUBLIC_TO_EVERYONE"

    video_size = os.path.getsize(video_path)
    piece_size, number_of_pieces = plan_pieces(video_size)

    # Step 1: tell TikTok a video is coming. It gives back an upload address.
    response = requests.post(
        POST_START_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        },
        json={
            "post_info": {
                "title": build_caption(description, hashtags),
                "privacy_level": privacy,
            },
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": video_size,
                "chunk_size": piece_size,
                "total_chunk_count": number_of_pieces,
            },
        },
    )
    answer = read_api_response(response, "Starting the TikTok post")
    publish_id = answer["data"]["publish_id"]
    upload_url = answer["data"]["upload_url"]

    # Step 2: send the video.
    upload_video_in_pieces(video_path, upload_url, video_size, piece_size, number_of_pieces)

    # Step 3: wait for TikTok to finish.
    wait_until_posted(publish_id, access_token)

    if is_private:
        return "Posted to TikTok as private (only you can see it)."
    return "Posted to TikTok."


def plan_pieces(video_size):
    """Returns (piece_size, number_of_pieces). The last piece also carries any leftover bytes."""
    if video_size <= BIGGEST_SINGLE_PIECE:
        return video_size, 1

    number_of_pieces = video_size // PIECE_SIZE
    return PIECE_SIZE, number_of_pieces


def upload_video_in_pieces(video_path, upload_url, video_size, piece_size, number_of_pieces):
    with open(video_path, "rb") as video_file:
        for piece_number in range(number_of_pieces):
            first_byte = piece_number * piece_size

            is_last_piece = piece_number == number_of_pieces - 1
            if is_last_piece:
                last_byte = video_size - 1
            else:
                last_byte = first_byte + piece_size - 1

            video_file.seek(first_byte)
            piece_data = video_file.read(last_byte - first_byte + 1)

            response = requests.put(
                upload_url,
                headers={
                    "Content-Type": "video/mp4",
                    "Content-Length": str(len(piece_data)),
                    "Content-Range": f"bytes {first_byte}-{last_byte}/{video_size}",
                },
                data=piece_data,
            )
            check_response(response, f"Uploading piece {piece_number + 1} of {number_of_pieces} to TikTok")


def wait_until_posted(publish_id, access_token):
    for check_number in range(MAX_STATUS_CHECKS):
        response = requests.post(
            POST_STATUS_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={"publish_id": publish_id},
        )
        answer = read_api_response(response, "Checking the TikTok post")
        status = answer["data"]["status"]

        if status == "PUBLISH_COMPLETE":
            return

        if status == "FAILED":
            raise RuntimeError(f"TikTok could not post the video: {answer['data']}")

        time.sleep(SECONDS_BETWEEN_STATUS_CHECKS)

    raise RuntimeError("TikTok took more than 10 minutes. Check the TikTok app, it may still show up.")


def read_api_response(response, action_description):
    """TikTok answers every request with an "error" section. Its code is "ok" when all went well."""
    check_response(response, action_description)
    answer = response.json()

    if answer["error"]["code"] != "ok":
        raise RuntimeError(f"{action_description} failed: {answer['error']}")

    return answer
