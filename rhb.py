import pdfplumber
import pytesseract
from PIL import Image
import regex as re
import pandas as pd
import os

# ===============================
# CONFIG & HELPERS
# ===============================
TEMP_DIR = "temp_ocr_images"
os.makedirs(TEMP_DIR, exist_ok=True)

def num(s):
    """
    Converts a string number with commas to float.
    Returns 0.0 if empty or None.
    """
    if not s:
        return 0.0
    try:
        # Remove commas and convert to float
        clean_s = s.replace(",", "").strip()
        if clean_s == "" or clean_s == "-":
            return 0.0
        return float(clean_s)
    except ValueError:
        return 0.0

def extract_text(page, page_num):
    """
    Extracts text from a page. Uses standard extraction first.
    If empty, falls back to OCR (Tesseract).
    """
    text = page.extract_text()
    if text and text.strip() != "":
        return text

    # OCR fallback
    img_path = f"{TEMP_DIR}/page_{page_num}.png"
    # Render page to image (resolution=300 is standard for OCR)
    page.to_image(resolution=300).save(img_path)
    
    # Perform OCR
    ocr_text = pytesseract.image_to_string(Image.open(img_path))
    
    # Cleanup temp image
    try:
        os.remove(img_path)
    except OSError:
        pass
        
    return ocr_text

def preprocess_rhb_text(text):
    """
    Merges multi-line descriptions.
    RHB transactions usually start with a Date (DD-MM-YYYY).
    """
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()
        if not line:
            continue

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
# REGEX PATTERN
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

def parse_transactions(text, page_num):
    """
    Parses the preprocessed text using regex and returns a list of dicts.
    """
    text = preprocess_rhb_text(text)
    txns = []

    for m in txn_pattern.finditer(text):
        # Extract raw groups
        dr_str = m.group("dr")
        cr_str = m.group("cr")
        bal_str = m.group("bal")
        body = m.group("body").strip() if m.group("body") else ""

        # Convert numbers
        dr_val = num(dr_str)
        cr_val = num(cr_str)
        bal_val = num(bal_str)

        # Handle 'dr_flag' if present (though RHB usually puts negative in balance)
        if m.group("dr_flag") == "-":
            dr_val = -abs(dr_val)

        # App logic expects positive values for Debit/Credit columns usually,
        # but if your logic requires negative debits, remove the abs().
        # Based on your app.py summary logic: debit and credit sums are usually positive.
        
        txns.append({
            "date": m.group("date"),
            "description": body,
            "debit": abs(dr_val),
            "credit": abs(cr_val),
            "balance": bal_val,
            "page": page_num
        })

    return txns

# ===============================
# MAIN EXTRACTOR
# ===============================
def extract_rhb(pdf_path):
    """
    Main entry point called by app.py.
    """
    all_txns = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                raw = extract_text(page, page_num)
                if not raw:
                    continue
                    
                txns = parse_transactions(raw, page_num)
                all_txns.extend(txns)
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return pd.DataFrame() # Return empty DF on failure

    # Convert to DataFrame
    df = pd.DataFrame(all_txns)
    
    if df.empty:
        return df

    # Ensure columns are correct types for app.py
    # app.py expects: date, debit, credit, balance
    # (description is good for display)
    
    return df
