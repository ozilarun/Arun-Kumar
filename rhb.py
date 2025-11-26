import regex as re

# =====================================================================
# NUMERIC CLEANER
# =====================================================================
def num(x):
    if not x or x.strip() == "":
        return 0.0
    return float(x.replace(",", ""))


# =====================================================================
# PREPROCESS — RHB MERGE WRAPPED LINES
# =====================================================================
def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()

        # Every transaction starts with DD-MM-YYYY
        if re.match(r"^\d{2}-\d{2}-\d{4}", line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return "\n".join(merged)


# =====================================================================
# VERIFIED ACCURATE RHB TRANSACTION PATTERN
# (Same as your working code)
# =====================================================================
txn_pattern = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})
    \s+
    (?P<body>.*?)
    \s+
    (?P<dr>[0-9,]*\.\d{2})?
    \s*
    (?P<dr_flag>-)?
    \s*
    (?P<cr>[0-9,]*\.\d{2})?
    \s+
    (?P<bal>-?[0-9,]*\.\d{2}[+-]?)
    """,
    re.VERBOSE | re.DOTALL
)


# =====================================================================
# MAIN PARSER — AUTO CALLED BY app.py
# =====================================================================
def parse_transactions_rhb(text, page_num):
    """
    Required signature:
    parse_transactions_rhb(text, page_num)
    """
    if not text or text.strip() == "":
        return []

    text = preprocess_rhb_text(text)

    txns = []

    for m in txn_pattern.finditer(text):
        dr_val = num(m.group("dr"))
        cr_val = num(m.group("cr"))
        bal_val = num(m.group("bal"))

        txns.append({
            "date": m.group("date"),
            "description": m.group("body").strip(),
            "debit": dr_val if dr_val > 0 else 0.0,
            "credit": cr_val if cr_val > 0 else 0.0,
            "balance": bal_val,
            "page": page_num
        })

    return txns
