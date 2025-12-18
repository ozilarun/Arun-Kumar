import pdfplumber
import pandas as pd
import re
from pathlib import Path

# ===================================================
# MAYBANK MTASB EXTRACTOR
# (Converted from working Jupyter Notebook)
# ===================================================

# Pattern:
# 01/06 TRANSFER TO A/C 320.00+61,430.41
TXN_PATTERN = re.compile(
    r"(\d{2}/\d{2})\s+"          # date
    r"(.+?)\s+"                 # description
    r"([0-9,]+\.\d{2})"         # amount
    r"([+-])"                   # sign
    r"([0-9,]+\.\d{2})"         # balance
)

SUMMARY_KEYWORDS = [
    "opening balance",
    "closing balance",
    "brought forward",
    "carried forward",
    "total debit",
    "total credit",
]

# ===================================================
def extract_maybank(pdf_path):
    transactions = []
    seen = set()

    def to_float(v):
        return float(str(v).replace(",", ""))

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""

            for raw_line in text.split("\n"):
                line = raw_line.strip()
                if not line:
                    continue

                m = TXN_PATTERN.search(line)
                if not m:
                    continue

                date_raw, desc, amount_raw, sign, balance_raw = m.groups()

                if any(k in desc.lower() for k in SUMMARY_KEYWORDS):
                    continue

                amount = to_float(amount_raw)
                balance = to_float(balance_raw)

                debit = amount if sign == "-" else 0.0
                credit = amount if sign == "+" else 0.0

                # Same logic as notebook (year fixed to statement year)
                day, month = date_raw.split("/")
                date = f"2025-{month}-{day}"

                key = (date, desc, debit, credit, balance)
                if key in seen:
                    continue
                seen.add(key)

                transactions.append({
                    "date": date,
                    "description": desc.strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

    df = pd.DataFrame(
        transactions,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    if df.empty:
        return df

    df["__dt"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("__dt").drop(columns="__dt").reset_index(drop=True)

    print(f"✔ MAYBANK extracted {len(df)} transactions from {Path(pdf_path).name}")
    return df
