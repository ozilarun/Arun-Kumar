import fitz  # PyMuPDF
import pdfplumber
import pandas as pd
import re
from datetime import datetime


# =========================================================
# HELPERS
# =========================================================

def _normalize_date(d, year="2025"):
    d = str(d).strip().upper()
    for fmt in ("%d/%m/%Y", "%d/%m", "%d-%m", "%d %b", "%d %b %Y"):
        try:
            if "%Y" in fmt:
                dt = datetime.strptime(d, fmt)
            else:
                dt = datetime.strptime(f"{d}/{year}", fmt + "/%Y")
            return dt.strftime("%d/%m/%Y")
        except:
            pass
    return None


def _clean_amount(x):
    return float(str(x).replace(",", "").replace("+", "").replace("-", ""))


# =========================================================
# ENGINE 1 — PyMuPDF (MYTUTOR – STRONG OCR)
# =========================================================

def _extract_maybank_pymupdf(pdf_path):
    doc = fitz.open(pdf_path)

    DATE_RE = re.compile(r"^(\d{2}/\d{2}|\d{2}-\d{2}|\d{2}\s+[A-Z]{3})$")
    AMT_RE = re.compile(r"\d{1,3}(?:,\d{3})*\.\d{2}[+-]?")

    txns = []
    prev_bal = None

    for page in doc:
        words = page.get_text("words")
        rows = [{"x": w[0], "y": w[1], "t": w[4].strip()} for w in words if w[4].strip()]
        rows.sort(key=lambda r: (round(r["y"], 1), r["x"]))

        used_y = set()

        for r in rows:
            if not DATE_RE.match(r["t"]):
                continue

            y_key = round(r["y"], 1)
            if y_key in used_y:
                continue

            line = [w for w in rows if abs(w["y"] - r["y"]) <= 1.8]
            line.sort(key=lambda w: w["x"])

            date = _normalize_date(r["t"])
            if not date:
                continue

            desc, amts = [], []
            for w in line:
                if w["t"] == r["t"]:
                    continue
                if AMT_RE.match(w["t"]):
                    amts.append(w["t"])
                else:
                    desc.append(w["t"])

            if not amts:
                continue

            bal_txt = amts[-1]
            bal = _clean_amount(bal_txt)
            if bal_txt.endswith("-"):
                bal = -bal

            debit = credit = 0.0

            if prev_bal is not None:
                delta = round(bal - prev_bal, 2)
                if delta > 0:
                    credit = abs(delta)
                elif delta < 0:
                    debit = abs(delta)

            txns.append({
                "date": date,
                "description": " ".join(desc).strip(),
                "debit": debit,
                "credit": credit,
                "balance": bal
            })

            prev_bal = bal
            used_y.add(y_key)

    return pd.DataFrame(txns)


# =========================================================
# ENGINE 2 — pdfplumber (CWS – LINE BASED)
# =========================================================

def _extract_maybank_pdfplumber(pdf_path):
    DATE_LINE = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}")
    AMT_LINE = re.compile(r"([0-9,]+\.\d{2})\s*([+-])\s*([0-9,]+\.\d{2})")

    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                line = line.strip()
                if not DATE_LINE.match(line):
                    continue

                m = AMT_LINE.search(line)
                if not m:
                    continue

                date = _normalize_date(line[:11])
                amt = float(m.group(1).replace(",", ""))
                sign = m.group(2)
                bal = float(m.group(3).replace(",", ""))

                rows.append({
                    "date": date,
                    "description": line[:m.start()].strip(),
                    "debit": amt if sign == "-" else 0.0,
                    "credit": amt if sign == "+" else 0.0,
                    "balance": bal
                })

    return pd.DataFrame(rows)


# =========================================================
# 🚀 FINAL COMBINED EXTRACTOR (USED BY STREAMLIT)
# =========================================================

def extract_maybank(pdf_path):
    df1 = _extract_maybank_pymupdf(pdf_path)
    df2 = _extract_maybank_pdfplumber(pdf_path)

    frames = []
    if not df1.empty:
        frames.append(df1)
    if not df2.empty:
        frames.append(df2)

    if not frames:
        return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])

    df = pd.concat(frames, ignore_index=True)

    # De-duplicate (same date + balance + description)
    df = df.drop_duplicates(subset=["date", "balance", "description"])

    # Final sort
    df["_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df.sort_values("_dt").drop(columns="_dt").reset_index(drop=True)

    return df
