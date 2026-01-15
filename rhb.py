# rhb.py
# =========================================================
# RHB BANK STATEMENT EXTRACTOR (STREAMLIT SAFE)
# =========================================================

import pdfplumber
import pytesseract
from PIL import Image
import pandas as pd
import regex as re
import tempfile
import os


# ---------------------------------------------------------
# OCR FALLBACK
# ---------------------------------------------------------
def extract_text(page, page_num):
    text = page.extract_text()
    if text and text.strip():
        return text

    # OCR fallback
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img:
        page.to_image(resolution=300).save(img.name)
        ocr_text = pytesseract.image_to_string(Image.open(img.name))
        os.unlink(img.name)
        return ocr_text


# ---------------------------------------------------------
# PREPROCESS TEXT (MERGE MULTI-LINE TXNS)
# ---------------------------------------------------------
def preprocess_lines(text):
    lines = text.split("\n")
    merged = []
    buffer = ""

    for line in lines:
        line = line.strip()
        if re.match(r"^\d{1,2}\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)", line, re.I):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return merged


# ---------------------------------------------------------
# TRANSACTION REGEX (OCR-TOLERANT)
# ---------------------------------------------------------
TX_PATTERN = re.compile(
    r"""
    (?P<day>\d{1,2})\s+
    (?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)
    .*?
    (?P<amount>[0-9,]+\.\d{2})
    \s+
    (?P<balance>-?[0-9,]+\.\d{2})
    """,
    re.IGNORECASE | re.VERBOSE
)


# ---------------------------------------------------------
# MAIN EXTRACTOR (REQUIRED BY app.py)
# ---------------------------------------------------------
def extract_rhb(pdf_path):
    transactions = []
    prev_balance = None

    # Infer year from filename
    year_match = re.search(r"(20\d{2})", pdf_path)
    year = year_match.group(1) if year_match else "2025"

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = extract_text(page, page_num)
            if not raw_text:
                continue

            lines = preprocess_lines(raw_text)

            for line in lines:
                m = TX_PATTERN.search(line)
                if not m:
                    continue

                day = m.group("day")
                month = m.group("month").title()
                amount = float(m.group("amount").replace(",", ""))
                balance = float(m.group("balance").replace(",", ""))

                # Clean description
                desc = re.sub(r"\s+", " ", line)
                desc = re.sub(r"[0-9,]+\.\d{2}\s+-?[0-9,]+\.\d{2}", "", desc).strip()

                debit = 0.0
                credit = 0.0

                # Balance math detection (PRIMARY)
                if prev_balance is not None:
                    if abs(prev_balance + amount - balance) < 1:
                        credit = amount
                    elif abs(prev_balance - amount - balance) < 1:
                        debit = amount
                    else:
                        # Fallback keyword detection
                        if any(k in desc.upper() for k in ["CR", "DEPOSIT", "INWARD", "HIBAH", "PROFIT"]):
                            credit = amount
                        else:
                            debit = amount
                else:
                    debit = amount  # First row fallback

                transactions.append({
                    "date": f"{day} {month} {year}",
                    "description": desc,
                    "debit": round(debit, 2),
                    "credit": round(credit, 2),
                    "balance": round(balance, 2)
                })

                prev_balance = balance

    # -----------------------------------------------------
    # SAFETY: NEVER RETURN EMPTY SCHEMA
    # -----------------------------------------------------
    if not transactions:
        return pd.DataFrame(
            columns=["date", "description", "debit", "credit", "balance"]
        )

    df = pd.DataFrame(transactions)

    # Sort by date
    df["_dt"] = pd.to_datetime(df["date"], format="%d %b %Y", errors="coerce")
    df = df.sort_values("_dt").drop(columns="_dt").reset_index(drop=True)

    return df
