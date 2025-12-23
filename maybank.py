# =====================================================
# MAYBANK.PY – COMBINED & STREAMLIT SAFE
# =====================================================

import re
import fitz  # PyMuPDF
import pdfplumber
import pandas as pd
from datetime import datetime


# =====================================================
# 1️⃣ PYMuPDF WORD-BASED EXTRACTOR (MTASB / MYTUTOR)
# (LOGIC UNCHANGED)
# =====================================================

def _extract_maybank_pymupdf(pdf_path):

    doc = fitz.open(pdf_path)

    # Detect statement year
    statement_year = "2025"
    STATEMENT_DATE_RE = re.compile(r"STATEMENT\s+DATE\s*:?\s*(\d{2})/(\d{2})/(\d{2})")

    for p in range(min(2, len(doc))):
        txt = doc[p].get_text("text").upper()
        m = STATEMENT_DATE_RE.search(txt)
        if m:
            statement_year = f"20{m.group(3)}"
            break

    DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}|\d{2}-\d{2}|\d{2}\s+[A-Z]{3})$")
    AMT_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)?\.\d{2}[+-]?$")

    def norm_date(token):
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

    def parse_amt(t):
        sign = "+" if t.endswith("+") else "-" if t.endswith("-") else None
        v = float(t.replace(",", "").rstrip("+-"))
        return v, sign

    transactions = []
    prev_balance = None

    for page in doc:
        words = page.get_text("words")
        rows = [{"x": w[0], "y": w[1], "t": w[4].strip()} for w in words if w[4].strip()]
        rows.sort(key=lambda r: (round(r["y"], 1), r["x"]))

        used_y = set()
        for r in rows:
            if not DATE_RE.match(r["t"]):
                continue

            y = round(r["y"], 1)
            if y in used_y:
                continue

            line = [w for w in rows if abs(w["y"] - r["y"]) <= 1.8]
            line.sort(key=lambda w: w["x"])

            date = norm_date(r["t"])
            if not date:
                continue

            desc, amts = [], []
            for w in line:
                if w["t"] == r["t"]:
                    continue
                if AMT_RE.match(w["t"]):
                    amts.append((w["x"], w["t"]))
                else:
                    desc.append(w["t"])

            if not amts:
                continue

            amts.sort(key=lambda a: a[0])
            bal, _ = parse_amt(amts[-1][1])

            txn_val, txn_sign = (None, None)
            if len(amts) > 1:
                txn_val, txn_sign = parse_amt(amts[-2][1])

            debit, credit = 0.0, 0.0
            if prev_balance is not None:
                delta = round(bal - prev_balance, 2)
                if delta > 0:
                    credit = delta
                elif delta < 0:
                    debit = abs(delta)
                else:
                    if txn_sign == "+":
                        credit = txn_val
                    elif txn_sign == "-":
                        debit = txn_val
            else:
                if txn_sign == "+":
                    credit = txn_val
                elif txn_sign == "-":
                    debit = txn_val

            transactions.append({
                "date": date,
                "description": " ".join(desc).strip(),
                "debit": debit,
                "credit": credit,
                "balance": bal
            })

            prev_balance = bal
            used_y.add(y)

    return pd.DataFrame(transactions)


# =====================================================
# 2️⃣ PDFPLUMBER LINE-BASED EXTRACTOR (CWS FORMAT)
# (LOGIC UNCHANGED)
# =====================================================

DATE_PATTERN = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}")
AMOUNT_PATTERN = re.compile(r'([0-9,]+\.\d{2})\s*([+-])\s*([0-9,]+\.\d{2})')

def _extract_maybank_pdfplumber(pdf_path):

    txns = []
    current = None
    desc_buf = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for raw in text.split("\n"):
                line = raw.strip()
                if not line:
                    continue

                if DATE_PATTERN.match(line):
                    if current:
                        current["description"] = " ".join(desc_buf).strip()
                        txns.append(current)

                    desc_buf = []
                    m = AMOUNT_PATTERN.search(line)
                    if not m:
                        continue

                    amt = float(m.group(1).replace(",", ""))
                    sign = m.group(2)
                    bal = float(m.group(3).replace(",", ""))

                    current = {
                        "date": line[:11],
                        "description": "",
                        "debit": amt if sign == "-" else 0.0,
                        "credit": amt if sign == "+" else 0.0,
                        "balance": bal
                    }

                    desc_buf.append(line[:m.start()].strip())
                else:
                    if current:
                        desc_buf.append(line)

        if current:
            current["description"] = " ".join(desc_buf).strip()
            txns.append(current)

    return pd.DataFrame(txns)


# =====================================================
# 3️⃣ PUBLIC FUNCTION (USED BY app.py)
# =====================================================

def extract_maybank(pdf_path):
    """
    Streamlit-safe Maybank extractor.
    Tries PyMuPDF first, falls back to pdfplumber.
    Output columns are STRICTLY:
    date | description | debit | credit | balance
    """

    try:
        df = _extract_maybank_pymupdf(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass

    try:
        df = _extract_maybank_pdfplumber(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass

    return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])
