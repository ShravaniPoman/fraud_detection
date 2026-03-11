"""
generate_fraud.py
─────────────────
Step 3: Generate fraud variants (Class 1 & Class 2) from the 500 clean invoices.

For each clean invoice, this script creates 1-2 tampered variants (Class 1)
by applying controlled corruption functions to the JSON + re-rendering the PDF.

Fraud types generated:
  Class 1:
    - amount_inflation   : inflate one or more line item prices
    - date_extension     : push discharge date forward
    - lineitem_added     : insert a fake high-value procedure
    - identity_tweak     : alter patient name, ID, or policy number

  Class 2:
    - ai_rewrite         : replace text fields with AI-style generic language

Output per fraud invoice:
  data/synthetic_fraud/invoice_XXXXX_<fraud_type>.docx
  data/synthetic_fraud/invoice_XXXXX_<fraud_type>.pdf
  data/synthetic_fraud/invoice_XXXXX_<fraud_type>.json

Usage (from project root):
    python src/generate_fraud.py
"""

import os
import json
import random
import subprocess
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from docxtpl import DocxTemplate
from tqdm import tqdm

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(__file__).resolve().parent.parent
CLEAN_DIR    = BASE_DIR / "data" / "synthetic_clean"
FRAUD_DIR    = BASE_DIR / "data" / "synthetic_fraud"
TEMPLATE_DIR = BASE_DIR / "data" / "medical_templates"
FRAUD_DIR.mkdir(parents=True, exist_ok=True)

TEMPLATES = {
    1: TEMPLATE_DIR / "template_01_hospital_placeholders.docx",
    2: TEMPLATE_DIR / "template_02_clinic_placeholders.docx",
    3: TEMPLATE_DIR / "template_03_insurance_placeholders.docx",
}

SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"

# ── Fake data for injecting into fraud variants ───────────────────────────────
FAKE_HIGH_VALUE_ITEMS = [
    ("CPT 93458", "Left Heart Catheterization with Coronary Angiography",  3800.00),
    ("CPT 92928", "Percutaneous Coronary Intervention — Stent Placement",  7200.00),
    ("CPT 70553", "MRI Brain with and without Contrast",                   1800.00),
    ("CPT 72148", "MRI Lumbar Spine without Contrast",                     1400.00),
    ("CPT 93306", "Echocardiography — Transthoracic, Complete",            1100.00),
    ("REV 0360",  "Operating Room Services",                               2500.00),
    ("REV 0370",  "Anesthesiology Services",                               1050.00),
    ("CPT 99291", "Critical Care — First 30-74 Minutes",                    850.00),
    ("CPT 27447", "Total Knee Arthroplasty",                               5500.00),
    ("CPT 33533", "Coronary Artery Bypass — Arterial",                     9800.00),
]

# AI-style generic text replacements for field values
AI_PHYSICIAN_NAMES = [
    "Dr. John A. Smith, MD", "Dr. Emily R. Johnson, MD",
    "Dr. Michael B. Williams, MD", "Dr. Sarah E. Davis, MD",
    "Dr. Robert C. Miller, MD", "Dr. Jennifer L. Brown, MD",
]

AI_HOSPITAL_NAMES = [
    "General Medical Center", "Regional Health System",
    "Community Hospital and Medical Center", "University Medical Center",
    "Advanced Care Medical Institute", "Metropolitan Hospital Group",
]

AI_GENERIC_ITEMS = [
    ("CPT 99999", "Medical Services Rendered",          200.00),
    ("CPT 88888", "Professional Services Fee",          350.00),
    ("REV 0001",  "Hospital Services",                  500.00),
    ("REV 0002",  "Inpatient Care Services",            750.00),
    ("CPT 77777", "Diagnostic and Treatment Services",  420.00),
]

AI_NOTES = [
    "Thank you for choosing our facility for your healthcare needs.",
    "We appreciate your trust in our medical professionals.",
    "Our team is dedicated to providing you with the highest quality care.",
    "Please do not hesitate to contact our billing department with any questions.",
]

# ── Helper functions ──────────────────────────────────────────────────────────

def fmt_money(amount):
    if amount == "" or amount is None:
        return ""
    return f"${float(amount):,.2f}"

