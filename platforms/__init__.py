"""One file per platform. Each one has the same two functions:

    connect()  - one-time login, saves the result to tokens.json
    post(video_path, description, hashtags, is_private)  - posts the video, returns a link or a short message
"""
