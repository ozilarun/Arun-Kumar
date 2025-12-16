import streamlit as st
import tempfile
import pandas as pd

from bank_rakyat import extract_bank_rakyat
from bank_islam import extract_bank_islam
from cimb import extract_cimb
from maybank import extract_maybank
from rhb import extract_rhb

# ---------------------------------------------------
# PAGE SETUP
# ---------------------------------------------------

st.set_page_config(page_title="Bank Statement Analyzer", layout="wide")
st.title("🏦 Bank Statement Analyzer")
st.write("Upload bank statements, enter OD limit, and generate analysis.")

# ---------------------------------------------------
# BANK SELECTION
# ---------------------------------------------------

bank_choice = st.selectbox(
    "Select Bank",
    [
        "Bank Rakyat",
        "Bank Islam",
        "CIMB",
        "Maybank",
        "RHB"
    ]
)

BANK_EXTRACTORS = {
    "Bank Rakyat": extract_bank_rakyat,
    "Bank Islam": extract_bank_islam,
    "CIMB": extract_cimb,
    "Maybank": extract_maybank,
    "RHB": extract_rhb,
}

# ---------------------------------------------------
# FILE UPLOAD
# ---------------------------------------------------

uploaded_files = st.file_uploader(
    "Upload PDF statements",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("Please upload one or more PDF files.")
    st.stop()

# ---------------------------------------------------
# EXTRACTION
# ---------------------------------------------------

extractor = BANK_EXTRACTORS[bank_choice]
all_dfs = []

for uploaded_file in uploaded_files:
    st.write(f"📄 Processing: **{uploaded_file.name}**")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    df = extractor(pdf_path)

    if df.empty:
        st.warning(f"No transactions found in {uploaded_file.name}")
        continue

    st.subheader(f"Extracted Transactions — {uploaded_file.name}")
    st.dataframe(df, use_container_width=True)

    all_dfs.append(df)

if not all_dfs:
    st.error("No valid transactions detected.")
    st.stop()

df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📚 Combined Transactions")
st.dataframe(df_all, use_container_width=True)

# ---------------------------------------------------
# USER INPUT: OD LIMIT
# ---------------------------------------------------

st.subheader("💳 OD Limit")

OD_LIMIT = st.number_input(
    "Enter OD Limit (RM)",
    min_value=0.0,
    step=1000.0
)

# ---------------------------------------------------
# CALCULATION
# ---------------------------------------------------

if st.button("Run Analysis"):

    first = df_all.iloc[0]
    opening = first["balance"] + first["debit"] - first["credit"]

    ending = df_all.iloc[-1]["balance"]

    total_debit = df_all["debit"].sum()
    total_credit = df_all["credit"].sum()

    highest = df_all["balance"].max()
    lowest = df_all["balance"].min()
    swing = abs(highest - lowest)

    if OD_LIMIT > 0:
        od_util = abs(ending) if ending < 0 else 0
        od_pct = (od_util / OD_LIMIT) * 100
    else:
        od_util = 0
        od_pct = 0

    summary = pd.DataFrame([{
        "Opening Balance": opening,
        "Total Debit": total_debit,
        "Total Credit": total_credit,
        "Ending Balance": ending,
        "Highest Balance": highest,
        "Lowest Balance": lowest,
        "Swing": swing,
        "OD Util (RM)": od_util,
        "OD %": od_pct
    }])

    st.subheader("📊 Analysis Summary")
    st.dataframe(summary, use_container_width=True)

