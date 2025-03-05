import os
import sys
import logging
import re
import json
import pandas as pd
from datetime import datetime

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

def read_all_csv_from_folder(folder_path):
    """
    Reads all CSV files from the given folder path and processes them.
    Then appends each processed DataFrame to a single combined_output.csv after each file.
    """
    all_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith('.csv')]
    processed_folder = os.path.join(folder_path, 'processed_csv')
    already_processed_folder = os.path.join(folder_path, 'already_processed')
    not_processed_folder = os.path.join(folder_path, 'not_processed')

    os.makedirs(processed_folder, exist_ok=True)
    os.makedirs(already_processed_folder, exist_ok=True)
    os.makedirs(not_processed_folder, exist_ok=True)

    # Prepare the single combined output file in processed_csv folder:
    output_file = os.path.join(processed_folder, 'combined_output.csv')

    for file in all_files:
        try:
            logging.info(f"Processing file: {file}")
            print(f"Processing file: {file}")

            # Read and map columns
            df = csv_reader(file)

            # Log row-level data (optional - can comment out if it’s too verbose)
            for index, row in df.iterrows():
                logging.info(f"Processing row {index + 1}: {row.to_dict()}")

            # Write (append) to combined_output.csv:
            if not os.path.exists(output_file):
                # If the combined file doesn't exist, write with header
                df.to_csv(output_file, index=False)
            else:
                # If the file already exists, append without header
                df.to_csv(output_file, mode='a', header=False, index=False)

            # Move the processed file to the "already_processed" folder
            os.rename(file, os.path.join(already_processed_folder, os.path.basename(file)))

        except Exception as e:
            # If there's an error, move file to "not_processed" folder
            os.rename(file, os.path.join(not_processed_folder, os.path.basename(file)))
            print(f"Error processing file {file}: {e}")
            logging.error(f"Error processing file {file}: {e}")

    print(f"\nAll files are processed. Combined CSV (appended) is at: {output_file}")
    logging.info(f"All files processed. Combined CSV saved/appended at: {output_file}")

def csv_reader(csv_file_path, read_line=0):
    """
    Reads and processes a single CSV file using mapper(), then performs additional transformations.
    """
    df = mapper(csv_file_path, read_line)

    date_columns = ["posting_date", "transaction_date"]
    if "transaction_date" not in df.columns and "posting_date" in df.columns:
        df["transaction_date"] = df["posting_date"]
    
    for col in date_columns:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: convert_to_yyyy_mm_dd(x) if isinstance(x, str) else x)

    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)

    if "type" not in df.columns and "amount" in df.columns:
        df["type"] = df["amount"].apply(lambda x: "Credit" if x >= 0 else "Debit")

    if "category" not in df.columns:
        df["category"] = "No Category Mentioned"

    # Create vendorName column from description
    if "description" in df.columns:
        df["vendorName"] = df["description"].apply(lambda x: strip_vendor(x))
    else:
        df["vendorName"] = "Unknown"

    return df

