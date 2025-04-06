import streamlit as st
import pandas as pd
from dbmodels import SessionLocal, AccountTransaction, Vendor, Users
import main
import os
from sqlalchemy import func
import plotly.express as px
from datetime import datetime, timedelta
import logging
import plotly.graph_objects as go
import numpy as np
import hashlib
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

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
            
            try:
                # Process file using main.csv_reader
                df = main.csv_reader(file_path)
                
                if df.empty:
                    st.error(f"No data found in file: {uploaded_file.name}")
                    stats['failed'] += 1
                    continue
                
                # Check for required columns
                required_columns = ['transaction_date', 'description', 'amount', 'category', 'type', 'vendorName', 'posting_date']
                missing_columns = [col for col in required_columns if col not in df.columns]
                if missing_columns:
                    st.error(f"Missing required columns in {uploaded_file.name}: {', '.join(missing_columns)}")
                    stats['failed'] += 1
                    continue
                
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
                        st.error(f"Error storing transaction: {result.get('message', 'Unknown error')}")
                
            finally:
                # Clean up the temporary file
                try:
                    os.remove(file_path)
                except Exception as e:
                    logging.warning(f"Failed to remove temporary file {file_path}: {e}")
                    
        except Exception as e:
            st.error(f"Error processing file {uploaded_file.name}: {str(e)}")
            stats['failed'] += 1
            
    # Clean up temp directory if empty
    try:
        os.rmdir(temp_dir)
    except:
        pass
            
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

def create_sankey_diagram(transactions):
    """Create a Sankey diagram for cash flow"""
    # Ensure amount and category are present
    if 'amount' not in transactions.columns or 'category' not in transactions.columns:
        return None
    
    # Separate income and expenses
    income = transactions[transactions['amount'] >= 0]
    expenses = transactions[transactions['amount'] < 0]
    
    # Prepare source data (income categories)
    income_categories = income.groupby('category')['amount'].sum()
    
    # Prepare target data (expense categories)
    expense_categories = expenses.groupby('category')['amount'].sum().abs()
    
    # Create labels for all nodes
    labels = ['Total Income'] + \
            list(income_categories.index) + \
            list(expense_categories.index)
    
    # Create source indices
    sources = []
    # From income categories to total income
    for i in range(len(income_categories)):
        sources.append(i + 1)  # +1 because 0 is "Total Income"
    # From total income to expense categories
    for i in range(len(expense_categories)):
        sources.append(0)
    
    # Create target indices
    targets = []
    # To total income
    for i in range(len(income_categories)):
        targets.append(0)
    # To expense categories
    for i in range(len(expense_categories)):
        targets.append(i + len(income_categories) + 1)
    
    # Create values
    values = list(income_categories.values) + list(expense_categories.values)
    
    # Create colors
    income_color = '#2ECC71'  # Green
    expense_color = '#E74C3C'  # Red
    neutral_color = '#3498DB'  # Blue
    
    colors = [neutral_color] + \
            [income_color] * len(income_categories) + \
            [expense_color] * len(expense_categories)
    
    # Create the figure
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="black", width=0.5),
            label=labels,
            color=colors
        ),
        link=dict(
            source=sources,
            target=targets,
            value=values,
            color=[income_color]*len(income_categories) + 
                  [expense_color]*len(expense_categories)
        )
    )])
    
    # Update layout
    fig.update_layout(
        title="Cash Flow Sankey Diagram",
        font_size=12,
        height=600
    )
    
    return fig

def display_cash_flow_summary(transactions):
    """Display cash flow summary statistics"""
    income = transactions[transactions['amount'] >= 0]
    expenses = transactions[transactions['amount'] < 0]
    
    summary = {
        'Total Income': income['amount'].sum(),
        'Total Expenses': abs(expenses['amount'].sum()),
        'Net Cash Flow': transactions['amount'].sum(),
        'Income Categories': len(income['category'].unique()),
        'Expense Categories': len(expenses['category'].unique()),
        'Top Income Category': income.groupby('category')['amount'].sum().idxmax() 
            if not income.empty else 'N/A',
        'Top Expense Category': expenses.groupby('category')['amount'].sum().idxmin() 
            if not expenses.empty else 'N/A'
    }
    
    return summary