def parse_money(s):
    """Convert '$1,234.56' or '-$1,234.56' back to float."""
    if not s or s == "":
        return 0.0
    s = str(s).replace("$", "").replace(",", "").strip()
    return float(s)

def fmt_date(d):
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return d.strftime("%B %-d, %Y")

def recompute_totals(items, discount=0.0, tax_rate=0):
    """Recompute all totals from scratch given a list of item dicts."""
    subtotal   = round(sum(i["line_total"] for i in items if i.get("line_total")), 2)
    taxable    = round(subtotal - discount, 2)
    tax_amount = round(taxable * (tax_rate / 100), 2)
    total      = round(taxable + tax_amount, 2)
    return subtotal, taxable, tax_amount, total

def load_clean_invoice(json_path):
    with open(json_path) as f:
        return json.load(f)

def save_fraud_invoice(record, ctx, template_id, out_stem):
    """Render docx → pdf, save json."""
    tpl_path  = TEMPLATES[template_id]
    docx_path = FRAUD_DIR / f"{out_stem}.docx"
    pdf_path  = FRAUD_DIR / f"{out_stem}.pdf"
    json_path = FRAUD_DIR / f"{out_stem}.json"

    # Render
    tpl = DocxTemplate(str(tpl_path))
    tpl.render(ctx)
    tpl.save(str(docx_path))

    # Convert to PDF
    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "pdf",
         str(docx_path), "--outdir", str(FRAUD_DIR)],
        check=True, capture_output=True
    )

    # Save JSON
    with open(json_path, "w") as f:
        json.dump(record, f, indent=2)

def build_context_from_record(record):
    """Rebuild a full docxtpl context dict from a clean JSON record."""
    items = record["items"]

    ctx = {
        "INVOICE_NO":       record["invoice_id"],
        "INVOICE_DATE":     fmt_date(record["invoice_date"]),
        "DUE_DATE":         fmt_date(
                                (date.fromisoformat(record["invoice_date"])
                                 + timedelta(days=random.randint(14,30))).isoformat()
                            ),
        "HOSPITAL_NAME":    record["hospital_name"],
        "CLINIC_NAME":      record["hospital_name"],
        "HOSPITAL_ADDRESS": record.get("hospital_address", ""),
        "CLINIC_ADDRESS":   record.get("hospital_address", ""),
        "HOSPITAL_PHONE":   record.get("hospital_phone", ""),
        "CLINIC_PHONE":     record.get("hospital_phone", ""),
        "HOSPITAL_EMAIL":   record.get("hospital_email", ""),
        "CLINIC_EMAIL":     record.get("hospital_email", ""),
        "HOSPITAL_WEBSITE": record.get("hospital_website", ""),
        "HOSPITAL_NPI":     record.get("hospital_npi", ""),
        "CLINIC_NPI":       record.get("hospital_npi", ""),
        "HOSPITAL_TAX_ID":  record.get("hospital_tax_id", ""),
        "HOSPITAL_FAX":     record.get("hospital_fax", ""),
        "PATIENT_NAME":     record["patient_name"],
        "PATIENT_ID":       record["patient_id"],
        "PATIENT_DOB":      fmt_date(record["patient_dob"]),
        "PATIENT_PHONE":    record.get("patient_phone", ""),
        "PATIENT_ADDRESS":  record.get("patient_address", ""),
        "ADMISSION_DATE":   fmt_date(record["admission_date"]),
        "DISCHARGE_DATE":   fmt_date(record["discharge_date"]),
        "VISIT_DATE":       fmt_date(record["admission_date"]),
        "WARD_ROOM":        record.get("ward_room", ""),
        "PHYSICIAN":        record.get("physician", ""),
        "REFERRAL":         record.get("referral", "Self-referred"),
        "INSURER_NAME":     record["insurer"],
        "POLICY_NO":        record["policy_no"],
        "GROUP_NO":         record.get("group_no", ""),
        "AUTH_NO":          record.get("auth_no", ""),
        "PRIMARY_INSURER":  record["insurer"],
        "PRIMARY_POLICY_NO":record["policy_no"],
        "SECONDARY_INSURER":record.get("secondary_insurer", "None"),
        "SECONDARY_POLICY_NO": record.get("secondary_policy_no", "N/A"),
        "DIAGNOSIS_CODE":   record.get("diagnosis_code", ""),
        "DIAGNOSIS_DESC":   record.get("diagnosis_desc", ""),
        "DRG_CODE":         record.get("drg_code", ""),
        "DRG_DESC":         record.get("drg_desc", ""),
        "BANK_NAME":        record.get("bank_name", ""),
        "ACCOUNT_NAME":     record.get("account_name", ""),
        "ACCOUNT_NO":       record.get("account_no", ""),
        "ROUTING_NO":       record.get("routing_no", ""),
        "PAYMENT_REF":      f"{record['invoice_id']} / {record['patient_id']}",
    }
    return ctx

