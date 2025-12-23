import streamlit as st
import tempfile
import pandas as pd

# =====================================================
# PAGE CONFIG (MUST BE FIRST STREAMLIT CALL)
# =====================================================
st.set_page_config(
    page_title="Bank Statement Analysis",
    layout="wide"
)

st.title("🏦 Bank Statement Analysis")

# =====================================================
# SESSION STATE
# =====================================================
if "status" not in st.session_state:
    st.session_state.status = "idle"

if "df_all" not in st.session_state:
    st.session_state.df_all = None

if "run_clicked" not in st.session_state:
    st.session_state.run_clicked = False

# =====================================================
# BANK SELECTION (SAFE – NO IMPORTS YET)
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

if uploaded_files:
    uploaded_files = sorted(uploaded_files, key=lambda x: x.name)

# =====================================================
# OD LIMIT
# =====================================================
OD_LIMIT = st.number_input(
    "Enter OD Limit (RM)",
    min_value=0.0,
    step=1000.0
)

# =====================================================
# RUN / RESET BUTTONS  ✅ THIS WILL NOW RENDER
# =====================================================
col1, col2 = st.columns(2)

with col1:
    if st.button("▶ Run Analysis", use_container_width=True):
        st.session_state.status = "running"
        st.session_state.run_clicked = True

with col2:
    if st.button("🔄 Reset", use_container_width=True):
        st.session_state.status = "idle"
        st.session_state.df_all = None
        st.session_state.run_clicked = False
        st.rerun()

st.markdown(f"### ⚙️ Status: **{st.session_state.status.upper()}**")

# =====================================================
# LAZY BANK IMPORTS (CRITICAL FIX)
# =====================================================
def get_bank_extractor(bank_name):
    if bank_name == "Bank Rakyat":
        from bank_rakyat import extract_bank_rakyat
        return extract_bank_rakyat

    if bank_name == "Bank Islam":
        from bank_islam import extract_bank_islam
        return extract_bank_islam

    if bank_name == "CIMB":
        from cimb import extract_cimb
        return extract_cimb

    if bank_name == "Maybank":
        from maybank import extract_maybank
        return extract_maybank

    if bank_name == "RHB":
        from rhb import extract_rhb
        return extract_rhb

    return None

# =====================================================
# EXTRACTION (RUNS ONLY AFTER BUTTON CLICK)
# =====================================================
if uploaded_files and st.session_state.run_clicked:

    extractor = get_bank_extractor(bank_choice)

    if extractor is None:
        st.error("❌ Bank extractor not found.")
    else:
        all_dfs = []

        with st.spinner("Extracting transactions..."):
            for uploaded_file in uploaded_files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.read())
                    pdf_path = tmp.name

                try:
                    df = extractor(pdf_path)
                except Exception as e:
                    st.error(f"Extraction failed: {e}")
                    df = None

                if df is not None and not df.empty:
                    try:
                        df["_dt"] = pd.to_datetime(
                            df["date"], dayfirst=True, errors="coerce"
                        )
                        df = (
                            df.sort_values("_dt")
                            .drop(columns="_dt")
                            .reset_index(drop=True)
                        )
                    except Exception:
                        pass

                    all_dfs.append(df)

        if not all_dfs:
            st.error("❌ No transactions extracted.")
            st.session_state.status = "idle"
        else:
            st.session_state.df_all = pd.concat(all_dfs, ignore_index=True)
            st.session_state.status = "completed"
            st.success("✅ Extraction completed.")

    st.session_state.run_clicked = False

# =====================================================
# DISPLAY RESULTS (UNCHANGED LOGIC)
# =====================================================
if st.session_state.df_all is not None:

    df_all = st.session_state.df_all

    st.subheader("📄 Cleaned Transaction List")
    st.dataframe(df_all, use_container_width=True)

    # -------------------------------
    # Helper functions
    # -------------------------------
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

    st.subheader("📅 Monthly Summary")
    months = split_by_month(df_all)
    monthly_summary = compute_monthly_summary(months, OD_LIMIT)
    st.dataframe(monthly_summary, use_container_width=True)
