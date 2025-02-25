import os
import pandas as pd
import json
from decimal import Decimal
from datetime import datetime
import re
import sys
import logging
# header_mapping = {
#     'description': ['description', 'Description', 'desc'],
#     'pdate': ['Posting Date', 'post_date', 'Post Date','Posted Date', 'posted_date', 'Date'],
#     'tdate': ['transaction date', 'Transaction Date', 'trans_date'],
#     'amount': ['debit/credit', 'debit','Debit', 'credit', 'Amount'],
#     'category': ['Category', 'cat'],
#     'type': ['sale_type', 'Type', "details"],
#     'balance': ['bal.', 'Running Bal.', 'Balance'],
#     'check or slip #': ['Check or Slip #', 'check or slip #', 'check #', 'slip #']
# }

# Setup logging
log_file = "process_log.txt"
logging.basicConfig(filename=log_file, level=logging.INFO, format="%(asctime)s - %(message)s")


# Function to load header mappings dynamically
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
    """
    all_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.csv')]
    combined_df = pd.DataFrame()
    
    for file in all_files:
        try:
            logging.info(f"Processing file: {file}")
            print(f"Processing file: {file}")
            df = csv_reader(file)
            for index, row in df.iterrows():
                logging.info(f"Processing row {index + 1}: {row.to_dict()}")
                print(f"Processing row {index + 1}")  # This prints to console if available
            combined_df = pd.concat([combined_df, df], ignore_index=True)
        except Exception as e:
            logging.error(f"Error processing file {file}: {e}")
            print(f"Error processing file {file}: {e}")
    
    if not combined_df.empty:
        output_file = os.path.join(folder_path, 'combined_output.csv')
        combined_df.to_csv(output_file, index=False)
        print(f"Combined CSV saved at: {output_file}")
        logging.info(f"Combined CSV saved at: {output_file}")
    else:
        logging.warning("No CSV files found or processed successfully.")
        print("No CSV files found or processed successfully.")

def csv_reader(csv_file_path, read_line=0):
    """
    Reads and processes a single CSV file.
    """
    df = mapper(csv_file_path, read_line)
    date_columns = ['pdate', 'tdate']
    
    if 'tdate' not in df.columns:
        df['tdate'] = df['pdate']
    
    for col in date_columns:
        df[col] = df[col].apply(lambda x: convert_to_yyyy_mm_dd(x) if isinstance(x, str) else x)
    
    if 'type' not in df.columns:
        df['type'] = df['amount'].apply(lambda x: 'Credit' if x >= 0 else 'Debit')
    if 'category' not in df.columns:
        df['category'] = 'No Category Mentioned'
    
    df['vendorName'] = df['description'].apply(lambda x: strip_vendor(x))
    return df

def mapper(csv_file_path, read_line=0):
    """
    Maps column headers based on predefined mappings.
    """
    header_mapping = load_header_mapping()

    df = pd.read_csv(csv_file_path, index_col=False, skiprows=read_line)
    reverse_mapping = {old_header: new_header for new_header, old_headers in header_mapping.items() for old_header in old_headers}
    
    final_column_order = []
    new_column_names = []
    
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
    return date_str
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
key = '|'.join(["DES:", "from", "transfer", " in ", "Deposit", "ATM", ','])  # Possible keywords
string = r'\w[]?\D*'  # Pattern for extracting text
plus_minus = r'\+\/\-'  # Plus/minus symbols

cases = fr'({string})(?:[\s\d\-\+\/]*)(?:{key})'
pattern = re.compile(cases)

def strip_vendor(strings):
    """
    Extracts vendor name from description.
    - If the extracted vendor name is less than 2 characters, take the first two words.
    """
    if not strings:
        return "Unknown"
    
    # Ensure the input string is within a reasonable length
    if len(strings) > 30:
        strings = strings[:30]

    matches = pattern.findall(strings)
    
    if matches:
        vendor_name = matches[0].strip()
    else:
        words = re.split(r'[\W_]+', strings)  # Split by non-word characters
        vendor_name = words[0] if words else "Unknown"

    # Ensure vendor name has at least two characters, else take first two words
    if len(vendor_name) < 5:
        words = strings.split()
        vendor_name = " ".join(words[:2]) if len(words) > 1 else strings

    return vendor_name

# Example usage
if __name__ == "__main__":
    exe_folder_path = os.path.dirname(os.path.abspath(sys.executable)) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
    data_folder_path = os.path.join(exe_folder_path, 'data')
    logging.info(f"Looking for CSV files in: {data_folder_path}")
    print(f"Looking for CSV files in: {data_folder_path}")
    read_all_csv_from_folder(data_folder_path)
