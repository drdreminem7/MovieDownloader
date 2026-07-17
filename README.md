# 1337x Movie Downloader

Automated movie downloader for 1337x. Give it a movie title, and it will search the site, rank the best-looking results from the first page, and start downloading the top three choices through uTorrent Web.

This tool is intended for movie searches and should be used with movie titles, not performer-style or celebrity-style queries.

## Setup

```bash
pip install -r requirements.txt
python3 -m playwright install chromium
```

## Usage

```bash
python3 download_1337x.py "movie title" [limit] [start_page]
```

### Parameters

- `movie title` (required): A movie name to search for
- `limit` (optional, default 3): How many torrent candidates to download after ranking
- `start_page` (optional, default 1): Which page to start from

### Examples

```bash
# Search for a movie and download the best three ranked results from page 1
python3 download_1337x.py "star wars"

# Search for a movie and download the best three from page 2
python3 download_1337x.py "dune" 3 2

# Search for a movie and download the best five ranked results
python3 download_1337x.py "inception" 5
```

## How It Works

1. Takes your movie query and builds the 1337x search URL.
2. Opens Brave using your existing browser profile and cached session.
3. Scans the search results from the requested page onward.
4. Looks at each torrent candidate and gathers available metadata such as:
    - resolution (for example 720p, 1080p, 2160p)
    - file size
    - seeders
    - other quality clues from the torrent title or metadata
5. Ranks the candidates by a simple quality-first rule:
    - higher resolution is preferred
    - larger files are preferred when they match the same quality tier
    - more seeders are preferred so downloads finish faster
6. Picks the best three results from the first page and starts downloading them through uTorrent Web.
7. Saves magnet links to `~/Downloads/Movies/magnets.txt` and sends them to uTorrent Web.

## Quality Ranking Strategy

The script is designed to prefer torrents that are most likely to be both high quality and practical to download.

The ranking logic favors:

- higher video resolution, such as 1080p, 1440p, 2160p, and beyond
- stronger bitrate/size signals when they indicate better quality
- higher seeder counts for faster, more reliable downloads

In short, the goal is to choose the best three torrents that are both visually strong and likely to finish quickly.

## Requirements

- macOS with Brave browser installed
- uTorrent Web app installed
- Python 3.12+

## Notes

- Best used with movie titles rather than actor or performer-style search terms
- Uses your cached Brave cookies for automatic access
- Starts the top three ranked torrent downloads automatically
- All downloads are routed to `~/Downloads/Torrents` when possible
