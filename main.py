import os
import pandas as pd
import json
from datetime import datetime
import re
import sys
import logging

# Setup logging
log_file = "process_log.txt"
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(message)s")

def load_header_mapping(json_file='header_mapping.json'):
    """Loads header mapping from JSON file."""
    if os.path.exists(json_file):
        with open(json_file, 'r') as f:
            return json.load(f)
    else:
        print(f"Error: {json_file} not found.")
        return {}

header_mapping = load_header_mapping()


def process_string(s):
    if isinstance(s, float) or s == "":
        return s  # Ignore empty strings and floats
    return s[1:] if isinstance(s, str) and s.startswith('$') else s


def read_all_csv_from_folder(folder_path):
    """
    Reads all CSV files from the given folder path and processes them.
    Combines processed CSVs into one output CSV.
    """
    all_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith('.csv')]
    combined_df = pd.DataFrame()
    processed_folder = os.path.join(folder_path, 'processed_csv')
    already_processed_folder = os.path.join(folder_path, 'already_processed')
    not_processed_folder = os.path.join(folder_path, 'not_processed')
    os.makedirs(processed_folder, exist_ok=True)
    os.makedirs(already_processed_folder, exist_ok=True)
    os.makedirs(not_processed_folder, exist_ok=True)
    
    for file in all_files:
        # try:
        logging.info(f"Processing file: {file}")
        df = csv_reader(file)
        logging.info(f"df.columns in main: {df.columns} for {file}")
        for i,row in df.iterrows():
            logging.info(f"i: {i} row: {row} for {file}")
        # print(f"df.columns: {df.columns} for {file}")
        combined_df = pd.concat([combined_df, df], ignore_index=False)
        # Reset index if duplicates exist
        if df.index.is_unique:
            df.reset_index(drop=True, inplace=True)
        os.rename(file, os.path.join(already_processed_folder, os.path.basename(file)))  # Move processed file
        # except Exception as e:
        #     print(f"Error processing file {file}: {e}")
        #     logging.error(f"Error processing file {file}: {e}")
    
    if not combined_df.empty:
        output_file = os.path.join(processed_folder, 'combined_output.csv')
        combined_df.to_csv(output_file, index=False)
        print(f"Combined CSV saved at: {output_file}")
        logging.info(f"Combined CSV saved at: {output_file}")
    else:
        logging.warning("No CSV files found or processed successfully.")
        print("No CSV files found or processed successfully.")

def csv_reader(csv_file_path, read_line=0):
    """
    Reads and processes a single CSV file:
    - Maps CSV headers to standardized names.
    - Converts date columns.
    - Creates a unified 'amount' column if credit/debit columns exist.
    - Creates a 'type' column (Credit/Debit) if needed.
    - Extracts vendor name.
    """
    df = mapper(csv_file_path, read_line)
    date_columns = ["posting_date", "transaction_date"]
    
    # If transaction_date doesn't exist, copy posting_date (if available)
    if "transaction_date" not in df.columns and "posting_date" in df.columns:
        df["transaction_date"] = df["posting_date"]
    
    for col in date_columns:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: convert_to_yyyy_mm_dd(x) if isinstance(x, str) else x)
    
    # Create the unified amount column from amount_c and amount_d if they exist.
    if "amount_c" in df.columns or "amount_d" in df.columns:
        if "amount_c" in df.columns and "amount_d" in df.columns:
            df["amount"] = df["amount_c"].fillna(0) - df["amount_d"].fillna(0)
        elif "amount_c" in df.columns:
            df["amount"] = df["amount_c"]
        elif "amount_d" in df.columns:
            df["amount"] = -df["amount_d"]
    
    if "type" not in df.columns and "amount" in df.columns:
        df["type"] = df["amount"].apply(lambda x: "Credit" if x >= 0 else "Debit")
        
    if "category" not in df.columns:
        df["category"] = "No Category Mentioned"
    if "description" in df.columns:
        df["vendorName"] = df["description"].apply(lambda x: strip_vendor(x) if pd.notna(x) else "")
    return df
