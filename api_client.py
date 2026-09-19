"""
api_client.py - BeatStars random-song API client (pure Python, no browser).

  python api_client.py https://dexterolsen2.github.io/beatstarstrapnovocals/api/5
  python api_client.py https://dexterolsen2.github.io/beatstarstrapnovocals/api/duration/1200

/api/N          -> downloads N random songs
/api/duration/S -> downloads random songs until total duration >= S seconds
                   (overshoot limited to one song)
Saves .mp3 if ffmpeg is installed, otherwise .ts (plays in VLC).
Output folder: ./api_downloads
"""
import os, random, re, shutil, subprocess, sys, time
from urllib.parse import urljoin
import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
OUT = "api_downloads"

def parse_link(url):
    url = url.rstrip("/")
    m = re.match(r"^(.*?)/api/duration/([\d.]+)$", url)
    if m: return m.group(1) + "/", "duration", float(m.group(2))
    m = re.match(r"^(.*?)/api/(\d+)$", url)
    if m: return m.group(1) + "/", "count", int(m.group(2))
    sys.exit("link must end in /api/<songs> or /api/duration/<seconds>")

def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    base, mode, value = parse_link(sys.argv[1])
    os.makedirs(OUT, exist_ok=True)
    have_ff = shutil.which("ffmpeg") is not None
    print("site:", base, "| mode:", mode, "| value:", value)
    print("ffmpeg:", "yes (mp3)" if have_ff else "NOT FOUND (raw .ts)")

    man = requests.get(urljoin(base, "data/manifest.json"), headers=UA,
                       timeout=30).json()
    print("catalog: {:,} tracks in {} chunks".format(man["total"], len(man["chunks"])))

    cache, used = {}, set()

    def pick():  # RANDOM track from a RANDOM chunk, no repeats
        for _ in range(30):
            ci = random.randrange(len(man["chunks"]))
            if ci not in cache:
                try:
                    r = requests.get(urljoin(base, "data/" + man["chunks"][ci]),
                                     headers=UA, timeout=60)
                    r.raise_for_status()
                    cache[ci] = r.json()
                except Exception:
                    continue
            arr = cache.get(ci) or []
            if arr:
                t = random.choice(arr)
                if t.get("u") and t["i"] not in used:
                    return t
        return None

    def playlist(t):
        r = requests.get(t["u"], headers=UA, timeout=30); r.raise_for_status()
        lines = [l.strip() for l in r.text.splitlines() if l.strip()]
        url = t["u"]
        if any(l.startswith("#EXT-X-STREAM-INF") for l in lines):
            k = next(i for i, l in enumerate(lines)
                     if l.startswith("#EXT-X-STREAM-INF"))
            url = urljoin(url, lines[k + 1])
            r = requests.get(url, headers=UA, timeout=30); r.raise_for_status()
            lines = [l.strip() for l in r.text.splitlines() if l.strip()]
        if any(l.startswith("#EXT-X-KEY") for l in lines):
            raise RuntimeError("encrypted stream")
        dur = 0.0
        for l in lines:
            if l.startswith("#EXTINF:"):
                try: dur += float(l[8:].split(",")[0])
                except ValueError: pass
        map_url = None
        for l in lines:
            if l.startswith("#EXT-X-MAP"):
                mu = re.search(r'URI="([^"]+)"', l)
                if mu: map_url = urljoin(url, mu.group(1))
        segs = [urljoin(url, l) for l in lines if not l.startswith("#")]
        if not segs or not dur:
            raise RuntimeError("empty playlist")
        return dur, map_url, segs

    n = total = 0
    attempts = 0
    while attempts < 4000:
        if mode == "count" and n >= value: break
        if mode == "duration" and total >= value: break
        attempts += 1
        t = pick()
        if not t:
            print("no more unique tracks"); break
        used.add(t["i"])
        try:
            dur, map_url, segs = playlist(t)
        except Exception as e:
            print("skip ({}): {}".format((t.get("t") or "?")[:50], e)); continue
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", t.get("t") or "track")
        name = "{} [{}]".format(safe.strip()[:100] or "track", t["i"])
        print("[{}] {} ({:.0f}s)...".format(n + 1, name, dur), end=" ", flush=True)
        try:
            blob = b""
            if map_url:
                blob += requests.get(map_url, headers=UA, timeout=60).content
            for s in segs:
                blob += requests.get(s, headers=UA, timeout=60).content
        except Exception as e:
            print("FAILED ({})".format(e)); continue
        ts_path = os.path.join(OUT, name + ".ts")
        with open(ts_path, "wb") as f:
            f.write(blob)
        if have_ff:
            mp3_path = os.path.join(OUT, name + ".mp3")
            p = subprocess.run(["ffmpeg", "-y", "-i", ts_path, "-vn",
                                "-c:a", "libmp3lame", "-b:a", "192k", mp3_path],
                               capture_output=True, timeout=600)
            if p.returncode == 0:
                os.remove(ts_path); print("saved .mp3")
            else:
                print("ffmpeg failed - kept .ts")
        else:
            print("saved .ts")
        n += 1; total += dur
        print("    -> {} songs, {:.0f}s total".format(n, total))
        time.sleep(0.3)
    print("\nDONE: {} songs, {:.0f}s of audio -> {}".format(
        n, total, os.path.abspath(OUT)))

if __name__ == "__main__":
    main()
