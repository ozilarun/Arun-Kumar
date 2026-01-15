import pdfplumber
import pandas as pd
import re
from datetime import datetime

# ==================================================
# HELPERS
# ==================================================

def to_float(v):
    try:
        return float(str(v).replace(",", "").strip())
    except:
        return 0.0


def clean_date(s):
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%d %b %Y")
        except:
            pass
    return s


# ==================================================
# FORMAT A — MAYBANK BUSINESS / CWS
# ==================================================

def extract_format_a(table):
    rows = []

    headers = [str(h).lower() if h else "" for h in table[0]]

    if not ("date" in headers and "balance" in headers):
        return None

    for r in table[1:]:
        if not r or all(c in [None, ""] for c in r):
            continue

        try:
            date = r[0]
            desc = r[1]
            debit = r[2]
            credit = r[3]
            balance = r[4]

            rows.append({
                "date": clean_date(date),
                "description": str(desc).replace("\n", " ").strip(),
                "debit": to_float(debit),
                "credit": to_float(credit),
                "balance": to_float(balance),
            })
        except:
            continue

    return rows if rows else None


# ==================================================
# FORMAT B — MAYBANK RETAIL / MYTUTOR
# ==================================================

def extract_format_b(table):
    rows = []

    for r in table:
        if not r or len(r) < 5:
            continue

        date = r[0]
        if not re.search(r"\d{1,2}/\d{1,2}/\d{4}", str(date)):
            continue

        try:
            desc = r[1]
            amount = to_float(r[2])
            bal = to_float(r[-1])

            debit = credit = 0.0
            if amount < 0:
                debit = abs(amount)
            else:
                credit = amount

            rows.append({
                "date": clean_date(date),
                "description": str(desc).replace("\n", " ").strip(),
                "debit": debit,
                "credit": credit,
                "balance": bal,
            })
        except:
            continue

    return rows if rows else None


# ==================================================
# MAIN EXTRACTOR
# ==================================================

def extract_maybank(pdf_path):
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            # Try Format A
            result = extract_format_a(table)
            if result:
                rows.extend(result)
                continue

            # Try Format B
            result = extract_format_b(table)
            if result:
                rows.extend(result)

    df = pd.DataFrame(
        rows,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    # ===============================
    # FAIL-SAFE (NO CRASH)
    # ===============================
    if df.empty:
        return pd.DataFrame([{
            "date": "",
            "description": "No extractable Maybank transactions",
            "debit": 0.0,
            "credit": 0.0,
            "balance": 0.0
        }])

    return df
