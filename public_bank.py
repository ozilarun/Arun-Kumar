import pdfplumber
import pandas as pd
import re
from datetime import datetime

# ==========================
# REGEX & CONSTANTS
# ==========================
DATE_LINE = re.compile(r"^(?P<date>\d{2}/\d{2})\s+(?P<rest>.*)$")

AMOUNT_BAL = re.compile(
    r"(?P<amount>\d{1,3}(?:,\d{3})*\.\d{2})\s+"
    r"(?P<balance>\d{1,3}(?:,\d{3})*\.\d{2})$"
)

BAL_ONLY = re.compile(
    r"^(?P<date>\d{2}/\d{2})\s+Balance.*\s+"
    r"(?P<balance>\d{1,3}(?:,\d{3})*\.\d{2})$",
    re.IGNORECASE
)

TX_KEYWORDS = [
    "TSFR", "DUITNOW", "GIRO", "JOMPAY", "RMT", "DR-ECP",
    "HANDLING", "FEE", "DEP", "RTN", "PROFIT",
    "CHARGES", "DEBIT", "CREDIT", "TRANSFER", "PAYMENT"
]

IGNORE_PREFIXES = [
    "CLEAR WATER", "/ROC", "PVCWS", "IMEPS",
    "PUBLIC BANK", "PAGE", "TEL:", "MUKA SURAT",
    "TARIKH", "DATE", "NO.", "URUS NIAGA",
    "STATEMENT", "ACCOUNT"
]

# ==========================
# HELPERS
# ==========================
def is_ignored(line):
    return any(line.upper().startswith(p) for p in IGNORE_PREFIXES)

def is_tx_start(line):
    return any(line.upper().startswith(k) for k in TX_KEYWORDS)

def extract_year_from_text(text):
    patterns = [
        r'(?:STATEMENT DATE|TARIKH PENYATA)\s*[:\s]+\d{1,2}/\d{1,2}/(\d{2,4})',
        r'Statement\s+(?:Date|Period)[:\s]+\d{1,2}/\d{1,2}/(\d{4})',
        r'FOR\s+THE\s+PERIOD[:\s]+\d{1,2}/\d{1,2}/(\d{4})',
        r'(\d{4})\s+Statement'
    ]

    for p in patterns:
        m = re.search(p, text, re.IGNORECASE)
        if m:
            y = m.group(1)
            return y if len(y) == 4 else str(2000 + int(y))

    return None

# ==========================
# MAIN EXTRACTOR
# ==========================
def extract_public_bank(pdf_path):
    transactions = []
    detected_year = None

    with pdfplumber.open(pdf_path) as pdf:

        # -------- Detect year from first pages --------
        for page in pdf.pages[:3]:
            text = page.extract_text() or ""
            detected_year = extract_year_from_text(text)
            if detected_year:
                break

        if not detected_year:
            detected_year = str(datetime.now().year)

        # -------- Parse pages --------
        for page in pdf.pages:
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

                bal_match = BAL_ONLY.match(line)
                if bal_match:
                    current_date = bal_match.group("date")
                    prev_balance = float(
                        bal_match.group("balance").replace(",", "")
                    )
                    desc_accum = ""
                    waiting_for_amount = False
                    continue

                amount_match = AMOUNT_BAL.search(line)
                date_match = DATE_LINE.match(line)
                keyword_match = is_tx_start(line)
                is_new_start = date_match or keyword_match

                if amount_match:
                    amount = float(amount_match.group("amount").replace(",", ""))
                    balance = float(amount_match.group("balance").replace(",", ""))

                    if is_new_start:
                        if date_match:
                            current_date = date_match.group("date")
                            final_desc = date_match.group("rest")
                        else:
                            final_desc = line.replace(amount_match.group(0), "").strip()
                    else:
                        final_desc = (desc_accum + " " +
                                      line.replace(amount_match.group(0), "").strip())

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
                        iso_date = f"{dd}/{mm}/{detected_year}"
                    else:
                        iso_date = f"01/01/{detected_year}"

                    transactions.append({
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

    df = pd.DataFrame(
        transactions,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    print(f"✔ Public Bank extracted {len(df)} rows from {pdf_path}")
    return df
