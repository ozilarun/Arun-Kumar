import streamlit as st
import tempfile
import pandas as pd

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

# =====================================================
# BANK IMPORTS (DO NOT TOUCH)
# =====================================================
from bank_rakyat import extract_bank_rakyat
from bank_islam import extract_bank_islam
from cimb import extract_cimb
from maybank import extract_maybank
from rhb import extract_rhb

# =====================================================
# PAGE SETUP
# =====================================================
st.set_page_config(page_title="Bank Statement Analysis", layout="wide")
st.title("🏦 Bank Statement Analysis")

# =====================================================
# BANK SELECTION
# =====================================================
bank_choice = st.selectbox(
    "Select Bank",
    ["Bank Rakyat", "Bank Islam", "CIMB", "Maybank", "RHB"]
)

BANK_EXTRACTORS = {
    "Bank Rakyat": extract_bank_rakyat,
    "Bank Islam": extract_bank_islam,
    "CIMB": extract_cimb,
    "Maybank": extract_maybank,
    "RHB": extract_rhb,
}

# =====================================================
# FILE UPLOAD
# =====================================================
uploaded_files = st.file_uploader(
    "Upload Bank Statement PDF(s)",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.stop()

# =====================================================
# EXTRACTION (NO SORTING, NO DATE CHANGES)
# =====================================================
extractor = BANK_EXTRACTORS[bank_choice]
all_dfs = []

for uploaded_file in uploaded_files:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    df = extractor(pdf_path)
    if not df.empty:
        all_dfs.append(df)

if not all_dfs:
    st.error("No transactions extracted.")
    st.stop()

df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📄 Transactions (Original Order)")
st.dataframe(df_all, use_container_width=True)

# =====================================================
# OD LIMIT
# =====================================================
OD_LIMIT = st.number_input(
    "Enter OD Limit (RM)",
    min_value=0.0,
    step=1000.0
)

# =====================================================
# HELPERS (NOTEBOOK-CORRECT)
# =====================================================
def opening_from_row(row):
    return row["balance"] + row["debit"] - row["credit"]


def split_by_month(df):
    temp = df.copy()
    temp["_month"] = pd.to_datetime(temp["date"], dayfirst=True).dt.to_period("M")

    months = {}
    for m in temp["_month"].unique():  # preserves appearance order
        label = m.strftime("%b %Y")
        months[label] = (
            temp[temp["_month"] == m]
            .drop(columns="_month")
            .reset_index(drop=True)
        )
    return months


def compute_monthly_summary(months, od_limit, bank_name):
    rows = []

    for month, df in months.items():

        # =========================
        # OPENING & ENDING (KEY FIX)
        # =========================
        if bank_name == "CIMB":
            opening_row = df.iloc[-1]   # descending
            ending = df.iloc[0]["balance"]
        else:
            opening_row = df.iloc[0]    # ascending
            ending = df.iloc[-1]["balance"]

        opening = opening_from_row(opening_row)

        debit = df["debit"].sum()
        credit = df["credit"].sum()
        highest = df["balance"].max()
        lowest = df["balance"].min()
        swing = abs(highest - lowest)

        if od_limit > 0 and ending < 0:
            od_util = abs(ending)
            od_pct = (od_util / od_limit) * 100
        else:
            od_util = 0
            od_pct = 0

        rows.append({
            "Month": month,
            "Opening": opening,
            "Debit": debit,
            "Credit": credit,
            "Ending": ending,
            "Highest": highest,
            "Lowest": lowest,
            "Swing": swing,
            "OD Util (RM)": od_util,
            "OD %": od_pct
        })

    return pd.DataFrame(rows)


def compute_ratios(summary, od_limit):
    df = summary.copy()

    if od_limit <= 0:
        avg_od_util = 0
        avg_od_pct = 0
        pct_swing = 0
    else:
        avg_od_util = df["OD Util (RM)"].mean()
        avg_od_pct = df["OD %"].mean()
        pct_swing = (df["Swing"].mean() / od_limit) * 100

    ratio = {
        "Total Credit (6 Months)": df["Credit"].sum(),
        "Total Debit (6 Months)": df["Debit"].sum(),
        "Annualized Credit": df["Credit"].sum() * 2,
        "Annualized Debit": df["Debit"].sum() * 2,
        "Average Opening Balance": df["Opening"].mean(),
        "Average Ending Balance": df["Ending"].mean(),
        "Highest Balance (Period)": df["Highest"].max(),
        "Lowest Balance (Period)": df["Lowest"].min(),
        "Average OD Utilization (RM)": avg_od_util,
        "Average % OD Utilization": avg_od_pct,
        "Average Monthly Swing (RM)": df["Swing"].mean(),
        "% of Swing": pct_swing,
        "Returned Cheques": 0,
        "Number of Excesses": 0
    }

    return pd.DataFrame(list(ratio.items()), columns=["Metric", "Value"])

# =====================================================
# RUN ANALYSIS
# =====================================================
if st.button("Run Analysis"):

    months = split_by_month(df_all)

    st.subheader("📂 Monthly Audit View")
    for m, mdf in months.items():
        st.markdown(f"### {m}")
        st.dataframe(mdf, use_container_width=True)

    monthly_summary = compute_monthly_summary(months, OD_LIMIT, bank_choice)
    ratio_df = compute_ratios(monthly_summary, OD_LIMIT)

    st.subheader("📅 Monthly Summary")
    st.dataframe(monthly_summary, use_container_width=True)

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)
