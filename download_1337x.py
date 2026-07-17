#!/usr/bin/env python3
"""
1337x Movie Downloader - Extract magnets by search term with pagination.
Usage: python3 download_1337x.py "movie name" [limit] [start_page]
Example: python3 download_1337x.py "autumn falls" 50 2
"""
import shutil
import sys
import subprocess
import tempfile
import threading
import time
from pathlib import Path
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


if len(sys.argv) < 2:
    print("Usage: python3 download_1337x.py 'search term' [limit] [start_page]")
    print("Examples:")
    print("  python3 download_1337x.py 'interstellar'          # 20 from page 1")
    print("  python3 download_1337x.py 'dune' 50       # 50 from page 1")
    print("  python3 download_1337x.py 'inception' 50 2     # 50 starting from page 2")
    sys.exit(1)

search_term = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 20
start_page = int(sys.argv[3]) if len(sys.argv) > 3 else 1

search_query = "+".join(search_term.split())

print(f"🔍 Searching for: {search_term}")
print(f"📍 Limit: {limit} torrents")
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
    
    all_links = []
    current_page = start_page
    
    # Loop through pages until we have enough torrents
    while len(all_links) < limit:
        url = f"https://www.1337x.to/search/{search_query}/{current_page}/"
        print(f"📄 Scraping page {current_page}...")
        
        try:
            page.goto(url, wait_until="networkidle", timeout=120000)
            
            # Wait for torrent links to appear
            time.sleep(2)
            page.wait_for_selector("a[href^='/torrent/']", timeout=30000)
            
            # Extract detail links from this page
            page_links = []
            for a in page.query_selector_all("a[href^='/torrent/']"):
                href = a.get_attribute("href")
                if href:
                    page_links.append(urljoin(url, href))
            
            page_links = list(dict.fromkeys(page_links))  # Remove duplicates
            all_links.extend(page_links)
            print(f"   Found {len(page_links)} torrents (total: {len(all_links)})")
            
            if len(page_links) == 0:
                print(f"   No more torrents found. Stopping.")
                break
                
            current_page += 1
        except Exception as e:
            print(f"   Error on page {current_page}: {e}")
            break
    
    # Trim to exact limit
    all_links = all_links[:limit]
    print(f"\n🔍 Total torrents to process: {len(all_links)}")
    print(f"📝 Extracting magnet links...\n")
    
    magnets = []
    for i, dlink in enumerate(all_links, start=1):
        print(f"[{i}/{len(all_links)}] Extracting magnet...")
        try:
            page.goto(dlink, wait_until="domcontentloaded", timeout=60000)
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
