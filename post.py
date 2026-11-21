"""Post a reel from the command line instead of the web page.

    uv run post.py my_reel.mp4 --description "Chopin Nocturne Op. 9 No. 2" --hashtags "piano chopin"
    uv run post.py my_reel.mp4 --description "Test" --platforms youtube tiktok --private
"""

import argparse

from poster import PLATFORMS, post_everywhere

parser = argparse.ArgumentParser(description="Post one video to YouTube Shorts, Instagram Reels and TikTok.")
parser.add_argument("video", help="path to the .mp4 file")
parser.add_argument("--description", default="")
parser.add_argument("--hashtags", default="", help='for example "piano cover chopin"')
parser.add_argument("--platforms", nargs="+", choices=PLATFORMS.keys(), default=list(PLATFORMS.keys()))
parser.add_argument("--private", action="store_true", help="only you can see it (YouTube and TikTok)")
arguments = parser.parse_args()

results = post_everywhere(
    arguments.video,
    arguments.description,
    arguments.hashtags,
    arguments.platforms,
    arguments.private,
)

print()
for result in results:
    if result["worked"]:
        print(f"OK      {result['platform']}: {result['message']}")
    else:
        print(f"FAILED  {result['platform']}: {result['message']}")
