import pdfplumber
import pandas as pd
import re
from datetime import datetime

# =========================================================
# MONTH MAP (UNCHANGED)
# =========================================================

MONTH_MAP = {
    "01": "January", "02": "February", "03": "March",
    "04": "April",   "05": "May",      "06": "June",
    "07": "July",    "08": "August",   "09": "September",
    "10": "October", "11": "November", "12": "December"
}

# =========================================================
# HELPERS (UNCHANGED)
# =========================================================

def detect_month_from_df(df):
    if df.empty:
        return "UnknownMonth"
    try:
        yyyy, mm, dd = df.iloc[0]["date"].split("-")
        return f"{MONTH_MAP.get(mm, 'Unknown')} {yyyy}"
    except:
        return "UnknownMonth"


DATE_RE = re.compile(r"\d{1,2}/\d{2}/\d{2}")
AMOUNT_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}-?")
ZERO_RE = re.compile(r"^0?\.00-?$")

# =========================================================
# SUMMARY TOTALS (UNCHANGED)
# =========================================================

def extract_agrobank_summary_totals(pdf):
    total_debit = None
    total_credit = None

    for page in reversed(pdf.pages):
        text = page.extract_text() or ""
        for line in text.splitlines():
            u = line.upper()
            if "TOTAL DEBIT" in u:
                m = re.search(r"([\d,]+\.\d{2})", line)
                if m:
                    total_debit = float(m.group(1).replace(",", ""))
            if "TOTAL CREDIT" in u:
                m = re.search(r"([\d,]+\.\d{2})", line)
                if m:
                    total_credit = float(m.group(1).replace(",", ""))
        if total_debit is not None and total_credit is not None:
            break

    return total_debit, total_credit

# =========================================================
# CORE PARSER (UNCHANGED)
# =========================================================

def parse_agro_bank(pdf, source_file):
    transactions = []
    previous_balance = None

    summary_debit, summary_credit = extract_agrobank_summary_totals(pdf)

    for page_num, page in enumerate(pdf.pages, start=1):
        words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
        words = sorted(words, key=lambda w: (w["top"], w["x0"]))

        i = 0
        while i < len(words):
            text = words[i]["text"]

            if DATE_RE.fullmatch(text):
                y_ref = words[i]["top"]
                same_line = [w for w in words if abs(w["top"] - y_ref) <= 2]

                description = " ".join(
                    w["text"] for w in same_line
                    if not DATE_RE.fullmatch(w["text"])
                    and not AMOUNT_RE.fullmatch(w["text"])
                    and not ZERO_RE.fullmatch(w["text"])
                ).strip()

                amounts = [
                    (w["x0"], w["text"])
                    for w in same_line
                    if AMOUNT_RE.fullmatch(w["text"])
                ]

                if not amounts:
                    i += 1
                    continue

                amounts.sort(key=lambda x: x[0])

                def to_float(v):
                    v = v.replace(",", "")
                    if v.endswith("-"):
                        return -float(v[:-1])
                    return float(v)

                balance = to_float(amounts[-1][1])
                iso_date = datetime.strptime(text, "%d/%m/%y").strftime("%Y-%m-%d")
                desc_upper = description.upper()

                if "BEGINNING BALANCE" in desc_upper:
                    previous_balance = balance
                    i += 1
                    continue

                if "CLOSING BALANCE" in desc_upper:
                    i += 1
                    continue

                debit = credit = None

                if previous_balance is not None:
                    delta = balance - previous_balance
                    if delta > 0.0001:
                        credit = round(delta, 2)
                    elif delta < -0.0001:
                        debit = round(abs(delta), 2)

                transactions.append({
                    "date": iso_date,
                    "description": description,
                    "debit": debit or 0.0,
                    "credit": credit or 0.0,
                    "balance": round(balance, 2)
                })

                previous_balance = balance

            i += 1

    # Summary check flag (unchanged)
    mismatch = False
    if summary_debit is not None:
        if abs(sum(t["debit"] for t in transactions) - summary_debit) > 0.01:
            mismatch = True
    if summary_credit is not None:
        if abs(sum(t["credit"] for t in transactions) - summary_credit) > 0.01:
            mismatch = True

    return transactions

# =========================================================
# STREAMLIT ENTRY POINT (NEW WRAPPER ONLY)
# =========================================================

def extract_agro_bank(pdf_path):
    """
    Streamlit-compatible extractor.
    DO NOT modify parsing logic.
    """

    with pdfplumber.open(pdf_path) as pdf:
        txns = parse_agro_bank(pdf, source_file=pdf_path)

    return pd.DataFrame(txns, columns=[
        "date", "description", "debit", "credit", "balance"
    ])
