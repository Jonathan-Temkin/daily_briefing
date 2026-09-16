"""
Picks a handful of random photos from data/photos/pool/ for the report's page-1
header strip. This never touches the network -- it only reads local files --
so it works the same whether or not a fresh photo was pulled from Google Photos
this run. If the pool is missing or empty, it writes an empty manifest rather
than raising, so a report build can always proceed with the strip simply
omitted. This script should never be the reason a daily report fails to
generate.

Usage: python pick_photos.py [count]   (count defaults to 3)
Writes data/photos_manifest.json: {"photos": ["../data/photos/pool/mazie_1.jpg", ...]}
"""

import json
import random
import sys
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POOL_DIR = DATA_DIR / "photos" / "pool"
MANIFEST_PATH = DATA_DIR / "photos_manifest.json"
VALID_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    photos = []
    try:
        if POOL_DIR.is_dir():
            candidates = sorted(
                p for p in POOL_DIR.iterdir() if p.suffix.lower() in VALID_EXT
            )
            random.shuffle(candidates)
            chosen = candidates[:count]
            photos = [f"../data/photos/pool/{p.name}" for p in chosen]
    except Exception as e:
        print(f"pick_photos.py: non-fatal error picking photos ({e}) -- writing empty manifest")
        photos = []

    MANIFEST_PATH.write_text(json.dumps({"photos": photos}, indent=2))
    if photos:
        print(f"Picked {len(photos)} photo(s) from the local pool: {photos}")
    else:
        print("No photos available in the pool -- manifest is empty, header strip will be omitted.")


if __name__ == "__main__":
    main()
