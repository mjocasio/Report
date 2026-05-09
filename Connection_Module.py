import sys
import cx_Oracle
from hdbcli import dbapi
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(
            stream=open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False)
        )
    ]
)

class OracleDatabase:
    def __init__(self, username, password, hostName, port, service_name):
        """
        Initialize Oracle connection parameters.
       
        :param user: Oracle username
        :param password: Oracle password
        :param host: Oracle database hostName
        :param port: Oracle database port
        :param service_name: Oracle service name
        """
        self.username = username
        self.password = password
        self.host = hostName
        self.port = port
        self.service_name = service_name
        self.connection = None

    def connect(self):
        """
        Establish a connection to the Oracle database.
        """
        try:
            # Create a DSN (Data Source Name)
            dsn = cx_Oracle.makedsn(self.host, self.port, service_name=self.service_name)
            logging.info(f"Connecting to Oracle database at {self.host}:{self.port}/{self.service_name}")
           
            # Establish connection
            self.connection = cx_Oracle.connect(user=self.username, password=self.password, dsn=dsn)
            logging.info("Connection to Oracle database successful.")
            return self.connection
       
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            logging.error(f"Failed to connect to Oracle database. Error: {error.message}")
            raise

    def validate_connection(self):
        """
        Validate the connection by executing a simple query.
       
        :return: True if the connection is valid, False otherwise.
        """
        if not self.connection:
            logging.error("No active connection to validate.")
            return False

        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM DUAL")
                result = cursor.fetchone()
                if result and result[0] == 1:
                    logging.info("Connection validation successful.")
                    return True
        except cx_Oracle.Error as e:
            logging.error(f"Error while validating connection: {e}")
        return False
    
    def execute_query(self, query, params=None):
        """
        Execute a SQL query on the connected database.
       
        :param query: SQL query string
        :param params: Optional query parameters
        :return: Query result as a list of tuples
        """
        if not self.connection:
            logging.error("No active database connection. Please connect first.")
            return None

        try:
            cursor = self.connection.cursor()
            logging.debug(f"Executing query: {query}")
            headers = [col[0] for col in cursor.description]

            cursor.execute(query, params or {})
            results = cursor.fetchall()
            logging.debug(f"Query executed successfully. Rows fetched: {len(results)}")
            return results
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            logging.error(f"Failed to execute query. Error: {error.message}")
            raise
        finally:
            cursor.close()

    def execute_modify(self, query, params=None):
        """
        Execute a SQL query on the connected database.
        :param query: SQL query string
        :param params: Optional query parameters
        :return: Query result as a list of tuples
        """
        if not self.connection:
            logging.error("No active database connection. Please connect first.")
            return None

        try:
            cursor = self.connection.cursor()
            logging.debug(f"Executing query: {query}")

            cursor.executemany(query, params or {})
            self.connection.commit()
            logging.debug(f"Query executed successfully.")
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            self.connection.rollback()
            logging.error(f"Failed to execute query. Error: {error.message}")
            encoding='utf-8'
            raise
        finally:
            cursor.close()
    
    def execute_bulk(self, query, params, batch_size=500):
        """
            Execute bulk insert/update using executemany ONLY.

            :param query: SQL query string
            :param params: list of tuples (data rows)
            :param batch_size: number of rows per batch
        """
        if not self.connection:
            logging.error("No active database connection.")
            return
        
        if params is None:
            logging.error("Params is None — invalid for bulk execution.")
            return
        
        if len(params) == 0:
            logging.info("No rows to insert after transformation.")
            return
        
        cursor = None
        try:
            cursor = self.connection.cursor()
            cursor.arraysize = batch_size  # performance tuning

            logging.info(f"Starting bulk insert: {len(params)} rows")

            for i in range(0, len(params), batch_size):
                batch = params[i:i + batch_size]
                cursor.executemany(query, batch)
                logging.debug(f"Inserted batch {i} to {i + len(batch)}")
                self.connection.commit()
                logging.info("Bulk insert completed successfully.")
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            self.connection.rollback()
            logging.error(f"Bulk execution failed: {error.message}")
            raise
        finally:
            if cursor:
               cursor.close()

    def execute_one_legacy(self, query):
        """
        Execute a SQL query on the connected database.
        :param query: SQL query string
        :param params: Optional query parameters
        :return: Query result as a list of tuples
        """
        if not self.connection:
            logging.error("No active database connection. Please connect first.")
            return None

        try:
            cursor = self.connection.cursor()
            logging.debug(f"Executing query: {query}")

            cursor.execute(query)
            self.connection.commit()
            logging.debug(f"Query executed successfully.")
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            self.connection.rollback()
            logging.error(f"Failed to execute query. Error: {error.message}")
            raise

    def execute_one(self, query):
        """
            Execute a single SQL statement (DELETE/INSERT/UPDATE).
            Returns number of rows affected.
        """

        if not self.connection:
            logging.error("No active database connection. Please connect first.")
            return 0
        cursor = None
        try:
            cursor = self.connection.cursor()
            logging.debug(f"Executing query: {query}")
            cursor.execute(query)
            rows_affected = cursor.rowcount  # ✅ KEY FIX
            self.connection.commit()
            logging.debug(f"Query executed successfully. Rows affected: {rows_affected}")
            return rows_affected  # ✅ RETURN VALUE
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            self.connection.rollback()
            logging.error(f"Failed to execute query. Error: {error.message}")
            raise
        finally:
            if cursor:
                cursor.close()

    def execute_statement(self, query):
        """
        Execute a SQL query on the connected database.
       
        :param query: SQL query string of a select or insert command
        :return: Query result as a list of tuples
        """
        if not self.connection:
            logging.error("No active database connection. Please connect first.")
            return None

        try:
            cursor = self.connection.cursor()
            logging.debug(f"Executing query: {query}")

            cursor.execute(query)
            results = cursor.fetchall()
            logging.debug(f"Query executed successfully. Rows fetched: {len(results)}")
            return results
        except cx_Oracle.DatabaseError as e:
            error, = e.args
            logging.error(f"Failed to execute query. Error: {error.message}")
            raise
        finally:
            cursor.close()
    
    def get_oracle_metadata(self, schema, table_name):
        
        """Fetch metadata for an Oracle table."""
        
        cursor = self.connection.cursor()
        try:    
            query = f"""
                SELECT COLUMN_NAME, DATA_TYPE, NULLABLE
                FROM ALL_TAB_COLUMNS
                WHERE TABLE_NAME = '{table_name.upper()}'  and OWNER= '{schema.upper()}'
                ORDER BY COLUMN_ID
            """
            cursor.execute(query)
            
            results = cursor.fetchall()
        
            # Get string column names
            col_names = [col[0] for col in results]
         
            # Dict of column name → (DATA_TYPE, NULLABLE)
            col_types = {row[0]: (row[1], row[2]) for row in results}

            logging.debug(f"Metadata fetched for {schema}.{table_name}: {len(col_names)} columns")

            return col_names, col_types
        except Exception as e:
            logging.error(f"Failed to fetch metadata for {schema}.{table_name}: {e}")
            raise
        finally:
            cursor.close()

    def close(self):
        """
        Close the database connection.
        """
        if self.connection:
            try:
                self.connection.close()
                logging.info("Connection to Oracle database closed.")
            except cx_Oracle.DatabaseError as e:
                error = e.args
                logging.error(f"Failed to close the connection. Error: {error.message}")
                raise

