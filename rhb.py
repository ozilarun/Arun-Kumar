# =====================================================
# RHB.PY – UNIFIED & STREAMLIT SAFE
# =====================================================

import re
import pdfplumber
import pandas as pd
from datetime import datetime

# OCR fallback (used ONLY if needed)
try:
    import pytesseract
    from PIL import Image
except Exception:
    pytesseract = None


# =====================================================
# 1️⃣ DIGITAL RHB PARSER (PRIMARY – pdfplumber)
# Preserves original balance-math logic
# =====================================================

TX_LINE_PATTERN = re.compile(
    r"^\s*(\d{1,2})\s*([A-Za-z]{3})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s*$"
)

def _extract_rhb_digital(pdf_path):
    transactions = []
    prev_balance = None

    # Infer year from filename, fallback = current year
    year_match = re.search(r"20\d{2}", pdf_path)
    year = year_match.group(0) if year_match else str(datetime.now().year)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                match = TX_LINE_PATTERN.match(line)
                if not match:
                    continue

                day, month, desc, amount_str, bal_str = match.groups()

                amount = float(amount_str.replace(",", ""))
                curr_balance = float(bal_str.replace(",", ""))

                is_credit = False
                is_debit = False

                # 🔑 Balance-difference logic (UNCHANGED)
                if prev_balance is not None:
                    if abs((prev_balance + amount) - curr_balance) < 0.05:
                        is_credit = True
                    elif abs((prev_balance - amount) - curr_balance) < 0.05:
                        is_debit = True

                # Fallback keywords
                if not is_credit and not is_debit:
                    if any(k in desc.upper() for k in ["CR", "DEPOSIT", "INWARD", "HIBAH", "PROFIT"]):
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

    return pd.DataFrame(transactions)


# =====================================================
# 2️⃣ OCR FALLBACK PARSER (SCANNED PDFs)
# =====================================================

OCR_TX_PATTERN = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})
    \s+
    (?P<body>.*?)
    \s+
    (?P<dr>[0-9,]*\.\d{2})?\s*(?P<dr_flag>-)?\s*
    (?P<cr>[0-9,]*\.\d{2})?
    \s+
    (?P<bal>-?[0-9,]*\.\d{2}[+-]?)
    """,
    re.VERBOSE | re.DOTALL
)

def _extract_rhb_ocr(pdf_path):
    if pytesseract is None:
        return pd.DataFrame()

    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):

            text = page.extract_text()
            if not text or not text.strip():
                img = page.to_image(resolution=300)
                text = pytesseract.image_to_string(img.original)

            if not text:
                continue

            for m in OCR_TX_PATTERN.finditer(text):
                dr = m.group("dr")
                cr = m.group("cr")
                bal = m.group("bal")

                transactions.append({
                    "date": m.group("date"),
                    "description": m.group("body").strip(),
                    "debit": float(dr.replace(",", "")) if dr else 0.0,
                    "credit": float(cr.replace(",", "")) if cr else 0.0,
                    "balance": float(
                        bal.replace(",", "").replace("+", "").replace("-", "")
                    )
                })

    return pd.DataFrame(transactions)


# =====================================================
# 3️⃣ PUBLIC FUNCTION (USED BY app.py)
# =====================================================

def extract_rhb(pdf_path):
    """
    Streamlit-safe RHB extractor.
    Strategy:
    1. Try digital pdfplumber parser
    2. If empty → OCR fallback
    Output columns:
    date | description | debit | credit | balance
    """

    # 1️⃣ Digital first
    try:
        df = _extract_rhb_digital(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass

    # 2️⃣ OCR fallback
    try:
        df = _extract_rhb_ocr(pdf_path)
        if df is not None and not df.empty:
            return df
    except Exception:
        pass

    # 3️⃣ Safe empty return
    return pd.DataFrame(
        columns=["date", "description", "debit", "credit", "balance"]
    )