def create_vendor_description_analysis(transactions):
    """Create combined analysis of vendors and descriptions"""
    
    # Create a detailed analysis dataframe
    analysis_df = transactions.groupby(['vendor_name', 'description']).agg({
        'amount': ['count', 'sum', 'mean', 'min', 'max'],
        'category': lambda x: x.value_counts().index[0]  # most common category
    }).round(2)
    
    # Flatten column names
    analysis_df.columns = [
        'Transaction_Count',
        'Total_Amount',
        'Average_Amount',
        'Min_Amount',
        'Max_Amount',
        'Most_Common_Category'
    ]
    
    # Reset index for better display
    analysis_df = analysis_df.reset_index()
    
    # Add frequency column (percentage of total transactions)
    total_transactions = analysis_df['Transaction_Count'].sum()
    analysis_df['Frequency'] = (analysis_df['Transaction_Count'] / total_transactions * 100).round(2)
    
    return analysis_df

def plot_vendor_patterns(transactions):
    """Create visualizations for vendor patterns"""
    # Changed 'M' to 'ME' for month end frequency
    vendor_time_data = transactions.groupby([
        'vendor_name', 
        pd.Grouper(key='transaction_date', freq='ME')  # Changed from 'M' to 'ME'
    ])['amount'].sum().reset_index()
    
    # Top vendors by transaction volume
    top_vendors = transactions.groupby('vendor_name')['amount'].agg(['count', 'sum'])\
        .sort_values('count', ascending=False).head(10)
    
    # Create figures
    fig_time = px.line(
        vendor_time_data,
        x='transaction_date',
        y='amount',
        color='vendor_name',
        title='Vendor Transaction Patterns Over Time'
    )
    
    fig_volume = px.bar(
        top_vendors,
        y=top_vendors.index,
        x='count',
        orientation='h',
        title='Top 10 Vendors by Transaction Volume'
    )
    
    return fig_time, fig_volume

def show_vendor_details(transactions, vendor_name):
    """Show detailed analysis for a specific vendor"""
    vendor_transactions = transactions[transactions['vendor_name'] == vendor_name].copy()
    
    st.subheader(f"Detailed Analysis for {vendor_name}")
    
    # Summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Total Transactions",
            len(vendor_transactions)
        )
    with col2:
        st.metric(
            "Total Amount",
            f"${vendor_transactions['amount'].sum():,.2f}"
        )
    with col3:
        st.metric(
            "Average Amount",
            f"${vendor_transactions['amount'].mean():,.2f}"
        )
    with col4:
        st.metric(
            "Most Common Category",
            vendor_transactions['category'].mode().iloc[0]
        )

    # Transaction timeline
    fig_timeline = px.line(
        vendor_transactions,
        x='transaction_date',
        y='amount',
        title=f'Transaction Timeline for {vendor_name}'
    )
    st.plotly_chart(fig_timeline)

    # Monthly pattern
    monthly_data = vendor_transactions.groupby(
        pd.Grouper(key='transaction_date', freq='ME')
    )['amount'].agg(['count', 'sum', 'mean']).reset_index()
    
    monthly_data.columns = ['Month', 'Count', 'Total', 'Average']
    
    # Monthly patterns visualization
    fig_monthly = px.bar(
        monthly_data,
        x='Month',
        y=['Total', 'Average'],
        title=f'Monthly Patterns for {vendor_name}',
        barmode='group'
    )
    st.plotly_chart(fig_monthly)

    # Detailed transactions table
    st.subheader("All Transactions")
    
    # Add date range filter for transactions
    date_range = st.date_input(
        "Filter by Date Range",
        value=(
            vendor_transactions['transaction_date'].min(),
            vendor_transactions['transaction_date'].max()
        )
    )
    
    filtered_transactions = vendor_transactions[
        (vendor_transactions['transaction_date'].dt.date >= date_range[0]) &
        (vendor_transactions['transaction_date'].dt.date <= date_range[1])
    ]
    
    # Sort transactions by date
    filtered_transactions = filtered_transactions.sort_values('transaction_date', ascending=False)
    
    # Display transactions with formatted columns
    st.dataframe(
        filtered_transactions,
        column_config={
            "transaction_date": st.column_config.DatetimeColumn(
                "Date",
                format="YYYY-MM-DD"
            ),
            "amount": st.column_config.NumberColumn(
                "Amount",
                format="$%.2f"
            ),
            "description": "Description",
            "category": "Category"
        },
        hide_index=True
    )

    # Add download button for vendor transactions
    csv = filtered_transactions.to_csv(index=False)
    st.download_button(
        "Download Vendor Transactions",
        csv,
        f"{vendor_name}_transactions.csv",
        "text/csv"
    )

