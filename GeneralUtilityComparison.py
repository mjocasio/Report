from datetime import datetime, timedelta
import io
import sys
import logging
logging.basicConfig(
    level=logging.INFO,   # change to DEBUG for more detail
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
from NameGenerator import *
from CSVHandler import *
from Connection_Module import *
from SQLQueryBuilder import *  # noqa: F403
from RetrieveOracleRecords import RetrieveOracleRecords
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

class GeneralUtilityComparison:
    def __init__(self, fileName, output_directory, hana_config, oracle_config, skipped_schema, skipped_table):
        """
        Initialize the GeneralUtilityComparison class.
        """
        self.fileSAP = fileName
        self.output_directory = output_directory
        self.hana_config = hana_config
        self.oracle_config = oracle_config
        self.skipped_schema = skipped_schema
        self.skipped_table = skipped_table
        self.hana_table = ""
        self.virtual_table = ""
        self.hana_select = ""
        self.hana_where_clause = ""
        self.hana_dup_where_clause = ""
        self.hana_conn = SAPHANADatabase(**self.hana_config)
        self.oracle_conn = OracleDatabase(**self.oracle_config)
        
    def check_count(self):
        """
        table1 (str): Name of the first table.
        table2 (str): Name of the second table.
        Returns:
            bool: True if row counts are equal, False otherwise.
        """
        connection = self.hana_conn.connect()

        OracleTable = f"SELECT COUNT(*) FROM {self.virtual_table}"
        HanaTable = f"SELECT COUNT(*) FROM {self.hana_table}"

        count1 = self.hana_conn.query_one(OracleTable)
        count2 = self.hana_conn.query_one(HanaTable)
        
        if count1 - count2 == 0:
           return 0
        elif count1 < count2:
            return count1 - count2
        elif count1 > count2:
            return  count1 - count2
    
    def process_tables(self, hana_table, virtual_table):
        self.hana_table = hana_table
        self.virtual_table = virtual_table

        RetrieveOracleRecords_config = {
            "fileName":self.fileSAP,
            "location":self.output_directory,
            "oracle_config":self.oracle_config,
            "source_table":self.hana_table.split(".")[1],
            "source_schema":self.hana_table.split(".")[0],
            "target_table":self.skipped_table,
            "target_schema":self.skipped_schema
        }

        if hana_table.lower() == "ehrp.ps_gvt_par_remarks":
            self.hana_select = "emplid, empl_rcd, effdt, effseq, gvt_sf50_remark"
            
            # Dynamic WHERE clauses
            self.hana_where_clause = "b.emplid = a.emplid and \
                b.empl_rcd = a.empl_rcd and \
                b.effseq = a.effseq AND \
                b.GVT_SF50_REMARK = A.GVT_SF50_REMARK"
            
            #check for HANA Dups rows 
            self.hana_dup_where_clause = "a.emplid, a.empl_rcd, a.effdt, a.effseq, a.gvt_sf50_remark"
        elif hana_table.lower() == "ehrp.ps_gvt_employment" or \
             hana_table.lower() == "ehrp.ps_gvt_pers_data" or \
             hana_table.lower() == "ehrp.ps_gvt_job":                        
             self.hana_select = "emplid, empl_rcd, effdt, effseq"
            
             # Dynamic WHERE clauses
             self.hana_where_clause = "b.emplid = a.emplid and \
             b.empl_rcd = a.empl_rcd and \
             b.effseq = a.effseq"
            
             #check for HANA Dups rows 
             self.hana_dup_where_clause = "a.emplid, a.empl_rcd, a.effdt, a.effseq"
        elif hana_table.lower() == "ehrp.ps_names":           
             self.hana_select = "emplid, effdt"
             self.hana_where_clause = "b.emplid = a.emplid"
            
             #check for HANA Dups rows
             self.hana_dup_where_clause = "a.emplid, a.effdt"
        elif hana_table.lower() == "ehrp.ps_addresses":
             self.hana_select = "emplid, effdt, address_type, eff_status"
            
             # Dynamic WHERE clauses
             self.hana_where_clause = "b.emplid = a.emplid and \
                b.address_type = a.address_type and \
                b.eff_status = a.eff_status"
            
             #check for HANA Dups rows
             self.hana_dup_where_clause = "a.emplid, a.effdt, a.address_type, a.eff_status"
        elif hana_table.lower() == "ehrp.ps_personal_data":
             self.hana_select = "emplid"
            
             # Dynamic WHERE clauses
             self.hana_where_clause = "b.emplid = a.emplid"
            
             # #check for HANA Dups rows
             self.hana_dup_where_clause = "a.emplid"
        elif hana_table.lower() == "ehrp.ps_position_data_new" :
             self.hana_select = "position_nbr,effdt"
            
             # Dynamic WHERE clauses
             self.hana_where_clause = "b.position_nbr = a.position_nbr"
            
             # #check for HANA Dups rows
             self.hana_dup_where_clause = "a.position_nbr, a.effdt"
        elif hana_table.lower() == "ehrp.ps_jpm_jp_items":
             self.hana_select = "Jpm_Profile_Id, JPM_CAT_TYPE, \
                 jpm_item_key_id, JPM_CAT_ITEM_ID, \
                 TO_VARCHAR(EFFDT, 'YYYY-MM-DD')"
            
             # Dynamic WHERE clauses
             self.hana_where_clause = "B.Jpm_Profile_Id = A.Jpm_Profile_Id  AND \
                 B.JPM_CAT_TYPE = A.JPM_CAT_TYPE AND \
                 B.JPM_CAT_ITEM_ID = A.JPM_CAT_ITEM_ID"
            
             # #check for HANA Dups rows
             self.hana_dup_where_clause = "a.Jpm_Profile_Id, a.JPM_CAT_TYPE, \
                 a.JPM_CAT_ITEM_ID, TO_VARCHAR(A.EFFDT, 'YYYY-MM-DD') EFFDT"
        elif hana_table.lower() == "ehrp.ps_jobcode_tbl_new":
             self.hana_select = "SETID, JOBCODE, EFFDT, EFF_STATUS"
            
             # Dynamic WHERE clauses
             self.hana_where_clause = "B.setid = A.setid  AND \
                 B.jobcode = A.jobcode AND \
                 B.effdt = A.effdt AND \
                 B.eff_status = A.eff_status"
            
             # #check for HANA Dups rows
             self.hana_dup_where_clause = "a.SETID, a.JOBCODE, a.EFFDT, a.EFF_STATUS"
            
        compareTable = GeneralUtilityComparison.check_count(self)
        
        #procedureName = "GET_MISSING_ROWS"
        procedureName = "dynamic_comparison_date_adjustment"
        
        if compareTable == 0:
            logging.info(f"No validation process for table '{hana_table}' needed.")
            return 0
        elif compareTable > 0:
            try:
              # call stored procedure 
              headers, mismatched_records = self.hana_conn.execute_proc_compare(procedureName, self.virtual_table, self.hana_table, self.hana_select, self.hana_where_clause, compareTable)
            except Exception as e:
                logging.error(f"Error executing stored procedure: {e}")
            
            if len(mismatched_records) > 0:
                recordsHanaMissing = CSVHandler(self.fileSAP)
                recordsHanaMissing.write_to_text_file(headers,mismatched_records, delimiter=",")
                setProcesRecords = RetrieveOracleRecords(**RetrieveOracleRecords_config)
                try:
                  setProcesRecords.setConnection()
                  # where_clauses = setProcesRecords.ProcessData()
                  #replace with Process_data which uses the bulk insert last revision 3/17/2026
                  where_clauses = setProcesRecords.process_data()
                except Exception as e: 
                  safe_error = str(e).encode('utf-8', errors='replace').decode('utf-8')
                  logging.error(f"Error processing Oracle records: {safe_error}")
                  exit(1)

                self.copy_to_hana(where_clauses)
        elif compareTable < 0:
            headers, dups = GeneralUtilityComparison.process_duplicates(self)

            if len(dups) > 0:
                fileDUPS = NameGenerator(r"C:\python\ReportValidationHana\log",self.hana_table + "_duplicates")
                RecordsDups = CSVHandler(fileDUPS.getName()) 
                
                try:
                    RecordsDups.write_dups_text_file(headers[:-1], dups)
                    setProcesRecords = RetrieveOracleRecords(**RetrieveOracleRecords_config)
                    setProcesRecords.setConnection()
                    where_clauses = setProcesRecords.DeleteRecords(fileDUPS.fileName, self.skipped_schema, self.skipped_table)
                    GeneralUtilityComparison.delete_from_hana(self, where_clauses)
                    self.skipped_schema = self.hana_table.split(".")[0]
                    self.skipped_table = self.hana_table.split(".")[1]
                    self.copy_to_hana(where_clauses)
                except Exception as e: 
                    logging.error(f"Error processing duplicates: {e}")  
                    exit()            
            else:
                logging.info(f"No duplicates found in table '{self.hana_table}'.")

            # Compare tables and get mismatched records from records missing in HANA but not in Oracle
            # with source and target compare tables

            self.hana_table, self.virtual_table =  self.virtual_table, self.hana_table
            self.fileName = self.hana_table
            
            headers, mismatched_records = self.hana_conn.execute_proc_compare(procedureName, self.virtual_table, self.hana_table, self.hana_select, self.hana_where_clause, abs(compareTable))
            
            if len(mismatched_records) > 0:
                fileORA = NameGenerator(r"C:\python\ReportValidationHana\log",self.fileName)
                RecordsOracleMissing = CSVHandler(fileORA.getName())
                RecordsOracleMissing.write_to_text_file(headers,mismatched_records, delimiter=",")
                setProcesRecords = RetrieveOracleRecords(**RetrieveOracleRecords_config)
                try:
                  setProcesRecords.setConnection()
                  where_clauses = setProcesRecords.DeleteRecords(fileORA.fileName, self.skipped_schema, self.skipped_table)
                  self.virtual_table, self.hana_table = self.hana_table, self.virtual_table
            
                  GeneralUtilityComparison.delete_from_hana(self, where_clauses)
                except Exception as e: 
                  logging.error(f"Error deleting Oracle missing records: {e}")

    def compare_tables(self):
        """
        Compare a HANA table and a virtual table to find records not in the HANA table using NOT EXISTS.
        :param hana_table: Name of the HANA table.
        :param virtual_table: Name of the virtual table.
        :hana_select: Select from Hana Table
        :param hana_where_clause: Dynamic WHERE clause for the HANA table.
        :return: List of tuples containing mismatched records.
        """

        if self.hana_table.lower() != "ehrp.ps_personal_data":
            query = f"""
                select {self.hana_select}
                from {self.virtual_table} a 
                where not exists (select 1
                                  from {self.hana_table} b
                                  WHERE {self.hana_where_clause})
                AND a.effdt BETWEEN TO_DATE('{self.start_date}', 'YYYY-MM-DD') AND 
                                    TO_DATE('{self.end_date}', 'YYYY-MM-DD')
            """
        else:
            query = f"""
                select {self.hana_select}
                from {self.virtual_table} a 
                where not exists (select 1
                                  from {self.hana_table} b
                                  WHERE {self.hana_where_clause})
            """

        try:
            return self.hana_conn.query_data(query)
        finally:
            self.hana_conn.close()

    def copy_to_hana_legacy(self, where_clauses):
        """
        Copy to HANA table the record(s) saved in skipp table.

        :param hana_table: Name of the HANA table.
        :param virtual_table: Name of the virtual table.
        :param where_clauses: Dynamic WHERE clause for the insert in HANA table.
        """
        virtualSchema = "v_" + self.skipped_schema
        virtualTable = "v_" + self.skipped_table
        fileHANA = NameGenerator(r"C:\python\ReportValidationHana\log",virtualTable + "_generated_sql")
        script_generator = CSVHandler(fileHANA.getName())
    
        try:
            for where_clause in where_clauses:
                # Step 1: Construct the dynamic FROM and INSERT statementSELECT count(*) FROM v_eh
                from_query = f"SELECT * FROM {virtualSchema}.{virtualTable}"
                insert_query = f"INSERT INTO {self.hana_table} {from_query} WHERE {where_clause}"
                script_generator.write_to_file(insert_query)
                self.hana_conn.execute_sql(insert_query)
            logging.info(f"SQL script copies data to HANA.")
        except Exception as e:
            logging.error(f"An error occurred coppying to HANA: {e}")

    def copy_to_hana(self, where_clauses):
        """
            Copy records from virtual table to HANA target table using WHERE clauses.
            Uses batching for performance and better error handling.
        """

        if not where_clauses:
            logging.warning("No WHERE clauses provided. Skipping copy_to_hana.")
            return

        virtual_schema = f"v_{self.skipped_schema}"
        virtual_table = f"v_{self.skipped_table}"

        fileHANA = NameGenerator(
            r"C:\python\ReportValidationHana\log",
            f"{virtual_table}_generated_sql"
        )

        script_generator = CSVHandler(fileHANA.getName())
        total_success = 0
        total_failed = 0

        # -----------------------------------
        # BATCH CONFIG (tune this if needed)
        # -----------------------------------
        BATCH_SIZE = 100

        for i in range(0, len(where_clauses), BATCH_SIZE):
            batch = where_clauses[i:i + BATCH_SIZE]
            batch_id = i // BATCH_SIZE + 1

            combined_where = " OR ".join([f"({wc})" for wc in batch])

            insert_query = f"""
                INSERT INTO {self.hana_table}
                SELECT *
                FROM {virtual_schema}.{virtual_table}
                WHERE {combined_where}
            """.strip()

            try:
                # Log batch info for debugging
                #script_generator.write_to_file(f"\n--- BATCH #{batch_id} ---\n")
                #script_generator.write_to_file(insert_query)

                rows_affected = self.hana_conn.execute_sql(insert_query)

                total_success += rows_affected or 0

                logging.info(
                    f"Batch #{batch_id} inserted rows: {rows_affected or 0}"
                )

            except Exception as e:
                logging.error(f"Batch #{batch_id} failed: {e}")
                total_failed += len(batch)
                script_generator.write_to_file(
                    f"\n-- FAILED BATCH #{batch_id} --\nERROR: {e}\n"
                )

                # -----------------------------------
                # FALLBACK: row-by-row execution
                # -----------------------------------
                for idx, where_clause in enumerate(batch, start=1):
                    single_query = f"""
                        INSERT INTO {self.hana_table}
                        SELECT *
                        FROM {virtual_schema}.{virtual_table}
                        WHERE {where_clause}
                    """.strip()

                    try:
                        self.hana_conn.execute_sql(single_query)
                        logging.info(f"Recovered WHERE #{idx} in batch #{batch_id}")
                        total_success += 1
                    except Exception as row_error:
                        total_failed += 1

                        logging.error(
                            f"Row failed in batch #{batch_id}: {row_error}"
                        )
                        script_generator.write_to_file(
                            f"Row failed in batch #{batch_id}: {row_error}\n"
                        )
                        script_generator.write_to_file(
                            f"FAILED WHERE: {where_clause}\nERROR: {row_error}\n"
                        )
        logging.info(
            f"Copy to HANA completed. Success: {total_success}, Failed: {total_failed}"
        )
    
    def delete_from_hana_legacy(self, where_clauses):
        """
        Delete from HANA table the record(s) not in Oracle table.
        :param hana_table: Name of the HANA table.
        :param hana_where_clause: Dynamic WHERE clause for the HANA table.
        """

        fileHANA = NameGenerator(r"C:\python\ReportValidationHana\log","DELETE_" + self.hana_table)
        RecordsHANADelete = CSVHandler(fileHANA.getName())
        
        # Create a SQL Delete statement 
        query_builder = SQLQueryBuilder(self.hana_table.split('.')[0],self.hana_table.split('.')[1])

        for where_clause in where_clauses:
            delete_query = query_builder.generate_delete_statement(self.hana_table, where_clause)
            
            try:
                RecordsHANADelete.write_to_file(delete_query)
                self.hana_conn.execute_sql(delete_query)
            except dbapi.Error as err:
                logging.error(f"Error executing query: {err}")
                
        logging.info(f"SQL scripts delete data from HANA {self.hana_table}.")    

    def delete_from_hana(self, where_clauses):
        """
            Delete records from HANA table using dynamic WHERE clauses.
        """

        if not where_clauses:
            logging.warning("No WHERE clauses provided. Skipping delete_from_hana.")
            return

        fileHANA = NameGenerator(
            r"C:\python\ReportValidationHana\log",
            f"DELETE_{self.hana_table}"
        )

        script_generator = CSVHandler(fileHANA.getName())
        total_success = 0
        total_failed = 0

        # -----------------------------------
        # BATCH CONFIG
        # -----------------------------------
        BATCH_SIZE = 500

        for i in range(0, len(where_clauses), BATCH_SIZE):
            batch = where_clauses[i:i + BATCH_SIZE]
            batch_id = i // BATCH_SIZE + 1

            combined_where = " OR ".join([f"({wc})" for wc in batch])

            delete_query = f"""
                DELETE FROM {self.hana_table}
                WHERE {combined_where}
            """.strip()

            try:
                # Log batch SQL for debugging 
                #script_generator.write_to_file(f"\n--- DELETE BATCH #{batch_id} ---\n")
                #script_generator.write_to_file(delete_query)

                rows_affected = self.hana_conn.execute_sql(delete_query)

                total_success += rows_affected or 0

                logging.info(
                    f"Batch #{batch_id} deleted rows: {rows_affected or 0}"
                )

            except Exception as e:
                logging.error(f"Batch #{batch_id} delete failed: {e}")
                total_failed += len(batch)

                script_generator.write_to_file(
                    f"\n-- FAILED DELETE BATCH #{batch_id} --\nERROR: {e}\n"
                )

                # -----------------------------------
                # FALLBACK: row-by-row delete
                # -----------------------------------
                for idx, where_clause in enumerate(batch, start=1):
                    single_delete = f"""
                        DELETE FROM {self.hana_table}
                        WHERE {where_clause}
                    """.strip()

                    try:
                        self.hana_conn.execute_sql(single_delete)
                        total_success += 1

                        logging.info(
                            f"Recovered DELETE WHERE #{idx} in batch #{batch_id}"
                        )

                    except Exception as row_error:
                        total_failed += 1

                        logging.error(
                            f"Delete failed in row #{idx}: {row_error}"
                        )
                        
                        script_generator.write_to_file(
                            f"Delete failed in row #{idx}\nERROR: {row_error}\n"
                        )

                        script_generator.write_to_file(
                            f"FAILED WHERE: {single_delete}\nERROR: {row_error}\n"
                        )
        logging.info(
            f"Delete from HANA completed. Success: {total_success}, Failed: {total_failed}"
        )

    def process_duplicates(self):
        """
        Find Duplicates in the HANA Table
        :param hana_table: Name of table to find duplicates.
        :param select_hana: Select statement to query for dups.
        """

        query = f"""
            select {self.hana_select}, COUNT(*)
            from {self.hana_table}  a 
            group by {self.hana_dup_where_clause}
            HAVING COUNT(*) > 1
        """
        
        try:
            return self.hana_conn.query_data(query)
        except dbapi.Error as err:
            logging.error(f"Error executing query: {err}")
    