"""One-time login for each platform. Run it once per platform:

    uv run connect.py youtube
    uv run connect.py instagram
    uv run connect.py tiktok
"""

import argparse

from poster import PLATFORMS

parser = argparse.ArgumentParser(description="Connect one of your accounts.")
parser.add_argument("platform", choices=PLATFORMS.keys())
arguments = parser.parse_args()

platform = PLATFORMS[arguments.platform]
platform.connect()
