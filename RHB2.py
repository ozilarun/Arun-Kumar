import streamlit as st
import pdfplumber
import pytesseract
from PIL import Image
import regex as re
import json
import os
import io
from tabulate import tabulate

# ==============================
# TEMP DIRECTORY FOR OCR IMAGES
# ==============================
TEMP_DIR = "temp_ocr_images"
os.makedirs(TEMP_DIR, exist_ok=True)

# ==============================
# OCR + TEXT EXTRACTION
# ==============================
def extract_text(page, page_num):
    text = page.extract_text()
    if text and text.strip() != "":
        return text

    img_path = f"{TEMP_DIR}/page_{page_num}.png"
    page.to_image(resolution=300).save(img_path)
    return pytesseract.image_to_string(Image.open(img_path))


# ==============================
# PREPROCESSOR FOR RHB TEXT (same as notebook)
# ==============================
def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()

        if re.match(r"^\d{2}-\d{2}-\d{4}", line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return "\n".join(merged)


# ==============================
# REGEX PATTERN (SAME AS YOUR NOTEBOOK)
# ==============================
txn_pattern = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})
    \s+
    (?P<branch>\d{3})?
    \s*
    (?P<description>[A-Z0-9 /&.\-]+?)
    \s+
    (?P<ref1>[A-Za-z0-9\/]*)?
    \s*
    (?P<ref2>[A-Za-z0-9\/]*)?
    \s*
    (?P<sender>[A-Za-z0-9]{1,40})?
    \s+
    (?P<dr>(?:[0-9,]*\.\d{2}|(?:\.\d{2})))?
    \s*
    (-)?
    \s*
    (?P<cr>(?:[0-9,]*\.\d{2}|(?:\.\d{2})))?
    \s+
    (?P<bal>-?[0-9,]*\.\d{2}-?)
    """,
    re.VERBOSE
)


# ==============================
# CLEAN NUMBER FUNCTION
# ==============================
def num(v):
    if not v:
        return 0.0
    v = v.replace(",", "")
    if v.startswith("."):
        v = "0" + v
    if v.endswith("-"):
        return -float(v[:-1])
    return float(v)


# ==============================
# PARSE TRANSACTIONS (same logic)
# ==============================
def parse_transactions(text, page_num):
    text = preprocess_rhb_text(text)
    txns = []

    for m in txn_pattern.finditer(text):
        dr = num(m.group("dr"))
        cr = num(m.group("cr"))
        bal = num(m.group("bal"))

        txns.append({
            "date": m.group("date"),
            "branch": m.group("branch") or "",
            "description": m.group("description"),
            "ref1": m.group("ref1") or "",
            "ref2": m.group("ref2") or "",
            "sender_reference": m.group("sender") or "",
            "debit": dr if dr != 0 else 0.0,
            "credit": cr if cr != 0 else 0.0,
            "balance": bal,
            "page": page_num
        })

    return txns


# ==============================
# PROCESS PDF (same logic)
# ==============================
def process_rhb_pdf(file):
    all_txns = []
    with pdfplumber.open(file) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            raw = extract_text(page, page_num)
            processed = preprocess_rhb_text(raw)
            txns = parse_transactions(processed, page_num)
            all_txns.extend(txns)
    return all_txns


# ==============================
# STREAMLIT UI
# ==============================
st.title("📄 RHB Bank Statement Parser (6 Months)")
st.write("Upload 1–6 PDFs and extract all transactions into a table.")

uploaded_files = st.file_uploader(
    "Upload RHB PDF bank statements",
    type=["pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.info(f"Processing {len(uploaded_files)} PDFs...")

    all_transactions = []

    for file in uploaded_files:
        st.write(f"📘 Processing: **{file.name}**")
        txns = process_rhb_pdf(file)
        all_transactions.extend(txns)

    st.success(f"✔ Extracted total {len(all_transactions)} transactions")

    # Display Table in Streamlit
    st.subheader("Extracted Transaction Table")

    st.dataframe(all_transactions)

    # Prepare tabulated text output
    rows = []
    for t in all_transactions:
        rows.append([
            t["date"],
            t["description"],
            f"{t['debit']:,.2f}",
            f"{t['credit']:,.2f}",
            f"{t['balance']:,.2f}",
            t["page"]
        ])

    headers = ["Date", "Description", "Debit", "Credit", "Balance", "Page"]
    table_text = tabulate(rows, headers=headers, tablefmt="grid")

    # Download Button
    st.download_button(
        label="⬇ Download Transactions (TXT)",
        data=table_text,
        file_name="transaction_table.txt",
        mime="text/plain"
    )

