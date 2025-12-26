import streamlit as st
import tempfile
import pandas as pd
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
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
st.set_page_config(page_title="Bank Statement Analysis", layout="wide")
st.title("🏦 Bank Statement Analysis")

# =====================================================
# SESSION STATE
# =====================================================
if "months" not in st.session_state:
    st.session_state.months = None

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

for f in uploaded_files:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(f.read())
        path = tmp.name

    df = extractor(path)
    if df is not None and not df.empty:
        df["_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        df = df.dropna(subset=["_dt"]).sort_values("_dt")
        df = df.drop(columns="_dt").reset_index(drop=True)
        all_dfs.append(df)

df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📄 Cleaned Transaction List")
st.dataframe(df_all, use_container_width=True)

# =====================================================
# OD LIMIT
# =====================================================
OD_LIMIT = st.number_input("Enter OD Limit (RM)", min_value=0.0, step=1000.0)

# =====================================================
# HELPERS
# =====================================================
def compute_opening_balance_from_row(row):
    return row["balance"] - row["credit"] + row["debit"]

def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True, errors="coerce")
    temp = temp.dropna(subset=["_dt"])

    months = {}
    for m, g in temp.groupby(temp["_dt"].dt.to_period("M")):
        months[m.strftime("%b %Y")] = g.drop(columns="_dt").reset_index(drop=True)

    return months

def compute_monthly_summary(months, od_limit):
    rows = []
    prev_ending = None

    for month, df in months.items():
        first = df.iloc[0]
        last = df.iloc[-1]

        opening = compute_opening_balance_from_row(first) if prev_ending is None else prev_ending
        ending = last["balance"]

        rows.append({
            "Month": month,
            "Opening": opening,
            "Debit": df["debit"].sum(),
            "Credit": df["credit"].sum(),
            "Ending": ending,
            "Highest": df["balance"].max(),
            "Lowest": df["balance"].min(),
            "Swing": abs(df["balance"].max() - df["balance"].min()),
            "OD Util (RM)": abs(ending) if od_limit > 0 and ending < 0 else 0,
            "OD %": abs(ending) / od_limit * 100 if od_limit > 0 and ending < 0 else 0,
        })

        prev_ending = ending

    return pd.DataFrame(rows)

def compute_ratios(summary):
    return pd.DataFrame([
        ("Total Credit", summary["Credit"].sum()),
        ("Total Debit", summary["Debit"].sum()),
        ("Annualized Credit", summary["Credit"].sum() * 2),
        ("Annualized Debit", summary["Debit"].sum() * 2),
        ("Average Opening Balance", summary["Opening"].mean()),
        ("Average Ending Balance", summary["Ending"].mean()),
        ("Highest Balance", summary["Highest"].max()),
        ("Lowest Balance", summary["Lowest"].min()),
    ], columns=["Metric", "Value"])

def df_to_txt(df, month):
    lines = [
        f">>> {month.upper()}",
        "-" * 100,
        f"{'Date':<12} | {'Description':<45} | {'Debit':>12} | {'Credit':>12} | {'Balance':>14}",
        "-" * 100,
    ]
    for _, r in df.iterrows():
        lines.append(
            f"{r['date']:<12} | {r['description'][:45]:<45} | "
            f"{r['debit']:>12.2f} | {r['credit']:>12.2f} | {r['balance']:>14.2f}"
        )
    return "\n".join(lines)

def export_excel(summary, ratios):
    wb = Workbook()
    ws1 = wb.active
    ws1.title = "Monthly Summary"

    for r in dataframe_to_rows(summary, index=False, header=True):
        ws1.append(r)

    ws2 = wb.create_sheet("Financial Ratios")
    for r in dataframe_to_rows(ratios, index=False, header=True):
        ws2.append(r)

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return bio

# =====================================================
# RUN ANALYSIS
# =====================================================
if st.button("Run Analysis", type="primary"):

    st.session_state.months = split_by_month(df_all)

    st.subheader("📂 Monthly Breakdown (TXT)")
    for month, mdf in st.session_state.months.items():
        with st.expander(f"Show {month}"):
            st.dataframe(mdf, use_container_width=True)
            st.download_button(
                f"⬇️ Download {month} (TXT)",
                df_to_txt(mdf, month).encode("utf-8"),
                f"{month.replace(' ', '_')}.txt",
                mime="text/plain"
            )

    summary = compute_monthly_summary(st.session_state.months, OD_LIMIT)
    ratios = compute_ratios(summary)

    st.subheader("📊 Monthly Summary")
    st.dataframe(summary, use_container_width=True)

    st.subheader("📈 Financial Ratios")
    st.dataframe(ratios, use_container_width=True)

    excel = export_excel(summary, ratios)
    st.download_button(
        "⬇️ Download Summary + Ratios (Excel)",
        excel,
        "Bank_Statement_Analysis.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
