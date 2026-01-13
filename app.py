import streamlit as st
import tempfile
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows
import re
import json

# ===============================
# BANK IMPORTS
# ===============================
from bank_rakyat import extract_bank_rakyat
from bank_islam import extract_bank_islam
from cimb import extract_cimb
from maybank import extract_maybank
from rhb import extract_rhb
from ambank import extract_ambank
from agro_bank import extract_agro_bank
from bank_muamalat import extract_bank_muamalat
from public_bank import extract_public_bank
from ocbc import extract_ocbc

BANK_EXTRACTORS = {
    "Bank Rakyat": extract_bank_rakyat,
    "Bank Islam": extract_bank_islam,
    "CIMB": extract_cimb,
    "Maybank": extract_maybank,
    "RHB": extract_rhb,
    "Ambank": extract_ambank,
    "Agrobank": extract_agro_bank,
    "Bank Muamalat": extract_bank_muamalat,
    "Public Bank": extract_public_bank,
    "OCBC": extract_ocbc,
}

# ===============================
# PAGE CONFIG
# ===============================
st.set_page_config(page_title="Bank Statement Analysis", layout="wide")
st.title("🏦 Bank Statement Analysis")

# ===============================
# INPUTS
# ===============================
bank_choice = st.selectbox("Select Bank", list(BANK_EXTRACTORS.keys()))
uploaded_files = st.file_uploader(
    "Upload Bank Statement PDF(s)",
    type=["pdf"],
    accept_multiple_files=True
)

OD_LIMIT = st.number_input("Enter OD Limit (RM)", min_value=0.0, step=1000.0)

if not uploaded_files:
    st.stop()

# ===============================
# OPENING BALANCE FORMULA (UNCHANGED)
# ===============================
def opening_from_first_row(r):
    return r["balance"] - r["credit"] + r["debit"]

# ===============================
# EXTRACT PER FILE
# ===============================
extractor = BANK_EXTRACTORS[bank_choice]
monthly_data = {}

