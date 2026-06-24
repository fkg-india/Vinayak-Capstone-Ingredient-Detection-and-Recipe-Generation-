"""

Scrapes, cleans, and organises images for a custom Indian ingredients dataset.

OUTPUT:
    indian_ingredients_dataset/
        moong_dal/
            00001.jpg
            00002.jpg
            ...
        haldi/
            ...
    dataset_review/        images flagged for manual review
    dataset_report.json     summary stats
"""

import os
import sys
import json
import time
import shutil
import hashlib
import argparse
from pathlib import Path
from PIL import Image


INGREDIENTS = [
    ("moong_dal",       "moong dal green lentils indian ingredient"),
    ("chana_dal",       "chana dal split chickpeas indian ingredient"),
    ("haldi",           "haldi turmeric powder spice indian"),
    ("cardamom",        "cardamom elaichi pods spice indian"),
    ("cumin",           "cumin seeds jeera indian spice"),
    ("coriander_seeds", "coriander seeds dhania indian spice"),
    ("mustard_seeds",   "mustard seeds rai indian spice"),
    ("red_chilli_powder",      "red chilli powder mirchi indian spice"),
    ("garam_masala",    "garam masala spice blend indian"),
    ("cinnamon",    "cinnamon sticks spice indian"),
    ("cloves",            "cloves laung spice indian"),
    ("besan",           "besan gram flour chickpea flour indian"),
    ("paneer",          "paneer fresh indian cottage cheese block"),
    ("ghee",            "ghee clarified butter indian cooking"),
    ("tamarind",        "tamarind imli indian ingredient"),
    ("curry_leaves",    "curry leaves kadi patta fresh indian"),
    ("methi",           "methi fenugreek seeds leaves indian"),
    ("hing",            "asafoetida hing spice indian"),
    ("amchur",          "amchur dry mango powder indian spice"),
    ("saffron",         "saffron kesar strands indian spice"),
]

IMAGES_PER_CLASS    = 600   # scrape 600 to end up with ~500 after cleaning
TARGET_PER_CLASS    = 500    
DATASET_DIR         = Path("indian_ingredients_dataset")
REVIEW_DIR          = Path("dataset_review")
MIN_WIDTH           = 100   # pixels
MIN_HEIGHT          = 100
MIN_FILE_SIZE_KB    = 5     # files smaller than this are likely corrupt
SCRAPE_DELAY_SEC    = 0.5    


def scrape_class(folder_name: str, search_query: str, max_images: int):
    """Scrape images for one ingredient class using Bing """
    from icrawler.builtin import BingImageCrawler

    out_dir = DATASET_DIR / "raw" / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)

    existing = len(list(out_dir.glob("*.jpg"))) + len(list(out_dir.glob("*.png")))
    if existing >= max_images:
        print(f"   {folder_name}: already has {existing} images, skipping scrape")
        return existing

    print(f"Scraping '{search_query}' → {out_dir}")

    try:
        crawler = BingImageCrawler(
            feeder_threads=2,
            parser_threads=2,
            downloader_threads=4,
            storage={"root_dir": str(out_dir)},
            log_level=50,
        )
        crawler.crawl(
            keyword=search_query,
            max_num=max_images,
            min_size=(MIN_WIDTH, MIN_HEIGHT),
        )
    except Exception as e:
        print(f"   Bing failed: {e}")

    count = len(list(out_dir.glob("*")))
    print(f"   Downloaded {count} images for {folder_name}")
    return count


def get_image_hash(img: Image.Image) -> str:
    thumb = img.convert("L").resize((16, 16))
    return hashlib.md5(thumb.tobytes()).hexdigest()


def clean_class(folder_name: str) -> dict:

    raw_dir    = DATASET_DIR / "raw" / folder_name
    clean_dir  = DATASET_DIR / folder_name
    review_dir = REVIEW_DIR / folder_name
    clean_dir.mkdir(parents=True, exist_ok=True)
    review_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "class": folder_name,
        "raw": 0,
        "kept": 0,
        "removed_corrupt": 0,
        "removed_duplicate": 0,
        "removed_too_small": 0,
        "removed_low_quality": 0,
        "flagged_for_review": 0,
    }

    seen_hashes = set()
    kept        = 0

    all_files = sorted(raw_dir.glob("*"))
    stats["raw"] = len(all_files)

    for fpath in all_files:
        if kept >= TARGET_PER_CLASS:
            break

        try:
            img = Image.open(fpath).convert("RGB")
        except Exception:
            stats["removed_corrupt"] += 1
            continue

        size_kb = fpath.stat().st_size / 1024
        if size_kb < MIN_FILE_SIZE_KB:
            stats["removed_corrupt"] += 1
            continue

        w, h = img.size
        if w < MIN_WIDTH or h < MIN_HEIGHT:
            stats["removed_too_small"] += 1
            continue

        img_hash = get_image_hash(img)
        if img_hash in seen_hashes:
            stats["removed_duplicate"] += 1
            continue
        seen_hashes.add(img_hash)

        pixels   = list(img.getdata())
        sample   = pixels[::100]   
        r_vals   = [p[0] for p in sample]
        g_vals   = [p[1] for p in sample]
        b_vals   = [p[2] for p in sample]
        r_range  = max(r_vals) - min(r_vals)
        g_range  = max(g_vals) - min(g_vals)
        b_range  = max(b_vals) - min(b_vals)
        if r_range < 15 and g_range < 15 and b_range < 15:
            stats["removed_low_quality"] += 1
            continue

         if w < 200 or h < 200:
            dest = review_dir / f"{kept+1:05d}.jpg"
            img.save(dest, "JPEG", quality=90)
            stats["flagged_for_review"] += 1
 
         kept += 1
        dest = clean_dir / f"{kept:05d}.jpg"
        try:
            img.save(dest, "JPEG", quality=92)
        except (TimeoutError, OSError) as e:
            print(f"  ⚠️  Save failed ({e}), skipping this image")
            continue

    stats["kept"] = kept
    return stats



