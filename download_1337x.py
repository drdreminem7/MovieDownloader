#!/usr/bin/env python3
"""
1337x Movie Downloader - Extract magnets by search term with pagination.
Usage: python3 download_1337x.py "movie name" [limit] [start_page]
Example: python3 download_1337x.py "inception" 50 2
"""
import re
import shutil
import sys
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import bencodepy
from playwright.sync_api import sync_playwright

BRAVE_PATH = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
BRAVE_PROFILE = Path.home() / "Library/Application Support/BraveSoftware/Brave-Browser/Default"
OUT = Path.home() / "Downloads" / "Movies"
TORRENTS_DIR = Path.home() / "Downloads" / "Torrents"
UTWEB_SETTINGS = Path.home() / "Library/Application Support/uTorrent Web/settings.dat"
UTWEB_SETTINGS_BAK = Path.home() / "Library/Application Support/uTorrent Web/settings.dat.bak"
OUT.mkdir(parents=True, exist_ok=True)
TORRENTS_DIR.mkdir(parents=True, exist_ok=True)


def ensure_utorrent_save_path(path: Path) -> None:
    """Set uTorrent Web's save path to the desired folder and restart the app so the setting takes effect."""
    if not UTWEB_SETTINGS.exists():
        print("⚠️  uTorrent Web settings file not found; download path may stay default.")
        return

    try:
        obj = bencodepy.decode(UTWEB_SETTINGS.read_bytes())
        obj[b"save_path"] = str(path).encode("utf-8")
        encoded = bencodepy.encode(obj)
        UTWEB_SETTINGS.write_bytes(encoded)
        if UTWEB_SETTINGS_BAK.exists():
            UTWEB_SETTINGS_BAK.write_bytes(encoded)
        print(f"📁 uTorrent Web save path set to: {path}")
    except Exception as exc:
        print(f"⚠️  Could not update uTorrent Web settings: {exc}")


def restart_utorrent_web() -> None:
    """Restart uTorrent Web so the new save path is loaded from disk."""
    subprocess.run(["killall", "-9", "uTorrent Web"], check=False)
    time.sleep(2)
    subprocess.run(["open", "-a", "uTorrent Web"], check=False)
    time.sleep(5)
    print("📱 uTorrent Web restarted; waiting for its settings to load.")


def move_completed_downloads(download_dir: Path, target_dir: Path) -> int:
    """Move completed files from Downloads into Downloads/Torrents."""
    moved = 0
    target_dir.mkdir(parents=True, exist_ok=True)

    for path in download_dir.iterdir():
        if path.name.startswith('.') or path.name == 'Movies' or path.name == 'Torrents':
            continue
        if path.is_dir():
            continue
        if path.suffix in {'.part', '.!ut', '.torrent'}:
            continue

        try:
            if path.exists() and path.stat().st_size > 0:
                dest = target_dir / path.name
                if not dest.exists():
                    shutil.move(str(path), str(dest))
                    moved += 1
        except Exception:
            continue

    return moved


