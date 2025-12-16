import pdfplumber
import pandas as pd
import re


# ===================================================
# BANK RAKYAT — EXTRACTION ONLY (TABULATE SOURCE)
# ===================================================

def extract_bank_rakyat(pdf_path):
    txns = []

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
                row = [(c or "").strip() for c in row]

                if len(row) < 6:
                    continue

                date, _, desc, debit, credit, balance = row[:6]

                skip_words = [
                    "BAKI PERMULAAN",
                    "BAKI PENUTUP",
                    "JUMLAH",
                    "TOTAL",
                    "BIL",
                    "NO"
                ]

                if any(w in desc.upper() for w in skip_words):
                    continue

                if not valid_date(date):
                    continue

                desc = re.sub(r"\s+", " ", desc).strip()

                txns.append({
                    "date": date,
                    "description": desc,
                    "debit": to_float(debit),
                    "credit": to_float(credit),
                    "balance": to_float(balance),
                })

    return pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )
