import pdfplumber
import pandas as pd
import re

# ===================================================
# MAYBANK MTASB — EXTRACTION ONLY (STREAMLIT SAFE)
# COMBINED STRICTLY FROM YOUR 2 NOTEBOOK FILES
# ===================================================

DATE_PATTERN = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}")
AMOUNT_PATTERN = re.compile(r"([0-9,]+\.\d{2})\s*([+-])\s*([0-9,]+\.\d{2})")

SUMMARY_WORDS = [
    "OPENING BALANCE",
    "CLOSING BALANCE",
    "BALANCE B/F",
    "BALANCE C/F",
    "BROUGHT FORWARD",
    "CARRIED FORWARD",
    "TOTAL DEBIT",
    "TOTAL CREDIT",
]

# ---------------------------------------------------

def extract_maybank(pdf_path):
    txns = []
    current_txn = None
    desc_buffer = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):

            text = page.extract_text()
            if not text:
                continue

            lines = text.split("\n")

            for raw_line in lines:
                line = raw_line.strip()
                if not line:
                    continue

                # 1️⃣ Start of new transaction (LINE BASED — KEY FIX)
                if DATE_PATTERN.match(line):

                    # Save previous txn
                    if current_txn:
                        current_txn["description"] = " ".join(desc_buffer).strip()
                        if not any(w in current_txn["description"].upper() for w in SUMMARY_WORDS):
                            txns.append(current_txn)

                    desc_buffer = []

                    m = AMOUNT_PATTERN.search(line)
                    if not m:
                        current_txn = None
                        continue

                    amt = float(m.group(1).replace(",", ""))
                    sign = m.group(2)
                    bal = float(m.group(3).replace(",", ""))

                    debit = amt if sign == "-" else 0.0
                    credit = amt if sign == "+" else 0.0

                    desc_text = line[:m.start()].strip()

                    current_txn = {
                        "date": line[:11],   # DD Mon YYYY (same as your notebook)
                        "description": "",
                        "debit": debit,
                        "credit": credit,
                        "balance": bal,
                    }

                    desc_buffer.append(desc_text)

                else:
                    # 2️⃣ Continuation of description
                    if current_txn:
                        desc_buffer.append(line)

        # Save last transaction
        if current_txn:
            current_txn["description"] = " ".join(desc_buffer).strip()
            if not any(w in current_txn["description"].upper() for w in SUMMARY_WORDS):
                txns.append(current_txn)

    return pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )
