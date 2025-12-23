import pdfplumber
import fitz  # PyMuPDF
import pandas as pd
import re
from datetime import datetime

# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================
def extract_maybank(pdf_path):
    """
    Universal Maybank Parser.
    1. Tries CWS Strategy (Corporate/Business - Text Regex).
    2. If empty, falls back to Mytutor Strategy (Personal - Coordinate/PyMuPDF).
    """
    # 1. Try CWS Strategy
    try:
        df = _parse_cws(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"CWS Strategy skipped: {e}")

    # 2. Try Mytutor Strategy
    try:
        df = _parse_mytutor(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"Mytutor Strategy skipped: {e}")

    # 3. Return Empty if both fail
    return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])

# ==============================================================================
# STRATEGY 1: CWS (Business/Corporate)
# ==============================================================================
def _parse_cws(pdf_path):
    # Regex for "01 Mar 2025"
    DATE_PATTERN = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}") 
    # Amount + sign + balance: "78.00 - 47,272.76"
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
                    
                    # Search for Amount/Balance pattern
                    m = AMOUNT_PATTERN.search(line)
                    if not m:
                        current_txn = None 
                        continue

                    # Extract numbers
                    amount = float(m.group(1).replace(",", ""))
                    sign = m.group(2)
                    balance = float(m.group(3).replace(",", ""))

                    if sign == "-":
                        debit = amount
                        credit = 0.0
                    else:
                        credit = amount
                        debit = 0.0

                    desc_text = line[:m.start()].strip()

                    current_txn = {
                        "date": line[:11],
                        "description": "",
                        "debit": debit,
                        "credit": credit,
                        "balance": balance
                    }
                    desc_buffer.append(desc_text)
                else:
                    if current_txn:
                        desc_buffer.append(line)
    
    # Append last
    if current_txn:
        current_txn["description"] = " ".join(desc_buffer).strip()
        transactions.append(current_txn)
    
    df = pd.DataFrame(transactions)
    if not df.empty:
        # Normalize date to DD/MM/YYYY
        df["date"] = pd.to_datetime(df["date"], format="%d %b %Y", errors='coerce').dt.strftime('%d/%m/%Y')
        
    return df

# ==============================================================================
# STRATEGY 2: Mytutor (Personal/Savings)
# ==============================================================================
def _parse_mytutor(pdf_path):
    doc = fitz.open(pdf_path)
    
    # Detect Year
    statement_year = str(datetime.now().year)
    STATEMENT_DATE_RE = re.compile(r"STATEMENT\s+DATE\s*:?\s*(\d{2})/(\d{2})/(\d{2})")
    
    for p in range(min(2, len(doc))):
        txt = doc[p].get_text("text").upper()
        m = STATEMENT_DATE_RE.search(txt)
        if m:
            statement_year = f"20{m.group(3)}"
            break

    DATE_RE_A = re.compile(r"^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}|\d{2}-\d{2}|\d{2}\s+[A-Z]{3})$", re.IGNORECASE)
    AMOUNT_RE_A = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)?\.\d{2}[+-]?$")

    transactions = []
    processed_y = set()
    previous_balance = None

    for page in doc:
        words = page.get_text("words")
        # Extract rows
        rows = [{"x0": w[0], "y0": w[1], "text": str(w[4]).strip()} for w in words if str(w[4]).strip()]
        rows.sort(key=lambda r: (round(r["y0"], 1), r["x0"]))

        for r in rows:
            token = r["text"]
            if not DATE_RE_A.match(token): continue
            
            y_ref = round(r["y0"], 1)
            if any(abs(y - y_ref) < 0.5 for y in processed_y): continue 

            line = [w for w in rows if abs(w["y0"] - r["y0"]) <= 2.0]
            line.sort(key=lambda w: w["x0"])

            amounts = []
            desc_parts = []
            for w in line:
                if w["text"] == token: continue 
                if AMOUNT_RE_A.match(w["text"]):
                    amounts.append((w["x0"], w["text"]))
                else:
                    desc_parts.append(w["text"])
            
            if not amounts: continue

            def parse_val(s):
                clean = s.replace(",", "").replace("CR","").replace("DR","")
                sign = "+" if clean.endswith("+") else "-" if clean.endswith("-") else ""
                clean = clean.rstrip("+-")
                try: v = float(clean)
                except: v = 0.0
                return v, sign

            amounts.sort(key=lambda a: a[0])
            balance_val, _ = parse_val(amounts[-1][1])
            
            txn_val = 0.0
            txn_sign = ""
            if len(amounts) > 1:
                txn_val, txn_sign = parse_val(amounts[-2][1])
            
            debit = 0.0
            credit = 0.0
            
            if txn_sign == "-": debit = txn_val
            elif txn_sign == "+": credit = txn_val
            else:
                if previous_balance is not None:
                    delta = round(balance_val - previous_balance, 2)
                    if delta < 0: debit = abs(delta)
                    elif delta > 0: credit = abs(delta)
                    else: debit = txn_val 
                else:
                    debit = txn_val

            previous_balance = balance_val
            processed_y.add(y_ref)
            
            date_display = token
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
