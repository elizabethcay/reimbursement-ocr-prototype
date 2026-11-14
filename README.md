# reimbursement-ocr-prototype

A prototype invoice and receipt parser for the **McMaster Solar Car** reimbursement platform. It tests whether [EasyOCR](https://github.com/JaidedAI/EasyOCR) can pull the key fields off a receipt image accurately enough to pre-fill a reimbursement request.

## What it does

`src/benchmark.py` runs EasyOCR on each receipt image, groups the text into lines, and uses regex rules to extract:

- **Store** (Amazon, Apple, Dell, DigiKey, Home Depot, Walmart)
- **Date** (normalized to `YYYY-MM-DD`)
- **Currency** (CAD, USD, INR, EUR, GBP)
- **Summary amounts**: subtotal, discount, delivery fee, service fee, tax, tip, total

It then compares the results against hand-labelled JSON and reports model size, speed, and accuracy.

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Data layout

```
data/
  receipts/   receipt images (.png, .jpg, ...); PDFs are skipped
  expected/   one ground-truth JSON per receipt, same file name (e.g. Amazon1.json)
models/       EasyOCR model weights (downloaded on first run)
output/       generated results
```

`data/`, `models/`, and `output/` are git-ignored.

## Run

```bash
python src/benchmark.py
```

For each receipt, `output/` gets the raw OCR text (`.txt`) and the parsed fields (`.json`). `output/summary.json` holds the overall report:

- **Size**: model file size
- **Speed**: load time, average, median, and slowest time per receipt
- **Accuracy**: fields correct, plus how many item names and prices the OCR read

## Limitations

- This is a prototype benchmark, not a production parser.
- Line items aren't parsed into structured fields yet; they're only checked for OCR recall.
- Only images are supported; PDFs need converting first.
- Store detection is limited to a fixed list of vendors.
