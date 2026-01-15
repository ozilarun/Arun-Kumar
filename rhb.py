import pdfplumber
import pytesseract
from PIL import Image
import regex as re
import json
import os
import pandas as pd

# ==========================================
# CONFIG & HELPERS
# ==========================================

TEMP_DIR = "temp_ocr_images"
os.makedirs(TEMP_DIR, exist_ok=True)

# [ADDED] Helper function required by parse_transactions
def num(s):
    """Converts string with commas to float. Returns 0.0 if empty/None."""
    if not s:
        return 0.0
    try:
        return float(str(s).replace(",", "").strip())
    except ValueError:
        return 0.0

def extract_text(page, page_num):
    text = page.extract_text()
    if text and text.strip() != "":
        return text

    # OCR fallback
    img_path = f"{TEMP_DIR}/page_{page_num}.png"
    page.to_image(resolution=300).save(img_path)
    return pytesseract.image_to_string(Image.open(img_path))

def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()

        # All transactions begin with DD-MM-YYYY
        if re.match(r"^\d{2}-\d{2}-\d{4}", line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return "\n".join(merged)

# ==========================================
# REGEX PATTERN
# ==========================================

txn_pattern = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})     # Date
    
    \s+
    
    (?P<body>.*?)                   # Everything until DR/CR
    
    \s+
    
    (?P<dr>[0-9,]*\.\d{2})?         # Debit (optional)
    \s*
    (?P<dr_flag>-)?
    \s*
    
    (?P<cr>[0-9,]*\.\d{2})?         # Credit (optional)
    \s+
    
    (?P<bal>-?[0-9,]*\.\d{2}[+-]?)  # Final Balance
    
    """,
    re.VERBOSE | re.DOTALL
)

# ==========================================
# PARSING LOGIC
# ==========================================

def parse_transactions(text, page_num):
    text = preprocess_rhb_text(text)

    txns = []

    for m in txn_pattern.finditer(text):

        dr_val = num(m.group("dr"))
        cr_val = num(m.group("cr"))
        bal_val = num(m.group("bal"))

        # description cleanup
        body = m.group("body").strip()

        # remove trailing sender ref if it's obviously numeric-only  
        # (not required, but cleans some lines)
    
        txns.append({
            "date": m.group("date"),
            "description": body,
            "debit": dr_val if dr_val > 0 else 0.0,
            "credit": cr_val if cr_val > 0 else 0.0,
            "balance": bal_val,
            "page": page_num
        })

    return txns

# ==========================================
# MAIN PROCESSOR
# ==========================================

def process_rhb_pdf(PDF_PATH):
    all_txns = []

    print("Processing:", PDF_PATH)

    with pdfplumber.open(PDF_PATH) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            print(f"Page {page_num}/{len(pdf.pages)}")

            raw = extract_text(page, page_num)   # your OCR fallback
            processed = preprocess_rhb_text(raw)
            txns = parse_transactions(processed, page_num)

            all_txns.extend(txns)

    print("Total transactions extracted:", len(all_txns))
    return all_txns

# ==========================================
# APP INTEGRATION WRAPPER
# ==========================================
def extract_rhb(pdf_path):
    """
    Wrapper function to make the script compatible with app.py
    """
    try:
        # Run your exact processing logic
        txns = process_rhb_pdf(pdf_path)
        
        # Convert list of dicts to DataFrame for the app
        df = pd.DataFrame(txns)
        return df
    except Exception as e:
        print(f"Error in extract_rhb: {e}")
        return pd.DataFrame()
