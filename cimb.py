import pdfplumber
import pandas as pd
import re
from pathlib import Path

# ===================================================
# CIMB UNIVERSAL + STREAMLIT SAFE EXTRACTOR
# ===================================================

SUMMARY_KEYWORDS = [
    "opening balance", "closing balance",
    "no of withdrawal", "no of deposit",
    "total withdrawal", "total deposit",
    "end of statement", "baki penutup",
    "ringkasan", "penyata tamat"
]

RAW_TXN_PATTERN = re.compile(
    r"(\d{2}/\d{2}/\d{4})\s+(.*?)\s+(-?[0-9,]*\.?\d*)\s+(-?[0-9,]*\.?\d*)\s+(-?[0-9,]*\.?\d*)$"
)


def extract_cimb(pdf_path):
    txns = []
    seen = set()

    # -----------------------------
    # HELPERS
    # -----------------------------
    def to_float(v):
        try:
            return float(str(v).replace(",", "").strip())
        except:
            return 0.0

    def valid_date(v):
        return bool(re.match(r"\d{2}/\d{2}/\d{4}", str(v).strip()))

    def is_summary(text):
        t = text.lower()
        return any(k in t for k in SUMMARY_KEYWORDS)

    # -----------------------------
    # PDF PROCESSING
    # -----------------------------
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:

            # ===================================================
            # 1️⃣ TABLE EXTRACTION (PRIMARY)
            # ===================================================
            table = page.extract_table()

            if table:
                for row in table[1:]:
                    if not row or all(c in [None, ""] for c in row):
                        continue

                    row = (row + [""] * 6)[:6]
                    date, desc, ref, wd, dep, bal = row

                    if not valid_date(date):
                        continue

                    joined = " ".join(str(c) for c in row if c)
                    if is_summary(joined):
                        continue

                    debit = to_float(wd)
                    credit = to_float(dep)
                    balance = to_float(bal)

                    if debit == 0 and credit == 0:
                        continue

                    desc = str(desc).replace("\n", " ").strip()
                    if ref and str(ref).strip():
                        desc = f"{desc} Ref: {str(ref).strip()}"

                    key = (date, desc, debit, credit, balance)
                    if key in seen:
                        continue
                    seen.add(key)

                    txns.append({
                        "date": date.strip(),
                        "description": desc,
                        "debit": debit,
                        "credit": credit,
                        "balance": balance
                    })

            # ===================================================
            # 2️⃣ RAW TEXT FALLBACK (CRITICAL)
            # ===================================================
            text = page.extract_text() or ""
            for line in text.split("\n"):
                m = RAW_TXN_PATTERN.search(line)
                if not m:
                    continue

                date, desc, wd, dep, bal = m.groups()
                if not valid_date(date):
                    continue

                if is_summary(desc):
                    continue

                debit = to_float(wd)
                credit = to_float(dep)
                balance = to_float(bal)

                if debit == 0 and credit == 0:
                    continue

                key = (date, desc, debit, credit, balance)
                if key in seen:
                    continue
                seen.add(key)

                txns.append({
                    "date": date.strip(),
                    "description": desc.strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

    # ===================================================
    # FINAL CLEANUP + ORDER FIX
    # ===================================================
    df = pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    if df.empty:
        return df

    df["__dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df.sort_values("__dt", ascending=True)
    df = df.drop(columns="__dt").reset_index(drop=True)

    print(f"✔ CIMB extracted {len(df)} transactions from {Path(pdf_path).name}")
    return df