for f in uploaded_files:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(f.read())
        path = tmp.name

    df = extractor(path)
    if df is None or df.empty:
        continue

    df["_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    valid_dates = df["_dt"].dropna()

    if not valid_dates.empty:
        period = valid_dates.iloc[0].to_period("M")
    else:
        m = re.search(
            r"(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|"
            r"January|February|March|April|May|June|July|August|"
            r"September|October|November|December)",
            f.name,
            re.IGNORECASE
        )
        if not m:
            raise ValueError(f"Cannot infer month from filename: {f.name}")

        month_str = m.group(1)[:3].title()
        period = pd.to_datetime(f"{month_str} 2023", format="%b %Y").to_period("M")

    label = period.strftime("%b %Y")
    df = df.drop(columns="_dt", errors="ignore").reset_index(drop=True)
    monthly_data[label] = df

# ===============================
# SORT MONTHS
# ===============================
def sort_months(d):
    items = []
    for k, v in d.items():
        items.append((pd.to_datetime(k, format="%b %Y"), k, v))
    items.sort(key=lambda x: x[0])
    return [(k, v) for _, k, v in items]

months = sort_months(monthly_data)

# ===============================
# DISPLAY DATA + TXT & JSON DOWNLOADS
# ===============================
st.subheader("📄 Extracted Monthly Data")

for month, df in months:
    with st.expander(month):
        st.dataframe(df, use_container_width=True)

        # -------- TXT FORMAT --------
        W_DATE, W_DESC, W_DEBIT, W_CREDIT, W_BAL = 12, 60, 15, 15, 15

        def fmt(x):
            return f"{float(x):,.2f}"

        def line(ch="-"):
            return (
                f"+{ch*(W_DATE+2)}"
                f"+{ch*(W_DESC+2)}"
                f"+{ch*(W_DEBIT+2)}"
                f"+{ch*(W_CREDIT+2)}"
                f"+{ch*(W_BAL+2)}+"
            )

        txt_lines = []
        txt_lines.append(f">>> {month.upper()}")
        txt_lines.append(line())
        txt_lines.append(
            f"| {'Date':^{W_DATE}} | {'Description':<{W_DESC}} | "
            f"{'Debit':>{W_DEBIT}} | {'Credit':>{W_CREDIT}} | {'Balance':>{W_BAL}} |"
        )
        txt_lines.append(line("="))

        for _, r in df.iterrows():
            txt_lines.append(
                f"| {r['date']:<{W_DATE}} | {r['description'][:W_DESC]:<{W_DESC}} | "
                f"{fmt(r['debit']):>{W_DEBIT}} | "
                f"{fmt(r['credit']):>{W_CREDIT}} | "
                f"{fmt(r['balance']):>{W_BAL}} |"
            )
            txt_lines.append(line())

        txt_data = "\n".join(txt_lines)

        # -------- JSON --------
        json_data = json.dumps(df.to_dict(orient="records"), indent=2)

        col1, col2 = st.columns(2)

        with col1:
            st.download_button(
                "⬇ Download TXT",
                data=txt_data,
                file_name=f"{month.replace(' ', '_')}.txt",
                mime="text/plain"
            )

        with col2:
            st.download_button(
                "⬇ Download JSON",
                data=json_data,
                file_name=f"{month.replace(' ', '_')}.json",
                mime="application/json"
            )

# ===============================
# MONTHLY SUMMARY (UNCHANGED)
# ===============================
rows = []

for month, df in months:
    first = df.iloc[0]
    last = df.iloc[-1]

    opening = opening_from_first_row(first)
    ending = last["balance"]

    highest = df["balance"].max()
    lowest = df["balance"].min()

    rows.append({
        "Month": month,
        "Opening": round(opening, 2),
        "Debit": round(df["debit"].sum(), 2),
        "Credit": round(df["credit"].sum(), 2),
        "Ending": round(ending, 2),
        "Highest": round(highest, 2),
        "Lowest": round(lowest, 2),
        "Swing": round(highest - lowest, 2),
        "OD Util (RM)": round(abs(ending), 2) if ending < 0 else 0,
        "OD %": round(abs(ending) / OD_LIMIT * 100, 2)
        if ending < 0 and OD_LIMIT > 0 else 0
    })

summary_df = pd.DataFrame(rows)

st.subheader("📅 Summary Table")
st.dataframe(summary_df, use_container_width=True)

# ===============================
# FINANCIAL RATIOS (UNCHANGED)
# ===============================
ratio = {
    "Total Credit (6 Months)": summary_df["Credit"].sum(),
    "Total Debit (6 Months)": summary_df["Debit"].sum(),
    "Annualized Credit": summary_df["Credit"].sum() * 2,
    "Annualized Debit": summary_df["Debit"].sum() * 2,
    "Average Opening Balance": summary_df["Opening"].mean(),
    "Average Ending Balance": summary_df["Ending"].mean(),
    "Highest Balance (Period)": summary_df["Highest"].max(),
    "Lowest Balance (Period)": summary_df["Lowest"].min(),
    "Average OD Utilization (RM)": summary_df["OD Util (RM)"].mean(),
    "Average % OD Utilization": summary_df["OD %"].mean(),
    "Average Monthly Swing (RM)": summary_df["Swing"].mean(),
    "% of Swing": (summary_df["Swing"].mean() / OD_LIMIT * 100) if OD_LIMIT > 0 else 0,
    "Returned Cheques": 0,
    "Number of Excesses": int((summary_df["OD Util (RM)"] > OD_LIMIT).sum())
    if OD_LIMIT > 0 else 0
}

ratio_df = pd.DataFrame(ratio.items(), columns=["Metric", "Value"])

st.subheader("📊 Financial Ratios")
st.dataframe(ratio_df, use_container_width=True)

# ===============================
# EXCEL EXPORT (UNCHANGED)
# ===============================
wb = Workbook()
ws = wb.active
ws.title = "Summary"

header = PatternFill("solid", fgColor="1F4E78")
font = Font(color="FFFFFF", bold=True)

for r, row in enumerate(dataframe_to_rows(summary_df, index=False, header=True), 1):
    for c, v in enumerate(row, 1):
        cell = ws.cell(row=r, column=c, value=v)
        if r == 1:
            cell.fill = header
            cell.font = font

start = ws.max_row + 3
ws.cell(row=start, column=1, value="Financial Ratios").font = Font(bold=True)

for r, row in enumerate(dataframe_to_rows(ratio_df, index=False, header=True), start + 1):
    for c, v in enumerate(row, 1):
        ws.cell(row=r, column=c, value=v)

bio = BytesIO()
wb.save(bio)
bio.seek(0)

st.download_button(
    "⬇ Download Summary + Ratios (Excel)",
    data=bio,
    file_name="Bank_Statement_Analysis.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)
