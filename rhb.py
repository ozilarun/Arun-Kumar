# rhb.py
# ---------------------------------------
# RHB Bank Statement Extractor (Streamlit)
# ---------------------------------------

import pdfplumber
import pytesseract
from PIL import Image
import pandas as pd
import regex as re
import tempfile
import os

# -----------------------------
# OCR helper
# -----------------------------
def extract_text(page, page_num):
    text = page.extract_text()
    if text and text.strip():
        return text

    # OCR fallback
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as img_file:
        page.to_image(resolution=300).save(img_file.name)
        ocr_text = pytesseract.image_to_string(Image.open(img_file.name))
        os.unlink(img_file.name)
        return ocr_text


# -----------------------------
# Preprocess text
# -----------------------------
def preprocess_text(text):
    lines = text.split("\n")
    merged = []
    buffer = ""

    for line in lines:
        line = line.strip()
        if re.match(r"^\d{1,2}\s+[A-Za-z]{3}", line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return merged


# -----------------------------
# Transaction regex
# -----------------------------
TX_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<day>\d{1,2})\s+
    (?P<month>[A-Za-z]{3})\s+
    (?P<desc>.*?)
    \s+
    (?P<amount>[0-9,]+\.\d{2})
    \s+
    (?P<balance>-?[0-9,]+\.\d{2})
    \s*$
    """,
    re.VERBOSE
)


# -----------------------------
# Main extractor
# -----------------------------
def extract_rhb(pdf_path):
    transactions = []
    prev_balance = None

    year_match = re.search(r"(20\d{2})", pdf_path)
    year = year_match.group(1) if year_match else "2025"

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw_text = extract_text(page, page_num)
            if not raw_text:
                continue

            lines = preprocess_text(raw_text)

            for line in lines:
                m = TX_PATTERN.match(line)
                if not m:
                    continue

                day = m.group("day")
                month = m.group("month")
                desc = m.group("desc").strip()
                amount = float(m.group("amount").replace(",", ""))
                balance = float(m.group("balance").replace(",", ""))

                # Determine debit / credit
                debit = 0.0
                credit = 0.0

                if prev_balance is not None:
                    if abs(prev_balance + amount - balance) < 0.05:
                        credit = amount
                    elif abs(prev_balance - amount - balance) < 0.05:
                        debit = amount
                    else:
                        # fallback keyword logic
                        if any(k in desc.upper() for k in ["CR", "DEPOSIT", "INWARD", "PROFIT", "HIBAH"]):
                            credit = amount
                        else:
                            debit = amount
                else:
                    debit = amount  # first row fallback

                transactions.append({
                    "date": f"{day} {month} {year}",
                    "description": desc,
                    "debit": round(debit, 2),
                    "credit": round(credit, 2),
                    "balance": round(balance, 2),
                })

                prev_balance = balance

    if not transactions:
        return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])

    df = pd.DataFrame(transactions)

    # Sort safely
    df["_dt"] = pd.to_datetime(df["date"], format="%d %b %Y", errors="coerce")
    df = df.sort_values("_dt").drop(columns="_dt").reset_index(drop=True)

    return df
