import pdfplumber
import pandas as pd
import re
from datetime import datetime

# =========================================================
# REGEX (UNCHANGED)
# =========================================================

DATE_RE = re.compile(r"\d{1,2}/\d{2}/\d{2}")
AMOUNT_RE = re.compile(r"(?:\d{1,3}(?:,\d{3})*|\d+)?\.\d{2}")
ZERO_RE = re.compile(r"^0?\.00$")

# =========================================================
# CORE PARSER (UNCHANGED)
# =========================================================

def parse_transactions_bank_muamalat(pdf, source_file):

    transactions = []
    previous_balance = None

    for page_num, page in enumerate(pdf.pages, start=1):

        words = page.extract_words(
            use_text_flow=True,
            keep_blank_chars=False
        )

        # sort visually (top → bottom, left → right)
        words = sorted(words, key=lambda w: (w["top"], w["x0"]))

        i = 0
        while i < len(words):

            text = words[i]["text"]

            # -------------------------
            # DATE ANCHOR
            # -------------------------
            if DATE_RE.fullmatch(text):

                y_ref = words[i]["top"]

                same_line = [
                    w for w in words
                    if abs(w["top"] - y_ref) <= 2
                ]

                description = " ".join(
                    w["text"] for w in same_line
                    if not DATE_RE.fullmatch(w["text"])
                    and not AMOUNT_RE.fullmatch(w["text"])
                    and not ZERO_RE.fullmatch(w["text"])
                ).strip()

                amounts = [
                    (w["x0"], w["text"])
                    for w in same_line
                    if AMOUNT_RE.fullmatch(w["text"])
                    and not ZERO_RE.fullmatch(w["text"])
                ]

                if not amounts:
                    i += 1
                    continue

                amounts = sorted(amounts, key=lambda x: x[0])

                current_balance = float(amounts[-1][1].replace(",", ""))

                txn_amount = None
                if len(amounts) > 1:
                    txn_amount = float(amounts[-2][1].replace(",", ""))

                debit = credit = None

                if txn_amount is not None and previous_balance is not None:
                    delta = current_balance - previous_balance
                    if delta > 0.0001:
                        credit = abs(delta)
                    elif delta < -0.0001:
                        debit = abs(delta)
                else:
                    desc_upper = description.upper()
                    if desc_upper.startswith("CR") or "PROFIT PAID" in desc_upper:
                        credit = txn_amount
                    else:
                        debit = txn_amount

                iso_date = datetime.strptime(text, "%d/%m/%y").strftime("%Y-%m-%d")

                transactions.append({
                    "date": iso_date,
                    "description": description,
                    "debit": debit or 0.0,
                    "credit": credit or 0.0,
                    "balance": current_balance
                })

                previous_balance = current_balance

            i += 1

    return transactions

# =========================================================
# STREAMLIT ENTRY POINT (WRAPPER ONLY)
# =========================================================

def extract_bank_muamalat(pdf_path):
    """
    Streamlit-compatible extractor.
    Parsing logic intentionally unchanged.
    """

    with pdfplumber.open(pdf_path) as pdf:
        txns = parse_transactions_bank_muamalat(
            pdf,
            source_file=pdf_path
        )

    return pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )
