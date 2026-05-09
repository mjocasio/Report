from GeneralUtilityComparison import *
from Connection_Module import *
from NameGenerator import *
from CSVHandler import *
from SQLQueryBuilder import *
from DataCleaner import *
import logging
logging.basicConfig(
    level=logging.INFO,   # change to DEBUG for more detail
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)

class RetrieveOracleRecords:
    def __init__(self, fileName, location, oracle_config, source_table, source_schema, target_table, target_schema):
        """
        Initialize connection parameters for Oracle and SAP HANA.
        """
        self.oracle_config = oracle_config
        self.fileName = fileName
        self.location = location
        self.SourceTable = source_table
        self.SourceSchema = source_schema
        self.TargetTable = target_table
        self.TargetSchema = target_schema
        self.oracle_connection = ""

    def get_nvl_placeholder(self, col, index, col_types):
        """Returns NVL wrapped placeholder based on Oracle column type"""
        placeholder = ":" + str(index + 1)
        col_upper   = col.strip().upper()
        col_info    = col_types.get(col_upper)

        if col_info is None:
            return placeholder

        data_type, nullable = col_info

        if nullable == 'Y':
            return placeholder

        if data_type in ('VARCHAR2', 'CHAR', 'NVARCHAR2', 'NCHAR'):
            return f"NVL({placeholder}, ' ')"

        elif data_type in ('NUMBER', 'INTEGER', 'FLOAT', 'BINARY_FLOAT', 'BINARY_DOUBLE'):
            return f"NVL({placeholder}, 0)"

        elif data_type in ('DATE', 'TIMESTAMP'):
            return f"NVL({placeholder}, TO_DATE('1900-01-01','YYYY-MM-DD'))"

        else:
            return placeholder

    def ProcessDataLegacy(self):
        fileSQL = NameGenerator(r"C:\python\ReportValidationHana\log",self.SourceTable + "_generated_sql")
        script_generator = CSVHandler(fileSQL.getName())
        query_builder = SQLQueryBuilder(self.SourceSchema, self.SourceTable)

        # Get table columns dynamically
        columns, col_types = self.oracle_connection.get_oracle_metadata(self.SourceSchema,self.SourceTable)
    
        # Step 2: Read WHERE clause values from the file
        readFile = CSVHandler(self.fileName)

        try:
            where_keys = readFile.read_dict()
        except Exception as e:
            logging.error(f"Error file format dict: {e}") 
            raise

        # WHERE clause construction from the input keys (like emplid, emplid_rec, etc.)
        try:
            where_clauses = query_builder.build_where_clause(where_keys)
        except Exception as e:
            logging.error(f"Error reading input file: {e}")
            raise

        for where_clause in where_clauses:
            # Generate the SELECT and INSERT SELECT queries
            select_query = query_builder.generate_select_statement_norowid(columns, where_clause)
            select_query_rowid = query_builder.generate_select_statement(columns, where_clause)
            insert_select_query = query_builder.generate_insert_select_statement(self.TargetSchema, self.TargetTable, columns, where_clause)

            # Write the queries to the SQL file
            script_generator.write_to_file(select_query_rowid)
            script_generator.write_to_file(insert_select_query)
    
            # Execute the SELECT query to retrieve data 
            results = self.oracle_connection.execute_statement(select_query)
    
            # Optionally write the raw data to the SQL file for testing 
            script_generator.write_query_results(results)

            # Clean the results before inserting into the target table
            cleaned_results = [DataCleaner.clean_row(result, columns) for result in results]

            # Step 2: Construct the dynamic INSERT statement
            column_names = ", ".join(columns)
            #placeholders = ", ".join([":" + str(i+1) for i in range(len(columns))])

            nvl_placeholders = ", ".join([
                self.get_nvl_placeholder(col, i, col_types) 
                for i, col in enumerate(columns)
            ])

            insert_query = (
                f"INSERT INTO {self.TargetSchema}.{self.TargetTable} "
                f"({column_names}) "
                f"VALUES ({nvl_placeholders})"
            )
            
            logging.debug(f"Insert query: {insert_query}")

            self.oracle_connection.execute_modify(insert_query,cleaned_results)

            # Optionally write the cleaned data to the SQL file
            script_generator.write_query_results(cleaned_results)
        return where_clauses

    def process_data(self):
        fileSQL = NameGenerator(r"C:\python\ReportValidationHana\log",self.SourceTable + "_generated_sql")

        script_generator = CSVHandler(fileSQL.getName())
        query_builder = SQLQueryBuilder(self.SourceSchema, self.SourceTable)

        # Get metadata
        columns, col_types = self.oracle_connection.get_oracle_metadata(
            self.SourceSchema,
            self.SourceTable
        )

        readFile = CSVHandler(self.fileName)

        try:
            where_keys = readFile.read_dict()
        except Exception as e:
            logging.error(f"Error reading input file: {e}")
            raise

        try:
            where_clauses = query_builder.build_where_clause(where_keys)
        except Exception as e:
            logging.error(f"Error building WHERE clauses: {e}")
            raise

        # -----------------------------------
        # Prepare INSERT statement ONCE
        # -----------------------------------

        column_names = ", ".join(columns)

        nvl_placeholders = ", ".join([
            self.get_nvl_placeholder(col, i, col_types)
            for i, col in enumerate(columns)
        ])

        insert_query = (
            f"INSERT INTO {self.TargetSchema}.{self.TargetTable} "
            f"({column_names}) VALUES ({nvl_placeholders})"
        )

        # -----------------------------------
        # Chunk buffer (prevents memory issues)
        # -----------------------------------

        BUFFER_LIMIT = 500
        buffer = []
        total_rows = 0
        failed_rows = 0

        for idx, where_clause in enumerate(where_clauses, start=1):
            logging.info(f"Processing WHERE clause #{idx}")
            
            #select_query = query_builder.generate_select_statement_norowid(columns,where_clause)
            select_query_rowid = query_builder.generate_select_statement(columns,where_clause)

            insert_select_query = query_builder.generate_insert_select_statement(
                self.TargetSchema,
                self.TargetTable,
                columns,
                where_clause)

            # Debug logging written to file 
            #script_generator.write_to_file(f"\n--- WHERE CLAUSE #{idx} ---\n")
            #script_generator.write_to_file(select_query_rowid)
            #script_generator.write_to_file(insert_select_query)

            # Fetch data
            try:
                results = self.oracle_connection.execute_statement(select_query_rowid)
            except Exception as e:
                logging.exception(f"SELECT failed for WHERE clause #{idx}")
                continue

            if not results:
                logging.info(f"No rows returned for WHERE clause #{idx}")
                continue

            # Write resuls of query to file to see garbled data in DEBUG
            #script_generator.write_query_results(results)

            # Transform data
            cleaned_results = []

            for row in results:
                rowid = row[0]          # first column = ROWID
                data = row[1:]          # rest = actual data

                try:
                    cleaned_row = DataCleaner.clean_row(data, columns)
                    cleaned_results.append((rowid, cleaned_row))
                except Exception:
                    logging.exception(f"Data cleaning failed for ROWID {rowid}")
                    failed_rows += 1
                    script_generator.write_to_file(f"ROWID={rowid} | CLEANING FAILED | DATA={data}")

            buffer.extend(cleaned_results)
            total_rows += len(cleaned_results)

            # -----------------------------------
            # Flush buffer when limit reached
            # -----------------------------------
            
            if len(buffer) >= BUFFER_LIMIT:
                logging.info(f"Flushing {len(buffer)} rows to database")
                rows_to_insert = [row for (_, row) in buffer]

                try:
                    self.oracle_connection.execute_bulk(insert_query, rows_to_insert)
                    buffer.clear()

                except Exception as e:
                    logging.error(f"Bulk insert failed, retrying row-by-row: {e}")
                    script_generator.write_to_file(f"\n-- FAILED ROWS FOR WHERE #{idx} --\n")

                    for rowid, row in buffer:
                        try:
                            self.oracle_connection.execute_bulk(insert_query, [row])
                        except Exception as row_error:
                            failed_rows += 1
                            logging.error(f"Row failed: ROWID={rowid} ERROR={row_error}")
                            script_generator.write_to_file(
                                f"ROWID={rowid} | ERROR={row_error} | DATA={row}")

                    buffer.clear()       

        # -----------------------------------
        # Final flush
        # -----------------------------------

        if buffer:
            logging.info(f"Final flush of {len(buffer)} rows")
            rows_to_insert = [row for (_, row) in buffer]

            try:
                self.oracle_connection.execute_bulk(insert_query, rows_to_insert)
            except Exception as e:
                    logging.error(f"Final bulk insert failed: {e}")

                    for rowid, row in buffer:
                        try:
                            self.oracle_connection.execute_bulk(insert_query, [row])
                        except Exception as row_error:
                            failed_rows += 1
                            script_generator.write_to_file(f"ROWID={rowid} | ERROR={row_error} | DATA={row}")

        # Optional logging
        # comment this out for performance issue , dumps eveything
        #script_generator.write_query_results(buffer)

        # -----------------------------------
        # SUMMARY
        # -----------------------------------
        logging.info(f"Total rows processed: {total_rows}")
        logging.info(f"Total failed rows: {failed_rows}")
        logging.info("SQL scripts generated, data transformed, and bulk inserted.")

        return where_clauses

    def setConnection(self) :
        self.oracle_connection = OracleDatabase(**self.oracle_config)
    
        try:
            self.oracle_connection.connect()
    
            if self.oracle_connection.validate_connection():
                logging.info("Oracle database connection is valid.")
            else:
                logging.info("Oracle database connection is not valid.")       
        except Exception as e: 
            logging.error(f"An error occurred: {e}")

    def DeleteRecordsLegacy(self, input, skipped_schema, skipped_table) :
        
        # Create ouput file
        fileSQL = NameGenerator(r"C:\python\ReportValidationHana\log",skipped_table + "_generated_sql")
        script_generator = CSVHandler(fileSQL.getName())
            
        # Create a SQL Delete statement 
        query_builder = SQLQueryBuilder(skipped_schema, skipped_table)

        # Step 2: Read WHERE clause values from the file    
        readFile = CSVHandler(input)
        
        try:
            where_keys = readFile.read_dict()
        except Exception as e:
            logging.error(f"An error occurred: {e}")
        
        # WHERE clause construction from the input keys (like emplid, emplid_rec, etc.)
        where_clauses = query_builder.build_where_clause(where_keys)

        for where_clause in where_clauses:
            # Step 1: Construct the dynamic DELETE statement
            delete_query = query_builder.generate_delete_statement(f"{skipped_schema}.{skipped_table}", where_clause)
            
            try:
                # Write the queries to the SQL file for debugging
                script_generator.write_to_file(delete_query)
                #delete from Oracle skipped table
                self.oracle_connection.execute_one(delete_query)
            except dbapi.Error as err:
                logging.error(f"Error executing query: {err}")
        logging.info(f"SQL scripts delete data from {skipped_table} table.")    
        return where_clauses
    
    def DeleteRecords(self, input, skipped_schema, skipped_table):

        # -----------------------------------
        # Setup
        # -----------------------------------
        fileSQL = NameGenerator(
            r"C:\python\ReportValidationHana\log",
            skipped_table + "_generated_sql"
        )

        script_generator = CSVHandler(fileSQL.getName())
        query_builder = SQLQueryBuilder(skipped_schema, skipped_table)

        readFile = CSVHandler(input)

        # -----------------------------------
        # Read input file
        # -----------------------------------
        try:
            where_keys = readFile.read_dict()
        except Exception as e:
            logging.error(f"Error reading input file: {e}")
            raise   # ✅ STOP — this is critical

        # -----------------------------------
        # Build WHERE clauses
        # -----------------------------------
        try:
            where_clauses = query_builder.build_where_clause(where_keys)
        except Exception as e:
            logging.error(f"Error building WHERE clauses: {e}")
            raise   # ✅ STOP — invalid input

        if not where_clauses:
            logging.warning("No WHERE clauses found. Skipping delete.")
            return []
        
        # -----------------------------------
        # Batch config
        # -----------------------------------
        BATCH_SIZE = 100
        total_deleted = 0
        total_failed = 0

        full_table_name = f"{skipped_schema}.{skipped_table}"

        # -----------------------------------
        # Process in batches
        # -----------------------------------
        for i in range(0, len(where_clauses), BATCH_SIZE):

            batch = where_clauses[i:i + BATCH_SIZE]
            batch_id = i // BATCH_SIZE + 1

            combined_where = " OR ".join([f"({wc})" for wc in batch])

            delete_query = f"""
                DELETE FROM {full_table_name}
                WHERE {combined_where}
            """.strip()

            try:
                rows_deleted = self.oracle_connection.execute_one(delete_query)
                total_deleted += rows_deleted or 0
                logging.info(f"Batch #{batch_id} deleted rows: {rows_deleted or 0}")
            except Exception as e:
                logging.error(f"Batch #{batch_id} delete failed: {e}")
                script_generator.write_to_file(f"\n-- FAILED BATCH #{batch_id} --\nERROR: {e}\n")
                total_failed += len(batch)

                # -----------------------------------
                # FALLBACK: row-by-row delete
                # -----------------------------------
                for idx, where_clause in enumerate(batch, start=1):
                    single_delete = query_builder.generate_delete_statement(
                        full_table_name,
                        where_clause
                    )

                    try:
                        self.oracle_connection.execute_sql(single_delete)
                        logging.info(
                            f"Recovered WHERE #{idx} in batch #{batch_id}"
                        )

                        total_deleted += 1
                    except Exception as row_error:
                        total_failed += 1
                        logging.error(
                            f"Row delete failed (row #{idx}): {row_error}"
                        )
                        script_generator.write_to_file(single_delete)

        # -----------------------------------
        # Summary
        # -----------------------------------
        logging.info(
            f"Delete completed. Deleted: {total_deleted}, Failed: {total_failed}"
        )
        return where_clauses