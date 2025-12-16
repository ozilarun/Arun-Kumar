import pdfplumber
import pandas as pd
import re
from pathlib import Path

# ===================================================
# MONTH MAP (FROM YOUR CODE)
# ===================================================

MONTH_MAP = {
    "JAN": "January", "FEB": "February", "MAR": "March",
    "APR": "April", "MAY": "May", "JUN": "June",
    "JUL": "July", "AUG": "August", "SEP": "September",
    "OCT": "October", "NOV": "November", "DEC": "December"
}


def get_month_name(pdf_path):
    name = Path(pdf_path).stem.upper()

    for k, v in MONTH_MAP.items():
        if k in name:
            year = re.search(r"(20\d{2})", name)
            return f"{v} {year.group(1)}" if year else v

    return "UnknownMonth"


# ===================================================
# 1️⃣ EXTRACTION — CIMB (UNCHANGED LOGIC)
# ===================================================

def extract_cimb(pdf_path):
    txns = []
    seen = set()

    def to_float(x):
        try:
            return float(str(x).replace(",", "").strip())
        except:
            return 0.0

    def valid_date(x):
        return bool(re.match(r"\d{2}/\d{2}/\d{4}", str(x).strip()))

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if not table:
                continue

            for row in table[1:]:
                row = (row + [""] * 6)[:6]
                date, desc, ref, wd, dep, bal = row

                if not date or not valid_date(date):
                    continue

                desc = str(desc).replace("\n", " ").strip()

                if any(x in desc.lower() for x in [
                    "no of withdrawal", "no of deposit",
                    "total withdrawal", "total deposit",
                    "end of statement", "baki penutup"
                ]):
                    continue

                debit = to_float(wd)
                credit = to_float(dep)
                balance = to_float(bal)

                if debit == 0 and credit == 0:
                    continue

                key = (date, desc, debit, credit, balance)
                if key in seen:
                    continue
                seen.add(key)

                if ref and ref.strip():
                    desc = f"{desc} Ref: {ref.strip()}"

                txns.append({
                    "date": date.strip(),
                    "description": desc,
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

    return pd.DataFrame(txns, columns=[
        "date", "description", "debit", "credit", "balance"
    ])

