import streamlit as st
import tempfile
import pandas as pd

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

# ===============================
# BANK IMPORTS (DO NOT TOUCH)
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

# ===============================
# BANK SELECTION
# ===============================
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

# ===============================
# FILE UPLOAD
# ===============================
uploaded_files = st.file_uploader(
    "Upload Bank Statement PDF(s)",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.stop()

# ===============================
# EXTRACTION
# ===============================
extractor = BANK_EXTRACTORS[bank_choice]
dfs = []

for f in uploaded_files:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(f.read())
        path = tmp.name

    df = extractor(path)
    if not df.empty:
        dfs.append(df)

df_all = pd.concat(dfs, ignore_index=True)

st.subheader("📄 Extracted Transactions")
st.dataframe(df_all, use_container_width=True)

# ===============================
# OD LIMIT
# ===============================
OD_LIMIT = st.number_input("Enter OD Limit (RM)", min_value=0.0, step=1000.0)

# ===============================
# MONTH SPLIT (CORRECT ORDER)
# ===============================
def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True)

    month_keys = (
        temp.assign(m=temp["_dt"].dt.to_period("M"))
        .groupby("m")["_dt"]
        .min()
        .sort_values()
        .index
    )

    months = {}
    for m in month_keys:
        label = m.strftime("%b %Y")
        months[label] = temp[temp["_dt"].dt.to_period("M") == m].drop(columns="_dt")

    return months

# ===============================
# MONTHLY SUMMARY (BANK-AWARE)
# ===============================
def compute_monthly_summary(months, od_limit, bank):
    rows = []
    prev_ending = None

    for month, df in months.items():

        if bank == "CIMB":
            base = df.iloc[-1]   # earliest txn
            opening = (
                base["balance"] + base["debit"] - base["credit"]
                if prev_ending is None else prev_ending
            )
            ending = df.iloc[0]["balance"]   # latest txn
        else:
            base = df.iloc[0]
            opening = (
                base["balance"] + base["debit"] - base["credit"]
                if prev_ending is None else prev_ending
            )
            ending = df.iloc[-1]["balance"]

        debit = df["debit"].sum()
        credit = df["credit"].sum()
        highest = df["balance"].max()
        lowest = df["balance"].min()
        swing = abs(highest - lowest)

        od_util = abs(ending) if ending < 0 and od_limit > 0 else 0
        od_pct = (od_util / od_limit * 100) if od_limit > 0 else 0

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

# ===============================
# RUN
# ===============================
if st.button("Run Analysis"):
    months = split_by_month(df_all)
    summary = compute_monthly_summary(months, OD_LIMIT, bank_choice)

    st.subheader("📅 Monthly Summary")
    st.dataframe(summary, use_container_width=True)