class SAPHANADatabase:
    def __init__(self, username, password, hostName, port):
        """
        Initialize SAP HANA connection parameters.
        :param user: SAP HANA username
        :param password: SAP HANA password
        :param host:  SAP HANA database hostName
        :param port: SAP HANA database port
        """
        self.username = username
        self.password = password
        self.host = hostName
        self.port = port
        self.connection = None

    def connect(self):
        try:
            self.connection = dbapi.connect(address=self.host, port=self.port, user=self.username, password=self.password)
            print(f"Successfully connected to SAP HANA:  {self.host}.")
            return self.connection
        except dbapi.Error as error:
            logging.error(f"Connection failed in SAP HANA: {error}.")

    def execute_sql_legacy(self, sql_statement):
        """
        Execute a SQL statement (e.g., TRUNCATE, INSERT).
        :param sql_statement: The SQL statement to execute.
        """
        try:
            self.connect()
            cursor = self.connection.cursor()
            cursor.execute(sql_statement)
            self.connection.commit()
            cursor.close()
            logging.info(f"Executed SQL: {sql_statement}")
        except dbapi.Error as err:
            error, = err.args
            self.connection.rollback()
            logging.error(f"Error executing SQL. Error: {error.message}")
            raise

    def execute_sql(self, sql_statement):
        """
            Execute a SQL statement (INSERT, DELETE, UPDATE).
            Returns number of rows affected when available.
        """
        try:
            # ✅ DO NOT reconnect every time if already connected
            if not self.connection:
                self.connect()

            cursor = self.connection.cursor()
            cursor.execute(sql_statement)
            rows_affected = cursor.rowcount  # ✅ capture result
            self.connection.commit()
            cursor.close()

            # ✅ Log only summary (NOT full SQL)
            logging.info(f"SQL executed successfully. Rows affected: {rows_affected}")
            return rows_affected
        except dbapi.Error as err:
            error, = err.args
        self.connection.rollback()
        logging.error(f"Error executing SQL: {error.message}")
        raise
    
    def execute_proc(self, sql_statement):
        """
        Execute a Store Procedure.
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("SET SCHEMA HISTDBA")
            cursor.callproc(sql_statement)
            self.connection.commit()
            cursor.close()
            logging.info(f"Executed SQL: {sql_statement}")
        except Exception as err:
            error, = err.args
            self.connection.rollback()
            logging.error(f"Error executing SQL. Error: {error.message}")
            raise

    def execute_proc_compare(self, procedureName, virtual_table, hana_table, hana_select, hana_where_clause, hana_compareTable):
        """
        Execute a Store Procedure to compare tables.
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute("SET SCHEMA HISTDBA")
            cursor.callproc(procedureName, [virtual_table, hana_table, hana_select, hana_where_clause, hana_compareTable])
            result_set = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()
            logging.debug("Executed stored procedure: GET_MISSING_ROWS_ADJUSTMENT_DATES")
            logging.debug(f"Retrieve columns: {columns}")
            logging.debug(f"Retrieve result: {result_set}")
            return columns, result_set
        except Exception as err:
            logging.error(f"Error executing SQL: {err}")
            raise

    def query_data(self, sql_query):
        """
        Execute an SQL query on the SAP HANA database.

        :param sql_query: The SQL query string to execute.
        :return: List of tuples containing query results.
        """
        try:
            cursor = self.connection.cursor()
            cursor.execute(sql_query)
            data = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            cursor.close()
            return columns, data
        except dbapi.Error as err:
            logging.error(f"Error executing query: {err}")
            raise

    def query_one(self, sql_query):
        """
        Execute an SQL query on the SAP HANA database.
        :param sql_query: The SQL query string to execute.
        :return: count from table.
        """

        try:            
            cursor = self.connection.cursor()
            cursor.execute(sql_query)
            return cursor.fetchone()[0]
        except dbapi.Error as err:
            logging.error(f"Error executing query: {err}")
            raise

    def close(self):
        """
        Close the database connection.
        """
        if self.connection:
            try:
                self.connection.close()
                logging.info("Connection to SAP HANA database closed.")
            except dbapi.Error.DatabaseError as e:
                error, = e.args
                logging.error(f"Failed to close the connection. Error: {error.message}")
                raise