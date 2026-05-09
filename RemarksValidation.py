import os
import sys
import re
from hdbcli import dbapi
from datetime import datetime
from Connection_Module import *

class HanaComparisonNotExistsDynamicWhere:
    def __init__(self, fileName, output_directory, connection):
        """
        Initialize the HanaComparisonNotExistsDynamicWhere class.
        """
        self.fileName = fileName
        self.output_directory = output_directory
        self.connection = connection
            
    def fetch_data(self, query):
        """Execute a query and fetch results."""
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()
            return rows
        except dbapi.Error as e:
            print(f"Error executing query: {e}")
            return None
    
    def check_count(self, table1, table2):
        """
        table1 (str): Name of the first table.
        table2 (str): Name of the second table.

        Returns:
            bool: True if row counts are equal, False otherwise.
        """
        with self.connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) FROM {table1}")
            count1 = cursor.fetchone()[0]

            cursor.execute(f"SELECT COUNT(*) FROM {table2}")
            count2 = cursor.fetchone()[0]

        if count1 == count2:
           return True
        else:
            return False
        
    def process_tables(self, hana_table, virtual_table, hana_where_clause):

        compareTable = HanaComparisonNotExistsDynamicWhere.check_count(hana_table,virtual_table)
        
        if compareTable == True:
            print(f"No Validation process for table '{hana_table}' needed.")
            return
        else:
            # Compare tables and get mismatched records
            mismatched_records = HanaComparisonNotExistsDynamicWhere.compare_tables(
                hana_table, virtual_table, hana_where_clause
            )
            HanaComparisonNotExistsDynamicWhere.write_to_text_file(mismatched_records, delimiter="|")
   
    def process_duplicates(self, hana_table, hana_where_clause):
        """
        Find Duplicates in the HANA Table 
        """
        query = f"""
        select a.emplid, a.empl_rcd, a.effdt, a.effseq, a.GVT_SF50_REMARK, COUNT(*)
        from {hana_table}  a 
        {hana_where_clause}
        HAVING COUNT(*) > 1
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            data = cursor.fetchall()
            cursor.close()
            return data
        except dbapi.Error as err:
            print(f"Error executing query: {err}")
            raise

    def compare_tables(self, hana_table, virtual_table, hana_where_clause):
        """
        Compare a HANA table and a virtual table to find records not in the HANA table using NOT EXISTS.

        :param hana_table: Name of the HANA table.
        :param virtual_table: Name of the virtual table.
        :param hana_where_clause: Dynamic WHERE clause for the HANA table.
        :return: List of tuples containing mismatched records.
        """
        query = f"""
        select a.emplid, a.empl_rcd, a.effdt, 
        a.effseq, A.GVT_SF50_REMARK
        from {virtual_table} a 
        where not exists (select b.emplid, b.empl_rcd, b.effdt, b.effseq, b.GVT_SF50_REMARK
                          from {hana_table} b
                          WHERE b.emplid = a.emplid and 
                          {hana_where_clause}
        )
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(query)
            data = cursor.fetchall()
            cursor.close()
            return data
        except dbapi.Error as err:
            print(f"Error executing query: {err}")
            raise

    def write_to_text_file(self, data, delimiter="|"):
        """
        Write the comparison results to a text file with a specified delimiter.

        :param data: List of tuples containing mismatched records.
        :param filename: Name of the text file to save results.
        :param delimiter: Delimiter to separate fields in the output file (default: pipe '|').
        """
        
         # Output file
        # Generate filename with the current date
        current_date = datetime.today().strftime("%Y-%m-%d")
        self.fileName = os.path.join(self.output_directory, f"{self.fileName}_{current_date}.txt")
        
        with open(self.fileName, 'w') as file:
            for row in data:
                file.write(delimiter.join(map(str, row)) + "\n")
        print(f"Results written to '{self.fileName}' successfully.")

    def read_file(file_path):
        """Read composite key values from a text file."""
        with open(file_path, "r") as file:
            # Assuming each line contains values separated by a pipe (where clause field)
            values = [tuple(line.strip().split("|")) for line in file if line.strip()]
        return values

    def clean_string(value):
        """Remove unwanted characters from a string."""
        return re.sub(r"[^a-zA-Z0-9\s\-\_\,\.\:\;\?\\\/\u0080-\u024F\p{L}]", "", value)  # Keep alphanumeric, spaces, and hyphens, under score

    def insert_into_oracle_table(conn, values, tableName):
        """Insert cleaned data into an Oracle table."""
        try:
            cursor = conn.cursor()

            # Prepare the insert statement
            query = """
            INSERT INTO {tableName} (EMPLID, EMPL_RCD, TO_DATE(EFFDT,'YYYY-MM-DD'), EFFSEQ, GVT_SF50_REMARK, GVT_INSERT_REQD, 
            GVT_REMARK_LINE1, GVT_REMARK_LINE2, GVT_REMARK_LINE3, GVT_REMARK_LINE4, GVT_REMARK_LINE5, 
            GVT_REMARK_LINE6, GVT_REMARK_LINE7, GVT_REMARK_LINE8, GVT_REMARK_LINE9)
            VALUES (:EMPLID, :EMPL_RCD, :EFFDT, :EFFSEQ, :GVT_SF50_REMARK, :GVT_INSERT_REQD, 
            :GVT_REMARK_LINE1, :GVT_REMARK_LINE2, :GVT_REMARK_LINE3, :GVT_REMARK_LINE4, :GVT_REMARK_LINE5, 
            :GVT_REMARK_LINE6, :GVT_REMARK_LINE7, :GVT_REMARK_LINE8, :GVT_REMARK_LINE9)
            """

            # Clean and insert each row
            for row in values:
                EMPLID_val = row[0]
                EMPL_RCD_val = row[1]
                EFFDT_val = row[2]
                GVT_SF50_REMARK_val = row[3]
                GVT_INSERT_REQD_val = row[4]
                GVT_REMARK_LINE1_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[5])
                GVT_REMARK_LINE2_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[6])
                GVT_REMARK_LINE3_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[7])
                GVT_REMARK_LINE4_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[8])
                GVT_REMARK_LINE5_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[9])
                GVT_REMARK_LINE6_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[10])
                GVT_REMARK_LINE7_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[11])
                GVT_REMARK_LINE8_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[12])
                GVT_REMARK_LINE9_val = HanaComparisonNotExistsDynamicWhere.clean_string(row[13])

            cursor.execute(query, {"EMPLID": EMPLID_val, "EMPL_RCD": EMPL_RCD_val, "EFFDT": EFFDT_val, "GVT_SF50_REMARK": GVT_SF50_REMARK_val,
                                   "GVT_INSERT_REQD": GVT_INSERT_REQD_val, "GVT_REMARK_LINE1": GVT_REMARK_LINE1_val,
                                   "GVT_REMARK_LINE2": GVT_REMARK_LINE2_val, "GVT_REMARK_LINE3": GVT_REMARK_LINE3_val,
                                   "GVT_REMARK_LINE4": GVT_REMARK_LINE4_val, "GVT_REMARK_LINE5": GVT_REMARK_LINE5_val,
                                   "GVT_REMARK_LINE6": GVT_REMARK_LINE6_val, "GVT_REMARK_LINE7": GVT_REMARK_LINE7_val,
                                   "GVT_REMARK_LINE8": GVT_REMARK_LINE8_val, "GVT_REMARK_LINE9": GVT_REMARK_LINE9_val})

            # Commit the transaction
            conn.commit()
            print(f"Inserted {len(values)} records into the table.")
        except cx_Oracle.DatabaseError as e:
            print(f"Database error: {e}")
        finally:
            # Close the connection
            if cursor:
                cursor.close()
            if  conn.connection:
                conn.close()

    def main():
        # SAP HANA connection details
        hana_config = {
            "username":"HHSBATCH",
            "password":"Poseidon@2021",
            "hostName":"4.16.73.11",
            "port":30041
        }

        # Oracle connection details
        oracle_config = {
            "oracle_host":'158.71.213.17',
            "oracle_port":'16821',
            "oracle_service_name":'PSFTEHCM',
            "oracle_user":'histdba',
            "oracle_password":'unclefnk'
        }
    
        hana_conn = SAPHANADatabase(**hana_config)
        output_directory = "C:\python\ReportValidationHana"  # Directory to save the output file from original logic
        fileName = "RemarksHanaValidation"

        # Table details
        hana_table = "ehrp.ps_gvt_par_remarks"
        virtual_table = "v_ehrp.v_ps_gvt_par_remarks"

        # Dynamic WHERE clauses
        hana_where_clause = f"""
            b.empl_rcd = a.empl_rcd and
            b.effdt = a.effdt and 
            b.effseq = a.effseq AND
            B.GVT_SF50_REMARK = A.GVT_SF50_REMARK 
         """
        try:
            connection = hana_conn.connect()
            hana_comparison = HanaComparisonNotExistsDynamicWhere(fileName, output_directory, connection)
            hana_comparison.process_tables(hana_table,virtual_table,hana_where_clause)
        
            # Read values from the file
            values = hana_comparison.read_file(hana_comparison.fileName)
            if not values:
                print("No values found in the file.")
        
            # Build the dynamic query
            query = """
                SELECT *
                FROM {hana_table}
                WHERE (emplid, empl_rcd, effdt, effseq, gvt_sf50_remark) IN (
            """ + ",".join([f"(:emplid{i}, :empl_rcd{i}, :effdt{i}, :effseq{i}, :gvt_sf50_remark{i})" for i in range(len(values))]) + """
            )
            """

            # Prepare parameters for the query
            params = {}
            for i, (emplid_val, empl_rcd_val, effdt_val, effseq_val, gvt_sf50_remark_val) in enumerate(values):
                params[f"emplid{i}"] = emplid_val
                params[f"empl_rcd{i}"] = empl_rcd_val
                params[f"effdt{i}"] = effdt_val
                params[f"effseq{i}"] = effseq_val
                params[f"gvt_sf50_remark{i}"] = gvt_sf50_remark_val
        
            # Connect to Oracle
            oracle_conn = OracleDatabase(**oracle_config)
        
            # Query the Oracle table
            rows = oracle_conn.execute_query(query, params=params)
            hana_comparison.insert_into_oracle_table(oracle_conn, rows, hana_table)
        
            ###### end params process hana missing rows. 

            #check for HANA Dups rows 
            # Dynamic WHERE clauses
            hana_where_clause = f"""
                GROUP BY a.emplid, a.empl_rcd, a.effdt, a.effseq, A.GVT_SF50_REMARK 
            """
            dups = hana_comparison.process_duplicates(hana_table,hana_where_clause)

            if len(dups) > 0:
                hana_comparison.fileName = "DuplicatesHana"
                hana_comparison.write_to_text_file(dups, delimiter="|")
            else:
                print(f"No Duplicates found in table '{hana_table}'.")
        
            # Table details
            hana_table = "v_ehrp.v_ps_gvt_par_remarks"
            virtual_table = "ehrp.ps_gvt_par_remarks"

            # Dynamic WHERE clauses
            hana_where_clause = f"""
            b.empl_rcd = a.empl_rcd and
            b.effdt = a.effdt and 
            b.effseq = a.effseq AND
            B.GVT_SF50_REMARK = A.GVT_SF50_REMARK 
            """
            hana_comparison.fileName = "RemarksOracleValidation"
            hana_comparison.process_tables(hana_table,virtual_table,hana_where_clause)

        ###########################################################################
            # Table details
            hana_table = "EHRP.PS_GVT_PERS_DATA"
            virtual_table = "V_EHRP.V_PS_GVT_PERS_DATA"

            # Dynamic WHERE clauses
            hana_where_clause = f"""
                b.empl_rcd = a.empl_rcd and
                b.effdt = a.effdt and 
                b.effseq = a.effseq 
            """
            hana_comparison.fileName = "PersDataValidation"
            hana_comparison.process_tables(hana_table,virtual_table,hana_where_clause)
        finally:
            hana_conn.close()

# Example Usage
    if __name__ == "__main__":
        main()
    