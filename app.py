import streamlit as st
import tempfile
import pandas as pd
from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils.dataframe import dataframe_to_rows

# ===============================
# BANK IMPORTS (DO NOT TOUCH)
# ===============================
from bank_rakyat import extract_bank_rakyat
from bank_islam import extract_bank_islam
from cimb import extract_cimb
from maybank import extract_maybank
from rhb import extract_rhb
from ambank import extract_ambank

BANK_EXTRACTORS = {
    "Bank Rakyat": extract_bank_rakyat,
    "Bank Islam": extract_bank_islam,
    "CIMB": extract_cimb,
    "Maybank": extract_maybank,
    "RHB": extract_rhb,
    "Ambank": extract_ambank,
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
# EXTRACT ALL TRANSACTIONS
# ===============================
extractor = BANK_EXTRACTORS[bank_choice]
all_dfs = []

for f in uploaded_files:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(f.read())
        path = tmp.name

    df = extractor(path)
    if df is not None and not df.empty:
        df["_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
        df = df.dropna(subset=["_dt"]).sort_values("_dt").drop(columns="_dt")
        all_dfs.append(df)

df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📄 Cleaned Transaction List")
st.dataframe(df_all, use_container_width=True)

# ===============================
# HELPERS
# ===============================
def split_by_month(df):
    df["_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["_dt"])

    months = {}
    for m, g in df.groupby(df["_dt"].dt.to_period("M")):
        label = m.strftime("%b %Y")
        months[label] = g.drop(columns="_dt").reset_index(drop=True)

    return dict(sorted(months.items()))

def opening_from_first_row(r):
    return r["balance"] - r["credit"] + r["debit"]

# ===============================
# TXT FORMAT (EXACT STYLE)
# ===============================
def month_to_txt(df, month_label):
    W_DATE, W_DESC, W_DEBIT, W_CREDIT, W_BAL = 12, 60, 15, 15, 15

    def fmt(x): return f"{float(x):,.2f}"

    def line(ch="-"):
        return (
            f"+{ch*(W_DATE+2)}"
            f"+{ch*(W_DESC+2)}"
            f"+{ch*(W_DEBIT+2)}"
            f"+{ch*(W_CREDIT+2)}"
            f"+{ch*(W_BAL+2)}+"
        )

    out = []
    out.append(f">>> {month_label.upper()}")
    out.append(line())
    out.append(
        f"| {'Date':^{W_DATE}} | {'Description':<{W_DESC}} | "
        f"{'Debit':>{W_DEBIT}} | {'Credit':>{W_CREDIT}} | {'Balance':>{W_BAL}} |"
    )
    out.append(line("="))

    for _, r in df.iterrows():
        out.append(
            f"| {r['date']:<{W_DATE}} | {r['description'][:W_DESC]:<{W_DESC}} | "
            f"{fmt(r['debit']):>{W_DEBIT}} | "
            f"{fmt(r['credit']):>{W_CREDIT}} | "
            f"{fmt(r['balance']):>{W_BAL}} |"
        )
        out.append(line())

    return "\n".join(out)

# ===============================
# RUN ANALYSIS
# ===============================
if st.button("Run Analysis", type="primary"):

    months = split_by_month(df_all)

    # ---------------------------
    # MONTHLY BREAKDOWN (TXT)
    # ---------------------------
    st.subheader("📂 Monthly Breakdown (Audit)")
    for month, mdf in months.items():
        with st.expander(f"Show {month}"):
            st.dataframe(mdf, use_container_width=True)

            txt = month_to_txt(mdf, month)
            st.download_button(
                f"⬇ Download {month} TXT",
                data=txt,
                file_name=f"{month.replace(' ', '_')}.txt",
                mime="text/plain"
            )

    # ---------------------------
    # MONTHLY SUMMARY
    # ---------------------------
    rows = []
    prev_end = None

    for month, mdf in months.items():
        first, last = mdf.iloc[0], mdf.iloc[-1]

        opening = opening_from_first_row(first) if prev_end is None else prev_end
        ending = last["balance"]

        rows.append({
            "Month": month,
            "Opening": opening,
            "Debit": mdf["debit"].sum(),
            "Credit": mdf["credit"].sum(),
            "Ending": ending,
            "Highest": mdf["balance"].max(),
            "Lowest": mdf["balance"].min(),
            "Swing": abs(mdf["balance"].max() - mdf["balance"].min()),
            "OD Util (RM)": abs(ending) if ending < 0 else 0,
            "OD %": (abs(ending) / OD_LIMIT * 100) if ending < 0 and OD_LIMIT > 0 else 0
        })

        prev_end = ending

    summary_df = pd.DataFrame(rows)

    st.subheader("📅 Summary Table")
    st.dataframe(summary_df, use_container_width=True)

    # ---------------------------
    # FINANCIAL RATIOS (FULL)
    # ---------------------------
    ratio = {}
    ratio["Total Credit (6 Months)"] = summary_df["Credit"].sum()
    ratio["Total Debit (6 Months)"] = summary_df["Debit"].sum()
    ratio["Annualized Credit"] = ratio["Total Credit (6 Months)"] * 2
    ratio["Annualized Debit"] = ratio["Total Debit (6 Months)"] * 2
    ratio["Average Opening Balance"] = summary_df["Opening"].mean()
    ratio["Average Ending Balance"] = summary_df["Ending"].mean()
    ratio["Highest Balance (Period)"] = summary_df["Highest"].max()
    ratio["Lowest Balance (Period)"] = summary_df["Lowest"].min()
    ratio["Average OD Utilization (RM)"] = summary_df["OD Util (RM)"].mean()
    ratio["Average % OD Utilization"] = summary_df["OD %"].mean()
    ratio["Average Monthly Swing (RM)"] = summary_df["Swing"].mean()
    ratio["% of Swing"] = (
        ratio["Average Monthly Swing (RM)"] / OD_LIMIT * 100
        if OD_LIMIT > 0 else 0
    )
    ratio["Returned Cheques"] = 0
    ratio["Number of Excesses"] = int(
        (summary_df["OD Util (RM)"] > OD_LIMIT).sum()
    ) if OD_LIMIT > 0 else 0

    ratio_df = pd.DataFrame(ratio.items(), columns=["Metric", "Value"])

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)

    # ---------------------------
    # EXCEL EXPORT
    # ---------------------------
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

    for r, row in enumerate(
        dataframe_to_rows(ratio_df, index=False, header=True),
        start + 1
    ):
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
