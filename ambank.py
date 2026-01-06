import pdfplumber
import pandas as pd
import re

# ============================================================
# =============== AMBANK TYPE 1 (UNCHANGED)
# ============================================================

def extract_ambank_type1(pdf_path):
    rows = []
    current_tx = None
    prev_balance = None

    year_match = re.search(r"20\d{2}", pdf_path)
    year = year_match.group(0) if year_match else "2024"

    date_start_pattern = re.compile(r"^(\d{2})([A-Za-z]{3})")

    def parse_amount(amount_str):
        if not amount_str:
            return 0.0
        is_negative = "DR" in amount_str.upper()
        clean_str = (
            amount_str.upper()
            .replace("DR", "")
            .replace("CR", "")
            .replace(",", "")
            .strip()
        )
        try:
            val = float(clean_str)
            return -val if is_negative else val
        except:
            return 0.0

    def clean_date(day, mon, year):
        month_map = {
            "JAN": "January", "FEB": "February", "MAR": "March", "MAC": "March",
            "APR": "April", "MAY": "May", "JUN": "June", "JUL": "July",
            "AUG": "August", "SEP": "September", "SEPT": "September",
            "OCT": "October", "NOV": "November", "DEC": "December"
        }
        return f"{day} {month_map.get(mon.upper(), mon)} {year}"

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                date_match = date_start_pattern.match(line)

                if date_match:
                    day, mon = date_match.groups()
                    parts = line.split()

                    amounts = []
                    desc_parts = []

                    for i in range(len(parts) - 1, -1, -1):
                        if re.match(r"[\d,]+\.\d{2}[A-Za-z]*$", parts[i]):
                            amounts.insert(0, parts[i])
                        else:
                            desc_parts = parts[:i+1]
                            break

                    description = " ".join(desc_parts[1:])
                    parsed_vals = [parse_amount(x) for x in amounts]

                    if len(parsed_vals) == 1:
                        prev_balance = parsed_vals[0]
                        continue

                    elif len(parsed_vals) >= 2:
                        tx_amount = parsed_vals[0]
                        balance = parsed_vals[-1]

                        debit = credit = 0.0

                        if prev_balance is not None:
                            diff = round(balance - prev_balance, 2)
                            if abs(diff - tx_amount) < 0.05:
                                credit = tx_amount
                            elif abs(diff + tx_amount) < 0.05:
                                debit = tx_amount
                            else:
                                if any(x in description.upper() for x in ["CREDIT", "CR", "TRF FROM"]):
                                    credit = tx_amount
                                else:
                                    debit = tx_amount

                        rows.append({
                            "date": clean_date(day, mon, year),
                            "description": description,
                            "debit": debit,
                            "credit": credit,
                            "balance": balance
                        })
                        prev_balance = balance

                else:
                    if current_tx and not re.search(r"\d+\.\d{2}", line):
                        current_tx["description"] += " " + line

    return pd.DataFrame(rows)


# ============================================================
# =============== AMBANK TYPE 2 (UNCHANGED)
# ============================================================

def extract_ambank_type2(pdf_path):
    transactions = []
    prev_balance = None

    year_match = re.search(r"20\d{2}", pdf_path)
    year = year_match.group(0) if year_match else "2024"

    TX_PATTERN = re.compile(
        r"^(\d{2})([A-Za-z]{3})\s+(.*?)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})$"
    )

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                m = TX_PATTERN.match(line.strip())
                if not m:
                    continue

                day, mon, desc, amt_str, bal_str = m.groups()
                amount = float(amt_str.replace(",", ""))
                balance = float(bal_str.replace(",", ""))

                debit = credit = 0.0

                if prev_balance is not None:
                    if abs(prev_balance + amount - balance) < 0.05:
                        credit = amount
                    else:
                        debit = amount

                transactions.append({
                    "date": f"{day} {mon} {year}",
                    "description": desc.strip(),
                    "debit": debit,
                    "credit": credit,
                    "balance": balance
                })

                prev_balance = balance

    return pd.DataFrame(transactions)


# ============================================================
# =============== AMBANK TYPE 3 (UNCHANGED)
# ============================================================

def extract_ambank_type3(pdf_path):
    df = extract_ambank_type2(pdf_path)

    if not df.empty:
        return df

    # no transactions → extract opening balance
    opening = 0.0
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                m = re.search(r"OPENING BALANCE\s+([0-9,]+\.\d{2})", text.upper())
                if m:
                    opening = float(m.group(1).replace(",", ""))
                    break

    return pd.DataFrame([{
        "date": "",
        "description": "Balance b/f (No transactions)",
        "debit": 0.0,
        "credit": 0.0,
        "balance": opening
    }])


# ============================================================
# =============== MASTER AMBANK EXTRACTOR
# ============================================================

def extract_ambank(pdf_path):
    """
    Tries all known AmBank formats.
    Returns FIRST successful DataFrame.
    """

    for extractor in (
        extract_ambank_type1,
        extract_ambank_type2,
        extract_ambank_type3
    ):
        try:
            df = extractor(pdf_path)
            if df is not None and not df.empty:
                return df
        except:
            continue

    return pd.DataFrame(columns=["date", "description", "debit", "credit", "balance"])
