import streamlit as st
import pdfplumber
import regex as re
import pandas as pd
from tabulate import tabulate


# ======================================================================
# NUMERIC CLEANER
# ======================================================================
def num(x):
    if not x or x.strip() == "":
        return 0.0
    x = x.replace(",", "")
    if x.endswith("+"):
        x = x[:-1]
    return float(x)


# ======================================================================
# RHB PREPROCESSOR
# ======================================================================
def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()

        if re.match(r"^\d{2}-\d{2}-\d{4}", line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return "\n".join(merged)


# ======================================================================
# FINAL RHB REGEX (with description)
# ======================================================================
txn_pattern_rhb = re.compile(
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


# ======================================================================
# PARSE RHB PDF
# ======================================================================
def parse_rhb_pdf(pdf_file):
    all_txns = []

    with pdfplumber.open(pdf_file) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):

            txt = page.extract_text()
            if not txt:
                continue

            txt = preprocess_rhb_text(txt)

            for m in txn_pattern_rhb.finditer(txt):
                all_txns.append({
                    "Date": m.group("date"),
                    "Description": m.group("body").strip(),
                    "Debit": num(m.group("dr")),
                    "Credit": num(m.group("cr")),
                    "Balance": num(m.group("bal")),
                    "Page": page_num
                })

    return all_txns


# ======================================================================
# CONVERT TO TXT (TABULATED)
# ======================================================================
def df_to_txt(df):
    return tabulate(df, headers="keys", tablefmt="grid")


# ======================================================================
# STREAMLIT APP
# ======================================================================
st.set_page_config(page_title="RHB Statement Parser", layout="wide")

st.title("📄 RHB Bank Statement Parser")
st.write("Upload an RHB PDF bank statement and extract transactions into a clean TXT table.")

uploaded_file = st.file_uploader("Upload RHB PDF", type=["pdf"])

if not uploaded_file:
    st.stop()

transactions = parse_rhb_pdf(uploaded_file)

if not transactions:
    st.error("No transactions detected. Check PDF quality.")
    st.stop()

df = pd.DataFrame(transactions)

# Show table
st.subheader("Extracted Transactions")
txt_table = df_to_txt(df)
st.text(txt_table)

# TXT export
st.download_button(
    label="⬇ Download TXT File",
    data=txt_table,
    file_name="RHB_Transactions.txt",
    mime="text/plain"
)