def mapper(csv_file_path, read_line=0):
    """
    Maps column headers based on predefined mappings.
    """
    # Reload header mappings
    header_map = load_header_mapping()

    # Read CSV
    df = pd.read_csv(csv_file_path, index_col=False, skiprows=read_line)

    # Reset index if duplicates exist
    df.reset_index(drop=True, inplace=True)

    # Make sure column names are consistent
    # (reads again just the header row to ensure original column names)
    df.columns = pd.io.parsers.read_csv(csv_file_path, nrows=0).columns
    df.columns = pd.Series(df.columns).astype(str)

    # Convert column names to lowercase without spaces
    df.columns = [col.lower().replace(" ", "") for col in df.columns]

    # Build a reverse mapping from the JSON data
    reverse_mapping = {old_header: new_header for new_header, old_headers in header_map.items()
                       for old_header in old_headers}

    # Check for separate debit/credit columns and combine into 'amount'
    credit_col = next((col for col in df.columns if 'credit' in col.lower()), None)
    debit_col  = next((col for col in df.columns if 'debit' in col.lower()), None)
    amount_col = next((col for col in df.columns if 'amount' in col.lower()), None)

    # If there's a separate debit and credit, combine them into a single 'amount'
    if credit_col and debit_col:
        df[credit_col] = pd.to_numeric(df[credit_col], errors='coerce').fillna(0)
        df[debit_col]  = pd.to_numeric(df[debit_col],  errors='coerce').fillna(0)
        df['amount']   = df[credit_col] - df[debit_col]
        df.drop(columns=[credit_col, debit_col], inplace=True)
    elif credit_col:
        df['amount'] = pd.to_numeric(df[credit_col], errors='coerce').fillna(0)
        df.drop(columns=[credit_col], inplace=True)
    elif debit_col:
        df['amount'] = -pd.to_numeric(df[debit_col], errors='coerce').fillna(0)
        df.drop(columns=[debit_col], inplace=True)
    elif amount_col:
        # rename or coerce to numeric if there's an 'amount' column
        df['amount'] = pd.to_numeric(df[amount_col], errors='coerce').fillna(0)

    # Re-map columns using the JSON definitions
    final_column_order = []
    new_column_names   = []
    for col in df.columns:
        if col in reverse_mapping:
            final_column_order.append(col)
            new_column_names.append(reverse_mapping[col])
        else:
            final_column_order.append(col)
            new_column_names.append(col)

    df_reordered = df[final_column_order]
    df_reordered.columns = new_column_names

    return df_reordered

def convert_to_yyyy_mm_dd(date_str):
    """
    Converts various date formats into YYYY-MM-DD format.
    """
    # For demonstration, just return date_str or implement your own date parsing logic
    return date_str
    # Try more sophisticated format detection/parsing if needed.
    # try:
    #     return datetime.strptime(date_str,'%Y/%m/%d').strftime('%Y-%m-%d')
    # except ValueError:
    #     try:
    #         return datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
    #     except ValueError:
    #         try:
    #             return datetime.strptime(date_str, '%m/%d/%Y').strftime('%Y-%m-%d')
    #         except ValueError:
    #             print("Unrecognized date format", date_str)
    #             return ""

# Pattern for possible vendor extraction
key = '|'.join(["DES:", "from", "transfer", " in ", "Deposit", "ATM", ','])  # Possible keywords
string = r'\w[]?\D*'  # Pattern for extracting text
plus_minus = r'\+\/\-'
cases = fr'({string})(?:[\s\d\-\+\/]*)(?:{key})'
pattern = re.compile(cases)

def strip_vendor(strings="Not Available"):
    """
    Extracts vendor name from description.
    If the extracted vendor name is too short, fallback to first two words.
    """
    if not strings or isinstance(strings, float):
        return "Unknown"

    # Truncate to 30 chars (optional)
    if len(strings) > 30:
        strings = strings[:30]

    matches = pattern.findall(strings)

    if matches:
        vendor_name = matches[0].strip()
    else:
        words = re.split(r'[\W_]+', strings)
        vendor_name = words[0] if words else "Unknown"

    # If less than 5 chars, take the first two words
    if len(vendor_name) < 5:
        words = strings.split()
        vendor_name = " ".join(words[:2]) if len(words) > 1 else strings

    return vendor_name

if __name__ == "__main__":
    exe_folder_path = (
        os.path.dirname(os.path.abspath(sys.executable))
        if getattr(sys, 'frozen', False)
        else os.path.dirname(os.path.abspath(__file__))
    )
    data_folder_path = os.path.join(exe_folder_path, 'data')
    logging.info(f"Looking for CSV files in: {data_folder_path}")
    print(f"Looking for CSV files in: {data_folder_path}")

    read_all_csv_from_folder(data_folder_path)
