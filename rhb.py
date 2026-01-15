import pdfplumber
import pytesseract
from PIL import Image
import regex as re
import json
import os
import pandas as pd

# ===============================
# CONFIG & HELPERS
# ===============================
TEMP_DIR = "temp_ocr_images"
os.makedirs(TEMP_DIR, exist_ok=True)

def num(s):
    """
    Helper to convert string to float (Handles commas and empty values).
    Required because parse_transactions calls 'num(dr)'.
    """
    if not s:
        return 0.0
    try:
        clean = str(s).replace(",", "").strip()
        if not clean or clean == "-":
            return 0.0
        return float(clean)
    except:
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

# ===============================
# REGEX PATTERN (EXACTLY AS PROVIDED)
# ===============================
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

# ===============================
# PARSING LOGIC
# ===============================
def parse_transactions(text, page_num):
    text = preprocess_rhb_text(text)
    txns = []

    for m in txn_pattern.finditer(text):
        
        # SAFE extraction
        body = m.group("body").strip() if m.group("body") else ""

        dr = m.group("dr")
        cr = m.group("cr")
        bal = m.group("bal")

        dr_val = num(dr) if dr else 0.0
        cr_val = num(cr) if cr else 0.0
        bal_val = num(bal) if bal else 0.0

        txns.append({
            "date": m.group("date"),
            "description": body,
            "debit": dr_val,
            "credit": cr_val,
            "balance": bal_val,
            "page": page_num
        })

    return txns

# ===============================
# WRAPPER FOR APP.PY
# ===============================
def extract_rhb(pdf_path):
    """
    Main entry point used by app.py
    """
    all_txns = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages):
                # 1. Get Text
                raw_text = extract_text(page, i+1)
                
                # 2. Parse using your logic
                page_txns = parse_transactions(raw_text, i+1)
                
                all_txns.extend(page_txns)
    except Exception as e:
        print(f"Error processing RHB: {e}")
        return pd.DataFrame()

    return pd.DataFrame(all_txns)