def fill_item_slots(ctx, items, template_id):
    """Fill ITEM_N_* placeholders. T03 has 8 slots, others have 5."""
    max_slots = 8 if template_id == 3 else 5
    padded    = items[:max_slots]
    while len(padded) < max_slots:
        padded.append({"code":"","description":"","qty":"","unit_price":"","line_total":""})

    for n, item in enumerate(padded, start=1):
        ctx[f"ITEM_{n}_CODE"]  = item.get("code", "")
        ctx[f"ITEM_{n}_DESC"]  = item.get("description", "")
        ctx[f"ITEM_{n}_QTY"]   = str(item["qty"])         if item.get("qty")        != "" else ""
        ctx[f"ITEM_{n}_UNIT"]  = fmt_money(item["unit_price"]) if item.get("unit_price") != "" else ""
        ctx[f"ITEM_{n}_TOTAL"] = fmt_money(item["line_total"])  if item.get("line_total")  != "" else ""

def fill_totals(ctx, record, subtotal, taxable, tax_amount, total, discount=0.0, template_id=1):
    tax_rate = record.get("tax_rate", 0)
    ctx["SUBTOTAL"]     = fmt_money(subtotal)
    ctx["DISCOUNT"]     = f"-{fmt_money(discount)}"
    ctx["TAXABLE"]      = fmt_money(taxable)
    ctx["TAX_RATE"]     = str(tax_rate)
    ctx["TAX_AMOUNT"]   = fmt_money(tax_amount)
    ctx["AMOUNT_PAID"]  = fmt_money(0.00)
    ctx["AMOUNT_DUE"]   = fmt_money(total)

    if template_id == 3:
        # Recompute insurance adjustments proportionally
        primary_pay   = round(total * random.uniform(0.55, 0.70), 2)
        secondary_pay = round(total * random.uniform(0.10, 0.18), 2)
        contractual   = round(total * random.uniform(0.08, 0.14), 2)
        medicare_c    = round(total * random.uniform(0.03, 0.07), 2)
        adj_total     = round(-(primary_pay + secondary_pay + contractual + medicare_c), 2)
        balance_due   = round(total + adj_total, 2)

        ctx["CHARGES_TOTAL"] = fmt_money(total)
        ctx["ADJ_1_DESC"]    = "Primary Insurance Payment"
        ctx["ADJ_1_AMOUNT"]  = fmt_money(-primary_pay)
        ctx["ADJ_2_DESC"]    = "Secondary Insurance Payment"
        ctx["ADJ_2_AMOUNT"]  = fmt_money(-secondary_pay)
        ctx["ADJ_3_DESC"]    = "Contractual Adjustment — Network Rate"
        ctx["ADJ_3_AMOUNT"]  = fmt_money(-contractual)
        ctx["ADJ_4_DESC"]    = "Contractual Adjustment — Medicare Rate"
        ctx["ADJ_4_AMOUNT"]  = fmt_money(-medicare_c)
        ctx["ADJ_TOTAL"]     = fmt_money(adj_total)
        ctx["BALANCE_DUE"]   = fmt_money(balance_due)
        ctx["AMOUNT_DUE"]    = fmt_money(balance_due)


# ══════════════════════════════════════════════════════════════════════════════
# FRAUD TRANSFORMATION FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════

