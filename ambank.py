import pdfplumber
import pandas as pd
import re

# ==========================
# HELPERS
# ==========================

MONTH_MAP = {
    "JAN": "January", "FEB": "February", "MAR": "March", "MAC": "March",
    "APR": "April", "MAY": "May", "JUN": "June", "JUL": "July",
    "AUG": "August", "SEP": "September", "SEPT": "September",
    "OCT": "October", "NOV": "November", "DEC": "December"
}

def parse_amount(s):
    if not s:
        return 0.0
    s = s.upper().replace(",", "").strip()
    neg = "DR" in s
    s = s.replace("DR", "").replace("CR", "")
    try:
        v = float(s)
        return -v if neg else v
    except:
        return 0.0

def clean_date(day, mon, year):
    return f"{day} {MONTH_MAP.get(mon.upper(), mon)} {year}"

# ==========================
# MAIN EXTRACTOR
# ==========================

def extract_ambank(pdf_path):
    rows = []
    current_tx = None
    prev_balance = None

    # Detect year from filename (fallback 2024)
    y = re.search(r"(20\d{2})", pdf_path)
    year = y.group(1) if y else "2024"

    date_start = re.compile(r"^(\d{2})([A-Za-z]{3})")

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                m = date_start.match(line)

                # ======================
                # NEW TRANSACTION LINE
                # ======================
                if m:
                    day, mon = m.groups()
                    parts = line.split()

                    nums = []
                    desc_parts = []

                    # scan from RIGHT → LEFT
                    for i in range(len(parts)-1, -1, -1):
                        if re.match(r"[\d,]+\.\d{2}[A-Za-z]*$", parts[i]):
                            nums.insert(0, parts[i])
                        else:
                            desc_parts = parts[:i+1]
                            break

                    description = " ".join(desc_parts[1:])
                    values = [parse_amount(x) for x in nums]

                    # Balance only line (Balance B/F)
                    if len(values) == 1:
                        prev_balance = values[0]
                        continue

                    if len(values) >= 2:
                        tx_amt = abs(values[0])
                        balance = values[-1]

                        debit = credit = 0.0

                        if prev_balance is not None:
                            diff = round(balance - prev_balance, 2)
                            if abs(diff - tx_amt) < 0.05:
                                credit = tx_amt
                            elif abs(diff + tx_amt) < 0.05:
                                debit = tx_amt
                            else:
                                # fallback
                                if any(k in description.upper() for k in ["CR", "CREDIT", "DEPOSIT", "INWARD"]):
                                    credit = tx_amt
                                else:
                                    debit = tx_amt
                        else:
                            if any(k in description.upper() for k in ["CR", "CREDIT", "DEPOSIT", "INWARD"]):
                                credit = tx_amt
                            else:
                                debit = tx_amt

                        current_tx = {
                            "date": clean_date(day, mon, year),
                            "description": description,
                            "debit": debit,
                            "credit": credit,
                            "balance": balance
                        }

                        rows.append(current_tx)
                        prev_balance = balance

                # ======================
                # CONTINUATION LINE
                # ======================
                else:
                    if current_tx:
                        if not re.search(r"\d+\.\d{2}", line) and \
                           "PAGE" not in line.upper() and \
                           "STATEMENT" not in line.upper():
                            current_tx["description"] += " " + line

    df = pd.DataFrame(rows)

    # ======================
    # NO TRANSACTIONS CASE
    # ======================
    if df.empty:
        opening_balance = 0.0
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if not t:
                    continue
                for l in t.splitlines():
                    if "OPENING BALANCE" in l.upper():
                        m = re.search(r"([\d,]+\.\d{2})", l)
                        if m:
                            opening_balance = float(m.group(1).replace(",", ""))
                            break

        df = pd.DataFrame([{
            "date": "",
            "description": "Balance B/F (No transactions)",
            "debit": 0.0,
            "credit": 0.0,
            "balance": opening_balance
        }])

    return df
