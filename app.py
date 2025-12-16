import streamlit as st
import tempfile
import pandas as pd

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

# =====================================================
# BANK IMPORTS (DO NOT TOUCH – YOUR ORIGINAL CODES)
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
# EXTRACTION (NO LOGIC CHANGE)
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

# =====================================================
# COMBINE (DO NOT SORT, DO NOT MODIFY DATE)
# =====================================================
df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📄 Cleaned Transaction List (Original Order)")
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
# HELPER FUNCTIONS (MATCH NOTEBOOK EXACTLY)
# =====================================================
def compute_opening_balance(df):
    first = df.iloc[0]
    return first["balance"] + first["debit"] - first["credit"]


# ✅ MONTH SPLIT — CORRECT MONTH ORDER, ROW ORDER PRESERVED
def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True)

    # Determine month order by FIRST transaction date per month
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

        # 🔑 BANK-AWARE OPENING / ENDING
        if bank_name == "CIMB":
            # CIMB = DESCENDING
            if prev_ending is None:
                last = df.iloc[-1]
                opening = last["balance"] + last["debit"] - last["credit"]
            else:
                opening = prev_ending

            ending = df.iloc[0]["balance"]

        else:
            # ALL OTHER BANKS = ASCENDING
            if prev_ending is None:
                first = df.iloc[0]
                opening = first["balance"] + first["debit"] - first["credit"]
            else:
                opening = prev_ending

            ending = df.iloc[-1]["balance"]

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
        "Number of Excesses": num_excess
    }

    return pd.DataFrame(list(ratio.items()), columns=["Metric", "Value"])

# =====================================================
# EXCEL EXPORT – ONE SHEET (NOTEBOOK STYLE)
# =====================================================
def export_analysis_excel(monthly_df, ratio_df, output_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Statement Analysis"

    header_fill = PatternFill("solid", fgColor="1F4E78")
    header_font = Font(color="FFFFFF", bold=True)
    title_font = Font(size=14, bold=True)

    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.append(["BANK STATEMENT ANALYSIS"])
    ws["A1"].font = title_font
    ws.append([])

    ws.append(["MONTHLY TRANSACTION SUMMARY"])
    ws.append([])

    start = ws.max_row + 1
    for r in dataframe_to_rows(monthly_df, index=False, header=True):
        ws.append(r)

    for c in ws[start]:
        c.fill = header_fill
        c.font = header_font
        c.border = border

    ws.append([])
    ws.append(["FINANCIAL RATIOS & CALCULATIONS"])
    ws.append([])

    rstart = ws.max_row + 1
    for r in dataframe_to_rows(ratio_df, index=False, header=True):
        ws.append(r)

    for c in ws[rstart]:
        c.fill = header_fill
        c.font = header_font
        c.border = border

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22

    wb.save(output_path)
    return output_path

# =====================================================
# RUN ANALYSIS
# =====================================================
if st.button("Run Analysis"):

    months = split_by_month(df_all)

    st.subheader("📂 Monthly Breakdown (Audit View)")
    for m, mdf in months.items():
        audit_df = mdf.copy()
        audit_df["date"] = audit_df["date"].astype(str)
        st.markdown(f"### {m}")
        st.dataframe(audit_df, use_container_width=True)

    monthly_summary = compute_monthly_summary(months, OD_LIMIT)
    ratio_df = compute_ratios(monthly_summary, OD_LIMIT)

    st.subheader("📅 Monthly Summary")
    st.dataframe(monthly_summary, use_container_width=True)

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        export_analysis_excel(monthly_summary, ratio_df, tmp.name)

    with open(tmp.name, "rb") as f:
        st.download_button(
            "⬇️ Download Excel (Monthly + Ratios)",
            f,
            file_name="Bank_Statement_Analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
