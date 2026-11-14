# Reimbursement OCR Prototype

<p align="center">
<img width="496" height="288" alt="Screenshot 2026-11-14 at 14 16 00" src="https://github.com/user-attachments/assets/20795575-676c-44c3-8498-a1aae9f55639" />
</p>

A machine learning pipeline to prototype automated invoice and receipt parsing for the [**McMaster Solar Car** reimbursement platform](https://github.com/McMaster-Solar-Car-Project/purchase-request-site) via optical character recognition (OCR). It tests whether the model can pull the key fields off of digital and physical receipts accurately enough to pre-fill a reimbursement request. [EasyOCR](https://github.com/JaidedAI/EasyOCR) was evaluated against key project benchmarks and hardware limitations.

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

For each receipt, `output/` gets the raw OCR text (`.txt`) and the parsed fields (`.json`). `output/summary.json` holds the overall report for the key benchmarks:

- **Size**: model file size
- **Speed**: load time, average, median, and slowest time per receipt
- **Accuracy**: fields correct, plus how many item names and prices the OCR read

## Limitations

- This is a prototype benchmark, not a production parser.
- Line items aren't parsed into structured fields yet; they're only checked for OCR recall.
- Only images are supported; PDFs need converting first.
- Store detection is limited to a fixed list of vendors.
