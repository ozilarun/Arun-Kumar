# =====================================================
# RHB.PY – UNIFIED (WITH BERKAT TERAS FIX)
# =====================================================

import re
import pdfplumber
import pandas as pd
from datetime import datetime

try:
    import pytesseract
    from PIL import Image
except:
    pytesseract = None


# =====================================================
# 1️⃣ DIGITAL FORMAT (DD Mon YYYY)
# =====================================================

PATTERN_MON = re.compile(
    r"^\s*(\d{1,2})\s+([A-Za-z]{3})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s*$"
)

def _extract_rhb_mon(pdf_path):
    rows = []
    prev_bal = None
    year = str(datetime.now().year)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                m = PATTERN_MON.match(line)
                if not m:
                    continue

                d, mon, desc, amt, bal = m.groups()
                amt = float(amt.replace(",", ""))
                bal = float(bal.replace(",", ""))

                debit = credit = 0.0
                if prev_bal is not None:
                    if abs(prev_bal - amt - bal) < 1:
                        debit = amt
                    elif abs(prev_bal + amt - bal) < 1:
                        credit = amt

                rows.append({
                    "date": f"{d} {mon} {year}",
                    "description": desc.strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": bal
                })
                prev_bal = bal

    return pd.DataFrame(rows)


# =====================================================
# 2️⃣ BERKAT TERAS FORMAT (DD/MM/YYYY with DR/CR)
# =====================================================

PATTERN_NUMERIC = re.compile(
    r"(?P<date>\d{2}[/-]\d{2}[/-]\d{4})\s+"
    r"(?P<desc>.*?)\s+"
    r"(?P<dr>[0-9,]*\.\d{2})?\s*"
    r"(?P<cr>[0-9,]*\.\d{2})?\s+"
    r"(?P<bal>-?[0-9,]+\.\d{2})"
)

def _extract_rhb_berkat(pdf_path):
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for m in PATTERN_NUMERIC.finditer(text):
                dr = m.group("dr")
                cr = m.group("cr")

                rows.append({
                    "date": m.group("date"),
                    "description": m.group("desc").strip(),
                    "debit": float(dr.replace(",", "")) if dr else 0.0,
                    "credit": float(cr.replace(",", "")) if cr else 0.0,
                    "balance": float(m.group("bal").replace(",", ""))
                })

    return pd.DataFrame(rows)


# =====================================================
# 3️⃣ OCR FALLBACK (UNCHANGED)
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
                r"(\d{2}-\d{2}-\d{4})\s+(.*?)\s+([0-9,]+\.\d{2})?\s+([0-9,]+\.\d{2})",
                text
            ):
                rows.append({
                    "date": m.group(1),
                    "description": m.group(2).strip(),
                    "debit": float(m.group(3).replace(",", "")) if m.group(3) else 0.0,
                    "credit": 0.0,
                    "balance": float(m.group(4).replace(",", ""))
                })

    return pd.DataFrame(rows)


# =====================================================
# 4️⃣ PUBLIC FUNCTION
# =====================================================

def extract_rhb(pdf_path):
    """
    Handles:
    - Standard RHB (DD Mon)
    - Berkat Teras (numeric date DR/CR)
    - OCR fallback
    """

    for extractor in (_extract_rhb_mon, _extract_rhb_berkat, _extract_rhb_ocr):
        try:
            df = extractor(pdf_path)
            if not df.empty:
                return df
        except:
            pass

    return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])
