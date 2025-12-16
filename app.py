import streamlit as st
import tempfile
import pandas as pd
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
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
# EXTRACTION
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

st.subheader("📄 Cleaned Transaction List")
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
# SPLIT BY MONTH
# =====================================================
def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True)

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

# =====================================================
# MONTHLY SUMMARY (YOUR EXACT LOGIC)
# =====================================================
def compute_monthly_summary(all_months, od_limit, bank_name):
    rows = []
    prev_ending = None

    for month, df in all_months.items():

        # =================================================
        # OPENING LOGIC
        # =================================================
        if prev_ending is None:
            # ---- FIRST MONTH ONLY ----
            if bank_name == "CIMB":
                # CIMB table is DESCENDING → first txn is BOTTOM row
                first_txn = df.iloc[-1]
            else:
                # Other banks → first txn is TOP row
                first_txn = df.iloc[0]

            opening = (
                first_txn["balance"]
                + first_txn["debit"]
                - first_txn["credit"]
            )
        else:
            # ---- CONTINUITY FOR ALL OTHER MONTHS ----
            opening = prev_ending

        # =================================================
        # ENDING LOGIC
        # =================================================
        if bank_name == "CIMB":
            # DESCENDING → last txn is TOP row
            ending = df.iloc[0]["balance"]
        else:
            # ASCENDING → last txn is BOTTOM row
            ending = df.iloc[-1]["balance"]

        # =================================================
        # AGGREGATES
        # =================================================
        debit = df["debit"].sum()
        credit = df["credit"].sum()
        highest = df["balance"].max()
        lowest = df["balance"].min()
        swing = abs(highest - lowest)

        if od_limit > 0:
            od_util = abs(ending) if ending < 0 else 0
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


# =====================================================
# RATIOS
# =====================================================
def compute_ratios(summary, od_limit):
    df = summary.copy()

    if od_limit <= 0:
        avg_od_util = 0
        avg_od_pct = 0
        num_excess = 0
        pct_swing = 0
    else:
        avg_od_util = df["OD Util (RM)"].mean()
        avg_od_pct = df["OD %"].mean()
        num_excess = int((df["OD Util (RM)"] > od_limit).sum())
        pct_swing = (df["Swing"].mean() / od_limit) * 100

    ratio = {
        "Total Credit": df["Credit"].sum(),
        "Total Debit": df["Debit"].sum(),
        "Annualized Credit": df["Credit"].sum() * 2,
        "Annualized Debit": df["Debit"].sum() * 2,
        "Average Opening Balance": df["Opening"].mean(),
        "Average Ending Balance": df["Ending"].mean(),
        "Highest Balance": df["Highest"].max(),
        "Lowest Balance": df["Lowest"].min(),
        "Average OD Util (RM)": avg_od_util,
        "Average OD %": avg_od_pct,
        "Average Swing": df["Swing"].mean(),
        "% Swing vs OD": pct_swing,
        "Number of Excesses": num_excess
    }

    return pd.DataFrame(list(ratio.items()), columns=["Metric", "Value"])

# =====================================================
# RUN ANALYSIS
# =====================================================
if st.button("Run Analysis"):

    months = split_by_month(df_all)

    st.subheader("📂 Monthly Breakdown (Audit)")
    for m, mdf in months.items():
        st.markdown(f"### {m}")
        st.dataframe(mdf, use_container_width=True)

    monthly_summary = compute_monthly_summary(months, OD_LIMIT, bank_choice)
    ratio_df = compute_ratios(monthly_summary, OD_LIMIT)

    st.subheader("📅 Monthly Summary")
    st.dataframe(monthly_summary, use_container_width=True)

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)

    # =====================================================
    # EXPORT TO EXCEL
    # =====================================================
    wb = Workbook()
    ws = wb.active
    ws.title = "Monthly Summary"

    ws["A1"] = "Bank Statement Analysis"
    ws["A1"].font = Font(bold=True)

    for r_idx, row in enumerate(
        dataframe_to_rows(monthly_summary, index=False, header=True),
        start=3
    ):
        for c_idx, value in enumerate(row, start=1):
            ws.cell(row=r_idx, column=c_idx, value=value)

    ws2 = wb.create_sheet("Ratios")
    for r_idx, row in enumerate(
        dataframe_to_rows(ratio_df, index=False, header=True),
        start=1
    ):
        for c_idx, value in enumerate(row, start=1):
            ws2.cell(row=r_idx, column=c_idx, value=value)

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)

    st.download_button(
        "📥 Download Excel",
        data=buffer,
        file_name="Bank_Statement_Analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
