import pdfplumber
import pytesseract
from PIL import Image
import regex as re
import os

# =====================================================================
# TEMP DIRECTORY FOR OCR
# =====================================================================
TEMP_DIR = "temp_ocr_images"
os.makedirs(TEMP_DIR, exist_ok=True)


# =====================================================================
# SAFE NUMERIC CLEANER
# =====================================================================
def num(x):
    if x is None:
        return 0.0
    x = str(x).strip()

    if x in ["", "-", "--"]:
        return 0.0

    # remove commas, plus or minus trailing symbols
    x = x.replace(",", "").replace(" ", "").replace("+", "").replace("−", "-")

    try:
        return float(x)
    except:
        return 0.0


# =====================================================================
# TEXT EXTRACTION (WITH OCR FALLBACK)
# =====================================================================
def extract_text(page, page_num):
    text = page.extract_text()
    if text and text.strip():
        return text

    # OCR fallback if pdfplumber can't extract text
    img_path = f"{TEMP_DIR}/rhb_page_{page_num}.png"
    page.to_image(resolution=300).save(img_path)
    return pytesseract.image_to_string(Image.open(img_path))


# =====================================================================
# MERGE WRAPPED LINES (CRITICAL FOR RHB)
# =====================================================================
def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()

        # New transaction always starts with DD-MM-YYYY
        if re.match(r"^\d{2}-\d{2}-\d{4}", line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return "\n".join(merged)


# =====================================================================
# UNIVERSAL RHB TRANSACTION PATTERN (MOST ACCURATE VERSION)
# =====================================================================
txn_pattern = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})          # Date: 01-07-2025
    \s+
    (?P<body>.*?)                        # Description, greedy
    \s+
    (?P<dr>[0-9,]*\.\d{2})?              # Debit (optional)
    \s*
    (?P<dr_flag>-)?
    \s*
    (?P<cr>[0-9,]*\.\d{2})?              # Credit (optional)
    \s+
    (?P<bal>-?[0-9,]*\.\d{2}[+-]?)       # Balance (sign optional)
    """,
    re.VERBOSE | re.DOTALL
)


# =====================================================================
# MAIN PARSER (CALLED BY app.py)
# =====================================================================
def parse_transactions_rhb(text, page_num):

    if not text:
        return []

    text = preprocess_rhb_text(text)
    txns = []

    for m in txn_pattern.finditer(text):

        dr_val = num(m.group("dr"))
        cr_val = num(m.group("cr"))
        bal_val = num(m.group("bal"))
        body = m.group("body").strip()

        txns.append({
            "date": m.group("date"),
            "description": body,
            "debit": dr_val,
            "credit": cr_val,
            "balance": bal_val,
            "page": page_num
        })

    return txns


# =====================================================================
# PROCESS ENTIRE PDF (for manual testing)
# =====================================================================
def process_rhb_pdf(path):
    all_tx = []

    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw = extract_text(page, page_num)
            tx = parse_transactions_rhb(raw, page_num)
            all_tx.extend(tx)

    return all_tx
