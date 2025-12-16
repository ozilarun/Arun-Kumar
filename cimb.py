import pdfplumber
import pandas as pd
import re
from pathlib import Path

# ===================================================
# MONTH MAP (UNCHANGED)
# ===================================================
MONTH_MAP = {
    "JAN": "January", "FEB": "February", "MAR": "March",
    "APR": "April", "MAY": "May", "JUN": "June",
    "JUL": "July", "AUG": "August", "SEP": "September",
    "OCT": "October", "NOV": "November", "DEC": "December"
}

# ===================================================
# CIMB UNIVERSAL EXTRACTOR (TABLE + RAW TEXT)
# ===================================================
def extract_cimb(pdf_path):
    txns = []
    seen = set()

    # RAW TEXT fallback regex (YOUR WORKING ONE)
    raw_pattern = re.compile(
        r"(\d{2}/\d{2}/\d{4})\s+(.*?)\s+(-?[0-9,]*\.?\d*)\s+(-?[0-9,]*\.?\d*)\s+(-?[0-9,]*\.?\d*)$"
    )

    def to_float(v):
        try:
            return float(str(v).replace(",", "").strip())
        except:
            return 0.0

    def valid_date(v):
        return bool(re.match(r"\d{2}/\d{2}/\d{4}", str(v).strip()))

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:

            # =========================================
            # 1️⃣ TABLE MODE (PRIMARY)
            # =========================================
            table = page.extract_table()

            if table:
                for row in table[1:]:
                    if not row or all((c is None or str(c).strip() == "") for c in row):
                        continue

                    joined = " ".join(str(c) for c in row if c)

                    # Skip summaries / footers
                    if any(k.lower() in joined.lower() for k in [
                        "opening balance", "closing balance",
                        "no of withdrawal", "no of deposits",
                        "total withdrawal", "total deposits",
                        "end of statement", "baki penutup"
                    ]):
                        continue

                    def safe(i):
                        return row[i] if i < len(row) and row[i] else ""

                    date = safe(0)
                    desc = safe(1)
                    ref  = safe(2)
                    wd   = safe(3)
                    dep  = safe(4)
                    bal  = safe(5)

                    if not valid_date(date):
                        continue

                    debit  = to_float(wd)
                    credit = to_float(dep)
                    balance = to_float(bal)

                    if debit == 0 and credit == 0:
                        continue

                    desc = str(desc).replace("\n", " ").strip()
                    if ref.strip():
                        desc = f"{desc} Ref: {ref.strip()}"

                    key = (date, desc, debit, credit, balance)
                    if key in seen:
                        continue
                    seen.add(key)

                    txns.append({
                        "date": date.strip(),
                        "description": desc,
                        "debit": debit,
                        "credit": credit,
                        "balance": balance
                    })

                # IMPORTANT: continue to next page
                continue

            # =========================================
            # 2️⃣ RAW TEXT MODE (FALLBACK – CRITICAL)
            # =========================================
            text = page.extract_text() or ""
            for line in text.split("\n"):
                m = raw_pattern.search(line)
                if not m:
                    continue

                date, desc, wd, dep, bal = m.groups()

                debit  = to_float(wd)
                credit = to_float(dep)
                balance = to_float(bal)

                if debit == 0 and credit == 0:
                    continue

                key = (date, desc, debit, credit, balance)
                if key in seen:
                    continue
                seen.add(key)

                txns.append({
                    "date": date.strip(),
                    "description": desc.strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

    df = pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    print(f"✔ CIMB extracted {len(df)} transactions from {Path(pdf_path).name}")
    return df
