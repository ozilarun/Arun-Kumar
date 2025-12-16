import streamlit as st
import tempfile
import pandas as pd

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

# ===============================
# BANK IMPORTS
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

# ===============================
# OD LIMIT
# ===============================
OD_LIMIT = st.number_input(
    "Enter OD Limit (RM)",
    min_value=0.0,
    step=1000.0
)

# ===============================
# HELPER FUNCTIONS
# ===============================
def compute_opening_balance(df):
    first = df.iloc[0]
    return first["balance"] + first["debit"] - first["credit"]


def split_by_month(df):
    df = df.copy()
    df["Month"] = pd.to_datetime(df["date"], dayfirst=True).dt.strftime("%b %Y")
    return dict(tuple(df.groupby("Month")))


def compute_monthly_summary(all_months, od_limit):
    rows = []
    for month, df in all_months.items():
        opening = compute_opening_balance(df)
        ending = df.iloc[-1]["balance"]

        debit = df["debit"].sum()
        credit = df["credit"].sum()
        highest = df["balance"].max()
        lowest = df["balance"].min()
        swing = abs(highest - lowest)

        od_util = abs(ending) if ending < 0 else 0
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

    return pd.DataFrame(rows)


def compute_ratios(summary, od_limit):
    df = summary.copy()
    ratio = {
        "Total Credit (6 Months)": df["Credit"].sum(),
        "Total Debit (6 Months)": df["Debit"].sum(),
        "Annualized Credit": df["Credit"].sum() * 2,
        "Annualized Debit": df["Debit"].sum() * 2,
        "Average Opening Balance": df["Opening"].mean(),
        "Average Ending Balance": df["Ending"].mean(),
        "Highest Balance (Period)": df["Highest"].max(),
        "Lowest Balance (Period)": df["Lowest"].min(),
        "Average OD Utilization (RM)": df["OD Util (RM)"].mean(),
        "Average % OD Utilization": df["OD %"].mean(),
        "Average Monthly Swing (RM)": df["Swing"].mean(),
        "% of Swing": (df["Swing"].mean() / od_limit * 100) if od_limit > 0 else 0,
        "Returned Cheques": 0,
        "Number of Excesses": int((df["OD Util (RM)"] > od_limit).sum()) if od_limit > 0 else 0
    }
    return pd.DataFrame(list(ratio.items()), columns=["Metric", "Value"])


# ===============================
# EXCEL EXPORT (ONE SHEET)
# ===============================
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

    ws.append(["MONTHLY SUMMARY"])
    ws.append([])

    start = ws.max_row + 1
    for r in dataframe_to_rows(monthly_df, index=False, header=True):
        ws.append(r)

    for cell in ws[start]:
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border

    ws.append([])
    ws.append([])
    ws.append(["FINANCIAL RATIOS"])
    ws.append([])

    rstart = ws.max_row + 1
    for r in dataframe_to_rows(ratio_df, index=False, header=True):
        ws.append(r)

    for cell in ws[rstart]:
        cell.fill = header_fill
        cell.font = header_font
        cell.border = border

    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = 22

    wb.save(output_path)
    return output_path


# ===============================
# RUN ANALYSIS
# ===============================
if st.button("Run Analysis"):
    months = split_by_month(df_all)
    monthly_summary = compute_monthly_summary(months, OD_LIMIT).reset_index(drop=True)
    ratio_df = compute_ratios(monthly_summary, OD_LIMIT).reset_index(drop=True)

    st.subheader("📅 Monthly Summary")
    st.dataframe(monthly_summary, use_container_width=True)

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        path = export_analysis_excel(monthly_summary, ratio_df, tmp.name)

    with open(path, "rb") as f:
        st.download_button(
            "⬇️ Download Excel (Monthly + Ratios)",
            f,
            file_name="Bank_Statement_Analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
