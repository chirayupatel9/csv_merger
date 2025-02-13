import os
import pandas as pd
import json
from decimal import Decimal
from datetime import datetime
import re

header_mapping = {
    'description': ['description', 'Description', 'desc'],
    'pdate': ['Posting Date', 'post_date', 'Post Date','Posted Date', 'posted_date', 'Date'],
    'tdate': ['transaction date', 'Transaction Date', 'trans_date'],
    'amount': ['debit/credit', 'debit','Debit', 'credit', 'Amount'],
    'category': ['Category', 'cat'],
    'type': ['sale_type', 'Type', "details"],
    'balance': ['bal.', 'Running Bal.', 'Balance'],
    'check or slip #': ['Check or Slip #', 'check or slip #', 'check #', 'slip #']
}


key = '|'.join(["DES:", "from", "transfer", " in ", "Deposit", "ATM", ','])  # possible units
string = '\w[]?\D*'  # '\d+[.,]?\d*'                              # pattern for number
plus_minus = '\+\/\-'  # plus minus

cases = fr'({string})(?:[\s\d\-\+\/]*)(?:{key})'
pattern = re.compile(cases)

def read_all_csv_from_folder(folder_path):
    """
    Reads all CSV files from the given folder path and processes them.
    """
    all_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.csv')]
    combined_df = pd.DataFrame()
    
    for file in all_files:
        try:
            print(f"Processing file: {file}")
            df = csv_reader(file)
            combined_df = pd.concat([combined_df, df], ignore_index=True)
        except Exception as e:
            print(f"Error processing file {file}: {e}")
    
    if not combined_df.empty:
        output_file = os.path.join(folder_path, 'combined_output.csv')
        combined_df.to_csv(output_file, index=False)
        print(f"Combined CSV saved at: {output_file}")
    else:
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

def strip_vendor(strings):
    """
    Extracts vendor name from description.
    """
    if len(strings) == 0 or len(strings) > 30:
        return strip_vendor(strings[:30])
    else:
        return pattern.findall(strings)[0] if len(pattern.findall(strings)) > 0 else re.split(r'[\W_]+', strings)[0]

# Example usage
if __name__ == "__main__":
    folder_path = input("Enter the folder path containing CSV files: ")
    read_all_csv_from_folder(folder_path)
