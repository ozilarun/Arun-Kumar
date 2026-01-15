import pdfplumber
import pandas as pd
import re

# ===============================
# CONFIG: COLUMN POSITIONS
# ===============================
# RHB Statement layouts are usually consistent. 
# We define "X-Axis" (horizontal) boundaries for the columns.
# Units are in PDF "points" (0 = Left edge, 595 = Right edge for A4)

LIMITS = {
    "debit_min": 320,
    "debit_max": 435,   # Numbers in this zone are DEBITS
    "credit_min": 436,
    "credit_max": 525,  # Numbers in this zone are CREDITS
    "bal_min": 526      # Numbers past this are BALANCE
}

def num(s):
    """Clean number string to float"""
    if not s: return 0.0
    try:
        clean = s.replace(",", "").strip()
        if clean == "-" or not clean:
            return 0.0
        return float(clean)
    except:
        return 0.0

def extract_rhb(pdf_path):
    all_txns = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                # 1. Extract words with their X/Y coordinates
                words = page.extract_words(keep_blank_chars=True)
                
                # 2. Group words into "Rows" based on their Y-position (top)
                # We allow a small tolerance (3 pixels) to group words on the same line
                rows = {}
                for w in words:
                    # Round 'top' to nearest 3 pixels to handle slight misalignments
                    y_approx = round(w['top'] / 3) * 3
                    if y_approx not in rows:
                        rows[y_approx] = []
                    rows[y_approx].append(w)

                # 3. Sort rows from top to bottom
                sorted_y = sorted(rows.keys())

                # 4. Process each row
                for y in sorted_y:
                    row_words = rows[y]
                    
                    # Sort words left-to-right
                    row_words.sort(key=lambda x: x['x0'])
                    
                    # Reconstruct the full text line for Date/Description
                    full_text = " ".join([w['text'] for w in row_words])
                    
                    # Check if this row starts with a Date (DD/MM)
                    # RHB format: 01/02/2025 or 01-02-2025
                    date_match = re.search(r"^\d{2}[/-]\d{2}", full_text)
                    if not date_match:
                        continue # Skip header/footer lines

                    # Initialize row data
                    date_str = row_words[0]['text'] # First word is date
                    debit = 0.0
                    credit = 0.0
                    balance = 0.0
                    
                    # Build Description: Join words that are largely on the LEFT side (x < 320)
                    desc_words = [w['text'] for w in row_words if w['x0'] < LIMITS["debit_min"] and w['text'] != date_str]
                    description = " ".join(desc_words)

                    # FIND NUMBERS IN COLUMNS
                    # We look at the words on the right side
                    for w in row_words:
                        text_val = w['text']
                        x_pos = w['x0']
                        
                        # Check if it looks like a number (has digits and dot)
                        if not re.match(r"[\d,]+\.\d{2}", text_val):
                            continue

                        val = num(text_val)

                        # Assign to column based on X-Position
                        if LIMITS["debit_min"] <= x_pos <= LIMITS["debit_max"]:
                            debit = val
                        elif LIMITS["credit_min"] <= x_pos <= LIMITS["credit_max"]:
                            credit = val
                        elif x_pos > LIMITS["bal_min"]:
                            balance = val
                            
                            # Handle Negative Balance indicators
                            # Sometimes the "-" or "OD" is a separate word next to the balance
                            # We check the next word in the list if it exists
                            idx = row_words.index(w)
                            if idx + 1 < len(row_words):
                                next_word = row_words[idx+1]['text']
                                if next_word in ["-", "OD", "Dr"]:
                                    balance = -abs(balance)

                    # Store Transaction
                    all_txns.append({
                        "date": date_str,
                        "description": description,
                        "debit": debit,
                        "credit": credit,
                        "balance": balance
                    })

    except Exception as e:
        print(f"Extraction Error: {e}")
        return pd.DataFrame()

    return pd.DataFrame(all_txns)
