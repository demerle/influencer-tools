"""Small helpers shared by every platform: settings files, captions, and API errors."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_FOLDER = Path(__file__).parent
CONFIG_FILE = PROJECT_FOLDER / "config.json"
TOKENS_FILE = PROJECT_FOLDER / "tokens.json"


# ---------- Settings and saved logins ----------

def load_config():
    """Read config.json (your app IDs and secrets)."""
    if not CONFIG_FILE.exists():
        raise RuntimeError("config.json is missing. Copy config.example.json to config.json and fill it in.")

    with open(CONFIG_FILE) as file:
        return json.load(file)


def load_all_tokens():
    """Read every saved login from tokens.json. Returns an empty dict if nothing is saved yet."""
    if not TOKENS_FILE.exists():
        return {}

    with open(TOKENS_FILE) as file:
        return json.load(file)


def load_tokens(platform_name):
    """Return the saved login for one platform, or None if it was never connected."""
    all_tokens = load_all_tokens()

    if platform_name in all_tokens:
        return all_tokens[platform_name]

    return None


def save_tokens(platform_name, tokens):
    """Save the login for one platform, keeping the other platforms' logins as they are."""
    all_tokens = load_all_tokens()
    all_tokens[platform_name] = tokens

    with open(TOKENS_FILE, "w") as file:
        json.dump(all_tokens, file, indent=2)

    # Only your user account should be able to read your logins.
    TOKENS_FILE.chmod(0o600)


# ---------- Captions ----------

def clean_hashtags(hashtags_text):
    """Turn whatever was typed ("piano, #cover chopin") into a tidy list: ["#piano", "#cover", "#chopin"]."""
    hashtags_text = hashtags_text.replace(",", " ")
    words = hashtags_text.split()

    hashtags = []
    for word in words:
        if not word.startswith("#"):
            word = "#" + word
        hashtags.append(word)

    return hashtags


def build_caption(description, hashtags):
    """The description, then a blank line, then the hashtags."""
    caption = description.strip()

    if len(hashtags) > 0:
        hashtag_line = " ".join(hashtags)
        caption = caption + "\n\n" + hashtag_line

    return caption.strip()


# ---------- Talking to APIs ----------

def check_response(response, action_description):
    """Stop with a readable error message if a platform's API said no."""
    if not response.ok:
        raise RuntimeError(f"{action_description} failed ({response.status_code}): {response.text}")


def ask_for_code_from_redirect():
    """Used while connecting Instagram and TikTok.

    After you approve the app, the platform sends your browser to the redirect address
    with "?code=..." on the end. That page won't load, and that's fine. We only need the code.
    """
    print()
    print("After you approve, your browser will open a page that doesn't load. That's expected.")
    pasted_address = input("Copy the whole address from the address bar and paste it here: ").strip()

    query_values = parse_qs(urlparse(pasted_address).query)

    if "code" not in query_values:
        raise RuntimeError("That address has no 'code=' in it. Try connecting again.")

    return query_values["code"][0]
