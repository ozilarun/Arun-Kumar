import streamlit as st
import tempfile
import pandas as pd
import io

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
st.title("🏦 Bank Statement Analysis (TXT Export)")

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
    st.info("Please upload a file to continue.")
    st.stop()

# =====================================================
# EXTRACTION
# =====================================================
extractor = BANK_EXTRACTORS[bank_choice]
all_dfs = []

progress_bar = st.progress(0)

for i, uploaded_file in enumerate(uploaded_files):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.read())
        pdf_path = tmp.name

    try:
        df = extractor(pdf_path)
        if df is not None and not df.empty:
            # AUTO-SORT Logic
            try:
                df["_sort_temp"] = pd.to_datetime(df["date"], dayfirst=True, errors='coerce')
                df = df.sort_values(by="_sort_temp", ascending=True)
                df = df.drop(columns=["_sort_temp"]).reset_index(drop=True)
            except:
                pass 
            all_dfs.append(df)
        else:
            st.warning(f"No data found in {uploaded_file.name}")
            
    except Exception as e:
        st.error(f"Error extracting {uploaded_file.name}: {e}")

    progress_bar.progress((i + 1) / len(uploaded_files))

if not all_dfs:
    st.error("No transactions extracted.")
    st.stop()

df_all = pd.concat(all_dfs, ignore_index=True)

# =====================================================
# INPUTS
# =====================================================
OD_LIMIT = st.number_input("Enter OD Limit (RM)", min_value=0.0, step=1000.0)

# =====================================================
# HELPER FUNCTIONS
# =====================================================
def compute_opening_balance_from_row(row):
    return row["balance"] - row["credit"] + row["debit"]

def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True, errors='coerce')
    temp = temp.dropna(subset=["_dt"])

    month_order = (
        temp.assign(m=temp["_dt"].dt.to_period("M"))
        .groupby("m")["_dt"]
        .min()
        .sort_values()
        .index
    )

    months = {}
    for m in month_order:
        label = m.strftime("%B %Y") # Full Month Name (e.g., January 2025)
        months[label] = (
            temp[temp["_dt"].dt.to_period("M") == m]
            .drop(columns="_dt")
            .reset_index(drop=True)
        )
    return months

def generate_txt_report(months_data, summary_df):
    """Creates a formatted text report with monthly breakdowns."""
    output = io.StringIO()
    
    # Write Header
    output.write("=================================================================\n")
    output.write("                 BANK STATEMENT ANALYSIS REPORT                  \n")
    output.write("=================================================================\n\n")

    # 1. SUMMARY SECTION
    if not summary_df.empty:
        output.write("SUMMARY BY MONTH\n")
        output.write("-" * 85 + "\n")
        output.write(f"{'Month':<15} | {'Debit':>12} | {'Credit':>12} | {'Ending Bal':>12} | {'High':>10} | {'Low':>10}\n")
        output.write("-" * 85 + "\n")
        
        for _, row in summary_df.iterrows():
            output.write(
                f"{row['Month']:<15} | "
                f"{row['Debit']:>12,.2f} | "
                f"{row['Credit']:>12,.2f} | "
                f"{row['Ending']:>12,.2f} | "
                f"{row['Highest']:>10,.2f} | "
                f"{row['Lowest']:>10,.2f}\n"
            )
        output.write("-" * 85 + "\n\n\n")

    # 2. DETAILED BREAKDOWN
    output.write("DETAILED TRANSACTION BREAKDOWN\n")
    output.write("=================================================================\n")

    for month_name, df_month in months_data.items():
        output.write(f"\n>>> {month_name.upper()}\n")
        output.write("-" * 110 + "\n")
        output.write(f"{'Date':<12} | {'Description':<50} | {'Debit':>12} | {'Credit':>12} | {'Balance':>12}\n")
        output.write("-" * 110 + "\n")

        for _, row in df_month.iterrows():
            # Truncate description to fit nicely
            desc = str(row['description']).replace("\n", " ")[:50]
            
            output.write(
                f"{str(row['date']):<12} | "
                f"{desc:<50} | "
                f"{row['debit']:>12,.2f} | "
                f"{row['credit']:>12,.2f} | "
                f"{row['balance']:>12,.2f}\n"
            )
        
        # Monthly Footer
        tot_deb = df_month['debit'].sum()
        tot_cred = df_month['credit'].sum()
        output.write("-" * 110 + "\n")
        output.write(f"{'TOTAL':<65} | {tot_deb:>12,.2f} | {tot_cred:>12,.2f} |\n")
        output.write("=" * 110 + "\n\n")

    return output.getvalue()

def compute_monthly_summary(all_months, od_limit):
    rows = []
    prev_ending = None

    for month, df in all_months.items():
        if df.empty: continue
        
        first_txn = df.iloc[0]
        last_txn = df.iloc[-1]

        if prev_ending is None:
            opening = compute_opening_balance_from_row(first_txn)
        else:
            opening = prev_ending

        ending = last_txn["balance"]
        
        rows.append({
            "Month": month,
            "Opening": opening,
            "Debit": df["debit"].sum(),
            "Credit": df["credit"].sum(),
            "Ending": ending,
            "Highest": df["balance"].max(),
            "Lowest": df["balance"].min(),
            "Swing": abs(df["balance"].max() - df["balance"].min())
        })
        prev_ending = ending

    return pd.DataFrame(rows)

# =====================================================
# RUN ANALYSIS
# =====================================================
if st.button("Run Analysis", type="primary"):
    
    # 1. Split Data
    months = split_by_month(df_all)
    
    # 2. Compute Summary
    monthly_summary = compute_monthly_summary(months, OD_LIMIT)
    
    # 3. Display on Screen
    st.subheader("📊 Summary Table")
    st.dataframe(monthly_summary, use_container_width=True)

    # 4. Generate Text Report
    txt_data = generate_txt_report(months, monthly_summary)
    
    # 5. Download Button
    st.download_button(
        label="📥 Download Full Report (.txt)",
        data=txt_data,
        file_name="Bank_Statement_Report.txt",
        mime="text/plain"
    )

    # 6. Optional: Show Preview of Text
    with st.expander("Preview Text Report"):
        st.text(txt_data)
