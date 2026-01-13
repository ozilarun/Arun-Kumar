import pdfplumber
import pandas as pd
import re

# ==========================
# HELPERS
# ==========================

MONTH_MAP = {
    "01": "January", "02": "February", "03": "March",
    "04": "April",   "05": "May",      "06": "June",
    "07": "July",    "08": "August",   "09": "September",
    "10": "October", "11": "November", "12": "December"
}

def to_float(v):
    try:
        s = str(v).replace("\n", "").replace(",", "")
        return float(s)
    except:
        return 0.0


# ==========================
# MAIN EXTRACTOR
# ==========================
def extract_bank_islam(pdf_path):
    txns = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:

            table = page.extract_table()
            if not table:
                continue

            # CASA tables are wide (Bank Islam CASA)
            is_casa = len(table[0]) >= 11

            for row in table[1:]:

                if not row or all(c in [None, ""] for c in row):
                    continue

                # =========================
                # CASA FORMAT
                # =========================
                if is_casa:
                    try:
                        raw_date = row[1]     # "28/05/2025\n23:59:59"
                        desc     = row[4]
                        debit    = row[7]
                        credit   = row[8]
                        balance  = row[9]

                        if not raw_date:
                            continue

                        date = raw_date.split("\n")[0].strip()
                        if not re.match(r"\d{2}/\d{2}/\d{4}", date):
                            continue

                        txns.append({
                            "date": date,
                            "description": desc.replace("\n", " ").strip(),
                            "debit": to_float(debit),
                            "credit": to_float(credit),
                            "balance": to_float(balance),
                        })
                    except:
                        continue

                # =========================
                # NORMAL FORMAT
                # =========================
                else:
                    try:
                        date    = row[0]
                        desc    = row[1]
                        debit   = row[2]
                        credit  = row[3]
                        balance = row[4]

                        if not date or not re.match(r"\d{1,2}/\d{1,2}/\d{2,4}", date):
                            continue

                        txns.append({
                            "date": date.strip(),
                            "description": desc.replace("\n", " ").strip(),
                            "debit": to_float(debit),
                            "credit": to_float(credit),
                            "balance": to_float(balance),
                        })
                    except:
                        continue

    df = pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    print(f"✔ Bank Islam extracted {len(df)} rows from {pdf_path}")
    return df
