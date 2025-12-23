import streamlit as st
import tempfile
import pandas as pd

# =====================================================
# PAGE CONFIG (MUST BE FIRST)
# =====================================================
st.set_page_config(
    page_title="Bank Statement Analysis",
    layout="wide"
)

st.title("🏦 Bank Statement Analysis")

# =====================================================
# SESSION STATE
# =====================================================
if "run_clicked" not in st.session_state:
    st.session_state.run_clicked = False

if "df_all" not in st.session_state:
    st.session_state.df_all = None

if "status" not in st.session_state:
    st.session_state.status = "idle"

# =====================================================
# 🔴 BUTTONS FIRST (CRITICAL FIX)
# =====================================================
col1, col2 = st.columns(2)

with col1:
    if st.button("▶ Run Analysis", use_container_width=True):
        st.session_state.run_clicked = True
        st.session_state.status = "running"

with col2:
    if st.button("🔄 Reset", use_container_width=True):
        st.session_state.run_clicked = False
        st.session_state.df_all = None
        st.session_state.status = "idle"
        st.rerun()

st.markdown(f"### ⚙️ Status: **{st.session_state.status.upper()}**")

st.divider()

# =====================================================
# BANK SELECTION
# =====================================================
bank_choice = st.selectbox(
    "Select Bank",
    ["Bank Rakyat", "Bank Islam", "CIMB", "Maybank", "RHB"]
)

# =====================================================
# FILE UPLOAD
# =====================================================
uploaded_files = st.file_uploader(
    "Upload Bank Statement PDF(s)",
    type=["pdf"],
    accept_multiple_files=True
)

# =====================================================
# OD LIMIT
# =====================================================
OD_LIMIT = st.number_input(
    "Enter OD Limit (RM)",
    min_value=0.0,
    step=1000.0
)

# =====================================================
# LAZY BANK IMPORTS (SAFE)
# =====================================================
def get_extractor(bank):
    if bank == "Bank Rakyat":
        from bank_rakyat import extract_bank_rakyat
        return extract_bank_rakyat
    if bank == "Bank Islam":
        from bank_islam import extract_bank_islam
        return extract_bank_islam
    if bank == "CIMB":
        from cimb import extract_cimb
        return extract_cimb
    if bank == "Maybank":
        from maybank import extract_maybank
        return extract_maybank
    if bank == "RHB":
        from rhb import extract_rhb
        return extract_rhb

# =====================================================
# EXTRACTION (ONLY AFTER BUTTON CLICK)
# =====================================================
if st.session_state.run_clicked:

    if not uploaded_files:
        st.warning("Please upload at least one PDF.")
    else:
        extractor = get_extractor(bank_choice)
        all_dfs = []

        with st.spinner("Extracting transactions..."):
            for f in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(f.read())
                    pdf_path = tmp.name

                try:
                    df = extractor(pdf_path)
                except Exception as e:
                    st.error(f"Extraction failed: {e}")
                    continue

                if df is not None and not df.empty:
                    df["_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors="coerce")
                    df = df.dropna(subset=["_dt"]).sort_values("_dt")
                    df = df.drop(columns="_dt").reset_index(drop=True)
                    all_dfs.append(df)

        if all_dfs:
            st.session_state.df_all = pd.concat(all_dfs, ignore_index=True)
            st.session_state.status = "completed"
            st.success("Extraction completed successfully.")
        else:
            st.error("No transactions extracted.")

    st.session_state.run_clicked = False

# =====================================================
# DISPLAY RESULTS
# =====================================================
if st.session_state.df_all is not None:
    st.subheader("📄 Transactions")
    st.dataframe(st.session_state.df_all, use_container_width=True)

# =====================================================
# CORE CALCULATION LOGIC (UNCHANGED)
# =====================================================
def split_by_month(df):
    temp = df.copy()
    temp["_dt"] = pd.to_datetime(temp["date"], dayfirst=True, errors="coerce")
    temp = temp.dropna(subset=["_dt"])

    months = {}
    for m, g in temp.groupby(temp["_dt"].dt.to_period("M")):
        months[m.strftime("%b %Y")] = (
            g.drop(columns="_dt").reset_index(drop=True)
        )
    return months


def compute_monthly_summary(months, od_limit):
    rows = []
    prev_ending = None

    for month, df in months.items():
        if df.empty:
            continue

        first_txn = df.iloc[0]
        last_txn = df.iloc[-1]

        opening = first_txn["balance"] if prev_ending is None else prev_ending
        ending = last_txn["balance"]

        debit = df["debit"].sum()
        credit = df["credit"].sum()
        highest = df["balance"].max()
        lowest = df["balance"].min()
        swing = abs(highest - lowest)

        if od_limit > 0 and ending < 0:
            od_util = abs(ending)
            od_pct = (od_util / od_limit) * 100
        else:
            od_util = 0
            od_pct = 0

        rows.append({
            "Month": month,
            "Opening Balance": opening,
            "Debit": debit,
            "Credit": credit,
            "Ending Balance": ending,
            "Highest Balance": highest,
            "Lowest Balance": lowest,
            "Monthly Swing": swing,
            "OD Utilization": od_util,
            "Monthly OD %": od_pct
        })

        prev_ending = ending

    return pd.DataFrame(rows)
if st.session_state.df_all is not None:

    df_all = st.session_state.df_all

    st.subheader("📄 Transactions")
    st.dataframe(df_all, use_container_width=True)

    # ===============================
    # MONTHLY CALCULATION
    # ===============================
    months = split_by_month(df_all)
    monthly_summary = compute_monthly_summary(months, OD_LIMIT)

    st.subheader("📅 Monthly Summary")
    st.dataframe(monthly_summary, use_container_width=True)
# ===============================
# EXCEL EXPORT
# ===============================
if not monthly_summary.empty:
    if st.button("📥 Export Excel"):
        output_path = write_to_excel(
            df_all=df_all,
            monthly_summary=monthly_summary,
            od_limit=OD_LIMIT
        )

        with open(output_path, "rb") as f:
            st.download_button(
                label="⬇️ Download Excel File",
                data=f,
                file_name=output_path,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

