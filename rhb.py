import pdfplumber
import pandas as pd
import re
from datetime import datetime

# =====================================================
# HELPERS
# =====================================================

def parse_amount(val):
    if val is None:
        return 0.0
    s = str(val).replace(",", "").strip()
    try:
        return float(s)
    except:
        return 0.0


def clean_date(s):
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%d %b %Y")
        except:
            pass
    return s


# =====================================================
# MAIN RHB EXTRACTOR (TEXT-BASED ONLY)
# =====================================================

def extract_rhb(pdf_path):
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            table = page.extract_table()

            if not table:
                continue

            headers = [h.lower() if h else "" for h in table[0]]

            # Expected RHB formats:
            # date | description | debit | credit | balance
            for row in table[1:]:
                if not row or all(c in [None, ""] for c in row):
                    continue

                try:
                    date = row[0]
                    desc = row[1]
                    debit = row[2] if len(row) > 2 else 0
                    credit = row[3] if len(row) > 3 else 0
                    balance = row[4] if len(row) > 4 else None

                    if not date or not re.search(r"\d", str(date)):
                        continue

                    rows.append({
                        "date": clean_date(str(date)),
                        "description": str(desc).replace("\n", " ").strip(),
                        "debit": parse_amount(debit),
                        "credit": parse_amount(credit),
                        "balance": parse_amount(balance),
                    })

                except:
                    continue

    df = pd.DataFrame(
        rows,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    # =================================================
    # FALLBACK: NO TRANSACTIONS FOUND
    # =================================================
    if df.empty:
        # Prevent Streamlit crash
        return pd.DataFrame([{
            "date": "",
            "description": "No extractable text (OCR-based PDF not supported)",
            "debit": 0.0,
            "credit": 0.0,
            "balance": 0.0
        }])

    return df
