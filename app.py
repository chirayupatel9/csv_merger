import streamlit as st
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy.exc import NoResultFound
from datetime import datetime
import main
from dbmodels import SessionLocal, AccountTransaction, Vendor, TransactionType, Categories, Accounts, Organization, Users, AccountTransaction
import numpy as np

st.title("CSV Processor (Store Merged Data in Relational DB)")

# Function to get or insert foreign key records
def get_or_create(session, model, filter_by, defaults):
    """Fetch foreign key record, if not found insert a new one."""
    try:
        record = session.query(model).filter_by(**filter_by).one()
    except NoResultFound:
        record = model(**{**filter_by, **defaults})
        session.add(record)
        session.commit()
        session.refresh(record)
    return record

def clean_value(value):
    """Convert NaN values to None for database insertion."""
    return None if pd.isna(value) or value in ["", "NaN", "nan", np.nan] else value
def save_combined_csv_to_db(df):
    """Saves Combined CSV Data into `accountTransaction` while ensuring FK constraints"""
    session = SessionLocal()

    try:
        records = []
        for _, row in df.iterrows():
            # Clean NaN values
            vendor_name = clean_value(row.get("vendorName"))
            tran_type_name = clean_value(row.get("type"))
            category_name = clean_value(row.get("category"))
            account_number = clean_value(row.get("accountNumber"))

            # Get or create Foreign Key relationships
            vendor = get_or_create(session, Vendor, {"vendor_name": vendor_name}, {"vendor_code": "AUTO", "vendor_description": "Added from CSV"}) if vendor_name else None
            tran_type = get_or_create(session, TransactionType, {"tran_type": tran_type_name}, {"tran_code": 999, "tran_desc": "Auto Added"}) if tran_type_name else None
            category = get_or_create(session, Categories, {"category_Name": category_name}, {}) if category_name else None
            
            # Handle missing account_Id
            account = get_or_create(session, Accounts, {"account_Number": account_number}, {"account_Name": "Auto Created", "account_code": "AUTO"}) if account_number else None
            default_account = session.query(Accounts).filter_by(account_Name="Default").first()
            account_id = account.account_Id if account else (default_account.account_Id if default_account else None)

            org = get_or_create(session, Organization, {"org_name": "DefaultOrg"}, {"org_code": "AUTO", "org_description": "Auto Added"})
            user = get_or_create(session, Users, {"username": "admin"}, {"name": "Admin", "password": "password"})

            record = AccountTransaction(
                org_id=org.org_id if org else None,
                account_Id=account_id,  # FIXED: Matches `account_Id`
                description=row.get("description"),
                vendor_id=vendor.vendor_id if vendor else None,
                tran_type_id=tran_type.tran_type_id if tran_type else None,
                card_number=row.get("cardNumber"),
                posting_date=row.get("posting_date"),
                transaction_date=row.get("transaction_date"),
                amount=row.get("amount"),
                category=category.category_id if category else None,
                payment_date=row.get("payment_date"),
                due_date=row.get("due_date"),
                balance_as_of_date=row.get("balance_as_of_date"),
                sale_type=row.get("sale_type"),
                source_id=row.get("source_id"),
                created_by=user.user_id if user else None,
                updated_by=user.user_id if user else None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            records.append(record)

        session.add_all(records)
        session.commit()
        st.success("Combined CSV data stored in PostgreSQL (Relational) successfully!")

    except Exception as e:
        session.rollback()
        st.error(f"Error saving data to PostgreSQL: {e}")

    finally:
        session.close()


# File Upload Section
uploaded_files = st.file_uploader("Upload Multiple CSV Files", type=['csv'], accept_multiple_files=True)

if uploaded_files:
    combined_df = pd.DataFrame()

    for file in uploaded_files:
        df = main.csv_reader(file)
        combined_df = pd.concat([combined_df, df], ignore_index=True)

    # Display combined data
    st.subheader("Combined CSV Data Preview")
    st.dataframe(combined_df.head(20))

    # Store combined data in PostgreSQL (Relational)
    if st.button("Save Combined CSV Data to PostgreSQL"):
        save_combined_csv_to_db(combined_df)

    # Display stored data option
    if st.button("View Stored CSV Data"):
        session = SessionLocal()
        query = session.query(AccountTransaction).all()
        session.close()
        
        if query:
            st.subheader("Stored CSV Data in Database")
            stored_data = pd.DataFrame([(row.transaction_date, row.posting_date, row.vendor_id, row.amount, row.type, row.category, row.description) for row in query],
                                       columns=["Transaction Date", "Posting Date", "Vendor", "Amount", "Type", "Category", "Description"])
            st.dataframe(stored_data)
        else:
            st.warning("No data found in the database.")

    # Download processed data
    csv = combined_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Processed CSV",
        data=csv,
        file_name="processed_data.csv",
        mime="text/csv"
    )
