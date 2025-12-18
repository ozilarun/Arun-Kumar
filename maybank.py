import pdfplumber
import pandas as pd
import re
from pathlib import Path

# ===================================================
# MAYBANK STREAMLIT-SAFE UNIVERSAL EXTRACTOR
# (CWS + SME / LARNEY)
# ===================================================

# -------- DATE PATTERNS --------
DATE_CWS = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}")   # 01 Mar 2025
DATE_SME = re.compile(r"^\d{2}/\d{2}")                  # 01/03

# -------- AMOUNT + SIGN + BALANCE --------
AMOUNT_PATTERN = re.compile(
    r"([0-9,]+\.\d{2})\s*([+-])\s*([0-9,]+\.\d{2})"
)

SUMMARY_KEYWORDS = [
    "opening balance", "closing balance",
    "brought forward", "carried forward",
    "total debit", "total credit",
    "ending balance"
]

# ===================================================
def extract_maybank(pdf_path):
    txns = []
    seen = set()

    def to_float(v):
        try:
            return float(str(v).replace(",", "").strip())
        except:
            return 0.0

    def is_summary(text):
        t = text.lower()
        return any(k in t for k in SUMMARY_KEYWORDS)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:

            text = page.extract_text() or ""
            lines = text.split("\n")

            current = None
            buffer_desc = []

            for raw in lines:
                line = raw.strip()
                if not line:
                    continue

                # -------------------------------
                # 1️⃣ Detect new transaction line
                # -------------------------------
                is_cws = DATE_CWS.match(line)
                is_sme = DATE_SME.match(line)

                if not (is_cws or is_sme):
                    if current:
                        buffer_desc.append(line)
                    continue

                m = AMOUNT_PATTERN.search(line)
                if not m:
                    if current:
                        buffer_desc.append(line)
                    continue

                # Save previous transaction
                if current:
                    current["description"] = " ".join(buffer_desc).strip()
                    key = (
                        current["date"],
                        current["description"],
                        current["debit"],
                        current["credit"],
                        current["balance"],
                    )
                    if key not in seen:
                        seen.add(key)
                        txns.append(current)

                buffer_desc = []

                amt = to_float(m.group(1))
                sign = m.group(2)
                bal = to_float(m.group(3))

                debit = amt if sign == "-" else 0.0
                credit = amt if sign == "+" else 0.0

                date = line[:11] if is_cws else line[:5]
                desc_text = line[:m.start()].strip()

                current = {
                    "date": date.strip(),
                    "description": "",
                    "debit": debit,
                    "credit": credit,
                    "balance": bal,
                }

                if desc_text:
                    buffer_desc.append(desc_text)

            # Save last txn on page
            if current:
                current["description"] = " ".join(buffer_desc).strip()
                key = (
                    current["date"],
                    current["description"],
                    current["debit"],
                    current["credit"],
                    current["balance"],
                )
                if key not in seen:
                    seen.add(key)
                    txns.append(current)

    # ===================================================
    # FINAL CLEANUP + ORDER FIX
    # ===================================================
    df = pd.DataFrame(
        txns,
        columns=["date", "description", "debit", "credit", "balance"]
    )

    if df.empty:
        return df

    df["__dt"] = pd.to_datetime(
        df["date"],
        dayfirst=True,
        errors="coerce"
    )

    df = df.sort_values("__dt", ascending=True)
    df = df.drop(columns="__dt").reset_index(drop=True)

    print(f"✔ MAYBANK extracted {len(df)} transactions from {Path(pdf_path).name}")
    return df
