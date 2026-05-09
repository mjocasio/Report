from GeneralUtilityComparison import *
from Connection_Module import *
from datetime import datetime
from NameGenerator import *

def get_oracle_metadata(self, table_name, schema):
    """Fetch metadata for an Oracle table."""
    cursor = self.connection.cursor()
    query = f"""
    SELECT COLUMN_NAME
    FROM ALL_TAB_COLUMNS
    WHERE TABLE_NAME = '{table_name.upper()}'  and OWNER= '{schema.upper()}'
    """
    cursor.execute(query)
    columns = cursor.fetchall()
    cursor.close()
    return columns

def insert_OracleTargetTable(tableName):
    # Oracle connection details
    oracle_config = {
        "username":"histdba",
        "password":"unclefnk",
        "hostName":"158.71.213.17",
        "port":"16821",
        "service_name":"PSFTEHCM"
    }

    OracleTargetTable = "skipped_ps_names_recs"
    schema = 'histdba'

    # Oracle connection details
    oracle_conn = OracleDatabase(**oracle_config)
       
    try:
        # Establish Oracle database connection
        oracle_conn.connect()
        
        if oracle_conn.validate_connection():
            print("Oracle database connection is valid.")
        else:
            print("Oracle database connection is not valid.")
        
        # Get metadata from Oracle
        oracle_columns = get_oracle_metadata(oracle_conn, OracleTargetTable, schema)    
        
        # Read values from the file
        values = hana_comparison.read_file(fileSAP.getName())
        if not values:
            print("No values found in the file.")
        else:
            def clean_value(value):
                """
                Cleans a string by removing invalid characters but retains extended characters.
                Extended characters include accented letters, currency symbols, and more.
                """
                if isinstance(value, str):
                    # Allow alphanumeric characters, basic punctuation, and extended characters
                    return re.sub(r"[^\w\s.,;'-]", "", value, flags=re.UNICODE)
                return value  # Return unchanged if not a string

            # Clean and validate values
        cleaned_values = [
            tuple(clean_value(value) for value in row) for row in values
        ]

        # Dynamically create the SQL INSERT statement
        columns_str = ", ".join(oracle_columns)
        placeholders = ", ".join([":" + str(i + 1) for i in range(len(columns))])
        sql_query = f"INSERT INTO {tableName} ({columns_str}) VALUES ({placeholders})"

        # Execute the INSERT statement for each row
        cursor.executemany(sql_query, values)

        # Commit the transaction
        oracle_conn.commit()
        print(f"Inserted {cursor.rowcount} rows into {tableName}.")

    except cx_Oracle.DatabaseError as e:
        print("Error occurred while inserting data:", str(e))
        oracle_conn.rollback()

    except ValueError as ve:
        print(str(ve))
        return

    finally:
        # Close cursor and connection
        cursor.close()
        oracle_conn.close()

def main():
    # SAP HANA connection details
    hana_config = {
        "username":"MOCASIO_ADMIN",
        "password":"XeroX23$",
        "hostName":"4.16.73.11",
        "port":30041
    }

    hana_conn = SAPHANADatabase(**hana_config)
    fileSAP = NameGenerator("C:\python\ReportValidationHana","PsNamesHanaValidation")

    # Table details
    hana_table = "ehrp.ps_names"
    virtual_table = "v_ehrp.v_ps_names"

    hana_select = f"""
        a.emplid, a.effdt
    """
 
    # Dynamic WHERE clauses
    hana_where_clause = f"""
        B.EFFDT = A.EFFDT 
    """
    try:
       connection = hana_conn.connect()
       hana_comparison = GeneralUtilityComparison(fileSAP.getName(), fileSAP.getDirectory(), connection)
       hana_comparison.process_tables(hana_table,virtual_table,hana_select, hana_where_clause)
     
       #check for HANA Dups rows 
       # Dynamic WHERE clauses
       hana_where_clause = f"""
         GROUP BY a.emplid, a.effdt 
       """
       dups = hana_comparison.process_duplicates(hana_table,hana_select,hana_where_clause)

       if len(dups) > 0:
            #hana_comparison.fileName = hana_table + "_DuplicatesHana"
            fileDUPS = NameGenerator("C:\python\ReportValidationHana","PsNamesDuplicates")
            hana_comparison.write_to_text_file(fileDUPS, delimiter="|")
       else:
            print(f"No Duplicates found in table '{hana_table}'.")
        
       # Table details
       hana_table = "v_ehrp.v_ps_names"
       virtual_table = "ehrp.ps_names"
       # Dynamic WHERE clauses
       hana_where_clause = f"""
            b.effdt = a.effdt
       """
       #hana_comparison.fileName = "PsNamesOracleValidation"
       fileOracle = NameGenerator("C:\python\ReportValidationHana","PsNamesOracleValidation")
       #hana_comparison.process_tables(hana_table,virtual_table,hana_where_clause)
    
    finally:
        hana_conn.close()
    
    # Oracle connection details
    oracle_config = {
        "username":"histdba",
        "password":"unclefnk",
        "hostName":"158.71.213.17",
        "port":"16821",
        "service_name":"PSFTEHCM"
    }

    OracleTargetTable = "skipped_ps_names_recs"
    schema = 'histdba'
       
    oracle_conn = OracleDatabase(**oracle_config)
    try:
        oracle_conn.connect()
        if oracle_conn.validate_connection():
            print("Oracle database connection is valid.")
        else:
            print("Oracle database connection is not valid.")
        
        # Get metadata from Oracle
        oracle_columns = get_oracle_metadata(oracle_conn, OracleTargetTable, schema)    

        # Read values from the file
        #current_date = datetime.today().strftime("%Y-%m-%d")
        #hana_comparison.fileName = os.path.join(hana_comparison.output_directory, f"{fileName}_{current_date}.txt")

        values = hana_comparison.read_file(fileSAP.getName())
        if not values:
            print("No values found in the file.")

    finally:
        # Close connections
        oracle_conn.close()

if __name__ == "__main__":
    main()
