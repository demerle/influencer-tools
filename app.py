"""The web page. Start it with:  uv run app.py   then open http://localhost:8765"""

import time

from flask import Flask, render_template, request

from common import PROJECT_FOLDER
from poster import PLATFORMS, post_everywhere

UPLOADS_FOLDER = PROJECT_FOLDER / "uploads"

app = Flask(__name__)


@app.get("/")
def show_form():
    return render_template("index.html", platform_names=PLATFORMS.keys())


@app.post("/")
def post_reel():
    video = request.files["video"]
    description = request.form["description"]
    hashtags_text = request.form["hashtags"]
    chosen_platforms = request.form.getlist("platforms")
    is_private = "private" in request.form

    # Save the uploaded video so the platforms can read it from disk.
    UPLOADS_FOLDER.mkdir(exist_ok=True)
    video_path = UPLOADS_FOLDER / f"{int(time.time())}.mp4"
    video.save(video_path)

    try:
        results = post_everywhere(video_path, description, hashtags_text, chosen_platforms, is_private)
    finally:
        video_path.unlink()

    # Show the form again, filled in, with the results on top.
    return render_template(
        "index.html",
        platform_names=PLATFORMS.keys(),
        results=results,
        description=description,
        hashtags=hashtags_text,
    )


if __name__ == "__main__":
    app.run(port=8765)