def watch_downloads_for_torrents(download_dir: Path, target_dir: Path, timeout_seconds: int = 180) -> None:
    """Background watcher that moves finished downloads into Torrents."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        moved = move_completed_downloads(download_dir, target_dir)
        if moved:
            print(f"📦 Moved {moved} finished file(s) into {target_dir}")
        time.sleep(5)

def make_temp_brave_profile(source: Path) -> Path:
    """Copy the Brave profile to a temporary folder so Playwright can use it without locking the live profile."""
    temp_root = Path(tempfile.mkdtemp(prefix="brave-profile-"))
    temp_profile = temp_root / "Default"
    shutil.copytree(source, temp_profile, dirs_exist_ok=True)
    return temp_profile


def parse_resolution(text: str) -> int:
    """Return a numeric score for resolution so higher-quality torrents rank higher."""
    lowered = text.lower()
    if "2160p" in lowered or "4k" in lowered:
        return 2160
    if "1440p" in lowered:
        return 1440
    if "1080p" in lowered:
        return 1080
    if "720p" in lowered:
        return 720
    if "480p" in lowered:
        return 480
    if "360p" in lowered:
        return 360
    return 0


def parse_size_bytes(text: str) -> float:
    """Parse a size string like 2.2 GB or 700 MB into bytes."""
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*(kb|mb|gb|tb)", text.lower())
    if not match:
        return 0.0
    value = float(match.group(1))
    unit = match.group(2)
    multipliers = {"kb": 1024, "mb": 1024 * 1024, "gb": 1024 * 1024 * 1024, "tb": 1024 * 1024 * 1024 * 1024}
    return value * multipliers[unit]


def parse_seeders(text: str) -> int:
    """Extract the seeder count from a text blob."""
    match = re.search(r"seeders?\s*[:#]?\s*(\d+)", text.lower())
    if match:
        return int(match.group(1))
    return 0


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank torrent candidates by resolution, file size, and seeders."""
    scored = []
    for candidate in candidates:
        text = (candidate.get("row_text") or "")
        resolution = parse_resolution(text)
        size_bytes = parse_size_bytes(text)
        seeders = parse_seeders(text)
        score = (resolution * 1000000) + (size_bytes // 1024) + seeders
        scored.append({**candidate, "score": score, "resolution": resolution, "size_bytes": size_bytes, "seeders": seeders})

    scored.sort(key=lambda item: (-item["score"], item["title"].lower()))
    return scored


if len(sys.argv) < 2:
    print("Usage: python3 download_1337x.py 'search term' [limit] [start_page]")
    print("Examples:")
    print("  python3 download_1337x.py 'interstellar'          # top 3 from page 1")
    print("  python3 download_1337x.py 'dune' 5       # top 5 from page 1")
    print("  python3 download_1337x.py 'inception' 5 2     # top 5 starting from page 2")
    sys.exit(1)

search_term = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 3
start_page = int(sys.argv[3]) if len(sys.argv) > 3 else 1

search_query = "+".join(search_term.split())

print(f"🔍 Searching for: {search_term}")
print(f"📍 Downloading the top {limit} ranked torrents")
print(f"📄 Starting from page: {start_page}\n")
ensure_utorrent_save_path(TORRENTS_DIR)
restart_utorrent_web()

with sync_playwright() as p:
    temp_profile = make_temp_brave_profile(BRAVE_PROFILE)
    context = p.chromium.launch_persistent_context(
        user_data_dir=str(temp_profile),
        executable_path=BRAVE_PATH,
        headless=False,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-gpu",
        ],
    )
    page = context.new_page()
    
    print("📱 Opening Brave with your profile...\n")
    
    all_candidates = []
    current_page = start_page
    
    # Loop through pages until we have enough candidates to rank
    while len(all_candidates) < max(limit * 3, 12):
        url = f"https://www.1337x.to/search/{search_query}/{current_page}/"
        print(f"📄 Scraping page {current_page}...")
        
        try:
            page.goto(url, wait_until="networkidle", timeout=120000)
            time.sleep(2)
            page.wait_for_selector("a[href^='/torrent/']", timeout=30000)
            
            page_candidates = []
            for a in page.query_selector_all("a[href^='/torrent/']"):
                href = a.get_attribute("href")
                if href:
                    detail_url = urljoin(url, href)
                    title = a.inner_text()
                    row_text = a.evaluate("el => el.closest('tr')?.innerText || ''")
                    page_candidates.append({
                        "title": title,
                        "row_text": row_text,
                        "detail_url": detail_url,
                    })
            
            page_candidates = list({item["detail_url"]: item for item in page_candidates}.values())
            all_candidates.extend(page_candidates)
            print(f"   Found {len(page_candidates)} torrents (total: {len(all_candidates)})")
            
            if len(page_candidates) == 0:
                print(f"   No more torrents found. Stopping.")
                break
                
            current_page += 1
        except Exception as e:
            print(f"   Error on page {current_page}: {e}")
            break
    
    ranked_candidates = rank_candidates(all_candidates)
    top_candidates = ranked_candidates[:limit]
    print(f"\n🔍 Ranked {len(top_candidates)} best torrents to process")
    print(f"📝 Extracting magnet links...\n")
    
    magnets = []
    for i, candidate in enumerate(top_candidates, start=1):
        print(f"[{i}/{len(top_candidates)}] Extracting magnet for {candidate['title']}...")
        try:
            page.goto(candidate["detail_url"], wait_until="domcontentloaded", timeout=60000)
            magnet_elem = page.query_selector("a[href^='magnet:']")
            if magnet_elem:
                magnet = magnet_elem.get_attribute("href")
                magnets.append(magnet)
                print(f"     ✓ Got magnet")
            else:
                print(f"     ✗ No magnet found")
        except Exception as e:
            print(f"     ✗ Error: {e}")
    
    context.close()
    shutil.rmtree(temp_profile.parent, ignore_errors=True)

# Save magnets
if magnets:
    magnet_file = OUT / "magnets.txt"
    with open(magnet_file, "w") as f:
        f.write("\n".join(magnets))
    print(f"\n✅ Saved {len(magnets)} magnet links to: {magnet_file}")
    
    # Open in uTorrent Web
    print(f"\n🚀 Opening {len(magnets)} torrents in uTorrent Web...")
    for magnet in magnets:
        subprocess.run(["open", "-a", "uTorrent Web", magnet], check=False)

    watcher = threading.Thread(target=watch_downloads_for_torrents, args=(Path.home()/"Downloads", TORRENTS_DIR), daemon=True)
    watcher.start()
    print(f"✅ All torrents sent to uTorrent Web!\n")
else:
    print("\n❌ No magnet links extracted.")
