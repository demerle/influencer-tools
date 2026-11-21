"""Posts one video to every chosen platform. Used by both the web page (app.py) and the command line (post.py)."""

from common import clean_hashtags
from platforms import instagram, tiktok, youtube

PLATFORMS = {
    "youtube": youtube,
    "instagram": instagram,
    "tiktok": tiktok,
}


def post_everywhere(video_path, description, hashtags_text, platform_names, is_private):
    """Posts to each platform in turn. If one fails, the others still get posted.

    Returns a list like:
        [{"platform": "youtube", "worked": True, "message": "https://youtube.com/shorts/..."}, ...]
    """
    hashtags = clean_hashtags(hashtags_text)
    results = []

    for platform_name in platform_names:
        print(f"Posting to {platform_name}...")
        platform = PLATFORMS[platform_name]

        try:
            message = platform.post(video_path, description, hashtags, is_private)
            worked = True
        except Exception as error:
            message = str(error)
            worked = False

        print(f"  {message}")
        results.append({"platform": platform_name, "worked": worked, "message": message})

    return results