def hash_password(password):
    """Create a SHA-256 hash of the password"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password):
    """Authenticate user and update login information"""
    session = SessionLocal()
    try:
        hashed_password = hash_password(password)
        user = session.query(Users).filter_by(username=username).first()
        
        if user and user.password == hashed_password:
            # Update login information
            user.last_login = datetime.utcnow()
            user.tries = 1  # Reset login attempts
            session.commit()
            
            # Extract user data before closing session
            user_data = {
                "user_id": user.user_id,
                "username": user.username,
                "name": user.name,
                "email": user.email
            }
            return user_data
        elif user:
            # Increment login attempts
            user.tries += 1
            session.commit()
        return None
    except Exception as e:
        st.error(f"Authentication error: {e}")
        return None
    finally:
        session.close()

def register_new_user(name, username, password, email):
    """Register a new user"""
    session = SessionLocal()
    try:
        # Check if username already exists
        existing_user = session.query(Users).filter_by(username=username).first()
        if existing_user:
            return False, "Username already exists"
            
        # Check if email already exists
        existing_email = session.query(Users).filter_by(email=email).first()
        if existing_email:
            return False, "Email already in use"
            
        # Create new user
        hashed_password = hash_password(password)
        new_user = Users(
            name=name,
            username=username,
            password=hashed_password,
            email=email,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            tries=1,
            last_login=datetime.utcnow()
        )
        session.add(new_user)
        session.commit()
        return True, "Registration successful"
    except IntegrityError:
        session.rollback()
        return False, "Database error: User could not be created"
    except Exception as e:
        session.rollback()
        return False, f"Error creating user: {e}"
    finally:
        session.close()

def login_page():
    """Display login page"""
    st.title("Transaction Dashboard - Login")
    
    # Check if already logged in
    if st.session_state.get("user_id"):
        st.success("You are already logged in!")
        st.button("Continue to Dashboard", on_click=lambda: st.session_state.update({"page": "dashboard"}))
        st.button("Logout", on_click=logout)
        return
    
    # Create tabs for login and registration
    tab1, tab2 = st.tabs(["Login", "Register"])
    
    with tab1:
        st.subheader("Login to Your Account")
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        
        col1, col2 = st.columns([1, 3])
        with col1:
            login_button = st.button("Login")
        
        if login_button:
            if not username or not password:
                st.error("Please enter both username and password")
            else:
                user_data = authenticate_user(username, password)
                if user_data:
                    # Store user data in session state
                    st.session_state["user_id"] = user_data["user_id"]
                    st.session_state["username"] = user_data["username"]
                    st.session_state["name"] = user_data["name"]
                    st.session_state["page"] = "dashboard"
                    st.success("Login successful!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
    
    with tab2:
        st.subheader("Create New Account")
        
        name = st.text_input("Full Name", key="reg_name")
        username = st.text_input("Username", key="reg_username")
        email = st.text_input("Email Address", key="reg_email")
        password = st.text_input("Password", type="password", key="reg_password")
        confirm_password = st.text_input("Confirm Password", type="password", key="reg_confirm")
        
        register_button = st.button("Register")
        
        if register_button:
            if not all([name, username, email, password, confirm_password]):
                st.error("Please fill in all fields")
            elif password != confirm_password:
                st.error("Passwords do not match")
            elif len(password) < 6:
                st.error("Password must be at least 6 characters long")
            else:
                success, message = register_new_user(name, username, password, email)
                if success:
                    st.success(message)
                    st.info("Please login with your new account")
                    # Switch to login tab
                    st.session_state["active_tab"] = "Login"
                else:
                    st.error(message)

def logout():
    """Log out the current user"""
    for key in ["user_id", "username", "name"]:
        if key in st.session_state:
            del st.session_state[key]
    
    st.session_state["page"] = "login"
    st.rerun()

def update_password_field_length():
    """Update the password field length in the database"""
    engine = SessionLocal().get_bind()
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE users ALTER COLUMN password TYPE varchar(100)"))
            conn.commit()
            return True
        except Exception as e:
            logging.error(f"Error updating password field length: {e}")
            return False

def initialize_session_state():
    """Initialize session state variables"""
    if "page" not in st.session_state:
        st.session_state["page"] = "login"
    
    # Try to update password field length
    if "db_schema_updated" not in st.session_state:
        update_success = update_password_field_length()
        st.session_state["db_schema_updated"] = update_success
        if not update_success:
            st.warning("Warning: Could not update database schema. Registration might not work correctly.")

def functions():
    # Initialize session state
    initialize_session_state()
    
    # Display appropriate page based on session state
    if st.session_state["page"] == "login":
        login_page()
    else:
        dashboard_page()

def dashboard_page():
    """Main dashboard functionality"""
    st.title("Transaction Analysis Dashboard")
    
    # Display user information and logout button in the sidebar
    st.sidebar.markdown(f"### Welcome, {st.session_state.get('name', 'User')}")
    st.sidebar.button("Logout", on_click=logout)
    
    # Sidebar for filters and search
    st.sidebar.title("Search & Filters")
    
    # Add file upload to sidebar
    uploaded_files = st.sidebar.file_uploader(
        "Upload Transaction Files",
        type=['csv'],
        accept_multiple_files=True
    )
    
    # Process uploaded files if any
    if uploaded_files:
        with st.sidebar.expander("Upload Results", expanded=True):
            stats = process_csv_files(uploaded_files)
            st.write("Upload Summary:")
            st.write(f"- Total Processed: {stats['total']}")
            st.write(f"- Successful: {stats['successful']}")
            st.write(f"- Duplicates: {stats['duplicates']}")
            st.write(f"- Failed: {stats['failed']}")
    
    # Date range selector
    st.sidebar.divider()  # Add visual separation
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

        # Vendor and Description Analysis Section
        st.subheader("Vendor and Description Analysis")
        
        tabs = st.tabs(["Combined Analysis", "Visualizations", "Pattern Search", "Vendor Details"])
        
        with tabs[0]:
            st.markdown("### Vendor-Description Patterns")
            
            # Get combined analysis
            analysis_df = create_vendor_description_analysis(transactions)
            
            # Add filters
            col1, col2, col3 = st.columns(3)
            with col1:
                min_transactions = st.number_input(
                    "Minimum Transactions",
                    min_value=1,
                    value=2,
                    step=1
                )
            with col2:
                min_amount = st.number_input(
                    "Minimum Total Amount",
                    min_value=0.0,
                    value=100.0,
                    step=50.0
                )
            with col3:
                vendor_search = st.text_input(
                    "Search Vendor/Description",
                    ""
                )
            
            # Filter the dataframe
            filtered_df = analysis_df[
                (analysis_df['Transaction_Count'] >= min_transactions) &
                (analysis_df['Total_Amount'] >= min_amount)
            ]
            
            if vendor_search:
                filtered_df = filtered_df[
                    filtered_df['vendor_name'].str.contains(vendor_search, case=False) |
                    filtered_df['description'].str.contains(vendor_search, case=False)
                ]
            
            # Display the filtered dataframe
            st.dataframe(
                filtered_df,
                column_config={
                    "vendor_name": "Vendor",
                    "description": "Description",
                    "Transaction_Count": st.column_config.NumberColumn("Count", format="%d"),
                    "Total_Amount": st.column_config.NumberColumn("Total ($)", format="$%.2f"),
                    "Average_Amount": st.column_config.NumberColumn("Average ($)", format="$%.2f"),
                    "Min_Amount": st.column_config.NumberColumn("Min ($)", format="$%.2f"),
                    "Max_Amount": st.column_config.NumberColumn("Max ($)", format="$%.2f"),
                    "Frequency": st.column_config.NumberColumn("Frequency (%)", format="%.2f%%"),
                    "Most_Common_Category": "Category"
                },
                hide_index=True
            )
            
            # Add download button
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                "Download Analysis",
                csv,
                "vendor_description_analysis.csv",
                "text/csv"
            )
        
        with tabs[1]:
            st.markdown("### Transaction Patterns")
            
            # Create and display visualizations
            fig_time, fig_volume = plot_vendor_patterns(transactions)
            
            st.plotly_chart(fig_time, use_container_width=True)
            st.plotly_chart(fig_volume, use_container_width=True)
            
            # Add summary statistics
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Top Recurring Transactions")
                recurring = analysis_df.sort_values('Frequency', ascending=False).head(5)
                st.dataframe(
                    recurring[['vendor_name', 'description', 'Frequency', 'Average_Amount']],
                    hide_index=True
                )
            
            with col2:
                st.markdown("#### Largest Transactions")
                largest = analysis_df.sort_values('Max_Amount', ascending=False).head(5)
                st.dataframe(
                    largest[['vendor_name', 'description', 'Max_Amount', 'Transaction_Count']],
                    hide_index=True
                )
        
        with tabs[2]:
            st.markdown("### Pattern Search")
            
            # Add pattern search functionality
            pattern_search = st.text_input(
                "Search for transaction patterns",
                placeholder="Enter keywords to search in descriptions..."
            )
            
            if pattern_search:
                pattern_results = transactions[
                    transactions['description'].str.contains(pattern_search, case=False) |
                    transactions['vendor_name'].str.contains(pattern_search, case=False)
                ]
                
                if not pattern_results.empty:
                    st.markdown(f"Found {len(pattern_results)} matching transactions")
                    
                    # Group by month to show patterns
                    monthly_patterns = pattern_results.groupby(
                        pattern_results['transaction_date'].dt.strftime('%Y-%m')
                    ).agg({
                        'amount': ['count', 'sum', 'mean'],
                        'description': 'first'
                    })
                    
                    monthly_patterns.columns = ['Count', 'Total', 'Average', 'Sample Description']
                    st.dataframe(monthly_patterns)
                    
                    # Plot pattern over time
                    fig_pattern = px.line(
                        pattern_results,
                        x='transaction_date',
                        y='amount',
                        title=f'Transaction Pattern: {pattern_search}'
                    )
                    st.plotly_chart(fig_pattern)
                else:
                    st.info("No matching patterns found")

        with tabs[3]:
            st.subheader("Vendor Analysis")
            
            # Create two columns
            col1, col2 = st.columns([1, 2])
            
            with col1:
                # Vendor selection
                vendors = sorted(transactions['vendor_name'].unique())
                selected_vendor = st.selectbox(
                    "Select Vendor",
                    vendors,
                    key="vendor_selector"
                )
                
                # Show vendor summary
                vendor_summary = transactions[
                    transactions['vendor_name'] == selected_vendor
                ].agg({
                    'amount': ['count', 'sum', 'mean'],
                    'category': lambda x: x.mode().iloc[0]
                })
                
                st.markdown("### Quick Summary")
                st.write(f"Total Transactions: {vendor_summary['amount']['count']:,}")
                st.write(f"Total Amount: ${vendor_summary['amount']['sum']:,.2f}")
                st.write(f"Average Amount: ${vendor_summary['amount']['mean']:,.2f}")
                st.write(f"Main Category: {vendor_summary['category']}")
            
            with col2:
                # Show vendor details in main area
                if selected_vendor:
                    show_vendor_details(transactions, selected_vendor)

        # Export functionality
        if st.button("Export Filtered Data"):
            csv = transactions.to_csv(index=False)
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="transactions_export.csv",
                mime="text/csv"
            )
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

        # Cash Flow Analysis Section
        st.subheader("Cash Flow Analysis")
        
        # Create tabs for different views
        tab1, tab2 = st.tabs(["Sankey Diagram", "Cash Flow Summary"])
        
        with tab1:
            # Create and display Sankey diagram
            sankey_fig = create_sankey_diagram(transactions)
            if sankey_fig:
                st.plotly_chart(sankey_fig, use_container_width=True)
                
                st.markdown("""
                **Understanding the Sankey Diagram:**
                - Green flows represent income
                - Red flows represent expenses
                - The width of each flow represents the amount
                - Hover over flows to see exact amounts
                - The diagram shows how money flows from income categories through total income to expense categories
                """)
            else:
                st.error("Could not create Sankey diagram. Please check your data.")
        
        with tab2:
            # Display cash flow summary
            summary = display_cash_flow_summary(transactions)
            
            # Create three columns for metrics
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "Total Income",
                    f"${summary['Total Income']:,.2f}",
                    delta=None
                )
                st.metric(
                    "Income Categories",
                    summary['Income Categories']
                )
                
            with col2:
                st.metric(
                    "Total Expenses",
                    f"${summary['Total Expenses']:,.2f}",
                    delta=None
                )
                st.metric(
                    "Expense Categories",
                    summary['Expense Categories']
                )
                
            with col3:
                st.metric(
                    "Net Cash Flow",
                    f"${summary['Net Cash Flow']:,.2f}",
                    delta=summary['Net Cash Flow'],
                    delta_color="normal"
                )
            
            # Display top categories
            st.markdown("### Top Categories")
            col1, col2 = st.columns(2)
            
            with col1:
                st.info(f"Top Income Category: {summary['Top Income Category']}")
            
            with col2:
                st.warning(f"Top Expense Category: {summary['Top Expense Category']}")
            
            # Category breakdown tables
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### Income Breakdown")
                income_breakdown = transactions[transactions['amount'] >= 0].groupby('category')['amount'].agg([
                    ('Total', 'sum'),
                    ('Count', 'count')
                ]).sort_values('Total', ascending=False)
                
                income_breakdown['Total'] = income_breakdown['Total'].apply(lambda x: f"${x:,.2f}")
                st.dataframe(income_breakdown)
            
            with col2:
                st.markdown("#### Expense Breakdown")
                expense_breakdown = transactions[transactions['amount'] < 0].groupby('category')['amount'].agg([
                    ('Total', lambda x: abs(sum(x))),
                    ('Count', 'count')
                ]).sort_values('Total', ascending=False)
                
                expense_breakdown['Total'] = expense_breakdown['Total'].apply(lambda x: f"${x:,.2f}")
                st.dataframe(expense_breakdown)

        
    else:
        st.info("No transactions found for the selected criteria.")

if __name__ == "__main__":
    functions() 