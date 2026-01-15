import pdfplumber
import pandas as pd
import re

from pdf2image import convert_from_path
import pytesseract
from PIL import Image

# ==========================
# REGEX
# ==========================
TX_PATTERN = re.compile(
    r"^\s*(\d{1,2})\s*([A-Za-z]{3})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s*$"
)

CREDIT_HINTS = [
    "CR", "CREDIT", "DEPOSIT", "INWARD",
    "PROFIT", "HIBAH", "GIRO", "CHEQUE"
]

IGNORE_LINES = [
    "RHB BANK",
    "PAGE",
    "STATEMENT",
    "BALANCE",
    "TOTAL",
    "MEMBER OF PIDM",
]

# ==========================
# CORE LINE PARSER
# ==========================
def parse_lines(lines, year):
    rows = []
    prev_balance = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if any(x in line.upper() for x in IGNORE_LINES):
            continue

        m = TX_PATTERN.match(line)
        if not m:
            continue

        day, mon, desc, amt_str, bal_str = m.groups()

        amount = float(amt_str.replace(",", ""))
        balance = float(bal_str.replace(",", ""))

        debit = credit = 0.0

        if prev_balance is not None:
            if abs(prev_balance + amount - balance) < 0.05:
                credit = amount
            elif abs(prev_balance - amount - balance) < 0.05:
                debit = amount
            else:
                if any(k in desc.upper() for k in CREDIT_HINTS):
                    credit = amount
                else:
                    debit = amount
        else:
            if any(k in desc.upper() for k in CREDIT_HINTS):
                credit = amount
            else:
                debit = amount

        rows.append({
            "date": f"{day} {mon} {year}",
            "description": desc.strip(),
            "debit": debit,
            "credit": credit,
            "balance": balance,
        })

        prev_balance = balance

    return rows

# ==========================
# MAIN EXTRACTOR
# ==========================
def extract_rhb(pdf_path):
    transactions = []

    # Detect year from filename
    y = re.search(r"(20\d{2})", pdf_path)
    year = y.group(1) if y else "2024"

    # ======================
    # PASS 1 — TEXT PDF
    # ======================
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            lines = text.splitlines()
            rows = parse_lines(lines, year)

            if rows:
                transactions.extend(rows)

    # ======================
    # PASS 2 — OCR FALLBACK
    # ======================
    if not transactions:
        try:
            images = convert_from_path(pdf_path, dpi=300)

            for img in images:
                gray = img.convert("L")
                text = pytesseract.image_to_string(gray, config="--psm 6")

                lines = text.splitlines()
                rows = parse_lines(lines, year)

                if rows:
                    transactions.extend(rows)

        except Exception as e:
            print("⚠ RHB OCR failed:", e)

    df = pd.DataFrame(
        transactions,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    print(f"✔ RHB extracted {len(df)} rows from {pdf_path}")
    return df
