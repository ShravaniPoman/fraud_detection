# Medical Invoice Fraud Detection

Detecting AI-generated and manipulated medical invoices using multi-modal Gen-AI features.

## Project Overview

This project builds a document-level classifier that predicts whether a medical invoice is:
- `Class 0` — Authentic / untampered
- `Class 1` — Manually tampered (amounts, dates, identity, line items)
- `Class 2` — AI-generated or heavily AI-rewritten

## Folder Structure

```
fraud_detection_project/
├── data/
│   ├── raw_invoices/          # Public invoice/receipt datasets (style references)
│   ├── medical_templates/     # 3–5 cleaned medical invoice templates (.docx)
│   ├── synthetic_clean/       # Generated authentic invoices (class 0)
│   ├── synthetic_fraud/       # Generated tampered/AI invoices (class 1 & 2)
│   └── split/
│       ├── train/             # 70% — training data
│       ├── val/               # 15% — validation data
│       └── test/              # 15% — held-out test data (touch only at the end)
├── src/
│   ├── generate_clean.py      # Step 2: generate authentic synthetic invoices
│   ├── generate_fraud.py      # Step 3: apply fraud transformations
│   ├── split_dataset.py       # Step 4: train/val/test split (no leakage)
│   ├── run_ocr.py             # Step 5: extract text from PDFs
│   └── train_model.py         # Step 5: baseline classifier
├── notebooks/
│   ├── 01_baseline.ipynb      # TF-IDF + classifier baseline
│   ├── 02_multimodal.ipynb    # Optional: image + text model
│   └── 03_error_analysis.ipynb
├── docs/
│   └── problem_definition.md  # ← START HERE: task, labels, features, evaluation
├── reports/
│   └── (plots and metrics saved here)
├── app.py                     # Step 6: Streamlit/Gradio demo
└── README.md
```

## Steps

| Step | Goal | Output |
|------|------|--------|
| **0** | Define task, labels, features, evaluation | `docs/problem_definition.md` ✅ |
| **1** | Collect medical invoice templates | `data/medical_templates/` |
| **2** | Generate clean synthetic invoices | `data/synthetic_clean/` |
| **3** | Generate fraud/AI variants | `data/synthetic_fraud/` |
| **4** | Split dataset (no leakage) | `data/split/train\|val\|test/` |
| **5** | OCR + train baseline model | `src/`, `notebooks/01_baseline.ipynb` |
| **6** | Evaluate, improve, build demo | `app.py`, `reports/` |
| **7** | Slides + presentation | Final deck |

## Quick Start

```bash
# Install dependencies
pip install docxtpl python-docx pytesseract scikit-learn pandas

# Step 2: generate clean invoices
python src/generate_clean.py

# Step 3: generate fraud variants
python src/generate_fraud.py

# Step 4: split dataset
python src/split_dataset.py

# Step 5: run OCR
python src/run_ocr.py

# Step 5: train baseline
python src/train_model.py

# Step 6: launch demo
streamlit run app.py
```

## Label Schema

```json
{
  "invoice_id": "INV-0001",
  "base_id": "BASE-001",
  "class": 0,
  "fraud_type": null,
  "provider_name": "Ithaca General Hospital",
  "patient_name": "...",
  "admission_date": "2025-11-01",
  "discharge_date": "2025-11-04",
  "invoice_date": "2025-11-05",
  "items": [
    {"description": "...", "code": "CPT99213", "qty": 1, "unit_price": 200.0, "line_total": 200.0}
  ],
  "subtotal": 200.0,
  "tax": 0.0,
  "total_amount": 200.0
}
```

## Evaluation Target

- **Primary:** Binary fraud F1 ≥ 0.75 on test set (`class 1+2` vs. `class 0`)
- **Secondary:** Per-class F1, confusion matrix, per-`fraud_type` breakdown
