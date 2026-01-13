import pdfplumber
import pandas as pd
import re


# ============================================================
# MAIN UNIVERSAL AMBANK EXTRACTOR
# ============================================================
def extract_ambank(pdf_path):

    rows = []

    # ========================================================
    # CODE 1 — FORMAT 1 (DR / CR suffix, English months)
    # ========================================================
    prev_balance = None
    current_tx = None

    date_pattern_1 = re.compile(r"^(\d{2})\s+([A-Z]{3})\s+(\d{4})")

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                m = date_pattern_1.match(line)

                if m:
                    day, mon, year = m.groups()
                    parts = line.split()

                    nums = []
                    desc = []

                    for i in range(len(parts) - 1, -1, -1):
                        if re.match(r"[\d,]+\.\d{2}(DR|CR)?$", parts[i]):
                            nums.insert(0, parts[i])
                        else:
                            desc = parts[i + 1:]
                            break

                    if len(nums) >= 2:
                        amt = float(nums[0].replace(",", "").replace("DR", "").replace("CR", ""))
                        bal = float(nums[-1].replace(",", "").replace("DR", "").replace("CR", ""))

                        debit = credit = 0.0
                        if prev_balance is not None:
                            diff = round(bal - prev_balance, 2)
                            if abs(diff - amt) < 0.05:
                                credit = amt
                            elif abs(diff + amt) < 0.05:
                                debit = amt

                        current_tx = {
                            "date": f"{day} {mon} {year}",
                            "description": " ".join(desc),
                            "debit": debit,
                            "credit": credit,
                            "balance": bal
                        }
                        rows.append(current_tx)
                        prev_balance = bal

                else:
                    if current_tx and not re.search(r"\d+\.\d{2}", line):
                        current_tx["description"] += " " + line

    if rows:
        return pd.DataFrame(rows, columns=["date", "description", "debit", "credit", "balance"])

    # ========================================================
    # CODE 2 — FORMAT 2 (Malay months e.g. MAC, continuation)
    # ========================================================
    rows = []
    prev_balance = None
    current_tx = None

    date_pattern_2 = re.compile(r"^(\d{2})(JAN|FEB|MAC|APR|MEI|JUN|JUL|OGO|SEP|OKT|NOV|DIS)")

    MONTH_FIX = {
        "MAC": "MAR", "MEI": "MAY", "OGO": "AUG", "OKT": "OCT", "DIS": "DEC"
    }

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                m = date_pattern_2.match(line)

                if m:
                    day, mon = m.groups()
                    mon = MONTH_FIX.get(mon, mon)

                    parts = line.split()
                    nums = []
                    desc = []

                    for i in range(len(parts) - 1, -1, -1):
                        if re.match(r"[\d,]+\.\d{2}$", parts[i]):
                            nums.insert(0, parts[i])
                        else:
                            desc = parts[i + 1:]
                            break

                    if len(nums) >= 2:
                        amt = float(nums[0].replace(",", ""))
                        bal = float(nums[-1].replace(",", ""))

                        debit = credit = 0.0
                        if prev_balance is not None:
                            diff = round(bal - prev_balance, 2)
                            if abs(diff - amt) < 0.05:
                                credit = amt
                            elif abs(diff + amt) < 0.05:
                                debit = amt

                        current_tx = {
                            "date": f"{day} {mon} 2023",
                            "description": " ".join(desc),
                            "debit": debit,
                            "credit": credit,
                            "balance": bal
                        }
                        rows.append(current_tx)
                        prev_balance = bal

                else:
                    if current_tx and not re.search(r"\d+\.\d{2}", line):
                        current_tx["description"] += " " + line

    if rows:
        return pd.DataFrame(rows, columns=["date", "description", "debit", "credit", "balance"])

    # ========================================================
    # CODE 3 — FORMAT 3 (Amount + Balance only, infer by diff)
    # ========================================================
    rows = []
    prev_balance = None

    date_pattern_3 = re.compile(r"^(\d{2})\s+([A-Z]{3})")

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                m = date_pattern_3.match(line)
                if not m:
                    continue

                parts = line.split()
                nums = [p for p in parts if re.match(r"[\d,]+\.\d{2}$", p)]

                if len(nums) == 2:
                    amt = float(nums[0].replace(",", ""))
                    bal = float(nums[1].replace(",", ""))

                    debit = credit = 0.0
                    if prev_balance is not None:
                        diff = round(bal - prev_balance, 2)
                        if abs(diff - amt) < 0.05:
                            credit = amt
                        elif abs(diff + amt) < 0.05:
                            debit = amt

                    rows.append({
                        "date": " ".join(parts[:3]),
                        "description": " ".join(parts[3:-2]),
                        "debit": debit,
                        "credit": credit,
                        "balance": bal
                    })

                    prev_balance = bal

    if rows:
        return pd.DataFrame(rows, columns=["date", "description", "debit", "credit", "balance"])

    # ========================================================
    # FINAL FALLBACK — NO TRANSACTIONS
    # ========================================================
    return pd.DataFrame(
        [{
            "date": "",
            "description": "No transactions",
            "debit": 0.0,
            "credit": 0.0,
            "balance": 0.0
        }],
        columns=["date", "description", "debit", "credit", "balance"]
    )
