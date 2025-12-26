import streamlit as st
import tempfile
import pandas as pd
from io import BytesIO

from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows

# =====================================================
# BANK IMPORTS (DO NOT TOUCH)
# =====================================================
try:
    from bank_rakyat import extract_bank_rakyat
    from bank_islam import extract_bank_islam
    from cimb import extract_cimb
    from maybank import extract_maybank
    from rhb import extract_rhb
except ImportError as e:
    st.error(f"Missing bank file: {e}")
    st.stop()

# =====================================================
# PAGE CONFIG
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
# EXTRACT DATA
# =====================================================
extractor = BANK_EXTRACTORS[bank_choice]
all_dfs = []

progress = st.progress(0)

for i, f in enumerate(uploaded_files):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(f.read())
        path = tmp.name

    df = extractor(path)

    if df is not None and not df.empty:
        df["_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        df = df.dropna(subset=["_dt"]).sort_values("_dt")
        df = df.drop(columns="_dt").reset_index(drop=True)
        all_dfs.append(df)

    progress.progress((i + 1) / len(uploaded_files))

if not all_dfs:
    st.error("No transactions extracted.")
    st.stop()

df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📄 Cleaned Transactions")
st.dataframe(df_all, use_container_width=True)

# =====================================================
# OD LIMIT
# =====================================================
OD_LIMIT = st.number_input("Enter OD Limit (RM)", min_value=0.0, step=1000.0)

# =====================================================
# HELPERS
# =====================================================
def compute_opening(row):
    return row["balance"] - row["credit"] + row["debit"]

def split_by_month(df):
    df["_dt"] = pd.to_datetime(df["date"], dayfirst=True)
    months = {}
    for p, g in df.groupby(df["_dt"].dt.to_period("M")):
        months[p.strftime("%b %Y")] = g.drop(columns="_dt").reset_index(drop=True)
    return dict(sorted(months.items()))

def compute_monthly_summary(months):
    rows = []
    prev_end = None

    for m, df in months.items():
        first, last = df.iloc[0], df.iloc[-1]
        opening = compute_opening(first) if prev_end is None else prev_end
        ending = last["balance"]

        rows.append({
            "Month": m,
            "Opening": opening,
            "Debit": df["debit"].sum(),
            "Credit": df["credit"].sum(),
            "Ending": ending,
            "Highest": df["balance"].max(),
            "Lowest": df["balance"].min(),
            "Swing": abs(df["balance"].max() - df["balance"].min()),
            "OD Util (RM)": abs(ending) if ending < 0 else 0,
            "OD %": (abs(ending) / OD_LIMIT * 100) if OD_LIMIT > 0 and ending < 0 else 0
        })

        prev_end = ending

    return pd.DataFrame(rows)

def compute_ratios(df):
    ratio = {}
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
    ratio["% of Swing"] = (ratio["Average Monthly Swing (RM)"] / OD_LIMIT * 100) if OD_LIMIT > 0 else 0
    ratio["Returned Cheques"] = 0
    ratio["Number of Excesses"] = int((df["OD Util (RM)"] > OD_LIMIT).sum()) if OD_LIMIT > 0 else 0

    return pd.DataFrame(ratio.items(), columns=["Metric", "Value"])

# =====================================================
# RUN ANALYSIS
# =====================================================
if st.button("Run Analysis", type="primary"):

    months = split_by_month(df_all)

    # -------- MONTHLY BREAKDOWN (TXT) --------
    st.subheader("📂 Monthly Breakdown (Audit)")
    txt_blocks = []

    for m, mdf in months.items():
        with st.expander(f"Show {m}"):
            st.dataframe(mdf, use_container_width=True)

        lines = [f">>> {m.upper()}", "-" * 120]
        lines.append("Date | Description | Debit | Credit | Balance")
        lines.append("-" * 120)

        for _, r in mdf.iterrows():
            lines.append(
                f"{r['date']} | {str(r['description'])[:50]} | "
                f"{r['debit']:.2f} | {r['credit']:.2f} | {r['balance']:.2f}"
            )

        txt_blocks.append("\n".join(lines))

    txt_report = "\n\n".join(txt_blocks)

    st.download_button(
        "📄 Download Monthly Breakdown (TXT)",
        txt_report,
        "monthly_breakdown.txt",
        "text/plain"
    )

    # -------- SUMMARY + RATIOS --------
    summary_df = compute_monthly_summary(months)
    ratio_df = compute_ratios(summary_df)

    st.subheader("📅 Monthly Summary")
    st.dataframe(summary_df, use_container_width=True)

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)

    # -------- EXCEL EXPORT --------
    output = BytesIO()
    wb = Workbook()

    ws1 = wb.active
    ws1.title = "Monthly Summary"
    for r in dataframe_to_rows(summary_df, index=False, header=True):
        ws1.append(r)

    ws2 = wb.create_sheet("Financial Ratios")
    for r in dataframe_to_rows(ratio_df, index=False, header=True):
        ws2.append(r)

    wb.save(output)

    st.download_button(
        "📊 Download Summary + Ratios (Excel)",
        output.getvalue(),
        "bank_analysis.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
