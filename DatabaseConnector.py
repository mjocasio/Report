import cx_Oracle
import hdbcli.dbapi as hana_db

class DatabaseConnector:
    def __init__(self, oracle_config=None, hana_config=None):
        """
        Initialize connection parameters for Oracle and SAP HANA.
        """
        self.oracle_config = oracle_config
        self.hana_config = hana_config
        self.oracle_connection = None
        self.hana_connection = None

    def connect_to_oracle(self):
        """
        Establish a connection to the Oracle database.
        """
        try:
            self.oracle_connection = cx_Oracle.connect(
                user=self.oracle_config['user'],
                password=self.oracle_config['password'],
                dsn=self.oracle_config['dsn']
            )
            print("Connected to Oracle Database")
        except cx_Oracle.DatabaseError as e:
            print(f"Oracle connection error: {e}")
            self.oracle_connection = None

    def connect_to_hana(self):
        """
        Establish a connection to the SAP HANA database.
        """
        try:
            self.hana_connection = hana_db.connect(
                address=self.hana_config['host'],
                port=self.hana_config['port'],
                user=self.hana_config['user'],
                password=self.hana_config['password']
            )
            print("Connected to SAP HANA Database")
        except hana_db.Error as e:
            print(f"SAP HANA connection error: {e}")
            self.hana_connection = None

    def execute_oracle_query(self, query, params=None):
        """
        Execute a query on the Oracle database.
        """
        if self.oracle_connection:
            cursor = self.oracle_connection.cursor()
            try:
                cursor.execute(query, params or [])
                results = cursor.fetchall()
                cursor.close()
                return results
            except cx_Oracle.DatabaseError as e:
                print(f"Oracle query error: {e}")
        else:
            print("Oracle connection is not established.")

    def execute_hana_query(self, query, params=None):
        """
        Execute a query on the SAP HANA database.
        """
        if self.hana_connection:
            cursor = self.hana_connection.cursor()
            try:
                cursor.execute(query, params or [])
                results = cursor.fetchall()
                cursor.close()
                return results
            except hana_db.Error as e:
                print(f"SAP HANA query error: {e}")
        else:
            print("SAP HANA connection is not established.")

    def close_connections(self):
        """
        Close both Oracle and SAP HANA connections if open.
        """
        if self.oracle_connection:
            self.oracle_connection.close()
            print("Oracle connection closed.")
        if self.hana_connection:
            self.hana_connection.close()
            print("SAP HANA connection closed.")