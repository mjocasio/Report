from GeneralUtilityComparison import *
from Connection_Module import *
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
    columns = [row[0] for row in cursor.fetchall()]
    cursor.close()
    return columns

def main():
    # SAP HANA connection details
    hana_config = {
        "username":"MOCASIO_ADMIN",
        "password":"XeroX23$",
        "hostName":"4.16.73.11",
        "port":30041
    }
    
    hana_conn = SAPHANADatabase(**hana_config)
    fileSAP = NameGenerator("C:\python\ReportValidationHana", "PsGvtPersDataHanaValidation")

    # Table details
    hana_table = "ehrp.ps_gvt_pers_data"
    virtual_table = "v_ehrp.v_ps_gvt_pers_data"

    hana_select = f"""
        a.emplid, a.empl_rcd, a.effdt, a.effseq
    """

    # Dynamic WHERE clauses
    hana_where_clause = f"""
        b.empl_rcd = a.empl_rcd and
        b.effdt = a.effdt and 
        b.effseq = a.effseq  
    """
    try:
        connection = hana_conn.connect()
        hana_comparison = GeneralUtilityComparison(fileSAP.getName(), fileSAP.getDirectory(), connection)
        #hana_comparison.process_tables(hana_table,virtual_table, hana_select, hana_where_clause)
        
        # Table details
       # hana_table = "v_ehrp.v_ps_gvt_pers_data"
       # virtual_table = "ehrp.ps_gvt_pers_data"
       # target_table = "SKIPPED_GVTPERSDATA_RECS"
       # schema = 'histdba'

      #  OracleFile = NameGenerator("C:\python\ReportValidationHana","PsGvtPersDataOracleValidation")
      #  hana_comparison.fileName = OracleFile.getName()
      #  hana_comparison.process_tables(hana_table,virtual_table, hana_select, hana_where_clause)
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

    OracleTargetTable = "SKIPPED_GVTPERSDATA_RECS"
    schema = 'histdba'
    SourceTable = "ehrp.ps_gvt_pers_data"
    SourceSchema = "ehrp"
    TargetTable = "Skipped_Gvtparremarks_Tbl"
    TargetSchema = 'histdba'

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
        values = hana_comparison.read_file(schema, SourceTable, fileSAP.getName())
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

        # Create SQL INSERT statement
        columns_str = ", ".join(oracle_columns)
        placeholders = ", ".join([":" + str(i + 1) for i in range(len(cleaned_values))])
        sql_query = f"INSERT INTO {schema}.{OracleTargetTable} ({columns_str}) VALUES ({placeholders})"
        
        cursor = oracle_conn.connection.cursor()
        # Insert cleaned rows
        cursor.executemany(sql_query, cleaned_values)

        # Commit the transaction
        #connection.commit()
        print(f"Inserted {cursor.rowcount} cleaned rows into {OracleTargetTable}.")

    except cx_Oracle.DatabaseError as e:
        print("Error occurred while inserting data:", str(e))
        connection.rollback()

    finally:
        # Close connections
        oracle_conn.close()

if __name__ == "__main__":
    main() 
