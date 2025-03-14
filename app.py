import streamlit as st
import pandas as pd
import main

st.title("CSV Data Processor & Pivot Table")

# File Upload Section
uploaded_file = st.file_uploader("Upload a CSV file", type=['csv'])

if uploaded_file:
    st.success("File uploaded successfully!")

    # Read and process the file
    df = main.csv_reader(uploaded_file)

    # Show raw data preview
    st.subheader("Processed Data Preview")
    st.dataframe(df.head(20))

    # Pivot Table Section
    st.subheader("Create a Pivot Table")

    # Allow users to select index, columns, and values
    index_col = st.multiselect("Select Index Columns", df.columns)
    columns_col = st.multiselect("Select Columns", df.columns)
    values_col = st.multiselect("Select Values", df.columns)

    # Aggregation function with "None" as default
    agg_funcs = ["None", "sum", "mean", "count", "min", "max"]
    agg_func = st.selectbox("Select Aggregation Function", agg_funcs, index=0)

    # Column Visibility Selection
    st.subheader("Select Columns to Display in Pivot Table")
    visible_columns = st.multiselect("Select Columns to Show", df.columns, default=df.columns)

    if index_col:
        try:
            # If no aggregation is selected, use `pivot()`
            if agg_func == "None":
                if values_col:
                    pivot_df = df.pivot(index=index_col, columns=columns_col, values=values_col)
                else:
                    pivot_df = df.pivot(index=index_col, columns=columns_col)
            else:
                # Use `pivot_table()` when an aggregation function is selected
                pivot_df = pd.pivot_table(df, index=index_col, columns=columns_col, values=values_col, aggfunc=agg_func)

            # Apply column visibility filter
            pivot_df = pivot_df[visible_columns] if set(visible_columns).issubset(pivot_df.columns) else pivot_df

            # Show pivot table
            st.subheader("Pivot Table Output")
            st.dataframe(pivot_df)

            # Provide download option
            csv_pivot = pivot_df.to_csv().encode('utf-8')
            st.download_button(
                label="Download Pivot Table CSV",
                data=csv_pivot,
                file_name="pivot_table.csv",
                mime="text/csv"
            )
        except Exception as e:
            st.error(f"Error creating Pivot Table: {e}")
    else:
        st.warning("Please select at least one index column for the pivot table.")

    # Download processed data
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Processed CSV",
        data=csv,
        file_name="processed_data.csv",
        mime="text/csv"
    )
