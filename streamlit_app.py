import streamlit as st
import pandas as pd
from dbmodels import SessionLocal, AccountTransaction, Vendor
import main
import os
from sqlalchemy import func
import plotly.express as px
from datetime import datetime, timedelta
import logging
import plotly.graph_objects as go

def load_transactions(start_date=None, end_date=None, search_term=None, search_column=None, selected_categories=None, amount_range=None):
    """Load transactions with search and filter capabilities"""
    session = SessionLocal()
    try:
        query = session.query(
            AccountTransaction.transaction_id,
            AccountTransaction.transaction_date,
            AccountTransaction.posting_date,
            AccountTransaction.description,
            AccountTransaction.amount,
            AccountTransaction.category,
            AccountTransaction.sale_type,
            Vendor.vendor_name
        ).join(
            Vendor,
            AccountTransaction.vendor_id == Vendor.vendor_id,
            isouter=True
        )
        
        # Apply filters
        if start_date and end_date:
            query = query.filter(AccountTransaction.transaction_date.between(start_date, end_date))
            
        if search_term and search_column:
            if search_column == 'amount':
                try:
                    search_value = float(search_term)
                    query = query.filter(AccountTransaction.amount == search_value)
                except ValueError:
                    st.warning("Please enter a valid number for amount search")
            elif search_column == 'vendor_name':
                query = query.filter(Vendor.vendor_name.ilike(f'%{search_term}%'))
            elif hasattr(AccountTransaction, search_column):
                query = query.filter(getattr(AccountTransaction, search_column).ilike(f'%{search_term}%'))
        
        if selected_categories:
            query = query.filter(AccountTransaction.category.in_(selected_categories))
            
        if amount_range:
            query = query.filter(
                AccountTransaction.amount.between(amount_range[0], amount_range[1])
            )
        
        # Execute query and convert to DataFrame
        df = pd.read_sql(query.statement, session.bind)
        
        # Ensure proper date formatting
        for date_col in ['transaction_date', 'posting_date']:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col])
        
        return df
    except Exception as e:
        st.error(f"Database error: {e}")
        return pd.DataFrame()
    finally:
        session.close()

def get_transaction_stats():
    session = SessionLocal()
    stats = {
        'total_transactions': session.query(AccountTransaction).count(),
        'total_credit': session.query(func.sum(AccountTransaction.amount)).\
            filter(AccountTransaction.sale_type == 'Credit').scalar() or 0,
        'total_debit': session.query(func.sum(AccountTransaction.amount)).\
            filter(AccountTransaction.sale_type == 'Debit').scalar() or 0,
        'unique_vendors': session.query(Vendor).count()
    }
    session.close()
    return stats

def check_existing_transaction(session, df_row):
    """Check if a transaction already exists in the database"""
    return session.query(AccountTransaction).filter(
        AccountTransaction.transaction_date == pd.to_datetime(df_row.get('transaction_date')),
        AccountTransaction.description == df_row.get('description'),
        AccountTransaction.amount == df_row.get('amount')
    ).first() is not None

