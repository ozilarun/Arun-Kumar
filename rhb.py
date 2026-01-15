import pdfplumber
import pandas as pd
import re

# ==========================
# REGEX (CORE RHB FORMAT)
# ==========================
TX_LINE_PATTERN = re.compile(
    r"^\s*(\d{1,2})\s*([A-Za-z]{3})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s*$"
)

IGNORE_LINES = [
    "RHB Bank",
    "Page",
    "Statement Period",
    "Balance",
    "Total Count",
    "Member of PIDM",
]

CREDIT_KEYWORDS = [
    "CR", "DEPOSIT", "INWARD", "HIBAH", "PROFIT", "DEP", "CHEQUE"
]

# ==========================
# MAIN EXTRACTOR
# ==========================
def extract_rhb(pdf_path):
    transactions = []

    # Detect year from filename (fallback to current year if missing)
    year_match = re.search(r"(20\d{2})", pdf_path)
    year = year_match.group(1) if year_match else "2024"

    prev_balance = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                # -------------------------
                # TRANSACTION LINE
                # -------------------------
                m = TX_LINE_PATTERN.match(line)
                if m:
                    day, month, desc, amt_str, bal_str = m.groups()

                    amount = float(amt_str.replace(",", ""))
                    balance = float(bal_str.replace(",", ""))

                    debit = credit = 0.0

                    # ----- Balance-diff logic -----
                    if prev_balance is not None:
                        if abs((prev_balance + amount) - balance) < 0.05:
                            credit = amount
                        elif abs((prev_balance - amount) - balance) < 0.05:
                            debit = amount
                        else:
                            # Fallback keyword logic
                            if any(k in desc.upper() for k in CREDIT_KEYWORDS):
                                credit = amount
                            else:
                                debit = amount
                    else:
                        # First row fallback
                        if any(k in desc.upper() for k in CREDIT_KEYWORDS):
                            credit = amount
                        else:
                            debit = amount

                    transactions.append({
                        "date": f"{day} {month} {year}",
                        "description": desc.strip(),
                        "debit": debit,
                        "credit": credit,
                        "balance": balance
                    })

                    prev_balance = balance
                    continue

                # -------------------------
                # MULTI-LINE DESCRIPTION
                # -------------------------
                if transactions:
                    if not any(k in line for k in IGNORE_LINES):
                        if not re.match(r"^\s*\d{1,2}\s*[A-Za-z]{3}", line):
                            transactions[-1]["description"] += " " + line.strip()

    df = pd.DataFrame(
        transactions,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    print(f"✔ RHB extracted {len(df)} rows from {pdf_path}")
    return df
