import pdfplumber
import pandas as pd
import re
from pathlib import Path

# ===================================================
# MAYBANK MTASB STREAMLIT EXTRACTOR (FIXED)
# ===================================================

TXN_PATTERN = re.compile(
    r"(\d{2}/\d{2})\s+"          # 01/06
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
