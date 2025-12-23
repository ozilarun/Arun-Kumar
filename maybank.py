import fitz  # PyMuPDF
import pdfplumber
import re
import pandas as pd
from datetime import datetime


# ============================================================
# 🔹 MYTUTOR ENGINE (COPIED 1:1 LOGIC – SAFE)
# ============================================================

def _extract_maybank_mytutor(pdf_path):
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

    DATE_RE = re.compile(
        r"^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2}|\d{2}-\d{2}|\d{2}\s+[A-Z]{3})$",
        re.IGNORECASE
    )
    AMOUNT_RE = re.compile(r"^(?:\d{1,3}(?:,\d{3})*|\d+)?\.\d{2}[+-]?$")

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
        t = t.strip()
        sign = "+" if t.endswith("+") else "-" if t.endswith("-") else None
        val = float(t.replace(",", "").rstrip("+-"))
        return val, sign

    transactions = []
    previous_balance = None

    for page in doc:
        words = page.get_text("words")
        rows = [{"x": w[0], "y": w[1], "t": w[4].strip()} for w in words if w[4].strip()]
        rows.sort(key=lambda r: (round(r["y"], 1), r["x"]))

        used_y = set()

        for r in rows:
            if not DATE_RE.match(r["t"]):
                continue

            y_key = round(r["y"], 1)
            if y_key in used_y:
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
                if AMOUNT_RE.match(w["t"]):
                    amts.append(w["t"])
                else:
                    desc.append(w["t"])

            if not amts:
                continue

            balance, _ = parse_amt(amts[-1])
            txn_val, txn_sign = (parse_amt(amts[-2]) if len(amts) > 1 else (None, None))

            debit = credit = 0.0
            if previous_balance is not None:
                delta = round(balance - previous_balance, 2)
                if delta > 0:
                    credit = abs(delta)
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
                "balance": balance
            })

            previous_balance = balance
            used_y.add(y_key)

    return pd.DataFrame(transactions)


# ============================================================
# 🔹 CWS ENGINE (pdfplumber – SAFE FALLBACK)
# ============================================================

def _extract_maybank_cws(pdf_path):
    DATE_PATTERN = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}")
    AMOUNT_PATTERN = re.compile(r'([0-9,]+\.\d{2})\s*([+-])\s*([0-9,]+\.\d{2})')

    txns = []
    means = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                line = line.strip()
                if not DATE_PATTERN.match(line):
                    continue

                m = AMOUNT_PATTERN.search(line)
                if not m:
                    continue

                amt = float(m.group(1).replace(",", ""))
                sign = m.group(2)
                bal = float(m.group(3).replace(",", ""))

                txns.append({
                    "date": line[:11],
                    "description": line[:m.start()].strip(),
                    "debit": amt if sign == "-" else 0.0,
                    "credit": amt if sign == "+" else 0.0,
                    "balance": bal
                })

    return pd.DataFrame(txns)


# ============================================================
# 🚀 FINAL EXTRACTOR (USED BY STREAMLIT)
# ============================================================

def extract_maybank(pdf_path):
    # 1️⃣ Try MyTutor FIRST (authoritative)
    df = _extract_maybank_mytutor(pdf_path)
    if not df.empty:
        return df.reset_index(drop=True)

    # 2️⃣ Fallback to CWS
    df = _extract_maybank_cws(pdf_path)
    if not df.empty:
        return df.reset_index(drop=True)

    return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])