def make_amount_inflation(record):
    """
    Inflate 1-3 line item prices by 2x-5x.
    Option A (easy fraud):   inflate items but do NOT fix subtotal/total → arithmetic mismatch
    Option B (hard fraud):   inflate AND recompute totals → internally consistent but prices suspicious
    50/50 split between easy and hard.
    """
    fraud = deepcopy(record)
    items = fraud["items"]
    if not items:
        return None

    # Pick 1-3 items to inflate
    n_inflate = random.randint(1, min(3, len(items)))
    targets   = random.sample(range(len(items)), n_inflate)
    easy_mode = random.random() < 0.5   # easy = inconsistent arithmetic

    for idx in targets:
        multiplier = round(random.uniform(2.0, 5.0), 1)
        old_unit   = items[idx]["unit_price"]
        new_unit   = round(old_unit * multiplier, 2)
        new_total  = round(new_unit * items[idx]["qty"], 2)
        items[idx]["unit_price"] = new_unit
        items[idx]["line_total"] = new_total

    if easy_mode:
        # Don't fix totals — creates an obvious arithmetic mismatch
        fraud["fraud_subtype"] = "amount_inflation_inconsistent"
    else:
        # Recompute everything correctly — harder to detect
        discount   = fraud.get("discount", 0.0)
        tax_rate   = fraud.get("tax_rate", 0)
        subtotal, taxable, tax_amount, total = recompute_totals(items, discount, tax_rate)
        fraud["subtotal"]     = subtotal
        fraud["tax_amount"]   = tax_amount
        fraud["total_amount"] = total
        fraud["fraud_subtype"] = "amount_inflation_consistent"

    fraud["class"]      = 1
    fraud["fraud_type"] = "amount_inflation"
    return fraud

def make_date_extension(record):
    """
    Push the discharge date forward by 3-7 days.
    This increases per-diem and room charges if present,
    or just creates a date inconsistency if not recomputed.
    """
    fraud = deepcopy(record)

    # Extend discharge date
    orig_discharge = date.fromisoformat(fraud["discharge_date"])
    extension_days = random.randint(3, 7)
    new_discharge  = orig_discharge + timedelta(days=extension_days)

    # Don't push past today
    if new_discharge > date.today():
        new_discharge = orig_discharge + timedelta(days=2)

    fraud["discharge_date"] = str(new_discharge)

    # Also update any per-diem or room & board line items
    items = fraud["items"]
    for item in items:
        if any(kw in item.get("description","").lower()
               for kw in ["per diem", "room & board", "room and board", "subsequent hospital"]):
            old_qty   = item["qty"]
            new_qty   = old_qty + extension_days
            item["qty"]        = new_qty
            item["line_total"] = round(item["unit_price"] * new_qty, 2)

    # Recompute totals
    discount   = fraud.get("discount", 0.0)
    tax_rate   = fraud.get("tax_rate", 0)
    subtotal, taxable, tax_amount, total = recompute_totals(items, discount, tax_rate)
    fraud["subtotal"]     = subtotal
    fraud["tax_amount"]   = tax_amount
    fraud["total_amount"] = total

    fraud["class"]      = 1
    fraud["fraud_type"] = "date_extension"
    fraud["fraud_meta"] = {"extension_days": extension_days}
    return fraud

def make_lineitem_added(record):
    """
    Insert a fake high-value procedure into the line items.
    The new item is added but totals may or may not be updated.
    """
    fraud    = deepcopy(record)
    items    = fraud["items"]
    template = fraud["template_id"]

    max_slots = 8 if template == 3 else 5

    # Only add if there's room
    if len(items) >= max_slots:
        # Replace least expensive item instead
        cheapest_idx = min(range(len(items)), key=lambda i: items[i]["unit_price"])
        code, desc, price = random.choice(FAKE_HIGH_VALUE_ITEMS)
        qty   = 1
        total = round(price, 2)
        items[cheapest_idx] = {
            "code": code, "description": desc,
            "qty": qty, "unit_price": price, "line_total": total
        }
    else:
        code, desc, price = random.choice(FAKE_HIGH_VALUE_ITEMS)
        qty   = 1
        total = round(price, 2)
        items.append({
            "code": code, "description": desc,
            "qty": qty, "unit_price": price, "line_total": total
        })

    # Recompute totals
    discount   = fraud.get("discount", 0.0)
    tax_rate   = fraud.get("tax_rate", 0)
    subtotal, taxable, tax_amount, total_amt = recompute_totals(items, discount, tax_rate)
    fraud["subtotal"]     = subtotal
    fraud["tax_amount"]   = tax_amount
    fraud["total_amount"] = total_amt

    fraud["class"]      = 1
    fraud["fraud_type"] = "lineitem_added"
    fraud["items"]      = items
    return fraud

