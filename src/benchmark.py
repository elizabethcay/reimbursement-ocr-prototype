# run with python src/benchmark.py

import json
import re
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")  # ignore pytorch warnings

import easyocr  

ROOT = Path(__file__).resolve().parent.parent     
RECEIPTS = ROOT / "data" / "receipts"
EXPECTED = ROOT / "data" / "expected"
MODELS = ROOT / "models"
OUTPUT = ROOT / "output"
OUTPUT.mkdir(exist_ok=True)

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
STORES = ["Amazon", "Apple", "Dell", "DigiKey", "Home Depot", "Walmart"]

# $20.27, CDN$ 20.27, -5.00, 1,234.56, and "3, 892.69"
MONEY = r"-?\s?[A-Z]{0,3}[$₹€£]?\s?-?(?:\d{1,3}(?:,\s?\d{3})+|\d+)\.\d{2}"
MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()

# any field not found on the receipt is reported as 0.0
SUMMARY_LABELS = {
    "subtotal":     [r"sub\s*-?\s*total", r"merchandise\s*total"],
    "discount":     [r"discount", r"promotion", r"savings", r"coupon"],
    "delivery_fee": [r"shipping", r"delivery", r"handling"],
    "service_fee":  [r"service\s*fee", r"eco\s*fee", r"environmental"],
    "tax":          [r"\b(hst|gst|pst|qst|tax)\b(?!.*total)"],
    "tip":          [r"\btip\b", r"gratuity"],
    #"total" skips "sub total", "merchandise total", "order total" and "total before tax".
    "total":        [r"grand\s*total", r"invoice\s*total",
                     r"(?<!sub)(?<!sub )(?<!sub-)(?<!merchandise )(?<!order )\btotal\b(?!.*before)",
                     r"order\s*total", r"amount\s*paid"],
}

def to_lines(results):
    """sorts easyocr boxes into reading order: top-to-bottom lines, left-to-right words."""
    boxes = sorted(results, key=lambda r: r[0][0][1])
    lines = []
    for box in boxes:
        y = box[0][0][1]
        height = box[0][2][1] - box[0][0][1]
        if lines and abs(y - lines[-1]["y"]) < height / 2:
            lines[-1]["boxes"].append(box)
        else:
            lines.append({"y": y, "boxes": [box]})
    return [" ".join(b[1] for b in sorted(l["boxes"], key=lambda b: b[0][0][0])) for l in lines]


def to_number(text):
    """'CDN$ 1,234.56' -> 1234.56"""
    return float(re.sub(r"[^\d.\-]", "", text))


def find_amount(lines, i, label_end):
    """last amount AFTER the label on line i, or else the first amount on the next line."""
    found = re.findall(MONEY, lines[i][label_end:])
    if not found and i + 1 < len(lines):
        found = re.findall(MONEY, lines[i + 1])[:1]
    return abs(to_number(found[-1])) if found else None


def find_date(text):
    """return the first date found as YYYY-MM-DD."""
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", text)                    # 2025-06-09
    if m:
        y, mo, d = m.groups()
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    m = re.search(r"([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s*(\d{4})", text)          # June 9, 2025 / June 9,2025
    if m and m.group(1).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS.index(m.group(1).lower()) + 1:02d}-{int(m.group(2)):02d}"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\.?\s+(\d{4})", text)            # 9 June 2025
    if m and m.group(2).lower() in MONTHS:
        return f"{m.group(3)}-{MONTHS.index(m.group(2).lower()) + 1:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)                              # 06/09/2025
    if m:
        a, b, y = map(int, m.groups())
        mo, d = (b, a) if a > 12 else (a, b)   # ambiguous: assumes MM/DD unless first > 12
        return f"{y}-{mo:02d}-{d:02d}"
    return None


def find_invoice_date(lines):
    """prefer the date next to an 'Invoice Date' label (on that line or the one below);
    otherwise use the first date on the receipt."""
    for i, line in enumerate(lines):
        if re.search(r"invoice\s*date", line, re.IGNORECASE):
            date = find_date(" ".join(lines[i:i + 2]))
            if date:
                return date
    return find_date("\n".join(lines))


def find_currency(text):
    """checks currency clues on the receipt."""
    up = text.upper()
    if "₹" in text or re.search(r"\bINR\b|\bRS\.?\s?\d|AMAZON\.IN", up):
        return "INR"   # checked before CAD because indian receipts also say "GST"
    if "€" in text or re.search(r"\bEUR\b", up):
        return "EUR"
    if "£" in text or re.search(r"\bGBP\b", up):
        return "GBP"
    if re.search(r"\bCAD\b|CDN|C\$|\bHST\b|\bGST\b|\bPST\b|\bQST\b|\.CA\b|CANADA", up):
        return "CAD"
    return "USD"       # plain $ with no Canadian clue


