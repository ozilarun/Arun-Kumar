import pdfplumber
import fitz  # PyMuPDF
import pandas as pd
import re
from datetime import datetime

# ==============================================================================
# MAIN ENTRY POINT (Called by app.py)
# ==============================================================================
def extract_maybank(pdf_path):
    """
    Universal Maybank Parser.
    1. Tries CWS Strategy first (Corporate/Business - Text Regex).
    2. If empty, falls back to Mytutor Strategy (Personal/Savings - Coordinate/PyMuPDF).
    """
    # 1. Try CWS Strategy
    try:
        df = _parse_cws(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"CWS Strategy skipped: {e}")

    # 2. Try Mytutor Strategy (Fallback)
    try:
        df = _parse_mytutor(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"Mytutor Strategy skipped: {e}")

    # 3. Return Empty if both fail
    return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])


# ==============================================================================
# STRATEGY 1: CWS (From your 'MAYBANK CODE CWS' file)
# ==============================================================================
def _parse_cws(pdf_path):
    # Regex from your doc
    DATE_PATTERN = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}") # e.g., 01 Mar 2025
    # Amount + sign + balance pattern: "78.00 - 47,272.76"
    AMOUNT_PATTERN = re.compile(r'([0-9,]+\.\d{2})\s*([+-])\s*([0-9,]+\.\d{2})')

    transactions = []
    current_txn = None
    desc_buffer = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            
            lines = text.split("\n")
            
            for raw_line in lines:
                line = raw_line.strip()
                if not line: continue

                # Check for Date at start
                if DATE_PATTERN.match(line):
                    # Save previous if exists
                    if current_txn:
                        current_txn["description"] = " ".join(desc_buffer).strip()
                        transactions.append(current_txn)
                    
                    desc_buffer = []
                    
                    # Search for Amount/Balance pattern in this line
                    m = AMOUNT_PATTERN.search(line)
                    if not m:
                        # Date found but no numbers? Reset and continue
                        current_txn = None 
                        continue

                    # Extract numbers
                    amt_str = m.group(1).replace(",", "")
                    sign = m.group(2)
                    bal_str = m.group(3).replace(",", "")

                    amount = float(amt_str)
                    balance = float(bal_str)

                    # Logic for Debit/Credit based on Sign
                    if sign == "-":
                        debit = amount
                        credit = 0.0
                    else:
                        credit = amount
                        debit = 0.0

                    # Description is text before the amount pattern
                    desc_text = line[:m.start()].strip()

                    current_txn = {
                        "date": line[:11], # Capture the date string part
                        "description": "",
                        "debit": debit,
                        "credit": credit,
                        "balance": balance
                    }
                    desc_buffer.append(desc_text)
                
                else:
                    # Continuation line for description
                    if current_txn:
                        desc_buffer.append(line)
    
    # Append last transaction
    if current_txn:
        current_txn["description"] = " ".join(desc_buffer).strip()
        transactions.append(current_txn)
    
    df = pd.DataFrame(transactions)
    if not df.empty:
        # Normalize date to DD/MM/YYYY
        df["date"] = pd.to_datetime(df["date"], format="%d %b %Y", errors='coerce').dt.strftime('%d/%m/%Y')
        
    return df


# ==============================================================================
# STRATEGY 2: Mytutor (From your 'Maybank Mytutor code' file)
# ==============================================================================
def _parse_mytutor(pdf_path):
    doc = fitz.open(pdf_path)
    
    # 1. Detect Year
    statement_year = str(datetime.now().year)
    STATEMENT_DATE_RE = re.compile(r"STATEMENT\s+DATE\s*:?\s*(\d{2})/(\d{2})/(\d{2})")
    
    # Scan first 2 pages for year
    for p in range(min(2, len(doc))):
        txt = doc[p].get_text("text").upper()
        m = STATEMENT_DATE_RE.search(txt)
        if m:
            statement_year = f"20{m.group(3)}"
            break

    # 2. Setup Regex
    DATE_RE_A = re.compile(r"^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}|\d{2}-\d{2}|\d{2}\s+[A-Z]{3})$", re.IGNORECASE)
    AMOUNT_RE_A = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)?\.\d{2}[+-]?$")

    transactions = []
    processed_y = set()
    previous_balance = None

    for page in doc:
        words = page.get_text("words")
        # Extract rows based on Y coordinates
        rows = [{"x0": w[0], "y0": w[1], "text": str(w[4]).strip()} for w in words if str(w[4]).strip()]
        rows.sort(key=lambda r: (round(r["y0"], 1), r["x0"]))

        for r in rows:
            token = r["text"]
            # Check if token matches Date regex
            if not DATE_RE_A.match(token): continue
            
            y_ref = round(r["y0"], 1)
            # Skip if we already processed this Y-line
            if any(abs(y - y_ref) < 0.5 for y in processed_y): continue 

            # Gather all words on this line (tolerance 2.0)
            line = [w for w in rows if abs(w["y0"] - r["y0"]) <= 2.0]
            line.sort(key=lambda w: w["x0"])

            # Separate Amounts from Description
            amounts = []
            desc_parts = []
            for w in line:
                if w["text"] == token: continue # Skip the date token itself
                if AMOUNT_RE_A.match(w["text"]):
                    amounts.append((w["x0"], w["text"]))
                else:
                    desc_parts.append(w["text"])
            
            if not amounts: continue

            # Helper to parse "1,000.00+" or "1,000.00CR"
            def parse_val(s):
                clean = s.replace(",", "").replace("CR","").replace("DR","")
                sign = "+" if clean.endswith("+") else "-" if clean.endswith("-") else ""
                clean = clean.rstrip("+-")
                try: v = float(clean)
                except: v = 0.0
                return v, sign

            # Last amount is typically Balance
            amounts.sort(key=lambda a: a[0])
            balance_val, _ = parse_val(amounts[-1][1])
            
            # 2nd last is Transaction Amount
            txn_val = 0.0
            txn_sign = ""
            if len(amounts) > 1:
                txn_val, txn_sign = parse_val(amounts[-2][1])
            
            # Logic: Debit vs Credit
            debit = 0.0
            credit = 0.0
            
            # Logic A: Explicit Sign in Text
            if txn_sign == "-": debit = txn_val
            elif txn_sign == "+": credit = txn_val
            else:
                # Logic B: Math Check (Delta from previous balance)
                if previous_balance is not None:
                    delta = round(balance_val - previous_balance, 2)
                    if delta < 0: debit = abs(delta)
                    elif delta > 0: credit = abs(delta)
                    else: debit = txn_val # Fallback
                else:
                    # Logic C: First row fallback
                    debit = txn_val # Default assumption

            previous_balance = balance_val
            processed_y.add(y_ref)
            
            # Format Date for display
            date_display = token
            # Try to fix partial dates (DD/MM) using found year
            if len(token) <= 5 and "/" in token:
                 try:
                     dt = datetime.strptime(f"{token}/{statement_year}", "%d/%m/%Y")
                     date_display = dt.strftime("%d/%m/%Y")
                 except: pass

            transactions.append({
                "date": date_display,
                "description": " ".join(desc_parts),
                "debit": debit,
                "credit": credit,
                "balance": balance_val
            })

    return pd.DataFrame(transactions)
