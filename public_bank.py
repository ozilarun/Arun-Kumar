import pdfplumber
import pandas as pd
import re
from datetime import datetime

# =========================================================
# YEAR DETECTION (UNCHANGED)
# =========================================================

def extract_year_from_text(text):
    match = re.search(
        r'(?:STATEMENT DATE|TARIKH PENYATA)\s*[:\s]+\d{1,2}/\d{1,2}/(\d{2,4})',
        text, re.IGNORECASE
    )
    if match:
        y = match.group(1)
        return y if len(y) == 4 else str(2000 + int(y))

    match = re.search(
        r'Statement\s+(?:Date|Period)[:\s]+\d{1,2}/\d{1,2}/(\d{4})',
        text, re.IGNORECASE
    )
    if match:
        return match.group(1)

    match = re.search(
        r'FOR\s+THE\s+PERIOD[:\s]+\d{1,2}/\d{1,2}/(\d{4})',
        text, re.IGNORECASE
    )
    if match:
        return match.group(1)

    match = re.search(r'(\d{4})\s+Statement', text, re.IGNORECASE)
    if match:
        y = int(match.group(1))
        if 2000 <= y <= 2100:
            return str(y)

    return None

# =========================================================
# REGEX (UNCHANGED)
# =========================================================

DATE_LINE = re.compile(r"^(?P<date>\d{2}/\d{2})\s+(?P<rest>.*)$")

AMOUNT_BAL = re.compile(
    r"(?P<amount>\d{1,3}(?:,\d{3})*\.\d{2})\s+(?P<balance>\d{1,3}(?:,\d{3})*\.\d{2})$"
)

BAL_ONLY = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+(Balance.*)\s+(?P<balance>\d{1,3}(?:,\d{3})*\.\d{2})$",
    re.IGNORECASE
)

TX_KEYWORDS = [
    "TSFR", "DUITNOW", "GIRO", "JOMPAY", "RMT", "DR-ECP",
    "HANDLING", "FEE", "DEP", "RTN", "PROFIT", "AUTOMATED",
    "CHARGES", "DEBIT", "CREDIT", "TRANSFER", "PAYMENT"
]

IGNORE_PREFIXES = [
    "CLEAR WATER", "/ROC", "PVCWS", "IMEPS",
    "PUBLIC BANK", "PAGE", "TEL:", "MUKA SURAT", "TARIKH",
    "DATE", "NO.", "URUS NIAGA", "STATEMENT", "ACCOUNT"
]

def is_ignored(line):
    return any(line.upper().startswith(p) for p in IGNORE_PREFIXES)

def is_tx_start(line):
    return any(line.upper().startswith(k) for k in TX_KEYWORDS)

# =========================================================
# CORE PARSER (UNCHANGED)
# =========================================================

def parse_transactions_pbb(pdf, source_filename=""):
    all_transactions = []
    detected_year = None

    for page in pdf.pages[:3]:
        text = page.extract_text() or ""
        detected_year = extract_year_from_text(text)
        if detected_year:
            break

    if not detected_year:
        detected_year = str(datetime.now().year)

    for page_num, page in enumerate(pdf.pages, start=1):
        text = page.extract_text() or ""
        lines = text.splitlines()

        current_date = None
        prev_balance = None
        desc_accum = ""
        waiting_for_amount = False

        for line in lines:
            line = line.strip()
            if not line or is_ignored(line):
                continue

            amount_match = AMOUNT_BAL.search(line)
            has_amount = bool(amount_match)
            date_match = DATE_LINE.match(line)
            is_new_start = date_match or is_tx_start(line)

            bal_match = BAL_ONLY.match(line)
            if bal_match:
                current_date = bal_match.group("date")
                prev_balance = float(bal_match.group("balance").replace(",", ""))
                desc_accum = ""
                waiting_for_amount = False
                continue

            if has_amount:
                amount = float(amount_match.group("amount").replace(",", ""))
                balance = float(amount_match.group("balance").replace(",", ""))

                if is_new_start:
                    if date_match:
                        current_date = date_match.group("date")
                        final_desc = date_match.group("rest")
                    else:
                        final_desc = line.replace(amount_match.group(0), "").strip()
                else:
                    final_desc = desc_accum + " " + line.replace(amount_match.group(0), "").strip()

                debit = credit = 0.0
                if prev_balance is not None:
                    if balance < prev_balance:
                        debit = amount
                    elif balance > prev_balance:
                        credit = amount
                else:
                    up = final_desc.upper()
                    credit = amount if ("CR" in up or "DEP" in up) else 0.0
                    debit = amount if credit == 0 else 0.0

                if current_date:
                    dd, mm = current_date.split("/")
                    iso_date = f"{detected_year}-{mm}-{dd}"
                else:
                    iso_date = f"{detected_year}-01-01"

                all_transactions.append({
                    "date": iso_date,
                    "description": final_desc.strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

                prev_balance = balance
                desc_accum = ""
                waiting_for_amount = False

            elif is_new_start:
                desc_accum = date_match.group("rest") if date_match else line
                current_date = date_match.group("date") if date_match else current_date
                waiting_for_amount = True

            elif waiting_for_amount:
                desc_accum += " " + line

    return all_transactions

# =========================================================
# STREAMLIT ENTRY POINT (WRAPPER ONLY)
# =========================================================

def extract_public_bank(pdf_path):
    """
    Streamlit-compatible extractor.
    Parsing logic intentionally unchanged.
    """

    with pdfplumber.open(pdf_path) as pdf:
        txns = parse_transactions_pbb(pdf, source_filename=pdf_path)

    return pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )
