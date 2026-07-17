import importlib.util
from pathlib import Path


SPEC = importlib.util.spec_from_file_location(
    "download_1337x",
    Path(__file__).resolve().parents[1] / "download_1337x.py",
)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_rank_candidates_prefers_high_resolution_seeders_and_size():
    candidates = [
        {
            "title": "Titanic 1997 720p BluRay",
            "row_text": "Titanic 1997 720p BluRay Size 700 MB Seeders 12",
            "detail_url": "https://example.com/1",
        },
        {
            "title": "Titanic 1997 1080p WEB-DL",
            "row_text": "Titanic 1997 1080p WEB-DL Size 2.2 GB Seeders 120",
            "detail_url": "https://example.com/2",
        },
        {
            "title": "Titanic 1997 2160p 4K Remux",
            "row_text": "Titanic 1997 2160p 4K Remux Size 8.4 GB Seeders 500",
            "detail_url": "https://example.com/3",
        },
        {
            "title": "Titanic 1997 1080p x265",
            "row_text": "Titanic 1997 1080p x265 Size 4.5 GB Seeders 80",
            "detail_url": "https://example.com/4",
        },
    ]

    ranked = module.rank_candidates(candidates)

    assert [item["title"] for item in ranked[:3]] == [
        "Titanic 1997 2160p 4K Remux",
        "Titanic 1997 1080p WEB-DL",
        "Titanic 1997 1080p x265",
    ]
