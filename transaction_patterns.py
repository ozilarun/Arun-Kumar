# transaction_patterns.py

import regex as re

# ---------------------------
# Compiled regex patterns
# ---------------------------

# Pattern for MTASB:
# Example: "01/05 TRANSFER TO A/C 320.00+ 43,906.52"
PATTERN_MTASB = re.compile(
    r"(\d{2}/\d{2})\s+"             # date: 01/05
    r"(.+?)\s+"                     # description
    r"([0-9,]+\.\d{2})([+-])\s+"    # amount + sign: 320.00+
    r"([0-9,]+\.\d{2})"             # balance
)

# Pattern for MBB:
# Example: "01 Apr 2025 CMS - DR CORP CHG 78.00 - 71,229.76"
PATTERN_MBB = re.compile(
    r"(\d{2})\s+([A-Za-z]{3})\s+(\d{4})\s+"  # 01 Apr 2025
    r"(.+?)\s+"                              # description
    r"([0-9,]+\.\d{2})\s+([+-])\s+"          # 78.00 -
    r"([0-9,]+\.\d{2})"                      # 71,229.76
)

MONTH_MAP = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
    "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
    "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


# ---------------------------
# Helpers: individual matchers
# ---------------------------

def parse_line_mtasb(line: str, page_num: int, default_year: str = "2025"):
    """
    Parse a single line in MTASB format using PATTERN_MTASB.
    Returns a transaction dict or None.
    """
    m = PATTERN_MTASB.search(line)
    if not m:
        return None

    date_raw, desc, amount_raw, sign, balance_raw = m.groups()
    day, month = date_raw.split("/")

    year = default_year  # could be extended later

    amount = float(amount_raw.replace(",", ""))
    balance = float(balance_raw.replace(",", ""))

    if sign == "+":
        credit = amount
        debit = 0.0
    else:
        credit = 0.0
        debit = amount

    full_date = f"{year}-{month}-{day.zfill(2)}"

    return {
        "date": full_date,
        "description": desc.strip(),
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "page": page_num,
    }


def parse_line_mbb(line: str, page_num: int):
    """
    Parse a single line in MBB format using PATTERN_MBB.
    Returns a transaction dict or None.
    """
    m = PATTERN_MBB.search(line)
    if not m:
        return None

    day, mon_abbr, year, desc, amount_raw, sign, balance_raw = m.groups()

    month = MONTH_MAP.get(mon_abbr.title(), "01")
    amount = float(amount_raw.replace(",", ""))
    balance = float(balance_raw.replace(",", ""))

    if sign == "+":
        credit = amount
        debit = 0.0
    else:
        credit = 0.0
        debit = amount

    full_date = f"{year}-{month}-{day.zfill(2)}"

    return {
        "date": full_date,
        "description": desc.strip(),
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "page": page_num,
    }


# ---------------------------
# Main entry point for app.py
# ---------------------------

def parse_line_any_bank(line: str, page_num: int, default_year: str = "2025"):
    """
    Try to parse a line using all known bank formats.
    Returns a transaction dict or None.
    """

    # 1) Try MTASB pattern
    tx = parse_line_mtasb(line, page_num, default_year=default_year)
    if tx is not None:
        return tx

    # 2) Try MBB pattern
    tx = parse_line_mbb(line, page_num)
    if tx is not None:
        return tx

    # 3) If no pattern matches, return None
    return None


def parse_transactions(text: str, page_num: int, default_year: str = "2025"):
    """
    Parse all transactions from a block of text for a given page.
    Uses parse_line_any_bank() internally.
    """
    transactions = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        tx = parse_line_any_bank(line, page_num, default_year=default_year)
        if tx:
            transactions.append(tx)

    return transactions
