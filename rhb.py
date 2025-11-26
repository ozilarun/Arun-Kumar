import pdfplumber
import pytesseract
from PIL import Image
import regex as re
import os
from tabulate import tabulate

# =====================================================================
# TEMP FOLDER FOR OCR
# =====================================================================
TEMP_DIR = "temp_ocr_images"
os.makedirs(TEMP_DIR, exist_ok=True)


# =====================================================================
# NUMERIC CLEANER
# =====================================================================
def num(x):
    if not x or x.strip() == "":
        return 0.0
    return float(x.replace(",", ""))


# =====================================================================
# TEXT EXTRACTION WITH OCR FALLBACK
# =====================================================================
def extract_text(page, page_num, file_label):
    text = page.extract_text()
    if text and text.strip() != "":
        return text

    # OCR fallback
    img_path = f"{TEMP_DIR}/{file_label}_page_{page_num}.png"
    page.to_image(resolution=300).save(img_path)
    return pytesseract.image_to_string(Image.open(img_path))


# =====================================================================
# RHB PRE-PROCESSING (MERGING WRAPPED LINES)
# =====================================================================
def preprocess_rhb_text(text):
    lines = text.split("\n")
    merged, buffer = [], ""

    for line in lines:
        line = line.strip()

        # New transaction always starts with DD-MM-YYYY
        if re.match(r"^\d{2}-\d{2}-\d{4}", line):
            if buffer:
                merged.append(buffer.strip())
            buffer = line
        else:
            buffer += " " + line

    if buffer:
        merged.append(buffer.strip())

    return "\n".join(merged)


# =====================================================================
# RHB TRANSACTION PATTERN
# =====================================================================
txn_pattern = re.compile(
    r"""
    (?P<date>\d{2}-\d{2}-\d{4})
    \s+
    (?P<body>.*?)
    \s+
    (?P<dr>[0-9,]*\.\d{2})?
    \s*
    (?P<dr_flag>-)?
    \s*
    (?P<cr>[0-9,]*\.\d{2})?
    \s+
    (?P<bal>-?[0-9,]*\.\d{2}[+-]?)
    """,
    re.VERBOSE | re.DOTALL
)


# =====================================================================
# PARSE TRANSACTIONS PER PAGE
# =====================================================================
def parse_transactions(text, page_num, file_label):
    text = preprocess_rhb_text(text)
    txns = []

    for m in txn_pattern.finditer(text):
        dr_val = num(m.group("dr"))
        cr_val = num(m.group("cr"))
        bal_val = num(m.group("bal"))

        txns.append({
            "file": file_label,
            "date": m.group("date"),
            "description": m.group("body").strip(),
            "debit": dr_val if dr_val > 0 else 0.0,
            "credit": cr_val if cr_val > 0 else 0.0,
            "balance": bal_val,
            "page": page_num
        })

    return txns


# =====================================================================
# PROCESS MULTIPLE PDFs
# =====================================================================
def process_multiple_rhb_pdfs(pdf_paths):
    all_txns = []

    for pdf_path in pdf_paths:
        file_label = os.path.splitext(os.path.basename(pdf_path))[0]

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                raw = extract_text(page, page_num, file_label)
                txns = parse_transactions(raw, page_num, file_label)
                all_txns.extend(txns)

    return all_txns


# =====================================================================
# EXPORT TO TXT (ONE OUTPUT FOR ALL PDFs)
# =====================================================================
def export_txt(txns, output_path="transaction_table.txt"):
    rows = []

    for t in txns:
        rows.append([
            t["file"],        # Which PDF file
            t["date"],
            t["description"],
            f"{t['debit']:,.2f}",
            f"{t['credit']:,.2f}",
            f"{t['balance']:,.2f}",
            t["page"]
        ])

    headers = ["File", "Date", "Description", "Debit", "Credit", "Balance", "Page"]
    table_text = tabulate(rows, headers=headers, tablefmt="grid")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(table_text)

    return output_path
