# =====================================================
# RHB.PY – FINAL, VERIFIED, STREAMLIT SAFE
# =====================================================

import re
import pdfplumber
import pandas as pd
from datetime import datetime

# OCR optional
try:
    import pytesseract
    from PIL import Image
except:
    pytesseract = None


# =====================================================
# 1️⃣ ORIGINAL BERKAT TERAS REGEX (DO NOT CHANGE)
# Handles: 04 Apr LOCAL CHQ DEP 70,000.00 215,382.56
# =====================================================

TX_LINE_PATTERN = re.compile(
    r"^\s*(\d{1,2})\s*([A-Za-z]{3})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s*$"
)


def _extract_rhb_berkat(pdf_path):
    rows = []
    prev_balance = None
    year = str(datetime.now().year)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                m = TX_LINE_PATTERN.match(line)
                if not m:
                    continue

                day, mon, desc, amt_str, bal_str = m.groups()
                amount = float(amt_str.replace(",", ""))
                balance = float(bal_str.replace(",", ""))

                debit = credit = 0.0

                # 🔑 ORIGINAL LOGIC (THIS IS WHAT WORKED)
                if prev_balance is not None:
                    if abs((prev_balance + amount) - balance) < 1:
                        credit = amount
                    elif abs((prev_balance - amount) - balance) < 1:
                        debit = amount

                rows.append({
                    "date": f"{day} {mon} {year}",
                    "description": desc.strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

                prev_balance = balance

    return pd.DataFrame(rows)


# =====================================================
# 2️⃣ NUMERIC DATE FORMAT (DR / CR COLUMNS)
# =====================================================

NUMERIC_PATTERN = re.compile(
    r"(?P<date>\d{2}[/-]\d{2}[/-]\d{4})\s+"
    r"(?P<desc>.*?)\s+"
    r"(?P<dr>[0-9,]*\.\d{2})?\s*"
    r"(?P<cr>[0-9,]*\.\d{2})?\s+"
    r"(?P<bal>-?[0-9,]+\.\d{2})"
)


def _extract_rhb_numeric(pdf_path):
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for m in NUMERIC_PATTERN.finditer(text):
                dr = m.group("dr")
                cr = m.group("cr")
                balance = float(m.group("bal").replace(",", ""))

                debit = float(dr.replace(",", "")) if dr else 0.0
                credit = float(cr.replace(",", "")) if cr else 0.0

                # 🔥 SAFETY: if BOTH missing → infer via balance
                if debit == 0 and credit == 0 and rows:
                    prev_balance = rows[-1]["balance"]
                    delta = round(balance - prev_balance, 2)
                    if delta > 0:
                        credit = delta
                    elif delta < 0:
                        debit = abs(delta)

                rows.append({
                    "date": m.group("date"),
                    "description": m.group("desc").strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

    return pd.DataFrame(rows)


# =====================================================
# 3️⃣ OCR FALLBACK (LAST RESORT)
# =====================================================

def _extract_rhb_ocr(pdf_path):
    if pytesseract is None:
        return pd.DataFrame()

    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            img = page.to_image(resolution=300)
            text = pytesseract.image_to_string(img.original)

            for m in re.finditer(
                r"(\d{2}-\d{2}-\d{4})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})",
                text
            ):
                rows.append({
                    "date": m.group(1),
                    "description": m.group(2).strip(),
                    "debit": 0.0,
                    "credit": float(m.group(3).replace(",", "")),
                    "balance": float(m.group(4).replace(",", ""))
                })

    return pd.DataFrame(rows)


# =====================================================
# 4️⃣ PUBLIC FUNCTION (USED BY app.py)
# ORDER MATTERS – DO NOT CHANGE
# =====================================================

def extract_rhb(pdf_path):
    """
    Extraction priority:
    1. Berkat Teras (text month, balance inference) ✅
    2. Numeric DR/CR format
    3. OCR fallback
    """

    for extractor in (
        _extract_rhb_berkat,   # 🔥 FIRST (fixes April)
        _extract_rhb_numeric,
        _extract_rhb_ocr
    ):
        try:
            df = extractor(pdf_path)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass

    return pd.DataFrame(
        columns=["date", "description", "debit", "credit", "balance"]
    )
