import pdfplumber
import pytesseract
from PIL import Image
import regex as re
import pandas as pd
import os
import tempfile

# Temporary directory for OCR images
TEMP_DIR = tempfile.gettempdir()

def num(s):
    """Convert string to float, handling commas and signs."""
    if not s or s == "":
        return 0.0
    s = str(s).strip()
    # Remove trailing +/- signs
    s = re.sub(r'[+-]$', '', s)
    # Remove commas
    s = s.replace(',', '')
    # Handle negative sign
    if s.startswith('-'):
        return -float(s[1:])
    try:
        return float(s)
    except:
        return 0.0

def extract_text(page, page_num):
    """Extract text from page, with OCR fallback."""
    text = page.extract_text()
    if text and text.strip() != "":
        return text
    
    # OCR fallback
    img_path = os.path.join(TEMP_DIR, f"rhb_page_{page_num}.png")
    try:
        page.to_image(resolution=300).save(img_path)
        ocr_text = pytesseract.image_to_string(Image.open(img_path))
        # Clean up temp file
        if os.path.exists(img_path):
            os.remove(img_path)
        return ocr_text
    except Exception as e:
        print(f"OCR failed for page {page_num}: {e}")
        return ""

def preprocess_rhb_text(text):
    """Merge broken lines that belong to the same transaction."""
    lines = text.split("\n")
    merged = []
    buffer = ""
    
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

# Transaction pattern for RHB statements
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
    """Parse transactions from preprocessed text."""
    text = preprocess_rhb_text(text)
    txns = []
    
    for m in txn_pattern.finditer(text):
        # Safe extraction
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
            "debit": dr_val if dr_val > 0 else 0.0,
            "credit": cr_val if cr_val > 0 else 0.0,
            "balance": bal_val,
            "page": page_num
        })
    
    return txns

def extract_rhb(pdf_path):
    """
    Main extraction function for RHB bank statements.
    Returns a pandas DataFrame with columns: date, description, debit, credit, balance.
    """
    all_txns = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                raw = extract_text(page, page_num)
                processed = preprocess_rhb_text(raw)
                txns = parse_transactions(processed, page_num)
                all_txns.extend(txns)
        
        if not all_txns:
            print(f"Warning: No transactions found in {pdf_path}")
            return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])
        
        # Convert to DataFrame
        df = pd.DataFrame(all_txns)
        
        # Drop the 'page' column if present (not needed in final output)
        if 'page' in df.columns:
            df = df.drop(columns=['page'])
        
        # Ensure correct column order
        df = df[["date", "description", "debit", "credit", "balance"]]
        
        print(f"RHB extraction complete: {len(df)} transactions")
        return df
    
    except Exception as e:
        print(f"Error extracting RHB statement from {pdf_path}: {e}")
        return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])
