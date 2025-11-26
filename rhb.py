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
# NUMERIC CLEANER
# =====================================================================
def num(x):
    if not x or x.strip() == "":
        return 0.0
    return float(x.replace(",", ""))


# =====================================================================
# OCR + TEXT EXTRACTION
# =====================================================================
def extract_text(page, page_num):
    text = page.extract_text()
    if text and text.strip():
        return text

    # OCR fallback
    img_path = f"{TEMP_DIR}/page_{page_num}.png"
    page.to_image(resolution=300).save(img_path)
    return pytesseract.image_to_string(Image.open(img_path))


# =====================================================================
# MERGE RHB WRAPPED LINES
# =====================================================================
def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()

        # START OF RHB transaction → DD-MM-YYYY
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
# EXACT WORKING REGEX PATTERN (from notebook)
# =====================================================================
txn_pattern = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})      # Date
    \s+
    (?P<body>.*?)                    # Description until DR/CR
    \s+
    (?P<dr>[0-9,]*\.\d{2})?          # Debit (opt)
    \s*
    (?P<dr_flag>-)?
    \s*
    (?P<cr>[0-9,]*\.\d{2})?          # Credit (opt)
    \s+
    (?P<bal>-?[0-9,]*\.\d{2}[+-]?)   # Running balance
    """,
    re.VERBOSE | re.DOTALL
)


# =====================================================================
# PARSE TRANSACTIONS — EXACT MATCH WITH NOTEBOOK
# =====================================================================
def parse_transactions_rhb(text, page_num):

    text = preprocess_rhb_text(text)
    txns = []

    for m in txn_pattern.finditer(text):

        dr = m.group("dr")
        cr = m.group("cr")
        bal = m.group("bal")

        dr_val = num(dr) if dr else 0.0
        cr_val = num(cr) if cr else 0.0
        bal_val = num(bal) if bal else 0.0

        body = m.group("body").strip()

        txns.append({
            "date": m.group("date"),
            "description": body,
            "debit": dr_val if dr_val > 0 else 0.0,
            "credit": cr_val if cr_val > 0 else 0.0,
            "balance": bal_val,
            "page": page_num
        })

    return txns


# =====================================================================
# PROCESS PDF — CALLED BY NOTEBOOK (NOT USED IN STREAMLIT)
# =====================================================================
def process_rhb_pdf(path):
    all_tx = []
    with pdfplumber.open(path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw = extract_text(page, page_num)
            txns = parse_transactions_rhb(raw, page_num)
            all_tx.extend(txns)
    return all_tx
