import regex as re

# ============================================================
# IMPROVED RHB STATEMENT PARSER (handles all formats)
# ============================================================

# This robust pattern handles:
# - Variable description formats containing "/", "-", numbers
# - Debit and credit in ANY position
# - Overdraft balances ending in "-"
# - Positive balances ending in "+"
#

PATTERN_RHB = re.compile(
    r"(\d{2}-\d{2}-\d{4})\s+"                       # date
    r"(\d{3})\s+"                                   # branch
    r"(.+?)\s+"                                     # description (greedy)
    r"([0-9,]+\.\d{2}|-)\s+"                        # debit OR '-'
    r"([0-9,]+\.\d{2}|-)\s+"                        # credit OR '-'
    r"([0-9,]+\.\d{2})([+-])"                       # balance + sign
)

def parse_line_rhb(line, page_num):
    m = PATTERN_RHB.search(line)
    if not m:
        return None

    date_raw, branch, desc, dr_raw, cr_raw, balance_raw, sign = m.groups()

    # Convert date: DD-MM-YYYY -> YYYY-MM-DD
    d, m_, y = date_raw.split("-")
    full_date = f"{y}-{m_}-{d}"

    # Debit / Credit
    debit = float(dr_raw.replace(",", "")) if dr_raw != "-" else 0.0
    credit = float(cr_raw.replace(",", "")) if cr_raw != "-" else 0.0

    # Balance with sign (+ or -)
    balance = float(balance_raw.replace(",", ""))
    if sign == "-":
        balance = -balance

    description = f"{branch} {desc.strip()}"

    return {
        "date": full_date,
        "description": description,
        "debit": debit,
        "credit": credit,
        "balance": balance,
        "page": page_num,
    }


def parse_transactions_rhb(text, page_num):
    tx_list = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        tx = parse_line_rhb(line, page_num)
        if tx:
            tx_list.append(tx)

    return tx_list
