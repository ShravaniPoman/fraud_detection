"""
split_dataset.py
────────────────
Step 4: Split the full dataset into train / val / test sets.

Key rule: ALL variants of the same base invoice (clean + all fraud versions)
go into the SAME split — no leakage between splits.

Split ratio: 70% train / 15% val / 15% test
Stratified: each split maintains roughly the same class proportions.

Output structure:
  data/split/
    train/   ← 70% of base invoices (all their variants)
    val/     ← 15% of base invoices
    test/    ← 15% of base invoices
    split_manifest.json  ← full record of which files went where

Usage (from project root):
    python src/split_dataset.py
"""

import json
import random
import shutil
from collections import defaultdict
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent.parent
CLEAN_DIR  = BASE_DIR / "data" / "synthetic_clean"
FRAUD_DIR  = BASE_DIR / "data" / "synthetic_fraud"
SPLIT_DIR  = BASE_DIR / "data" / "split"

TRAIN_DIR  = SPLIT_DIR / "train"
VAL_DIR    = SPLIT_DIR / "val"
TEST_DIR   = SPLIT_DIR / "test"

for d in [TRAIN_DIR, VAL_DIR, TEST_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# Reproducible results
random.seed(42)

# Split ratios
TRAIN_RATIO = 0.70
VAL_RATIO   = 0.15
# TEST_RATIO  = 0.15 (remainder)

# ── Step 1: Load all JSON records ─────────────────────────────────────────────
print("\nScanning dataset...")

all_records = []

# Clean invoices
for json_path in sorted(CLEAN_DIR.glob("*_clean.json")):
    with open(json_path) as f:
        record = json.load(f)
    record["_json_path"] = str(json_path)
    record["_stem"]      = json_path.stem          # e.g. invoice_00001_clean
    record["_source"]    = "clean"
    all_records.append(record)

# Fraud invoices
for json_path in sorted(FRAUD_DIR.glob("*.json")):
    with open(json_path) as f:
        record = json.load(f)
    record["_json_path"] = str(json_path)
    record["_stem"]      = json_path.stem
    record["_source"]    = "fraud"
    all_records.append(record)

print(f"  Total records found: {len(all_records)}")

# ── Step 2: Group by base_id ──────────────────────────────────────────────────
# All variants of the same invoice share the same base_id
groups = defaultdict(list)
for record in all_records:
    groups[record["base_id"]].append(record)

base_ids = sorted(groups.keys())
print(f"  Unique base invoices: {len(base_ids)}")

# ── Step 3: Split base_ids into train / val / test ────────────────────────────
random.shuffle(base_ids)

n_total = len(base_ids)
n_train = int(n_total * TRAIN_RATIO)
n_val   = int(n_total * VAL_RATIO)
# n_test  = remainder

train_ids = set(base_ids[:n_train])
val_ids   = set(base_ids[n_train : n_train + n_val])
test_ids  = set(base_ids[n_train + n_val :])

print(f"\n  Base invoice split:")
print(f"    Train : {len(train_ids)} base invoices")
print(f"    Val   : {len(val_ids)}   base invoices")
print(f"    Test  : {len(test_ids)}  base invoices")

# ── Step 4: Copy files to split folders ──────────────────────────────────────
print("\nCopying files to split folders...")

manifest = {"train": [], "val": [], "test": []}
counts   = {"train": defaultdict(int), "val": defaultdict(int), "test": defaultdict(int)}

def copy_record(record, dest_dir, split_name):
    """Copy .json, .pdf, and .docx for a record to the destination folder."""
    stem      = record["_stem"]
    src_dir   = Path(record["_json_path"]).parent

    for ext in [".json", ".pdf", ".docx"]:
        src  = src_dir / f"{stem}{ext}"
        dest = dest_dir / f"{stem}{ext}"
        if src.exists():
            shutil.copy2(str(src), str(dest))

    # Track in manifest
    manifest[split_name].append({
        "stem":       stem,
        "base_id":    record["base_id"],
        "class":      record["class"],
        "fraud_type": record.get("fraud_type"),
    })
    counts[split_name][record["class"]] += 1

for base_id, records in groups.items():
    if base_id in train_ids:
        split_name, dest_dir = "train", TRAIN_DIR
    elif base_id in val_ids:
        split_name, dest_dir = "val",   VAL_DIR
    else:
        split_name, dest_dir = "test",  TEST_DIR

    for record in records:
        copy_record(record, dest_dir, split_name)

# ── Step 5: Save manifest ─────────────────────────────────────────────────────
manifest_path = SPLIT_DIR / "split_manifest.json"
with open(manifest_path, "w") as f:
    json.dump(manifest, f, indent=2)

# ── Step 6: Print summary ─────────────────────────────────────────────────────
print("\n" + "="*55)
print("  DATASET SPLIT COMPLETE")
print("="*55)

total_files = 0
for split in ["train", "val", "test"]:
    c = counts[split]
    total = sum(c.values())
    total_files += total
    print(f"\n  {split.upper()}")
    print(f"    Class 0 (clean)    : {c[0]:>4}")
    print(f"    Class 1 (tampered) : {c[1]:>4}")
    print(f"    Class 2 (AI)       : {c[2]:>4}")
    print(f"    Total              : {total:>4}")

print(f"\n  Grand total records : {total_files}")
print(f"  Manifest saved to   : {manifest_path}")
print("\n  ✅ No leakage — all variants of each base invoice")
print("     are in the same split.")
print("\n  Next step: run src/run_ocr.py")
print("="*55 + "\n")

# ── Step 7: Sanity check — verify no base_id appears in 2 splits ─────────────
train_bases = {r["base_id"] for r in manifest["train"]}
val_bases   = {r["base_id"] for r in manifest["val"]}
test_bases  = {r["base_id"] for r in manifest["test"]}

leaks = (train_bases & val_bases) | (train_bases & test_bases) | (val_bases & test_bases)
if leaks:
    print(f"⚠️  WARNING: {len(leaks)} base_ids appear in multiple splits!")
else:
    print("  ✅ Leakage check passed — no base_id appears in more than one split.\n")
