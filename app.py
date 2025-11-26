import streamlit as st
import pdfplumber
import json
import pandas as pd

from maybank import parse_transactions_maybank
from public_bank import parse_transactions_pbb
from rhb import parse_transactions_rhb


# ---------------------------------------------------
# Streamlit Setup
# ---------------------------------------------------

st.set_page_config(page_title="Bank Statement Parser", layout="wide")

st.title("📄 Bank Statement Parser (Multi-File Support)")
st.write("Upload one or more bank statement PDFs to extract transactions into a clean readable table.")


# ---------------------------------------------------
# Bank Selection
# ---------------------------------------------------

bank_choice = st.selectbox(
    "Select Bank Format",
    ["Auto-detect", "Maybank", "Public Bank (PBB)", "RHB Bank"]
)

bank_hint = None
if bank_choice == "Maybank":
    bank_hint = "maybank"
elif bank_choice == "Public Bank (PBB)":
    bank_hint = "pbb"
elif bank_choice == "RHB Bank":
    bank_hint = "rhb"


# ---------------------------------------------------
# Multiple File Upload
# ---------------------------------------------------

uploaded_files = st.file_uploader("Upload PDF files", type=["pdf"], accept_multiple_files=True)
default_year = st.text_input("Default Year", "2025")


# ---------------------------------------------------
# Auto Detect Parsing Logic
# ---------------------------------------------------

def auto_detect_and_parse(text, page_num, default_year="2025"):
    tx = parse_transactions_maybank(text, page_num, default_year)
    if tx:
        return tx

    tx = parse_transactions_pbb(text, page_num, default_year)
    if tx:
        return tx

    tx = parse_transactions_rhb(text, page_num)
    if tx:
        return tx

    return []


# ---------------------------------------------------
# Main Multi-File Processing
# ---------------------------------------------------

all_tx = []

if uploaded_files:
    for uploaded_file in uploaded_files:

        st.write(f"Processing: **{uploaded_file.name}**")

        with pdfplumber.open(uploaded_file) as pdf:

            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""

                # Parse by selected bank or auto-detect
                if bank_hint == "maybank":
                    tx = parse_transactions_maybank(text, page_num, default_year)

                elif bank_hint == "pbb":
                    tx = parse_transactions_pbb(text, page_num, default_year)

                elif bank_hint == "rhb":
                    tx = parse_transactions_rhb(text, page_num)

                else:
                    tx = auto_detect_and_parse(text, page_num, default_year)

                # Add to main list
                for t in tx:
                    t["source_file"] = uploaded_file.name  # track which PDF it came from

                all_tx.extend(tx)


# ---------------------------------------------------
# Display Results
# ---------------------------------------------------

if all_tx:
    st.subheader("Extracted Transactions (Readable Table)")

    df = pd.DataFrame(all_tx)

    # Arrange columns nicely
    column_order = ["date", "description", "debit", "credit", "balance", "page", "source_file"]
    df = df[[c for c in column_order if c in df.columns]]

    st.dataframe(df, use_container_width=True)

    # JSON Export
    json_data = json.dumps(all_tx, indent=4)
    st.download_button("Download JSON", json_data, file_name="transactions.json", mime="application/json")

    # TXT Export (Pretty Table)
    df_txt = df[["date", "description", "debit", "credit", "balance", "source_file"]]

    w_date = 12
    w_desc = 45
    w_debit = 12
    w_credit = 12
    w_balance = 14
    w_file = 20

    header = (
        f"{'DATE':<{w_date}} | "
        f"{'DESCRIPTION':<{w_desc}} | "
        f"{'DEBIT':>{w_debit}} | "
        f"{'CREDIT':>{w_credit}} | "
        f"{'BALANCE':>{w_balance}} | "
        f"{'FILE':<{w_file}}"
    )
    separator = "-" * len(header)

    lines = [header, separator]

    for _, row in df_txt.iterrows():
        line = (
            f"{row['date']:<{w_date}} | "
            f"{str(row['description'])[:w_desc]:<{w_desc}} | "
            f"{row['debit']:>{w_debit}.2f} | "
            f"{row['credit']:>{w_credit}.2f} | "
            f"{row['balance']:>{w_balance}.2f} | "
            f"{row['source_file']:<{w_file}}"
        )
        lines.append(line)

    txt_data = "\n".join(lines)

    st.download_button("Download TXT", txt_data, file_name="transactions.txt", mime="text/plain")

else:
    st.info("Upload one or more PDF files to begin.")
