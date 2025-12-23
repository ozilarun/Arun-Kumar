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
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="Bank Statement Analysis",
    layout="wide"
)

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
# EXTRACTION
# =====================================================
extractor = BANK_EXTRACTORS[bank_choice]
all_dfs = []

for uploaded_file in uploaded_files:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    df = extractor(pdf_path)

    if df is not None and not df.empty:
        # -----------------------------------------------------------
        # AUTO-SORT LOGIC (Essential for Maybank Integration)
        # -----------------------------------------------------------
        # Ensures all data is Chronological (Oldest -> Newest)
        # regardless of how the bank formatted the PDF.
        try:
            df["_sort_temp"] = pd.to_datetime(df["date"], dayfirst=True, errors='coerce')
            df = df.sort_values(by="_sort_temp").drop(columns=["_sort_temp"]).reset_index(drop=True)
        except Exception:
            pass # Fallback to original order if date fails
        
        all_dfs.append(df)

if not all_dfs:
    st.error("No transactions extracted.")
    st.stop()

df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📄 Cleaned Transaction List (Original Order)")
st.dataframe(df_all, use_container_width=True)

# =====================================================
# OD LIMIT INPUT
# =====================================================
OD_LIMIT = st.number_input(
    "Enter OD Limit (RM)",
    min_value=0.0,
    step=1000.0
)

# =====================================================
# HELPER FUNCTIONS
# =====================================================
def compute_opening_balance_from_row(row):
    return row["balance"] + row["debit"] - row["credit"]


def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True, errors='coerce')
    temp = temp.dropna(subset=["_dt"]) # Remove rows with bad dates

    month_order = (
        temp.assign(m=temp["_dt"].dt.to_period("M"))
        .groupby("m")["_dt"]
        .min()
        .sort_values()
        .index
    )

    months = {}
    for m in month_order:
        label = m.strftime("%b %Y")
        months[label] = (
            temp[temp["_dt"].dt.to_period("M") == m]
            .drop(columns="_dt")
            .reset_index(drop=True)
        )

    return months


def compute_monthly_summary(all_months, od_limit, bank_name):
    rows = []
    prev_ending = None

    for month, df in all_months.items():
        if df.empty: continue

        # Since we Auto-Sorted everything to Chronological above,
        # we don't need special "if CIMB" logic anymore.
        # First row is always Start, Last row is always End.
        first_txn = df.iloc[0]
        last_txn = df.iloc[-1]

        # Opening balance
        if prev_ending is None:
            opening = compute_opening_balance_from_row(first_txn)
        else:
            opening = prev_ending

        ending = last_txn["balance"]

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

        prev_ending = ending

    return pd.DataFrame(rows)


def compute_ratios(summary, od_limit):
    df = summary.copy()
    if df.empty: return pd.DataFrame()

    return pd.DataFrame(
        [
            ("Total Credit (6 Months)", df["Credit"].sum()),
            ("Total Debit (6 Months)", df["Debit"].sum()),
            ("Annualized Credit", df["Credit"].sum() * 2),
            ("Annualized Debit", df["Debit"].sum() * 2),
            ("Average Opening Balance", df["Opening"].mean()),
            ("Average Ending Balance", df["Ending"].mean()),
            ("Highest Balance (Period)", df["Highest"].max()),
            ("Lowest Balance (Period)", df["Lowest"].min()),
            ("Average OD Utilization (RM)", df["OD Util (RM)"].mean() if od_limit > 0 else 0),
            ("Average % OD Utilization", df["OD %"].mean() if od_limit > 0 else 0),
            ("Average Monthly Swing (RM)", df["Swing"].mean()),
            ("% of Swing", (df["Swing"].mean() / od_limit * 100) if od_limit > 0 else 0),
            ("Returned Cheques", 0),
            ("Number of Excesses", int((df["OD Util (RM)"] > od_limit).sum()) if od_limit > 0 else 0),
        ],
        columns=["Metric", "Value"]
    )

# =====================================================
# RUN ANALYSIS
# =====================================================
if st.button("Run Analysis"):

    months = split_by_month(df_all)

    st.subheader("📂 Monthly Breakdown (Audit)")
    for month, mdf in months.items():
        st.markdown(f"### {month}")
        st.dataframe(mdf, use_container_width=True)

    monthly_summary = compute_monthly_summary(
        months,
        OD_LIMIT,
        bank_choice
    )

    ratio_df = compute_ratios(
        monthly_summary,
        OD_LIMIT
    )

    st.subheader("📅 Monthly Summary")
    st.dataframe(monthly_summary, use_container_width=True)

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)
