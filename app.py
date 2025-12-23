import streamlit as st
import tempfile
import pandas as pd

# =====================================================
# BANK IMPORTS
# =====================================================
# Make sure you have these files in the same folder
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
# 1. SIDEBAR / INPUTS
# =====================================================
st.sidebar.header("Settings")

# Bank Selection
bank_choice = st.sidebar.selectbox(
    "Select Bank",
    ["Bank Rakyat", "Bank Islam", "CIMB", "Maybank", "RHB"]
)

# OD Limit Input
OD_LIMIT = st.sidebar.number_input(
    "Enter OD Limit (RM)",
    min_value=0.0,
    step=1000.0,
    value=0.0
)

BANK_EXTRACTORS = {
    "Bank Rakyat": extract_bank_rakyat,
    "Bank Islam": extract_bank_islam,
    "CIMB": extract_cimb,
    "Maybank": extract_maybank,
    "RHB": extract_rhb,
}

# =====================================================
# 2. FILE UPLOAD & EXTRACTION (Happens Immediately)
# =====================================================
uploaded_files = st.file_uploader(
    f"Upload {bank_choice} Statement PDF(s)",
    type=["pdf"],
    accept_multiple_files=True
)

if not uploaded_files:
    st.info("👋 Please upload a PDF to begin.")
    st.stop()

# --- PROCESSING ---
extractor = BANK_EXTRACTORS[bank_choice]
all_dfs = []

st.write("---")
with st.spinner(f"Extracting data from {len(uploaded_files)} files..."):
    for uploaded_file in uploaded_files:
        # Save temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.read())
            pdf_path = tmp.name

        try:
            # Run Extractor
            df = extractor(pdf_path)

            if df is not None and not df.empty:
                # -----------------------------------------------------------
                # AUTO-SORT LOGIC (Fix for Maybank Personal vs Business)
                # -----------------------------------------------------------
                try:
                    # Create temp date for sorting
                    df["_sort_temp"] = pd.to_datetime(df["date"], dayfirst=True, errors='coerce')
                    # Force sort: Oldest -> Newest
                    df = df.sort_values(by="_sort_temp", ascending=True)
                    # Clean up
                    df = df.drop(columns=["_sort_temp"]).reset_index(drop=True)
                except Exception:
                    pass 
                
                all_dfs.append(df)
            else:
                st.warning(f"⚠️ No transactions found in {uploaded_file.name}")

        except Exception as e:
            st.error(f"❌ Error parsing {uploaded_file.name}: {e}")

if not all_dfs:
    st.error("No valid data extracted. Please check your files.")
    st.stop()

# Combine all extracted data
df_all = pd.concat(all_dfs, ignore_index=True)

# Show the raw data first (Verification)
st.subheader(f"✅ Extracted Transactions ({len(df_all)} rows)")
st.dataframe(df_all, use_container_width=True, height=300)

# =====================================================
# 3. ANALYSIS LOGIC (Hidden until Button Click)
# =====================================================

def compute_opening_balance_from_row(row):
    # Backward calculation: Prev = Curr - Credit + Debit
    return row["balance"] - row["credit"] + row["debit"]

def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True, errors='coerce')
    temp = temp.dropna(subset=["_dt"])

    month_order = (
        temp.assign(m=temp["_dt"].dt.to_period("M"))
        .groupby("m")["_dt"].min().sort_values().index
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

def compute_monthly_summary(all_months, od_limit):
    rows = []
    prev_ending = None

    for month, df in all_months.items():
        if df.empty: continue
        
        # Data is already sorted Oldest -> Newest
        first_txn = df.iloc[0]
        last_txn = df.iloc[-1]

        if prev_ending is None:
            opening = compute_opening_balance_from_row(first_txn)
        else:
            opening = prev_ending

        ending = last_txn["balance"]
        
        # Stats
        debit = df["debit"].sum()
        credit = df["credit"].sum()
        highest = df["balance"].max()
        lowest = df["balance"].min()
        swing = abs(highest - lowest)

        # OD Logic
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
    
    # Simple Ratio Table
    metrics = [
        ("Total Credit (All Months)", df["Credit"].sum()),
        ("Total Debit (All Months)", df["Debit"].sum()),
        ("Average Opening Balance", df["Opening"].mean()),
        ("Average Ending Balance", df["Ending"].mean()),
        ("Highest Balance (Period)", df["Highest"].max()),
        ("Lowest Balance (Period)", df["Lowest"].min()),
        ("Average Monthly Swing", df["Swing"].mean()),
    ]
    
    if od_limit > 0:
        metrics.append(("Average OD Utilization (RM)", df["OD Util (RM)"].mean()))
        metrics.append(("Average OD Utilization (%)", df["OD %"].mean()))
        metrics.append(("Number of Excesses", int((df["OD Util (RM)"] > od_limit).sum())))

    return pd.DataFrame(metrics, columns=["Metric", "Value"])

# =====================================================
# 4. RUN ANALYSIS BUTTON
# =====================================================
st.write("---")
col1, col2, col3 = st.columns([1, 2, 1])

with col2:
    # PRIMARY BUTTON (Blue)
    run_btn = st.button("🚀 RUN ANALYSIS", type="primary", use_container_width=True)

if run_btn:
    st.success("Running Analysis...")
    
    # A. Split Data
    months = split_by_month(df_all)
    
    # B. Compute Summary
    summary_df = compute_monthly_summary(months, OD_LIMIT)
    ratio_df = compute_ratios(summary_df, OD_LIMIT)

    # C. Display Results
    st.subheader("📅 Monthly Summary")
    st.dataframe(summary_df, use_container_width=True)

    st.subheader("📊 Financial Ratios")
    st.dataframe(ratio_df, use_container_width=True)

    st.subheader("📂 Monthly Audit (Details)")
    for month, mdf in months.items():
        with st.expander(f"Show {month} Transactions"):
            st.dataframe(mdf, use_container_width=True)