def store_transaction_in_db(df_row):
    """Store a single transaction row in the database with duplicate checking"""
    session = SessionLocal()
    try:
        # Check for existing transaction
        if check_existing_transaction(session, df_row):
            logging.info(f"Skipping duplicate transaction: {df_row.get('description')} on {df_row.get('transaction_date')}")
            return {'status': 'duplicate'}

        # Process vendor
        vendor = session.query(Vendor).filter_by(vendor_name=df_row.get('vendorName')).first()
        if not vendor:
            vendor = Vendor(
                vendor_name=df_row.get('vendorName'),
                vendor_code=df_row.get('vendorName')[:10],
                created_by=1,
                updated_by=1
            )
            session.add(vendor)
            session.flush()

        # Create transaction
        transaction = AccountTransaction(
            description=df_row.get('description'),
            vendor_id=vendor.vendor_id,
            posting_date=pd.to_datetime(df_row.get('posting_date')),
            transaction_date=pd.to_datetime(df_row.get('transaction_date')),
            amount=df_row.get('amount'),
            category=df_row.get('category'),
            sale_type=df_row.get('type'),
            created_by=1,
            updated_by=1,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(transaction)
        session.commit()
        return {'status': 'success'}
        
    except Exception as e:
        session.rollback()
        logging.error(f"Error storing transaction in database: {e}")
        return {'status': 'error', 'message': str(e)}
    finally:
        session.close()

def process_csv_files(uploaded_files):
    """Process uploaded CSV files with duplicate checking"""
    stats = {
        'total': 0,
        'duplicates': 0,
        'successful': 0,
        'failed': 0
    }
    
    temp_dir = "temp_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    for uploaded_file in uploaded_files:
        try:
            # Save uploaded file
            file_path = os.path.join(temp_dir, uploaded_file.name)
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            # Process file
            df = csv_reader(file_path)
            
            # Check for duplicates within the file
            internal_duplicates = df[df.duplicated(subset=[
                'transaction_date',
                'description',
                'amount'
            ], keep=False)]
            
            if not internal_duplicates.empty:
                st.warning(f"Found internal duplicates in {uploaded_file.name}:")
                st.dataframe(internal_duplicates)
            
            # Process each row
            for _, row in df.iterrows():
                stats['total'] += 1
                result = store_transaction_in_db(row)
                
                if result['status'] == 'success':
                    stats['successful'] += 1
                elif result['status'] == 'duplicate':
                    stats['duplicates'] += 1
                else:
                    stats['failed'] += 1
                    
        except Exception as e:
            st.error(f"Error processing file {uploaded_file.name}: {str(e)}")
            stats['failed'] += 1
            
    return stats

def update_transaction(transaction_id, updated_data):
    """Update transaction in database"""
    session = SessionLocal()
    try:
        transaction = session.query(AccountTransaction).filter_by(transaction_id=transaction_id).first()
        if transaction:
            for key, value in updated_data.items():
                if key in ['transaction_date', 'posting_date']:
                    value = pd.to_datetime(value)
                if key == 'vendor_name':
                    # Handle vendor update
                    vendor = session.query(Vendor).filter_by(vendor_name=value).first()
                    if not vendor:
                        vendor = Vendor(
                            vendor_name=value,
                            vendor_code=value[:10],
                            created_by=1,
                            updated_by=1
                        )
                        session.add(vendor)
                        session.flush()
                    transaction.vendor_id = vendor.vendor_id
                else:
                    setattr(transaction, key, value)
            
            transaction.updated_at = datetime.utcnow()
            session.commit()
            return True
    except Exception as e:
        session.rollback()
        st.error(f"Error updating transaction: {e}")
        return False
    finally:
        session.close()

def create_monthly_boxplot(transactions):
    """Create monthly aggregation boxplot"""
    # Ensure transaction_date is datetime
    transactions['transaction_date'] = pd.to_datetime(transactions['transaction_date'])
    
    # Add month-year column
    transactions['month_year'] = transactions['transaction_date'].dt.strftime('%Y-%m')
    
    # Create boxplot using plotly
    fig = px.box(
        transactions,
        x='month_year',
        y='amount',
        title='Monthly Transaction Distribution',
        labels={
            'month_year': 'Month',
            'amount': 'Transaction Amount ($)'
        }
    )
    
    # Customize the layout
    fig.update_layout(
        xaxis_title="Month",
        yaxis_title="Amount ($)",
        showlegend=False,
        xaxis={'tickangle': 45},
        height=500,
        hovermode='x unified'
    )
    
    # Add mean line
    fig.add_trace(
        go.Scatter(
            x=transactions.groupby('month_year')['amount'].mean().index,
            y=transactions.groupby('month_year')['amount'].mean().values,
            mode='lines+markers',
            name='Monthly Mean',
            line=dict(color='red', dash='dash'),
            marker=dict(color='red')
        )
    )
    
    return fig

def display_monthly_stats(transactions):
    """Display monthly statistics"""
    monthly_stats = transactions.groupby('month_year').agg({
        'amount': ['count', 'mean', 'std', 'min', 'max', 'sum']
    }).round(2)
    
    monthly_stats.columns = ['Count', 'Mean', 'Std Dev', 'Min', 'Max', 'Total']
    monthly_stats = monthly_stats.reset_index()
    
    # Format currency columns
    for col in ['Mean', 'Min', 'Max', 'Total']:
        monthly_stats[col] = monthly_stats[col].apply(lambda x: f"${x:,.2f}")
    
    return monthly_stats

def main():
    st.title("Transaction Analysis Dashboard")
    
    # Sidebar for filters and search
    st.sidebar.title("Search & Filters")
    
    # Date range selector
    date_range = st.sidebar.date_input(
        "Date Range",
        value=(datetime.now() - timedelta(days=30), datetime.now()),
        max_value=datetime.now()
    )
    
    # Search functionality
    search_term = st.sidebar.text_input("Search Transactions", "")
    search_column = st.sidebar.selectbox(
        "Search In",
        ["description", "vendor_name", "category", "amount"]
    )
    
    # Amount range filter
    amount_range = st.sidebar.slider(
        "Amount Range",
        min_value=0.0,
        max_value=10000.0,
        value=(0.0, 10000.0),
        step=100.0
    )
    
    # Category filter
    session = SessionLocal()
    categories = [cat[0] for cat in session.query(AccountTransaction.category).distinct()]
    selected_categories = st.sidebar.multiselect("Categories", categories)
    session.close()

    # Load filtered transactions
    transactions = load_transactions(
        start_date=date_range[0],
        end_date=date_range[1],
        search_term=search_term,
        search_column=search_column,
        selected_categories=selected_categories,
        amount_range=amount_range
    )
    
    if not transactions.empty:
        # Convert date columns to datetime before editing
        for date_col in ['transaction_date', 'posting_date']:
            if date_col in transactions.columns:
                transactions[date_col] = pd.to_datetime(transactions[date_col])

        # Display editable transaction table
        st.subheader("Transaction Details")
        
        # Make DataFrame editable with corrected column config
        edited_df = st.data_editor(
            transactions,
            column_config={
                "transaction_id": "Transaction ID",  # Simple column config
                "transaction_date": st.column_config.DatetimeColumn(
                    "Transaction Date",
                    format="YYYY-MM-DD",
                    step=60,
                ),
                "posting_date": st.column_config.DatetimeColumn(
                    "Posting Date",
                    format="YYYY-MM-DD",
                    step=60,
                ),
                "amount": st.column_config.NumberColumn(
                    "Amount",
                    format="$%.2f",
                    min_value=0,
                    max_value=1000000
                ),
                "category": st.column_config.SelectboxColumn(
                    "Category",
                    options=categories,
                    required=True
                ),
                "description": st.column_config.TextColumn(
                    "Description",
                    max_chars=200
                ),
                "vendor_name": st.column_config.TextColumn(
                    "Vendor",
                    max_chars=100
                ),
            },
            hide_index=True,
            key="transaction_editor"
        )

        # Check for changes and update database
        if not edited_df.equals(transactions):
            for idx, row in edited_df.iterrows():
                original_row = transactions.loc[idx]
                updates = {}
                
                # Collect changed values
                for column in transactions.columns:
                    if column != 'transaction_id' and row[column] != original_row[column]:
                        updates[column] = row[column]
                
                if updates:
                    transaction_id = row['transaction_id']
                    success = update_transaction(transaction_id, updates)
                    if success:
                        st.success(f"Updated transaction {transaction_id}")
                    else:
                        st.error(f"Failed to update transaction {transaction_id}")

        # Show summary statistics for filtered data
        st.subheader("Summary")
        col1, col2, col3 = st.columns(3)
        col1.metric("Filtered Transactions", len(transactions))
        col2.metric("Total Amount", f"${transactions['amount'].sum():,.2f}")
        col3.metric("Average Amount", f"${transactions['amount'].mean():,.2f}")

        # Visualizations
        st.subheader("Transaction Analysis")
        
        # Time series plot
        fig_timeline = px.line(
            transactions,
            x='transaction_date',
            y='amount',
            title='Transaction Timeline'
        )
        st.plotly_chart(fig_timeline)

        # Category breakdown
        col1, col2 = st.columns(2)
        
        with col1:
            category_data = transactions.groupby('category')['amount'].sum()
            fig_category = px.pie(
                values=category_data.values,
                names=category_data.index,
                title='Spending by Category'
            )
            st.plotly_chart(fig_category)
        
        with col2:
            monthly_data = transactions.groupby(
                transactions['transaction_date'].dt.strftime('%Y-%m')
            )['amount'].sum()
            fig_monthly = px.bar(
                x=monthly_data.index,
                y=monthly_data.values,
                title='Monthly Spending'
            )
            st.plotly_chart(fig_monthly)

        # Monthly Analysis Section
        st.subheader("Monthly Transaction Analysis")
        
        # Create tabs for different views
        tab1, tab2 = st.tabs(["Distribution Plot", "Monthly Statistics"])
        
        with tab1:
            # Monthly boxplot
            st.plotly_chart(create_monthly_boxplot(transactions))
            
            # Add explanatory text
            st.markdown("""
            **Understanding the Boxplot:**
            - The box shows the interquartile range (IQR) containing 50% of the transactions
            - The line inside the box is the median
            - The whiskers extend to show the rest of the distribution
            - Points beyond the whiskers are outliers
            - The red dashed line shows the monthly mean
            """)
        
        with tab2:
            # Monthly statistics table
            st.markdown("### Monthly Transaction Statistics")
            monthly_stats = display_monthly_stats(transactions)
            st.dataframe(
                monthly_stats,
                column_config={
                    "month_year": "Month",
                    "Count": st.column_config.NumberColumn("Count", format="%d"),
                    "Mean": "Average Amount",
                    "Std Dev": st.column_config.NumberColumn("Std Deviation", format="%.2f"),
                    "Min": "Minimum Amount",
                    "Max": "Maximum Amount",
                    "Total": "Total Amount"
                },
                hide_index=True
            )
            
            # Download button for statistics
            csv = monthly_stats.to_csv(index=False)
            st.download_button(
                label="Download Monthly Statistics",
                data=csv,
                file_name="monthly_statistics.csv",
                mime="text/csv"
            )

        # Export functionality
        if st.button("Export Filtered Data"):
            csv = transactions.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="transactions_export.csv",
                mime="text/csv"
            )
    else:
        st.info("No transactions found for the selected criteria.")

if __name__ == "__main__":
    main() 