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
    Universal Maybank Extractor.
    Attempts two strategies:
    1. CWS Strategy (Text-based, typical for Corporate/Business with specific ID)
    2. Mytutor Strategy (Coordinate-based, typical for Statements with irregular columns)
    """
    # 1. Try CWS Strategy
    try:
        df = _parse_cws_strategy(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"CWS Strategy failed: {e}")

    # 2. Try Mytutor Strategy (Fallback)
    try:
        df = _parse_mytutor_strategy(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        print(f"Mytutor Strategy failed: {e}")

    # 3. Return empty if both fail
    return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])

# ==============================================================================
# STRATEGY 1: CWS (Corporate/Business - Text Regex)
# ==============================================================================
def _parse_cws_strategy(pdf_path):
    DATE_PATTERN = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}") # e.g., 01 Mar 2025
    # Amount pattern: "1,234.56 + 5,000.00" (Amount Sign Balance)
    AMOUNT_PATTERN = re.compile(r'([0-9,]+\.\d{2})\s*([+-])\s*([0-9,]+\.\d{2})')
    
    txns = []
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

                # Detect start of transaction (Date)
                if DATE_PATTERN.match(line):
                    # Save previous transaction
                    if current_txn:
                        current_txn["description"] = " ".join(desc_buffer).strip()
                        txns.append(current_txn)
                    
                    desc_buffer = [] # Reset

                    # Search for Amount/Balance pattern in this line
                    m = AMOUNT_PATTERN.search(line)
                    if not m:
                        continue # Date found but no numbers, skip

                    # Extract numbers
                    amt = float(m.group(1).replace(",", ""))
                    sign = m.group(2)
                    bal = float(m.group(3).replace(",", ""))

                    debit = amt if sign == "-" else 0.0
                    credit = amt if sign == "+" else 0.0

                    # Description is usually before the numbers
                    desc_text = line[:m.start()].strip()

                    current_txn = {
                        "date": line[:11], # Keep raw date for now
                        "description": "",
                        "debit": debit,
                        "credit": credit,
                        "balance": bal
                    }
                    desc_buffer.append(desc_text)
                
                else:
                    # Continuation of description
                    if current_txn:
                        desc_buffer.append(line)
    
    # Append last transaction
    if current_txn:
        current_txn["description"] = " ".join(desc_buffer).strip()
        txns.append(current_txn)

    df = pd.DataFrame(txns)
    if df.empty: return None

    # Post-process Date
    df["date"] = pd.to_datetime(df["date"], errors='coerce').dt.strftime('%d/%m/%Y')
    return df

# ==============================================================================
# STRATEGY 2: Mytutor (Coordinate/PyMuPDF - Complex Layouts)
# ==============================================================================
def _parse_mytutor_strategy(pdf_path):
    doc = fitz.open(pdf_path)
    
    # 1. Detect Year
    statement_year = "2025" # Default
    STATEMENT_DATE_RE = re.compile(r"STATEMENT\s+DATE\s*:?\s*(\d{2})/(\d{2})/(\d{2})")
    
    # Scan first 2 pages for year
    for p in range(min(2, len(doc))):
        txt = doc[p].get_text("text").upper()
        m = STATEMENT_DATE_RE.search(txt)
        if m:
            statement_year = f"20{m.group(3)}"
            break

    # 2. Regex Helpers
    DATE_RE_A = re.compile(r"^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}|\d{2}-\d{2}|\d{2}\s+[A-Z]{3})$", re.IGNORECASE)
    AMOUNT_RE_A = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)?\.\d{2}[+-]?$")

    def norm_date(token, year):
        token = token.strip().upper()
        formats = [
            ("%d/%m/%Y", None),
            ("%d/%m", f"/%Y"), 
            ("%d-%m", f"-%Y"), 
            ("%d %b", f" %Y")
        ]
        
        for fmt, suffix in formats:
            try:
                parse_str = token + ("/" + year if suffix else "")
                parse_fmt = fmt + (suffix if suffix else "")
                if suffix: # Adjust parse string for suffix logic
                     parse_str = token + "/" + year
                     parse_fmt = fmt + "/%Y"
                
                # Simplified date parsing
                if fmt == "%d/%m/%Y":
                    dt = datetime.strptime(token, fmt)
                else:
                    dt = datetime.strptime(f"{token}/{year}", fmt + "/%Y")
                return dt.strftime("%Y-%m-%d")
            except:
                continue
        return None

    def parse_amt(t):
        t = t.strip()
        sign = "+" if t.endswith("+") else "-" if t.endswith("-") else None
        # Clean cleanup
        clean_t = t.replace(",", "").replace("CR","").replace("DR","").rstrip("+-")
        try:
            v = float(clean_t)
        except:
            v = 0.0
        return v, sign

    transactions = []
    previous_balance = None
    processed_y = set()
    Y_TOL = 2.0 # Tolerance for same line

    for page in doc:
        words = page.get_text("words")
        # word structure: (x0, y0, x1, y1, text, block_no, line_no, word_no)
        # We need a dict list
        rows = [{"x0": w[0], "y0": w[1], "text": str(w[4]).strip()} for w in words if str(w[4]).strip()]
        rows.sort(key=lambda r: (round(r["y0"], 1), r["x0"]))

        for r in rows:
            token = r["text"]
            # Check if this token looks like a date
            if not DATE_RE_A.match(token): continue

            y_ref = r["y0"]
            y_bucket = round(y_ref, 1)
            
            # Avoid processing the same line twice
            if any(abs(y - y_bucket) < 0.5 for y in processed_y): continue

            # Get all words on this line
            line = [w for w in rows if abs(w["y0"] - y_ref) <= Y_TOL]
            line.sort(key=lambda w: w["x0"])

            # Verify date
            date_iso = norm_date(token, statement_year)
            if not date_iso: continue
            
            # Format date for display
            try:
                date_display = datetime.strptime(date_iso, "%Y-%m-%d").strftime("%d/%m/%Y")
            except:
                date_display = token

            # Extract content
            desc_parts = []
            amounts = []
            
            for w in line:
                if w["text"] == token: continue # Skip the date token itself
                if AMOUNT_RE_A.match(w["text"]):
                    amounts.append((w["x0"], w["text"]))
                else:
                    desc_parts.append(w["text"])

            if not amounts: continue

            # Sort amounts by X position (Balance is usually last)
            amounts.sort(key=lambda a: a[0])
            
            # Identify Balance (Last one)
            balance_val, _ = parse_amt(amounts[-1][1])
            
            # Identify Transaction Amount (2nd to last if exists)
            txn_val, txn_sign = 0.0, None
            if len(amounts) > 1:
                txn_val, txn_sign = parse_amt(amounts[-2][1])
            
            description = " ".join(desc_parts).strip()

            # Logic to determine Debit vs Credit
            debit, credit = 0.0, 0.0
            
            # Method A: Use math delta if we have previous balance
            if previous_balance is not None:
                delta = round(balance_val - previous_balance, 2)
                if delta > 0:
                    credit = abs(delta)
                elif delta < 0:
                    debit = abs(delta)
                else:
                    # No change? check explicit transaction value
                    if txn_sign == "+": credit = txn_val
                    elif txn_sign == "-": debit = txn_val
            else:
                # Method B: First row (no prev balance), rely on signs or keywords
                if txn_sign == "+": credit = txn_val
                elif txn_sign == "-": debit = txn_val
                else:
                    # Fallback keywords
                    if any(x in description.upper() for x in ["DEPOSIT", "TRANSFER FROM", "CREDIT"]):
                        credit = txn_val
                    else:
                        debit = txn_val # Assume debit by default for first row if unclear

            processed_y.add(y_bucket)
            previous_balance = balance_val

            transactions.append({
                "date": date_display,
                "description": description,
                "debit": debit,
                "credit": credit,
                "balance": balance_val
            })

    return pd.DataFrame(transactions)