def squash(s):
    """checks currency clues on the receipt."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def to_json(lines):
    text = "\n".join(lines)
    store = next((s for s in STORES if squash(s) in squash(text)), None)
    currency = find_currency(text)

    summary = {}
    for field, patterns in SUMMARY_LABELS.items():
        summary[field] = 0.0
        for pattern in patterns:
            hits = []
            for i, line in enumerate(lines):
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    hits.append(find_amount(lines, i, m.end()))
            hits = [h for h in hits if h is not None]
            if hits:
                summary[field] = hits[-1]
                break

    return {
        "store": store,
        "date": find_invoice_date(lines),
        "currency": currency,
        "items": [],                 # line items not parsed in this basic test
        "summary": {"number_of_items": None, **summary},
    }


def same(predicted, expected):
    if expected is None:
        return predicted is None
    if isinstance(expected, (int, float)):
        return predicted is not None and abs(float(predicted) - expected) < 0.01
    return squash(predicted or "") == squash(expected)


# size and load time
start = time.perf_counter()
reader = easyocr.Reader(["en"], gpu=False, model_storage_directory=str(MODELS))
load_time = time.perf_counter() - start
model_mb = sum(f.stat().st_size for f in MODELS.glob("*.pth")) / 1e6

# speed and accuracy
receipts = sorted(p for p in RECEIPTS.iterdir()
                  if p.suffix.lower() in IMAGE_TYPES and (EXPECTED / f"{p.stem}.json").exists())
skipped = [p.name for p in RECEIPTS.iterdir() if p.suffix.lower() not in IMAGE_TYPES]
if skipped:
    print(f"Skipped (not images, EasyOCR can't read these): {skipped}")
if not receipts:
    raise SystemExit("No receipt images with a matching expected JSON found.")

reader.readtext(str(receipts[0]))  # warm-up, not timed

times = []
checked = correct = 0
items_total = prices_found = names_found = 0
name_words_total = name_words_found = 0

for img in receipts:
    expected = json.loads((EXPECTED / f"{img.stem}.json").read_text(encoding="utf-8"))

    start = time.perf_counter()
    results = reader.readtext(str(img))
    seconds = time.perf_counter() - start
    times.append(seconds)

    lines = to_lines(results)
    predicted = to_json(lines)
    (OUTPUT / f"{img.stem}.json").write_text(json.dumps(predicted, indent=2), encoding="utf-8")
    (OUTPUT / f"{img.stem}.txt").write_text("\n".join(lines), encoding="utf-8")

    # field accuracy: store, date, currency + every summary amount except number_of_items
    pairs = [("store", predicted["store"], expected.get("store")),
             ("date", predicted["date"], expected.get("date")),
             ("currency", predicted["currency"], expected.get("currency"))]
    for key, value in expected.get("summary", {}).items():
        if key != "number_of_items":
            pairs.append((f"summary.{key}", predicted["summary"].get(key), value))
    for key, got, want in pairs:
        checked += 1
        if same(got, want):
            correct += 1
        else:
            print(f"  {img.name} {key}: expected {want!r}, got {got!r}")

    # item recall: checks if OCR read each item's price, and the words of its name
    flat = squash(" ".join(lines))
    ocr_words = set(re.findall(r"[a-z0-9]+", " ".join(lines).lower()))
    for item in expected.get("items", []):
        items_total += 1
        prices_found += f"{item['total_price']:.2f}".replace(".", "") in flat
        words = [w for w in re.findall(r"[a-z0-9]+", str(item["name"]).lower()) if len(w) > 2]
        hit = sum(w in ocr_words for w in words)
        name_words_total += len(words)
        name_words_found += hit
        if words and hit / len(words) >= 0.6:   # name counts as read if 60%+ of its words are there
            names_found += 1
        else:
            print(f"  {img.name} item name mostly missing: {item['name'][:60]!r}")

    print(f"{img.name}: {seconds:.2f}s")

# summary report
times.sort()
summary = {
    "size": {"model_files_mb": round(model_mb, 1)},
    "speed": {
        "model_load_s": round(load_time, 2),
        "receipts": len(times),
        "avg_s_per_receipt": round(sum(times) / len(times), 2),
        "median_s": round(times[len(times) // 2], 2),
        "slowest_s": round(times[-1], 2),
    },
    "accuracy": {
        "fields_correct": f"{correct}/{checked} ({correct / checked:.0%})",
    },
}
if items_total:
    summary["accuracy"].update({
        "item_prices_read": f"{prices_found}/{items_total} ({prices_found / items_total:.0%})",
        "item_names_read": f"{names_found}/{items_total} ({names_found / items_total:.0%})",
        "item_name_words_read": f"{name_words_found}/{name_words_total} "
                                f"({name_words_found / max(name_words_total, 1):.0%})",
    })
(OUTPUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
print(json.dumps(summary, indent=2))