def make_identity_tweak(record):
    """
    Subtly alter patient name, ID, or policy number.
    Creates a document that looks legitimate but has mismatched identity fields.
    """
    fraud   = deepcopy(record)
    tweaks  = random.sample(["name", "id", "policy"], k=random.randint(1, 2))

    for tweak in tweaks:
        if tweak == "name":
            # Swap first and last name, or add a typo
            parts = fraud["patient_name"].split()
            if len(parts) >= 2:
                if random.random() < 0.5:
                    # Swap first and last
                    fraud["patient_name"] = f"{parts[-1]} {' '.join(parts[:-1])}"
                else:
                    # Change middle initial
                    if len(parts) == 3:
                        new_initial = random.choice("BCDFGHJKLMNPQRSTVWXYZ") + "."
                        fraud["patient_name"] = f"{parts[0]} {new_initial} {parts[2]}"

        elif tweak == "id":
            # Change one digit in patient ID
            pid    = fraud["patient_id"]
            digits = [c for c in pid if c.isdigit()]
            if digits:
                idx       = random.randint(0, len(digits)-1)
                new_digit = str((int(digits[idx]) + random.randint(1,8)) % 10)
                fraud["patient_id"] = pid.replace(digits[idx], new_digit, 1)

        elif tweak == "policy":
            # Change a few characters in policy number
            pol = list(fraud["policy_no"])
            for _ in range(random.randint(1, 3)):
                idx = random.randint(0, len(pol)-1)
                if pol[idx].isdigit():
                    pol[idx] = str((int(pol[idx]) + random.randint(1,8)) % 10)
                elif pol[idx].isalpha():
                    pol[idx] = random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ")
            fraud["policy_no"] = "".join(pol)

    fraud["class"]      = 1
    fraud["fraud_type"] = "identity_tweak"
    fraud["fraud_meta"] = {"tweaked_fields": tweaks}
    return fraud

def make_ai_rewrite(record):
    """
    Class 2: Replace text fields with AI-style overly generic language.
    Keeps structure and arithmetic intact but replaces specific names/details
    with generic boilerplate — characteristic of LLM-generated documents.
    """
    fraud = deepcopy(record)

    # Replace hospital name with generic AI-style name
    fraud["hospital_name"] = random.choice(AI_HOSPITAL_NAMES)

    # Replace physician with generic name
    fraud["physician"] = random.choice(AI_PHYSICIAN_NAMES)

    # Replace some item descriptions with generic AI text
    items = fraud["items"]
    n_replace = random.randint(1, min(3, len(items)))
    targets   = random.sample(range(len(items)), n_replace)

    for idx in targets:
        code, desc, price = random.choice(AI_GENERIC_ITEMS)
        # Keep the price similar (±20%) to avoid obvious numeric fraud
        adjusted_price = round(items[idx]["unit_price"] * random.uniform(0.85, 1.15), 2)
        items[idx]["code"]        = code
        items[idx]["description"] = desc
        items[idx]["unit_price"]  = adjusted_price
        items[idx]["line_total"]  = round(adjusted_price * items[idx]["qty"], 2)

    # Recompute totals
    discount   = fraud.get("discount", 0.0)
    tax_rate   = fraud.get("tax_rate", 0)
    subtotal, taxable, tax_amount, total = recompute_totals(items, discount, tax_rate)
    fraud["subtotal"]     = subtotal
    fraud["tax_amount"]   = tax_amount
    fraud["total_amount"] = total

    fraud["class"]      = 2
    fraud["fraud_type"] = "ai_rewrite"
    fraud["items"]      = items
    return fraud


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════