def verify_dataset():
    """Print a summary table of the final dataset."""
    print("\n📊 Dataset Summary")
    print(f"{'Class':<22} {'Images':>8} {'Status':>10}")
    print("-" * 44)

    total = 0
    for folder_name, _ in INGREDIENTS:
        class_dir = DATASET_DIR / folder_name
        count = len(list(class_dir.glob("*.jpg"))) if class_dir.exists() else 0
        total += count
        status = " Good" if count >= 400 else ("⚠  Low" if count >= 200 else " Poor")
        print(f"  {folder_name:<20} {count:>8} {status:>10}")

    print("-" * 44)
    print(f"  {'TOTAL':<20} {total:>8}")
    print(f"\n  Dataset saved to: {DATASET_DIR.resolve()}")
    if REVIEW_DIR.exists():
        print(f"  Review flagged:   {REVIEW_DIR.resolve()}")

def main():
    parser = argparse.ArgumentParser(description="Indian Ingredients Dataset Builder")
    parser.add_argument("--clean-only", action="store_true",
                        help="Skip scraping, only re-run the cleaning step")
    parser.add_argument("--class", dest="single_class", default=None,
                        help="Only process one class e.g. --class haldi")
    parser.add_argument("--verify", action="store_true",
                        help="Just print the dataset summary, no scraping or cleaning")
    args = parser.parse_args()

    try:
        import icrawler
    except ImportError:
        print("  icrawler not installed. Run: pip install icrawler")
        sys.exit(1)

    if args.verify:
        verify_dataset()
        return

    targets = INGREDIENTS
    if args.single_class:
        targets = [(n, q) for n, q in INGREDIENTS if n == args.single_class]
        if not targets:
            print(f"  Class '{args.single_class}' not found in INGREDIENTS list.")
            sys.exit(1)

    print(f"\nBuilding Indian Ingredients Dataset")
    print(f"   Classes:    {len(targets)}")
    print(f"   Target:     {TARGET_PER_CLASS} images per class")
    print(f"   Output:     {DATASET_DIR.resolve()}\n")

    all_stats = []

    for i, (folder_name, search_query) in enumerate(targets):
        print(f"\n[{i+1}/{len(targets)}] {folder_name.upper()}")
        print("─" * 50)

        
        if not args.clean_only:
            scrape_class(folder_name, search_query, IMAGES_PER_CLASS)
            time.sleep(SCRAPE_DELAY_SEC)

         
        print(f"  Cleaning images...")
        stats = clean_class(folder_name)
        all_stats.append(stats)

        print(f" Kept: {stats['kept']} | "
              f"Removed: corrupt={stats['removed_corrupt']} "
              f"dup={stats['removed_duplicate']} "
              f"small={stats['removed_too_small']} "
              f"low-q={stats['removed_low_quality']} | "
              f"Flagged: {stats['flagged_for_review']}")

     
    report = {
        "total_classes": len(targets),
        "target_per_class": TARGET_PER_CLASS,
        "total_images": sum(s["kept"] for s in all_stats),
        "per_class": all_stats,
    }
    with open("dataset_report.json", "w") as f:
        json.dump(report, f, indent=2)

    
    verify_dataset()
    print(f"\n Full report saved → dataset_report.json")

    if REVIEW_DIR.exists():
        review_count = sum(1 for _ in REVIEW_DIR.rglob("*.jpg"))
        if review_count > 0:
            print(f"\n  {review_count} images flagged for manual review in {REVIEW_DIR}/")
            print("   Open that folder, delete any obviously wrong images,")
            print("   then run: python build_dataset.py --clean-only")

    print("\n Done!\n")


if __name__ == "__main__":
    main()