def mapper(csv_file_path, read_line=0):
    """
    Reads the CSV file and renames its columns based on the header mapping.
    """
    header_mapping = load_header_mapping()
    # Read CSV
    df = pd.read_csv(csv_file_path, index_col=False, skiprows=read_line)
    
    # Normalize header names
    print(f"df.columns normalized: {df.columns}")
    normalized_columns = [str(col).lower().replace(" ", "") for col in df.columns]
    print(f"df.columns normalized: {df.columns}")
    df.columns = normalized_columns
    
    # Build reverse mapping from header_mapping
    reverse_mapping = {}
    for std_name, alt_names in header_mapping.items():
        for alt in alt_names:
            alt_norm = alt.lower().replace(" ", "")
            reverse_mapping[alt_norm] = std_name

    new_columns = []
    seen_columns = set()  # Keep track of column names already assigned
    
    for col in normalized_columns:
        # First, try to get a standardized name from the reverse mapping.
        std_col = reverse_mapping.get(col)
        
        if std_col:
            # If this standard column name already exists, append a suffix
            if std_col in seen_columns:
                suffix = 1
                while f"{std_col}_{suffix}" in seen_columns:
                    suffix += 1
                std_col = f"{std_col}_{suffix}"
            new_columns.append(std_col)
            seen_columns.add(std_col)
        else:
            # Fallback: if not mapped, check for credit/debit keywords.
            if "credit" in col and "debit" not in col:
                new_col = "amount_c"
            elif "debit" in col and "credit" not in col:
                new_col = "amount_d"
            else:
                new_col = col
                
            # Make sure it's unique
            if new_col in seen_columns:
                suffix = 1
                while f"{new_col}_{suffix}" in seen_columns:
                    suffix += 1
                new_col = f"{new_col}_{suffix}"
            
            new_columns.append(new_col)
            seen_columns.add(new_col)
    
    print(f"new_columns: {new_columns}")
    df.columns = new_columns

    # Convert amount_c and amount_d to numeric if they exist.
    if "amount_c" in df.columns:
        df["amount_c"] = df["amount_c"].apply(process_string)
        df["amount_c"] = pd.to_numeric(df["amount_c"], errors='coerce')
    if "amount_d" in df.columns:
        df["amount_d"] = df["amount_d"].apply(process_string)
        df["amount_d"] = pd.to_numeric(df["amount_d"], errors='coerce')
    
    logging.info(f"df.columns in mapper: {df}")
    return df
def convert_to_yyyy_mm_dd(date_str):
    """
    Converts various date formats into YYYY-MM-DD format.
    Currently returns the input; extend with actual conversion logic as needed.
    """
    return date_str

# Precompile regex pattern for vendor extraction.
key = '|'.join(["DES:", "from", "transfer", " in ", "Deposit", "ATM", ','])
string = r'\w[]?\D*'
plus_minus = r'\+\/\-'  
cases = fr'({string})(?:[\s\d\-\+\/]*)(?:{key})'
pattern = re.compile(cases)

def strip_vendor(strings="Not Available"):
    """
    Extracts vendor name from description.
    If the extracted vendor name is too short, takes the first two words.
    This version ensures the input is a scalar value.
    """
    # If the input is a Series or list, get the first element.
    if isinstance(strings, (pd.Series, list)):
        try:
            strings = strings.iloc[0] if isinstance(strings, pd.Series) else strings[0]
        except Exception:
            return "Unknown"
    
    if pd.isnull(strings):
        return "Unknown"
    strings = str(strings)
    
    # Limit the text length for pattern matching.
    if len(strings) > 30:
        strings = strings[:30]
    
    matches = pattern.findall(strings)
    if matches:
        vendor_name = matches[0].strip()
    else:
        # Fallback: split by non-word characters and take the first word.
        words = re.split(r'[\W_]+', strings)
        vendor_name = words[0] if words else "Unknown"
    
    # If the extracted vendor name is too short, try taking the first two words.
    if len(vendor_name) < 5:
        words = strings.split()
        vendor_name = " ".join(words[:2]) if len(words) > 1 else strings
    
    return vendor_name

# Example usage
# if __name__ == "__main__":
#     exe_folder_path = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
#     data_folder_path = os.path.join(exe_folder_path, 'data')
#     logging.info(f"Looking for CSV files in: {data_folder_path}")
#     print(f"Looking for CSV files in: {data_folder_path}")
#     read_all_csv_from_folder(data_folder_path)
