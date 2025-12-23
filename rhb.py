# =====================================================
# RHB.PY — FINAL, LOCKED, PURE COMBINATION
# =====================================================

import re
import pdfplumber
import pandas as pd

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
# PARSER 3 — OCR / NUMERIC DATE (UNCHANGED)
# =====================================================

def parse_rhb_ocr(pdf_path):
    try:
        import pytesseract
        from PIL import Image
    except:
        return pd.DataFrame()

    txn_pattern = re.compile(
        r"(?P<date>\d{2}-\d{2}-\d{4})\s+"
        r"(?P<body>.*?)\s+"
        r"(?P<dr>[0-9,]*\.\d{2})?\s*"
        r"(?P<cr>[0-9,]*\.\d{2})?\s+"
        r"(?P<bal>-?[0-9,]*\.\d{2})",
        re.DOTALL
    )

    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            img = page.to_image(resolution=300)
            text = pytesseract.image_to_string(img.original)

            for m in txn_pattern.finditer(text):
                rows.append({
                    "date": m.group("date"),
                    "description": m.group("body").strip(),
                    "debit": float(m.group("dr").replace(",", "")) if m.group("dr") else 0.0,
                    "credit": float(m.group("cr").replace(",", "")) if m.group("cr") else 0.0,
                    "balance": float(m.group("bal").replace(",", ""))
                })

    return pd.DataFrame(rows)


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
