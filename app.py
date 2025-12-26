import streamlit as st
import tempfile
import pandas as pd

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
st.set_page_config(
    page_title="Bank Statement Analysis",
    layout="wide"
)

st.title("🏦 Bank Statement Analysis")

# =====================================================
# SESSION STATE (CRITICAL)
# =====================================================
if "months" not in st.session_state:
    st.session_state.months = None

if "monthly_summary" not in st.session_state:
    st.session_state.monthly_summary = None

if "ratio_df" not in st.session_state:
    st.session_state.ratio_df = None

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
            try:
                df["_sort_temp"] = pd.to_datetime(
                    df["date"], dayfirst=True, errors="coerce"
                )
                df = (
                    df.sort_values("_sort_temp")
                    .drop(columns="_sort_temp")
                    .reset_index(drop=True)
                )
            except:
                pass

            all_dfs.append(df)

    except Exception as e:
        st.error(f"Error extracting {uploaded_file.name}: {e}")

    progress_bar.progress((i + 1) / len(uploaded_files))

if not all_dfs:
    st.error("No transactions extracted.")
    st.stop()

df_all = pd.concat(all_dfs, ignore_index=True)

st.subheader("📄 Cleaned Transaction List (Chronological)")
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
# HELPER FUNCTIONS (UNCHANGED)
# =====================================================
def compute_opening_balance_from_row(row):
    return row["balance"] - row["credit"] + row["debit"]


def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True, errors="coerce")
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
        if df.empty:
            continue

        first_txn = df.iloc[0]
        last_txn = df.iloc[-1]

        opening = (
            compute_opening_balance_from_row(first_txn)
            if prev_ending is None
            else prev_ending
        )

        ending = last_txn["balance"]

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


def compute_ratios(summary, od_limit):
    if summary.empty:
        return pd.DataFrame()

    return pd.DataFrame([
        ("Total Credit (6 Months)", summary["Credit"].sum()),
        ("Total Debit (6 Months)", summary["Debit"].sum()),
        ("Annualized Credit", summary["Credit"].sum() * 2),
        ("Annualized Debit", summary["Debit"].sum() * 2),
        ("Average Opening Balance", summary["Opening"].mean()),
        ("Average Ending Balance", summary["Ending"].mean()),
        ("Highest Balance", summary["Highest"].max()),
        ("Lowest Balance", summary["Lowest"].min()),
    ], columns=["Metric", "Value"])


def df_to_txt(df, month_label):
    lines = [
        f"Month: {month_label}",
        "-" * 100,
        f"{'Date':<12} | {'Description':<45} | {'Debit':>12} | {'Credit':>12} | {'Balance':>14}",
        "-" * 100,
    ]

    for _, row in df.iterrows():
        lines.append(
            f"{str(row['date']):<12} | "
            f"{str(row['description'])[:45]:<45} | "
            f"{row['debit']:>12.2f} | "
            f"{row['credit']:>12.2f} | "
            f"{row['balance']:>14.2f}"
        )

    lines.append("-" * 100)
    return "\n".join(lines)

# =====================================================
# RUN ANALYSIS (BUTTON)
# =====================================================
if st.button("Run Analysis", type="primary"):

    st.session_state.months = split_by_month(df_all)

    st.session_state.monthly_summary = compute_monthly_summary(
        st.session_state.months, OD_LIMIT
    )

    st.session_state.ratio_df = compute_ratios(
        st.session_state.monthly_summary, OD_LIMIT
    )

# =====================================================
# MONTHLY BREAKDOWN + TXT DOWNLOADS
# =====================================================
if st.session_state.months:

    st.subheader("📂 Monthly Breakdown (Audit)")

    for month, mdf in st.session_state.months.items():

        with st.expander(f"Show {month}"):

            st.dataframe(mdf, use_container_width=True)

            txt_data = df_to_txt(mdf, month)

            st.download_button(
                label=f"⬇️ Download {month} as TXT",
                data=txt_data,
                file_name=f"{month.replace(' ', '_')}_transactions.txt",
                mime="text/plain",
                key=f"download_{month}"
            )

# =====================================================
# SUMMARY OUTPUTS
# =====================================================
if st.session_state.monthly_summary is not None:

    st.subheader("📅 Monthly Summary")
    st.dataframe(st.session_state.monthly_summary, use_container_width=True)

    st.subheader("📊 Financial Ratios")
    st.dataframe(st.session_state.ratio_df, use_container_width=True)
