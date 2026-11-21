# influencer-tools

Post one reel to **YouTube Shorts, Instagram Reels and TikTok** at once.

```
uv run app.py          # web page at http://localhost:8765
uv run post.py my_reel.mp4 --description "Chopin Nocturne" --hashtags "piano chopin"
```

## How it fits together

| File | What it does |
|---|---|
| `app.py` | The web page (Flask). |
| `post.py` | Same thing from the command line. |
| `connect.py` | One-time login per platform. |
| `poster.py` | Posts to each chosen platform in turn. One failing doesn't stop the others. |
| `platforms/*.py` | One file per platform, each with `connect()` and `post()`. |
| `common.py` | Reading/saving settings, building captions, error messages. |

Secrets live in `config.json`, `client_secret.json` and `tokens.json`. All three are in `.gitignore`.

Captions: the description, a blank line, then the hashtags. YouTube uses the first line of the description as the title.

## One-time setup

```
cp config.example.json config.json
```

### YouTube
1. Go to https://console.cloud.google.com and create a project.
2. Enable **YouTube Data API v3**.
3. Set up the OAuth consent screen: **External**, and add your own Google account as a test user.
4. Under **Credentials**, create an **OAuth client ID** of type **Desktop app**. Download the JSON and save it here as `client_secret.json`.
5. Run `uv run connect.py youtube`. A browser opens. Log in and approve.

Limits to know about:
- While the consent screen is in **Testing**, the login expires after 7 days. Switch it to **In production** to keep it. Google will show an "unverified app" warning that you can click through, since the app is only for you.
- Until Google audits the API project, uploads are forced to **private**. You can switch each video to public in YouTube Studio, or apply for the audit (it's free).

### Instagram
1. Switch your Instagram account to **Professional** (Creator or Business).
2. Go to https://developers.facebook.com, create an app, and pick the Instagram use case (**API setup with Instagram login**).
3. Add your Instagram account under the app's roles as an **Instagram tester**, and accept the invite in Instagram if asked.
4. In **Set up Instagram business login**, add the `redirect_uri` from `config.json` (`https://localhost/callback`) as a redirect URL.
5. Copy the **Instagram app ID** and **Instagram app secret** into `config.json`.
6. Run `uv run connect.py instagram`, open the link it prints, approve, and paste back the address you land on.

Instagram can't receive an upload straight from your computer, so it downloads the video from a link instead. While posting, `cloudflared` opens a temporary public link to a copy of that one video under a random name, and closes it once Instagram has the video.

Instagram has no private posts, so it refuses "Private test post".

### TikTok
1. Go to https://developers.tiktok.com and create an app of type **Web**.
2. Add **Login Kit** and **Content Posting API**, and turn on **Direct Post**.
3. Add the scopes `user.info.basic` and `video.publish`.
4. Add `https://localhost/callback` as the redirect URI.
5. Copy the **client key** and **client secret** into `config.json`. If you test with a sandbox, use the sandbox keys and add your account as a target user.
6. Run `uv run connect.py tiktok`, open the link, approve, and paste back the address you land on.

Until TikTok audits the app, posts must be private, so tick "Private test post". You can make a video public afterwards in the TikTok app.

## If a portal rejects `https://localhost/callback`
Use any https address you control, for example your own website. Put the same address in both the portal and `config.json`. The page doesn't need to work; you only paste back the address with `?code=...` on the end.
