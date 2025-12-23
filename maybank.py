import fitz  # PyMuPDF
import pandas as pd
import re
from datetime import datetime

# ===================================================
# MAYBANK MTASB — EXTRACTION ONLY (STREAMLIT SAFE)
# Matches Bank Rakyat / CIMB contract exactly
# ===================================================

DATE_RE = re.compile(
    r"^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}|\d{2}-\d{2}|\d{2}\s+[A-Z]{3})$",
    re.IGNORECASE
)

AMOUNT_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}[+-]?$")

STATEMENT_YEAR_RE = re.compile(r"STATEMENT\s+DATE\s*:?\s*(\d{2})/(\d{2})/(\d{2})")

SUMMARY_WORDS = [
    "OPENING BALANCE",
    "CLOSING BALANCE",
    "BALANCE B/F",
    "BALANCE C/F",
    "BROUGHT FORWARD",
    "CARRIED FORWARD",
    "TOTAL DEBIT",
    "TOTAL CREDIT",
]

# ---------------------------------------------------

def extract_maybank(pdf_path):
    transactions = []

    doc = fitz.open(pdf_path)

    # ----------------------------
    # Detect statement year safely
    # ----------------------------
    statement_year = None
    for p in range(min(2, len(doc))):
        text = doc[p].get_text("text").upper()
        m = STATEMENT_YEAR_RE.search(text)
        if m:
            statement_year = f"20{m.group(3)}"
            break

    if not statement_year:
        return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])

    # ----------------------------
    def normalize_date(token):
        token = token.strip().upper()
        for fmt in ("%d/%m/%Y", "%d/%m", "%d-%m", "%d %b"):
            try:
                if fmt == "%d/%m/%Y":
                    dt = datetime.strptime(token, fmt)
                else:
                    dt = datetime.strptime(f"{token}/{statement_year}", fmt + "/%Y")
                return dt.strftime("%d/%m/%Y")
            except:
                pass
        return None

    def parse_amount(t):
        sign = "+" if t.endswith("+") else "-" if t.endswith("-") else None
        value = float(t.replace(",", "").rstrip("+-"))
        return value, sign

    # ----------------------------
    previous_balance = None

    for page in doc:
        words = page.get_text("words")
        rows = [
            {"x": w[0], "y": w[1], "text": str(w[4]).strip()}
            for w in words if str(w[4]).strip()
        ]

        rows.sort(key=lambda r: (round(r["y"], 1), r["x"]))

        Y_TOL = 1.8
        used_y = set()

        for r in rows:
            token = r["text"]
            if not DATE_RE.match(token):
                continue

            y_key = round(r["y"], 1)
            if y_key in used_y:
                continue

            line = [w for w in rows if abs(w["y"] - r["y"]) <= Y_TOL]
            line.sort(key=lambda w: w["x"])

            date_str = normalize_date(token)
            if not date_str:
                continue

            desc_parts = []
            amounts = []

            for w in line:
                if w["text"] == token:
                    continue
                if AMOUNT_RE.match(w["text"]):
                    amounts.append((w["x"], w["text"]))
                else:
                    desc_parts.append(w["text"])

            if not amounts:
                continue

            amounts.sort(key=lambda a: a[0])

            balance_val, _ = parse_amount(amounts[-1][1])

            txn_val, txn_sign = (None, None)
            if len(amounts) > 1:
                txn_val, txn_sign = parse_amount(amounts[-2][1])

            description = " ".join(desc_parts).strip()

            if any(k in description.upper() for k in SUMMARY_WORDS):
                continue

            debit, credit = 0.0, 0.0

            if previous_balance is not None:
                delta = round(balance_val - previous_balance, 2)
                if delta > 0:
                    credit = abs(delta)
                elif delta < 0:
                    debit = abs(delta)
                else:
                    if txn_sign == "+":
                        credit = txn_val or 0.0
                    elif txn_sign == "-":
                        debit = txn_val or 0.0
            else:
                if txn_sign == "+":
                    credit = txn_val or 0.0
                elif txn_sign == "-":
                    debit = txn_val or 0.0

            transactions.append({
                "date": date_str,          # DD/MM/YYYY (same as Bank Rakyat)
                "description": description,
                "debit": debit,
                "credit": credit,
                "balance": balance_val
            })

            previous_balance = balance_val
            used_y.add(y_key)

    return pd.DataFrame(
        transactions,
        columns=["date", "description", "debit", "credit", "balance"]
    )
