import pdfplumber
import pandas as pd
import re

# ===================================================
# CIMB — EXTRACTION ONLY (UNIVERSAL, DO NOT ADD LOGIC)
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
            if not table or len(table) < 2:
                continue

            for row in table[1:]:
                # normalize row length safely
                row = (row + [""] * 6)[:6]
                date, desc, ref, wd, dep, bal = row

                # ---- date must be valid ----
                if not date or not valid_date(date):
                    continue

                desc = str(desc).replace("\n", " ").strip()

                # ---- skip CIMB summary/footer rows ----
                skip_words = [
                    "no of withdrawal",
                    "no of deposit",
                    "total withdrawal",
                    "total deposit",
                    "end of statement",
                    "baki penutup"
                ]

                if any(w in desc.lower() for w in skip_words):
                    continue

                debit = to_float(wd)
                credit = to_float(dep)
                balance = to_float(bal)

                # ---- skip empty movements ----
                if debit == 0 and credit == 0:
                    continue

                # ---- de-duplication (CIMB repeats rows) ----
                key = (date, desc, debit, credit, balance)
                if key in seen:
                    continue
                seen.add(key)

                if ref and str(ref).strip():
                    desc = f"{desc} Ref: {str(ref).strip()}"

                txns.append({
                    "date": date.strip(),          # KEEP STRING
                    "description": desc,
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

    return pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )
