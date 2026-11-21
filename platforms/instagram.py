"""Post a Reel to Instagram, using "Instagram API with Instagram Login".

Instagram can't take an upload straight from your computer. It downloads the video
from a public link instead, so PublicFileShare makes a temporary link for it.
"""

import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode

import requests

from common import ask_for_code_from_redirect, build_caption, check_response, load_config, load_tokens, save_tokens

API_VERSION = "v27.0"
GRAPH_URL = f"https://graph.instagram.com/{API_VERSION}"

# Instagram logins last 60 days. We renew them once they are a week old.
# (Instagram refuses to renew a login that is less than a day old.)
SECONDS_IN_A_DAY = 24 * 60 * 60
RENEW_LOGIN_AFTER_SECONDS = 7 * SECONDS_IN_A_DAY

# How long to wait for Instagram to finish processing the video.
SECONDS_BETWEEN_STATUS_CHECKS = 15
MAX_STATUS_CHECKS = 40  # 40 checks x 15 seconds = 10 minutes


# ---------- Connecting your account (one time) ----------

def connect():
    config = load_config()

    login_page_options = {
        "client_id": config["instagram_app_id"],
        "redirect_uri": config["redirect_uri"],
        "response_type": "code",
        "scope": "instagram_business_basic,instagram_business_content_publish",
    }
    login_page = "https://www.instagram.com/oauth/authorize?" + urlencode(login_page_options)

    print("Open this link, log in to Instagram, and approve the app:")
    print(login_page)
    code = ask_for_code_from_redirect()

    # Step 1: trade the code for a short login (lasts 1 hour).
    response = requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={
            "client_id": config["instagram_app_id"],
            "client_secret": config["instagram_app_secret"],
            "grant_type": "authorization_code",
            "redirect_uri": config["redirect_uri"],
            "code": code,
        },
    )
    check_response(response, "Getting an Instagram login")
    short_login = response.json()

    # Instagram sometimes wraps the answer in a "data" list.
    if "data" in short_login:
        short_login = short_login["data"][0]

    # Step 2: trade the short login for a long one (lasts 60 days).
    response = requests.get(
        "https://graph.instagram.com/access_token",
        params={
            "grant_type": "ig_exchange_token",
            "client_secret": config["instagram_app_secret"],
            "access_token": short_login["access_token"],
        },
    )
    check_response(response, "Getting a long Instagram login")
    access_token = response.json()["access_token"]

    # Step 3: look up your account ID, which every posting request needs.
    response = requests.get(
        f"{GRAPH_URL}/me",
        params={"fields": "user_id,username", "access_token": access_token},
    )
    check_response(response, "Looking up your Instagram account")
    account = response.json()

    save_tokens("instagram", {
        "access_token": access_token,
        "user_id": account["user_id"],
        "username": account["username"],
        "saved_at": time.time(),
    })
    print(f"Instagram is connected as @{account['username']}.")


def get_fresh_login():
    """Load the saved login, renewing it if it is more than a week old."""
    login = load_tokens("instagram")
    if login is None:
        raise RuntimeError("Instagram is not connected yet. Run: uv run connect.py instagram")

    login_age_in_seconds = time.time() - login["saved_at"]

    if login_age_in_seconds > RENEW_LOGIN_AFTER_SECONDS:
        response = requests.get(
            "https://graph.instagram.com/refresh_access_token",
            params={"grant_type": "ig_refresh_token", "access_token": login["access_token"]},
        )
        check_response(response, "Renewing the Instagram login (if it expired, run: uv run connect.py instagram)")

        login["access_token"] = response.json()["access_token"]
        login["saved_at"] = time.time()
        save_tokens("instagram", login)

    return login


# ---------- Posting ----------

def post(video_path, description, hashtags, is_private):
    if is_private:
        raise RuntimeError("Instagram has no private posts, so it was skipped. Uncheck Instagram for test posts.")

    login = get_fresh_login()
    access_token = login["access_token"]
    user_id = login["user_id"]

    file_share = PublicFileShare(video_path)
    try:
        public_video_link = file_share.start()

        # Step 1: tell Instagram where the video is. It starts downloading and processing it.
        response = requests.post(
            f"{GRAPH_URL}/{user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": public_video_link,
                "caption": build_caption(description, hashtags),
                "access_token": access_token,
            },
        )
        check_response(response, "Sending the video to Instagram")
        container_id = response.json()["id"]

        # Step 2: wait until Instagram has finished with the video.
        wait_until_video_is_ready(container_id, access_token)
    finally:
        # Instagram has its own copy now (or it failed), so take the public link down.
        file_share.stop()

    # Step 3: publish it.
    response = requests.post(
        f"{GRAPH_URL}/{user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
    )
    check_response(response, "Publishing the Instagram reel")
    post_id = response.json()["id"]

    # Step 4: get the link to the new post.
    response = requests.get(
        f"{GRAPH_URL}/{post_id}",
        params={"fields": "permalink", "access_token": access_token},
    )
    check_response(response, "Getting the Instagram post link")
    return response.json()["permalink"]


