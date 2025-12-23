# =====================================================
# RHB.PY – ORIGINAL BERKAT TERAS LOGIC (LOCKED)
# =====================================================

import re
import pdfplumber
import pandas as pd

# =====================================================
# ORIGINAL REGEX – DO NOT CHANGE
# =====================================================

TX_LINE_PATTERN = re.compile(
    r"^\s*(\d{1,2})\s*([A-Za-z]{3})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s*$"
)

# =====================================================
# ORIGINAL PARSER – DO NOT MODIFY
# =====================================================

def parse_rhb_pdf(pdf_path):
    transactions = []

    # Extract year (default 2025)
    year_match = re.search(r"20\d{2}", pdf_path)
    year = year_match.group(0) if year_match else "2025"

    prev_balance = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.split('\n')

            for line in lines:
                match = TX_LINE_PATTERN.match(line)

                if match:
                    day, month, desc, amount_str, bal_str = match.groups()

                    amount = float(amount_str.replace(",", ""))
                    curr_balance = float(bal_str.replace(",", ""))

                    # --- MATH CHECK ---
                    is_credit = False
                    is_debit = False

                    if prev_balance is not None:
                        # Balance went UP -> Credit
                        if abs((prev_balance + amount) - curr_balance) < 0.05:
                            is_credit = True
                        # Balance went DOWN -> Debit
                        elif abs((prev_balance - amount) - curr_balance) < 0.05:
                            is_debit = True

                    # --- FALLBACK (If Math fails or is first row) ---
                    if not is_credit and not is_debit:
                        credit_keywords = [
                            "CR", "DEPOSIT", "INWARD",
                            "HIBAH", "PROFIT", "DEP", "CHEQUE"
                        ]

                        if any(k in desc.upper() for k in credit_keywords):
                            is_credit = True
                        else:
                            is_debit = True  # Default

                    credit_val = amount if is_credit else 0.0
                    debit_val = amount if is_debit else 0.0

                    transactions.append({
                        "date": f"{day} {month} {year}",
                        "description": desc.strip(),
                        "debit": debit_val,
                        "credit": credit_val,
                        "balance": curr_balance
                    })

                    prev_balance = curr_balance

                # --- DESCRIPTION CONTINUATION ---
                elif transactions and len(line.strip()) > 0:
                    ignore_list = [
                        "RHB Bank", "Page", "Statement Period",
                        "Balance", "Total Count", "Member of PIDM"
                    ]
                    if not any(k in line for k in ignore_list):
                        if not re.match(r"^\s*\d{1,2}\s*[A-Za-z]{3}", line):
                            transactions[-1]["description"] += " " + line.strip()

    return pd.DataFrame(transactions)


# =====================================================
# PUBLIC FUNCTION (USED BY app.py)
# =====================================================

def extract_rhb(pdf_path):
    """
    Streamlit entry point.
    Uses original Berkat Teras parser WITHOUT modification.
    """
    try:
        df = parse_rhb_pdf(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass

    return pd.DataFrame(
        columns=["date", "description", "debit", "credit", "balance"]
    )