def process_clean_invoice(json_path):
    """Load one clean invoice and generate its fraud variants."""
    record      = load_clean_invoice(json_path)
    template_id = record["template_id"]
    base_stem   = json_path.stem.replace("_clean", "")   # e.g. "invoice_00001"

    # Pick which fraud types to apply (always 2 from Class 1 + optionally 1 Class 2)
    class1_transforms = [
        ("amount_inflation", make_amount_inflation),
        ("date_extension",   make_date_extension),
        ("lineitem_added",   make_lineitem_added),
        ("identity_tweak",   make_identity_tweak),
    ]
    # Always apply 2 random Class 1 types per invoice
    chosen_c1 = random.sample(class1_transforms, k=2)

    # Apply Class 2 to ~40% of invoices
    apply_c2  = random.random() < 0.4

    results = []

    for fraud_name, transform_fn in chosen_c1:
        fraud_record = transform_fn(record)
        if fraud_record is None:
            continue

        out_stem = f"{base_stem}_{fraud_name}"
        ctx      = build_context_from_record(fraud_record)

        # Override with fraud values
        ctx["PATIENT_NAME"]  = fraud_record["patient_name"]
        ctx["PATIENT_ID"]    = fraud_record["patient_id"]
        ctx["POLICY_NO"]     = fraud_record["policy_no"]
        ctx["PRIMARY_POLICY_NO"] = fraud_record["policy_no"]
        ctx["DISCHARGE_DATE"]= fmt_date(fraud_record["discharge_date"])
        ctx["HOSPITAL_NAME"] = fraud_record["hospital_name"]
        ctx["CLINIC_NAME"]   = fraud_record["hospital_name"]
        ctx["PHYSICIAN"]     = fraud_record.get("physician", ctx.get("PHYSICIAN",""))

        fill_item_slots(ctx, fraud_record["items"], template_id)
        fill_totals(ctx, fraud_record,
                    fraud_record["subtotal"],
                    fraud_record["subtotal"] - fraud_record.get("discount", 0),
                    fraud_record["tax_amount"],
                    fraud_record["total_amount"],
                    fraud_record.get("discount", 0.0),
                    template_id)

        save_fraud_invoice(fraud_record, ctx, template_id, out_stem)
        results.append(out_stem)

    if apply_c2:
        fraud_record = make_ai_rewrite(record)
        out_stem     = f"{base_stem}_ai_rewrite"
        ctx          = build_context_from_record(fraud_record)

        ctx["HOSPITAL_NAME"] = fraud_record["hospital_name"]
        ctx["CLINIC_NAME"]   = fraud_record["hospital_name"]
        ctx["PHYSICIAN"]     = fraud_record.get("physician", ctx.get("PHYSICIAN",""))

        fill_item_slots(ctx, fraud_record["items"], template_id)
        fill_totals(ctx, fraud_record,
                    fraud_record["subtotal"],
                    fraud_record["subtotal"] - fraud_record.get("discount", 0),
                    fraud_record["tax_amount"],
                    fraud_record["total_amount"],
                    fraud_record.get("discount", 0.0),
                    template_id)

        save_fraud_invoice(fraud_record, ctx, template_id, out_stem)
        results.append(out_stem)

    return results


if __name__ == "__main__":
    # Find all clean JSON files
    clean_jsons = sorted(CLEAN_DIR.glob("*_clean.json"))

    if not clean_jsons:
        print(f"No clean invoices found in {CLEAN_DIR}")
        print("Run generate_clean.py first.")
        exit(1)

    print(f"\nFound {len(clean_jsons)} clean invoices.")
    print(f"Generating fraud variants into: {FRAUD_DIR}\n")

    total_generated = 0
    errors          = 0

    for json_path in tqdm(clean_jsons, unit="invoice"):
        try:
            stems = process_clean_invoice(json_path)
            total_generated += len(stems)
        except Exception as e:
            errors += 1
            tqdm.write(f"[ERROR] {json_path.name}: {e}")

    print(f"\n✅  Done!")
    print(f"   Fraud invoices generated : {total_generated}")
    print(f"   Errors                   : {errors}")
    print(f"   Output folder            : {FRAUD_DIR}")
    print(f"\nEach fraud invoice has a .docx, .pdf, and .json file.")
    print(f"Next step: run src/split_dataset.py to create train/val/test splits.")
