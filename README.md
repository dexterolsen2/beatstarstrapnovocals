# Free Trap Beats (No Vocals)

Streaming player for BeatStars free trap instrumentals.
Audio streams directly from BeatStars' CDN; this site only hosts the link list.

## Deploy
1. Create a new GitHub repository (public).
2. Upload everything in this folder (index.html + the whole data/ directory):
       git init
       git add .
       git commit -m "tracks"
       git remote add origin https://github.com/<user>/<repo>.git
       git push -u origin main
3. Repo Settings -> Pages -> Source: "Deploy from a branch" -> main -> / (root).
4. Open https://<user>.github.io/<repo>/ a few minutes later.

## Notes
- Chunks load lazily; "+10 chunks" loads more into the searchable list.
- If Chrome refuses to play (CORS), Safari works, or edit index.html and set
  PROXY = "https://corsproxy.io/?url="
