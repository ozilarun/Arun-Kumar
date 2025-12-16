import streamlit as st
import tempfile
import pandas as pd

# ===============================
# BANK IMPORTS (ALL BANKS)
# ===============================

from bank_rakyat import extract_bank_rakyat
from bank_islam import extract_bank_islam
from cimb import extract_cimb
from maybank import extract_maybank
from rhb import extract_rhb

# ===============================
# PAGE SETUP
# ===============================

st.set_page_config(page_title="Bank Statement Analysis", layout="wide")
st.title("🏦 Bank Statement Analysis")
st.write("Upload statements, select bank, enter OD limit, and generate analysis.")

# ===============================
# BANK SELECTION
# ===============================

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

# ===============================
# FILE UPLOAD
# ===============================

uploaded_files = st.file_uploader(
    "Upload Bank Statement PDF(s)",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("Please upload one or more PDF files.")
    st.stop()

# ===============================
# EXTRACTION
# ===============================

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

# ===============================
# COMBINE ALL FILES
# ===============================

df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📚 Combined Transactions")
st.dataframe(df_all, use_container_width=True)

# ===============================
# OD LIMIT INPUT
# ===============================

st.subheader("💳 OD Limit")

OD_LIMIT = st.number_input(
    "Enter OD Limit (RM)",
    min_value=0.0,
    step=1000.0
)

# ===============================
# HELPER FUNCTIONS (COMMON TO ALL BANKS)
# ===============================

def compute_opening_balance(df):
    first = df.iloc[0]
    return first["balance"] + first["debit"] - first["credit"]


def split_by_month(df):
    df = df.copy()
    df["Month"] = pd.to_datetime(df["date"], dayfirst=True).dt.strftime("%b %Y")
    return dict(tuple(df.groupby("Month")))


def compute_monthly_summary(all_months, od_limit):
    results = []

    for month, df in all_months.items():
        opening = compute_opening_balance(df)
        ending = df.iloc[-1]["balance"]

        total_debit = df["debit"].sum()
        total_credit = df["credit"].sum()

        highest = df["balance"].max()
        lowest = df["balance"].min()
        swing = abs(highest - lowest)

        if od_limit > 0:
            od_util = abs(ending) if ending < 0 else 0
            od_pct = (od_util / od_limit) * 100
        else:
            od_util = 0
            od_pct = 0

        results.append({
            "Month": month,
            "Opening": opening,
            "Debit": total_debit,
            "Credit": total_credit,
            "Ending": ending,
            "Highest": highest,
            "Lowest": lowest,
            "Swing": swing,
            "OD Util (RM)": od_util,
            "OD %": od_pct
        })

    return pd.DataFrame(results)


def compute_ratios(summary, od_limit):
    ratio = {}
    df = summary.copy()

    ratio["Total Credit (6 Months)"] = df["Credit"].sum()
    ratio["Total Debit (6 Months)"] = df["Debit"].sum()
    ratio["Annualized Credit"] = ratio["Total Credit (6 Months)"] * 2
    ratio["Annualized Debit"] = ratio["Total Debit (6 Months)"] * 2
    ratio["Average Opening Balance"] = df["Opening"].mean()
    ratio["Average Ending Balance"] = df["Ending"].mean()
    ratio["Highest Balance (Period)"] = df["Highest"].max()
    ratio["Lowest Balance (Period)"] = df["Lowest"].min()

    ratio["Average OD Utilization (RM)"] = df["OD Util (RM)"].mean()
    ratio["Average % OD Utilization"] = df["OD %"].mean()
    ratio["Average Monthly Swing (RM)"] = df["Swing"].mean()

    ratio["% of Swing"] = (
        (ratio["Average Monthly Swing (RM)"] / od_limit) * 100
        if od_limit > 0 else 0
    )

    ratio["Returned Cheques"] = 0
    ratio["Number of Excesses"] = int((df["OD Util (RM)"] > od_limit).sum()) if od_limit > 0 else 0

    return pd.DataFrame(list(ratio.items()), columns=["Metric", "Value"])

# ===============================
# RUN ANALYSIS
# ===============================

if st.button("Run Analysis"):

    all_months = split_by_month(df_all)

    monthly_summary = compute_monthly_summary(all_months, OD_LIMIT)

    st.subheader("📅 Monthly Summary")
    st.dataframe(monthly_summary, use_container_width=True)

    ratio_df = compute_ratios(monthly_summary, OD_LIMIT)

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)
