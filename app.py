import streamlit as st
import tempfile
import pandas as pd
import pdfplumber
import fitz  # PyMuPDF
import re
from datetime import datetime

# =====================================================
# EXTERNAL BANK IMPORTS (Safe Imports)
# =====================================================
try:
    from bank_rakyat import extract_bank_rakyat
    from bank_islam import extract_bank_islam
    from cimb import extract_cimb
    from rhb import extract_rhb
except ImportError:
    # Dummy functions to prevent crash if files missing
    def extract_bank_rakyat(f): return pd.DataFrame()
    def extract_bank_islam(f): return pd.DataFrame()
    def extract_cimb(f): return pd.DataFrame()
    def extract_rhb(f): return pd.DataFrame()

# =====================================================
# UNIVERSAL MAYBANK PARSER (Embedded for Safety)
# =====================================================
def extract_maybank_universal(pdf_path):
    # 1. Try CWS Strategy (Text/Regex)
    try:
        df = _parse_maybank_cws(pdf_path)
        if df is not None and not df.empty: return df
    except: pass
    
    # 2. Try Mytutor Strategy (Coordinates)
    try:
        df = _parse_maybank_mytutor(pdf_path)
        if df is not None and not df.empty: return df
    except: pass
    
    return pd.DataFrame()

def _parse_maybank_cws(pdf_path):
    DATE_PATTERN = re.compile(r"^\d{2}\s+[A-Za-z]{3}\s+\d{4}") 
    AMOUNT_PATTERN = re.compile(r'([0-9,]+\.\d{2})\s*([+-])\s*([0-9,]+\.\d{2})')
    transactions = []
    current_txn = None
    desc_buffer = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            for line in text.split("\n"):
                line = line.strip()
                if not line: continue
                if DATE_PATTERN.match(line):
                    if current_txn:
                        current_txn["description"] = " ".join(desc_buffer).strip()
                        transactions.append(current_txn)
                    desc_buffer = []
                    m = AMOUNT_PATTERN.search(line)
                    if not m: current_txn = None; continue
                    
                    amt = float(m.group(1).replace(",", ""))
                    sign = m.group(2)
                    bal = float(m.group(3).replace(",", ""))
                    debit, credit = (amt, 0.0) if sign == "-" else (0.0, amt)
                    
                    current_txn = {"date": line[:11], "description": "", "debit": debit, "credit": credit, "balance": bal}
                    desc_buffer.append(line[:m.start()].strip())
                else:
                    if current_txn: desc_buffer.append(line)
    if current_txn:
        current_txn["description"] = " ".join(desc_buffer).strip()
        transactions.append(current_txn)
    
    df = pd.DataFrame(transactions)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], format="%d %b %Y", errors='coerce').dt.strftime('%d/%m/%Y')
    return df

def _parse_maybank_mytutor(pdf_path):
    doc = fitz.open(pdf_path)
    statement_year = str(datetime.now().year)
    for p in range(min(2, len(doc))):
        txt = doc[p].get_text("text").upper()
        m = re.search(r"STATEMENT\s+DATE\s*:?\s*(\d{2})/(\d{2})/(\d{2})", txt)
        if m: statement_year = f"20{m.group(3)}"

    transactions = []
    prev_bal = None
    DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{4}|\d{2}/\d{2})$")
    
    for page in doc:
        words = page.get_text("words")
        rows = [{"x": w[0], "y": w[1], "text": str(w[4]).strip()} for w in words]
        rows.sort(key=lambda x: (round(x["y"], 1), x["x"]))
        processed_y = set()
        
        for r in rows:
            if round(r["y"], 1) in processed_y: continue
            if not DATE_RE.match(r["text"]): continue
            
            line_y = round(r["y"], 1)
            line_items = [w for w in rows if abs(round(w["y"],1) - line_y) < 2]
            line_items.sort(key=lambda w: w["x"])
            
            amounts = []
            desc_parts = []
            for item in line_items:
                if item["text"] == r["text"]: continue
                clean = item["text"].replace(",","").replace("CR","").replace("DR","")
                if re.match(r"^\d+\.\d{2}[+-]?$", clean):
                    amounts.append({"val": clean, "x": item["x"]})
                else:
                    desc_parts.append(item["text"])
            
            if not amounts: continue
            processed_y.add(line_y)
            
            bal_str = amounts[-1]["val"]
            bal = float(bal_str.rstrip("+-"))
            debit, credit = 0.0, 0.0
            
            if len(amounts) > 1:
                txn_str = amounts[-2]["val"]
                val = float(txn_str.rstrip("+-"))
                if txn_str.endswith("-"): debit = val
                elif txn_str.endswith("+"): credit = val
                elif prev_bal and round(prev_bal - val, 2) == bal: debit = val
                else: credit = val
            elif prev_bal is not None:
                diff = round(bal - prev_bal, 2)
                if diff < 0: debit = abs(diff)
                else: credit = diff
            
            date_str = r["text"]
            if len(date_str) == 5: date_str += f"/{statement_year}"
            
            transactions.append({
                "date": date_str, "description": " ".join(desc_parts), 
                "debit": debit, "credit": credit, "balance": bal
            })
            prev_bal = bal
    return pd.DataFrame(transactions)