def wait_until_video_is_ready(container_id, access_token):
    for check_number in range(MAX_STATUS_CHECKS):
        response = requests.get(
            f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code,status", "access_token": access_token},
        )
        check_response(response, "Checking the Instagram upload")
        upload_status = response.json()

        if upload_status["status_code"] == "FINISHED":
            return

        if upload_status["status_code"] == "ERROR" or upload_status["status_code"] == "EXPIRED":
            raise RuntimeError(f"Instagram could not process the video: {upload_status}")

        time.sleep(SECONDS_BETWEEN_STATUS_CHECKS)

    raise RuntimeError("Instagram took more than 10 minutes to process the video. Check the Instagram app.")


# ---------- Temporary public link for the video ----------

class PublicFileShare:
    """Makes one video reachable from the internet for a few minutes, using a Cloudflare quick tunnel.

    Only a copy of that one file, under a random name, is shared. stop() takes the link down
    and deletes the copy.
    """

    def __init__(self, video_path):
        self.video_path = Path(video_path)
        self.temp_folder = None
        self.web_server = None
        self.tunnel_process = None
        self.log_file = None

    def start(self):
        """Returns the public link to the video."""
        # 1. Copy the video into a new empty folder, so nothing else on your computer gets shared.
        self.temp_folder = Path(tempfile.mkdtemp())
        shared_folder = self.temp_folder / "shared"
        shared_folder.mkdir()

        random_file_name = secrets.token_hex(16) + ".mp4"
        shutil.copy(self.video_path, shared_folder / random_file_name)

        # 2. Serve that folder on a free port on this computer.
        # partial() fills in the "directory" setting for the file server ahead of time.
        file_handler = partial(QuietFileHandler, directory=str(shared_folder))
        self.web_server = ThreadingHTTPServer(("127.0.0.1", 0), file_handler)
        port = self.web_server.server_address[1]

        server_thread = threading.Thread(target=self.web_server.serve_forever, daemon=True)
        server_thread.start()

        # 3. Open a Cloudflare tunnel to that port. cloudflared writes the public address into its log.
        log_path = self.temp_folder / "cloudflared.log"
        self.log_file = open(log_path, "w")
        self.tunnel_process = subprocess.Popen(
            ["cloudflared", "tunnel", "--no-autoupdate", "--url", f"http://127.0.0.1:{port}"],
            stdout=self.log_file,
            stderr=self.log_file,
        )

        tunnel_address = wait_for_tunnel_address(log_path)
        public_video_link = tunnel_address + "/" + random_file_name

        wait_until_link_works(public_video_link)
        return public_video_link

    def stop(self):
        if self.tunnel_process is not None:
            self.tunnel_process.terminate()
            self.tunnel_process.wait()

        if self.log_file is not None:
            self.log_file.close()

        if self.web_server is not None:
            self.web_server.shutdown()

        if self.temp_folder is not None:
            shutil.rmtree(self.temp_folder)


class QuietFileHandler(SimpleHTTPRequestHandler):
    """A normal file server that doesn't print a line for every request."""

    def log_message(self, format, *args):
        pass


def wait_for_tunnel_address(log_path):
    """cloudflared prints its public address (https://something.trycloudflare.com) after a few seconds."""
    for attempt in range(60):
        log_text = log_path.read_text()
        match = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", log_text)

        if match is not None:
            return match.group(0)

        time.sleep(0.5)

    raise RuntimeError(f"cloudflared did not start a tunnel. Its log is at {log_path}")


def wait_until_link_works(link):
    """A brand-new tunnel can take a few seconds before it is reachable."""
    for attempt in range(30):
        try:
            response = requests.head(link, timeout=10)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass

        time.sleep(2)

    raise RuntimeError("The temporary public link for Instagram never started working.")
