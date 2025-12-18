import pdfplumber
import pandas as pd
import re
from pathlib import Path

# ===================================================
# MAYBANK STREAMLIT SAFE EXTRACTOR (FIXED REGEX)
# ===================================================

TXN_PATTERN = re.compile(
    r"(\d{2}/\d{2})\s+"        # date: 01/06
    r"(.+?)\s+"               # description
    r"([0-9,]+\.\d{2})"       # amount
    r"([+-])\s*"              # sign (CRITICAL FIX)
    r"([0-9,]+\.\d{2})"       # balance
)

SUMMARY_KEYWORDS = [
    "opening balance", "closing balance",
    "brought forward", "carried forward",
    "total debit", "total credit"
]


def extract_maybank(pdf_path):
    txns = []
    seen = set()

    def to_float(v):
        return float(str(v).replace(",", ""))

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                m = TXN_PATTERN.search(line)
                if not m:
                    continue

                date, desc, amt, sign, bal = m.groups()

                if any(k in desc.lower() for k in SUMMARY_KEYWORDS):
                    continue

                amount = to_float(amt)
                balance = to_float(bal)

                debit = amount if sign == "-" else 0.0
                credit = amount if sign == "+" else 0.0

                key = (date, desc, debit, credit, balance)
                if key in seen:
                    continue
                seen.add(key)

                txns.append({
                    "date": date,
                    "description": desc.strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

    df = pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    if df.empty:
        return df

    df["__dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df.sort_values("__dt").drop(columns="__dt").reset_index(drop=True)

    print(f"✔ MAYBANK extracted {len(df)} transactions from {Path(pdf_path).name}")
    return df