# =====================================================
# STREAMLIT APP CONFIGURATION
# =====================================================
st.set_page_config(page_title="Bank Statement Parser", layout="wide")
st.title("📄 Bank Statement Parser")

# --- SESSION STATE INITIALIZATION ---
if "data_extracted" not in st.session_state:
    st.session_state.data_extracted = None

# --- SIDEBAR SETTINGS ---
st.sidebar.header("Settings")
bank_choice = st.sidebar.selectbox("Select Bank Format", ["Maybank", "CIMB", "Bank Rakyat", "Bank Islam", "RHB"])
od_limit = st.sidebar.number_input("OD Limit (RM)", min_value=0.0, step=1000.0)

# Map Extractors
EXTRACTORS = {
    "Maybank": extract_maybank_universal,
    "CIMB": extract_cimb,
    "Bank Rakyat": extract_bank_rakyat,
    "Bank Islam": extract_bank_islam,
    "RHB": extract_rhb,
}

# =====================================================
# 1. FILE UPLOAD
# =====================================================
uploaded_files = st.file_uploader("Upload PDF Files", type=["pdf"], accept_multiple_files=True)

# =====================================================
# 2. RUN ANALYSIS BUTTON
# =====================================================
# This button triggers the processing and saves to session state
if st.button("▶️ RUN ANALYSIS", type="primary"):
    
    if not uploaded_files:
        st.error("Please upload at least one PDF file.")
    else:
        all_tx = []
        extractor = EXTRACTORS[bank_choice]
        progress_bar = st.progress(0)
        
        for i, uploaded_file in enumerate(uploaded_files):
            # Save temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(uploaded_file.read())
                pdf_path = tmp.name
            
            try:
                # Extract
                df = extractor(pdf_path)
                
                if df is not None and not df.empty:
                    # Auto-Sort (Chronological)
                    try:
                        df["_sort"] = pd.to_datetime(df["date"], dayfirst=True, errors='coerce')
                        df = df.sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)
                    except: pass
                    
                    all_tx.append(df)
            except Exception as e:
                st.error(f"Error reading {uploaded_file.name}: {e}")
            
            progress_bar.progress((i + 1) / len(uploaded_files))
            
        if all_tx:
            # SAVE TO SESSION STATE
            st.session_state.data_extracted = pd.concat(all_tx, ignore_index=True)
            st.success(f"✅ Successfully extracted {len(st.session_state.data_extracted)} transactions!")
        else:
            st.warning("⚠️ No transactions found.")

# =====================================================
# 3. DISPLAY RESULTS (FROM SESSION STATE)
# =====================================================
if st.session_state.data_extracted is not None:
    df_all = st.session_state.data_extracted
    
    st.divider()
    
    # --- A. Transaction Table ---
    st.subheader("📊 Extracted Transactions")
    st.dataframe(df_all, use_container_width=True, height=300)
    
    # --- B. Monthly Calculations ---
    def get_monthly_summary(df):
        df = df.copy()
        df["_dt"] = pd.to_datetime(df["date"], dayfirst=True, errors='coerce')
        df = df.dropna(subset=["_dt"])
        
        summary = []
        prev_end = None
        
        # Group by Month
        for period, group in df.groupby(df["_dt"].dt.to_period("M")):
            first, last = group.iloc[0], group.iloc[-1]
            
            # Opening Balance Logic
            opening = (first["balance"] - first["credit"] + first["debit"]) if prev_end is None else prev_end
            ending = last["balance"]
            
            od_util = abs(ending) if (od_limit > 0 and ending < 0) else 0
            
            summary.append({
                "Month": period.strftime("%b %Y"),
                "Opening": opening,
                "Debit": group["debit"].sum(),
                "Credit": group["credit"].sum(),
                "Ending": ending,
                "Highest": group["balance"].max(),
                "Lowest": group["balance"].min(),
                "Swing": group["balance"].max() - group["balance"].min(),
                "OD Util": od_util
            })
            prev_end = ending
            
        return pd.DataFrame(summary)

    # Calculate Summary
    summary_df = get_monthly_summary(df_all)
    
    # --- C. Display Summary ---
    st.subheader("📅 Monthly Summary")
    st.dataframe(summary_df, use_container_width=True)
    
    # --- D. Key Metrics ---
    if not summary_df.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total Credits", f"{summary_df['Credit'].sum():,.2f}")
        col2.metric("Total Debits", f"{summary_df['Debit'].sum():,.2f}")
        col3.metric("Avg Ending Balance", f"{summary_df['Ending'].mean():,.2f}")

    # --- E. Download Button ---
    csv = df_all.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="⬇️ Download CSV",
        data=csv,
        file_name='transactions.csv',
        mime='text/csv',
    )
