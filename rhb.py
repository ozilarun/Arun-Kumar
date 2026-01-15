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
    """Converts string number to float, handling commas and empty strings."""
    if not s:
        return 0.0
    try:
        # Remove commas and convert to float
        clean = s.replace(",", "").strip()
        if not clean or clean == "-":
            return 0.0
        return float(clean)
    except ValueError:
        return 0.0

def extract_text(page, page_num):
    """Extracts text, falls back to OCR if empty."""
    text = page.extract_text()
    if text and text.strip():
        return text

    # OCR Fallback
    img_path = f"{TEMP_DIR}/page_{page_num}.png"
    page.to_image(resolution=300).save(img_path)
    text = pytesseract.image_to_string(Image.open(img_path))
    
    # Clean up temp image
    try:
        os.remove(img_path)
    except:
        pass
        
    return text

def preprocess_rhb_text(text):
    """Merges wrapped lines. RHB lines start with Date."""
    lines = text.split("\n")
    merged, buffer = [], ""

    # RHB Date format: DD/MM/YYYY or DD-MM-YYYY
    date_start_pattern = re.compile(r"^\d{2}[/-]\d{2}[/-]\d{4}")

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if date_start_pattern.match(line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return "\n".join(merged)

# ===============================
# ROBUST PARSING LOGIC
# ===============================
def parse_transactions(text, page_num):
    text = preprocess_rhb_text(text)
    txns = []

    # Regex to capture the Date and the "Rest of the line"
    line_pattern = re.compile(r"^(?P<date>\d{2}[/-]\d{2}[/-]\d{4})\s+(?P<rest>.*)$")

    for line in text.split('\n'):
        m = line_pattern.match(line)
        if not m:
            continue

        date_str = m.group("date")
        rest = m.group("rest")

        # 1. FIND ALL NUMBERS IN THE LINE
        # This regex catches amounts like "1,234.56" or "50.00"
        amounts = re.findall(r"([\d,]+\.\d{2})", rest)
        
        if not amounts:
            continue

        # 2. IDENTIFY BALANCE (Always the last number)
        raw_balance = amounts[-1]
        bal_val = num(raw_balance)

        # 3. CHECK FOR NEGATIVE/OD BALANCE
        # RHB indicates OD with a trailing '-' or 'OD' or 'Dr' immediately after the number
        safe_bal_str = re.escape(raw_balance)
        
        # Check if the text *after* the balance contains negative indicators
        if re.search(f"{safe_bal_str}\s*[-]", rest) or \
           re.search(f"{safe_bal_str}\s*OD", rest) or \
           re.search(f"{safe_bal_str}\s*Dr", rest, re.IGNORECASE):
            bal_val = -abs(bal_val)  # Force negative
        else:
            bal_val = abs(bal_val)   # Force positive (unless explicit negative found)

        # 4. IDENTIFY TRANSACTION AMOUNT (Debit vs Credit)
        dr_val = 0.0
        cr_val = 0.0
        description = rest.split(raw_balance)[0].strip() # Text before balance

        # If we have 2 numbers found: [Amount, Balance]
        if len(amounts) >= 2:
            txn_amt_str = amounts[-2] 
            txn_val = num(txn_amt_str)
            
            # Remove the amount from description to clean it up
            description = description.replace(txn_amt_str, "").strip()

            # HEURISTIC: DECIDE IF DEBIT OR CREDIT
            # Since extracted text loses column position, we use keywords.
            desc_upper = description.upper()
            
            # Keywords that definitely mean CREDIT (Inflow)
            credit_keywords = [
                "DEPOSIT", "CREDIT", "TRF FR", "TRANSFER FROM", 
                "D/D", "REVERSAL", "DIVIDEND", "INTEREST"
            ]
            
            if any(k in desc_upper for k in credit_keywords):
                cr_val = txn_val
            else:
                # Default to DEBIT for everything else (Withdrawal, Cheque, Payment, Fee)
                dr_val = txn_val

        txns.append({
            "date": date_str,
            "description": description if description else "Transaction",
            "debit": dr_val,
            "credit": cr_val,
            "balance": bal_val,
            "page": page_num
        })

    return txns

def extract_rhb(pdf_path):
    all_txns = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                raw = extract_text(page, i)
                txns = parse_transactions(raw, i)
                all_txns.extend(txns)
    except Exception as e:
        print(f"Error processing {pdf_path}: {e}")
        return pd.DataFrame()

    df = pd.DataFrame(all_txns)
    return df
