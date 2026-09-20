#!/usr/bin/env python3
"""
api_client.py v2 - BeatStars random-song API client with custom folders.

Link formats (folder part is optional):
  https://<site>/api/<count>                    e.g. .../api/5
  https://<site>/api/<count>/folder/<name>      e.g. .../api/5/folder/TrapMix
  https://<site>/api/duration/<seconds>         e.g. .../api/duration/1200
  https://<site>/api/duration/<seconds>/folder/<name>
  (?folder=<name> is also accepted on either link)

Output folder rules:
  --out PATH + URL folder   ->  PATH/<folder>
  --out PATH                ->  PATH
  URL folder only           ->  ./<folder>
  neither                   ->  ./api_downloads

Examples:
  python api_client.py https://dexterolsen2.github.io/beatstarstrapnovocals/api/5
  python api_client.py https://dexterolsen2.github.io/beatstarstrapnovocals/api/5/folder/TrapMix
  python api_client.py https://dexterolsen2.github.io/beatstarstrapnovocals/api/duration/1200 --out E:/Music
  python api_client.py https://dexterolsen2.github.io/beatstarstrapnovocals/api/duration/1200/folder/Chill -o D:/Beats

All songs are picked at RANDOM. Saves .mp3 if ffmpeg is installed, else .ts (VLC-playable).
"""
import argparse
import os
import random
import re
import shutil
import subprocess
import sys
import time
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def sanitize_folder(s):
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(s or ""))
    s = re.sub(r"\s+", " ", s).strip().strip(".")
    return s[:80]


def parse_link(url):
    if "//" not in url:
        url = "https://" + url
    u = urlparse(url)
    qs = parse_qs(u.query)
    folder = (qs.get("folder") or [""])[0]          # ?folder=... variant
    p = u.path.rstrip("/")
    m = re.match(r"^(.*)/api/duration/([\d.]+)(?:/folder/([^/]+))?$", p)
    if m:
        mode, value = "duration", float(m.group(2))
        if m.group(3):
            folder = unquote(m.group(3))
    else:
        m = re.match(r"^(.*)/api/(\d+)(?:/folder/([^/]+))?$", p)
        if not m:
            sys.exit("link must be /api/<songs> or /api/duration/<seconds> "
                     "(optionally followed by /folder/<name>)")
        mode, value = "count", int(m.group(2))
        if m.group(3):
            folder = unquote(m.group(3))
    base = "%s://%s%s/" % (u.scheme, u.netloc, m.group(1))
    return base, mode, value, folder


def main():
    ap = argparse.ArgumentParser(
        description="BeatStars random-song API client (custom folders supported)")
    ap.add_argument("link",
                    help="API link, e.g. https://.../api/5/folder/TrapMix")
    ap.add_argument("--out", "-o", default=None,
                    help="base output directory (URL folder appended if present)")
    args = ap.parse_args()

    base, mode, value, url_folder = parse_link(args.link)
    folder = sanitize_folder(url_folder)
    if args.out:
        root = os.path.expanduser(args.out)
        out = os.path.join(root, folder) if folder else root
    else:
        out = folder if folder else "api_downloads"
    os.makedirs(out, exist_ok=True)

    have_ff = shutil.which("ffmpeg") is not None
    print("site:", base, "| mode:", mode, "| value:", value)
    print("output folder:", os.path.abspath(out))
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
        ts_path = os.path.join(out, name + ".ts")
        with open(ts_path, "wb") as f:
            f.write(blob)
        if have_ff:
            mp3_path = os.path.join(out, name + ".mp3")
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
        n, total, os.path.abspath(out)))


if __name__ == "__main__":
    main()
