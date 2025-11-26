import regex as re

# --------------------------------------
# PUBLIC BANK (PBB) PATTERN
# Debit or Credit may be blank depending on column
# --------------------------------------

PATTERN_PBB = re.compile(
    r"(\d{2}/\d{2})\s+"                     # date
    r"(.+?)\s+"                             # description
    r"(?:(\d{1,3}(?:,\d{3})*\.\d{2}))?\s*"  # debit (optional)
    r"(?:(\d{1,3}(?:,\d{3})*\.\d{2}))?\s+"  # credit (optional)
    r"(\d{1,3}(?:,\d{3})*\.\d{2})"          # balance
)


def parse_line_pbb(line, page_num, default_year="2025"):
    m = PATTERN_PBB.search(line)
    if not m:
        return None

    date_raw, desc, debit_raw, credit_raw, balance_raw = m.groups()
    day, month = date_raw.split("/")
    year = default_year

    debit = float(debit_raw.replace(",", "")) if debit_raw else 0.0
    credit = float(credit_raw.replace(",", "")) if credit_raw else 0.0
    balance = float(balance_raw.replace(",", ""))

    full_date = f"{year}-{month}-{day}"

    return {
        "date": full_date,
        "description": desc,
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "page": page_num,
    }


def parse_transactions_pbb(text, page_num, default_year="2025"):
    tx_list = []

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        tx = parse_line_pbb(line, page_num, default_year)
        if tx:
            tx_list.append(tx)

    return tx_list
