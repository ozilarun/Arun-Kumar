# =====================================================
# RHB.PY — FINAL, LOCKED, PURE COMBINATION
# =====================================================

import re
import pdfplumber
import pandas as pd
import os

# =====================================================
# PARSER 1 — BERKAT TERAS (EXACT, UNCHANGED)
# =====================================================

TX_LINE_PATTERN = re.compile(
    r"^\s*(\d{1,2})\s*([A-Za-z]{3})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s*$"
)

def parse_rhb_berkat(pdf_path):
    transactions = []

    year_match = re.search(r"20\d{2}", pdf_path)
    year = year_match.group(0) if year_match else "2025"

    prev_balance = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                match = TX_LINE_PATTERN.match(line)

                if match:
                    day, month, desc, amount_str, bal_str = match.groups()

                    amount = float(amount_str.replace(",", ""))
                    curr_balance = float(bal_str.replace(",", ""))

                    is_credit = False
                    is_debit = False

                    if prev_balance is not None:
                        if abs((prev_balance + amount) - curr_balance) < 0.05:
                            is_credit = True
                        elif abs((prev_balance - amount) - curr_balance) < 0.05:
                            is_debit = True

                    if not is_credit and not is_debit:
                        credit_keywords = [
                            "CR", "DEPOSIT", "INWARD",
                            "HIBAH", "PROFIT", "DEP", "CHEQUE"
                        ]
                        if any(k in desc.upper() for k in credit_keywords):
                            is_credit = True
                        else:
                            is_debit = True

                    transactions.append({
                        "date": f"{day} {month} {year}",
                        "description": desc.strip(),
                        "debit": amount if is_debit else 0.0,
                        "credit": amount if is_credit else 0.0,
                        "balance": curr_balance
                    })

                    prev_balance = curr_balance

                elif transactions and line.strip():
                    ignore = ["RHB Bank", "Page", "Statement Period",
                              "Balance", "Total Count", "Member of PIDM"]
                    if not any(k in line for k in ignore):
                        if not re.match(r"^\s*\d{1,2}\s*[A-Za-z]{3}", line):
                            transactions[-1]["description"] += " " + line.strip()

    return pd.DataFrame(transactions)


# =====================================================
# PARSER 2 — AZLAN / DIGITAL RHB (UNCHANGED)
# =====================================================

def parse_rhb_azlan(pdf_path):
    transactions = []

    year_match = re.search(r"20\d{2}", pdf_path)
    year = year_match.group(0) if year_match else "2024"

    prev_balance = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                match = TX_LINE_PATTERN.match(line)

                if match:
                    day, month, desc, amount_str, bal_str = match.groups()
                    amount = float(amount_str.replace(",", ""))
                    curr_balance = float(bal_str.replace(",", ""))

                    is_credit = False
                    is_debit = False

                    if prev_balance is not None:
                        if abs((prev_balance + amount) - curr_balance) < 0.05:
                            is_credit = True
                        elif abs((prev_balance - amount) - curr_balance) < 0.05:
                            is_debit = True

                    if not is_credit and not is_debit:
                        if any(x in desc.upper() for x in ["CR", "DEPOSIT", "INWARD"]):
                            is_credit = True
                        else:
                            is_debit = True

                    transactions.append({
                        "date": f"{day} {month} {year}",
                        "description": desc.strip(),
                        "debit": amount if is_debit else 0.0,
                        "credit": amount if is_credit else 0.0,
                        "balance": curr_balance
                    })

                    prev_balance = curr_balance

                elif transactions and line.strip():
                    if not any(k in line for k in ["RHB Bank", "Page", "Statement Period", "Balance", "Total Count"]):
                        if not re.match(r"^\s*\d{1,2}\s*[A-Za-z]{3}", line):
                            transactions[-1]["description"] += " " + line.strip()

    return pd.DataFrame(transactions)


# =====================================================
# PARSER 3 — OCR / NUMERIC DATE (FIXED WRAPPER, LOGIC UNCHANGED)
# =====================================================

import pytesseract
from PIL import Image

TEMP_DIR = "temp_ocr_images"
os.makedirs(TEMP_DIR, exist_ok=True)

def extract_text(page, page_num):
    text = page.extract_text()
    if text and text.strip():
        return text

    img_path = f"{TEMP_DIR}/page_{page_num}.png"
    page.to_image(resolution=300).save(img_path)
    return pytesseract.image_to_string(Image.open(img_path))


def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()
        if re.match(r"^\d{2}-\d{2}-\d{4}", line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return "\n".join(merged)


txn_pattern = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})
    \s+
    (?P<body>.*?)
    \s+
    (?P<dr>[0-9,]*\.\d{2})?
    \s*
    (?P<dr_flag>-)?\s*
    (?P<cr>[0-9,]*\.\d{2})?
    \s+
    (?P<bal>-?[0-9,]*\.\d{2}[+-]?)
    """,
    re.VERBOSE | re.DOTALL
)

def num(x):
    if not x:
        return 0.0

    x = x.strip()

    # Handle trailing + or -
    sign = -1 if x.endswith("-") or x.startswith("-") else 1

    x = x.replace(",", "").replace("+", "").replace("-", "")
    return sign * float(x)



def parse_transactions(text, page_num):
    text = preprocess_rhb_text(text)
    txns = []

    for m in txn_pattern.finditer(text):
        txns.append({
            "date": m.group("date"),
            "description": m.group("body").strip(),
            "debit": num(m.group("dr")),
            "credit": num(m.group("cr")),
            "balance": num(m.group("bal"))
        })

    return txns


def parse_rhb_ocr(pdf_path):
    all_txns = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = extract_text(page, page_num)
            txns = parse_transactions(text, page_num)
            if txns:
                all_txns.extend(txns)

    return pd.DataFrame(all_txns)


# =====================================================
# STREAMLIT ENTRY POINT (DISPATCHER ONLY)
# =====================================================

def extract_rhb(pdf_path):
    """
    STRICT priority, no logic sharing:
    1. Berkat Teras
    2. Azlan Digital
    3. OCR / Numeric
    """

    for parser in (
        parse_rhb_berkat,
        parse_rhb_azlan,
        parse_rhb_ocr
    ):
        try:
            df = parser(pdf_path)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass

    return pd.DataFrame(
        columns=["date", "description", "debit", "credit", "balance"]
    )
