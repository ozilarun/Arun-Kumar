# rhb.py
# ============================================================
# RHB BANK STATEMENT EXTRACTOR
# OCR-BASED | STREAMLIT-COMPATIBLE | VERIFIED
# ============================================================

import pdfplumber
import pytesseract
from PIL import Image
import pandas as pd
import regex as re
import tempfile
import os


# ------------------------------------------------------------
# NUMBER PARSER
# ------------------------------------------------------------
def num(x):
    try:
        return float(str(x).replace(",", "").replace("+", "").replace("-", ""))
    except:
        return 0.0


# ------------------------------------------------------------
# EXTRACT TEXT (PDF → OCR FALLBACK)
# ------------------------------------------------------------
def extract_text(page, page_num):
    text = page.extract_text()
    if text and text.strip():
        return text

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img:
        page.to_image(resolution=300).save(img.name)
        ocr_text = pytesseract.image_to_string(Image.open(img.name))
        os.unlink(img.name)
        return ocr_text


# ------------------------------------------------------------
# PREPROCESS TEXT (MERGE MULTI-LINE TRANSACTIONS)
# ------------------------------------------------------------
def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged = []
    buffer = ""

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


# ------------------------------------------------------------
# TRANSACTION REGEX (MATCHES RHB FORMAT)
# ------------------------------------------------------------
TX_PATTERN = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})      # Date
    \s+
    (?P<body>.*?)                   # Description
    \s+
    (?P<dr>[0-9,]*\.\d{2})?          # Debit (optional)
    \s*
    (?P<cr>[0-9,]*\.\d{2})?          # Credit (optional)
    \s+
    (?P<bal>-?[0-9,]*\.\d{2}[+-]?)   # Balance
    """,
    re.VERBOSE | re.DOTALL
)


# ------------------------------------------------------------
# MAIN EXTRACTOR (CALLED BY app.py)
# ------------------------------------------------------------
def extract_rhb(pdf_path):

    transactions = []

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):

            raw = extract_text(page, page_num)
            if not raw:
                continue

            processed = preprocess_rhb_text(raw)

            for m in TX_PATTERN.finditer(processed):

                raw_date = m.group("date")
                desc = m.group("body").strip()

                debit = num(m.group("dr"))
                credit = num(m.group("cr"))
                balance = num(m.group("bal"))

                # 🔑 NORMALIZE DATE FORMAT FOR app.py
                dt = pd.to_datetime(raw_date, format="%d-%m-%Y", errors="coerce")
                date_str = dt.strftime("%d %b %Y") if not pd.isna(dt) else raw_date

                transactions.append({
                    "date": date_str,          # <-- CRITICAL FIX
                    "description": desc,
                    "debit": round(debit, 2),
                    "credit": round(credit, 2),
                    "balance": round(balance, 2)
                })

    # --------------------------------------------------------
    # SAFETY RETURN (PREVENTS STREAMLIT CRASH)
    # --------------------------------------------------------
    if not transactions:
        return pd.DataFrame(
            columns=["date", "description", "debit", "credit", "balance"]
        )

    df = pd.DataFrame(transactions)

    # Final sort
    df["_dt"] = pd.to_datetime(df["date"], format="%d %b %Y", errors="coerce")
    df = df.sort_values("_dt").drop(columns="_dt").reset_index(drop=True)

    return df
