import pdfplumber
import pandas as pd
import re


def extract_ocbc(pdf_path):
    rows = []
    current_tx = None
    prev_balance = None
    balance_bf = None

    tx_start_pattern = re.compile(
        r"^(\d{2})\s+"
        r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+"
        r"(\d{4})\s+(.*)"
    )

    balance_bf_pattern = re.compile(r"Balance B/F\s+([\d,]+\.\d{2})")

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            # ---- Balance B/F first (important for empty months)
            if balance_bf is None:
                m = balance_bf_pattern.search(text)
                if m:
                    balance_bf = float(m.group(1).replace(",", ""))
                    prev_balance = balance_bf

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                m = tx_start_pattern.match(line)

                if m:
                    day, mon, year, rest = m.groups()
                    parts = rest.split()

                    amounts = []
                    desc_parts = []

                    for i in range(len(parts) - 1, -1, -1):
                        if re.match(r"[\d,]+\.\d{2}$", parts[i]):
                            amounts.insert(0, parts[i])
                        else:
                            desc_parts = parts[:i+1]
                            break

                    if len(amounts) < 2:
                        continue

                    tx_amount = float(amounts[0].replace(",", ""))
                    balance = float(amounts[-1].replace(",", ""))

                    description = " ".join(desc_parts)
                    desc_upper = description.upper()

                    debit = 0.0
                    credit = 0.0

                    if "CR /IB" in desc_upper or "CR INWARD" in desc_upper:
                        credit = tx_amount
                    elif (
                        "DR /IB" in desc_upper
                        or "DEBIT AS ADVISED" in desc_upper
                        or "DUITNOW SC" in desc_upper
                    ):
                        debit = tx_amount
                    elif prev_balance is not None:
                        diff = round(balance - prev_balance, 2)
                        if abs(diff - tx_amount) < 0.05:
                            credit = tx_amount
                        elif abs(diff + tx_amount) < 0.05:
                            debit = tx_amount

                    rows.append({
                        "date": f"{day} {mon} {year}",
                        "description": description,
                        "debit": debit,
                        "credit": credit,
                        "balance": balance
                    })

                    prev_balance = balance
                    current_tx = rows[-1]

                else:
                    if current_tx:
                        if (
                            not re.search(r"[\d,]+\.\d{2}", line)
                            and not any(x in line.upper() for x in [
                                "PAGE", "STATEMENT", "SUMMARY",
                                "TOTAL", "WITHDRAWALS", "DEPOSITS"
                            ])
                        ):
                            current_tx["description"] += " " + line

    # ---- Handle month with NO transactions
    if not rows and balance_bf is not None:
        rows.append({
            "date": "Balance B/F",
            "description": "Balance B/F",
            "debit": 0.0,
            "credit": 0.0,
            "balance": balance_bf
        })

    return pd.DataFrame(
        rows,
        columns=["date", "description", "debit", "credit", "balance"]
    )
