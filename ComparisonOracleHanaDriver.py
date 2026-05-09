import cx_Oracle

import csv



# Database connection class

class DatabaseConnector:

    def __init__(self, username, password, host, port, service_name):

        dsn = cx_Oracle.makedsn(host, port, service_name=service_name)

        self.connection = cx_Oracle.connect(username, password, dsn)

        self.cursor = self.connection.cursor()



    def close_connection(self):

        self.cursor.close()

        self.connection.close()





# CSV reader/writer class

class CSVHandler:

    def __init__(self, file_path):

        self.file_path = file_path



    def read_csv(self):

        with open(self.file_path, mode='r', encoding='utf-8') as file:

            csv_reader = csv.reader(file)

            return [row for row in csv_reader]



    def write_query_results(self, result_file_path, headers, data):

        with open(result_file_path, mode='w', encoding='utf-8', newline='') as result_file:

            csv_writer = csv.writer(result_file)

            # Write headers first

            csv_writer.writerow(headers)

            # Write each row of data

            for row in data:

                csv_writer.writerow(row)





# SQL query builder class

class SQLQueryBuilder:

    def __init__(self, db_connector, table_name):

        self.db_connector = db_connector

        self.table_name = table_name



    def get_all_columns(self):

        query = f"""

            SELECT COLUMN_NAME 

            FROM ALL_TAB_COLUMNS 

            WHERE TABLE_NAME = '{self.table_name.upper()}'

            ORDER BY COLUMN_ID

        """

        self.db_connector.cursor.execute(query)

        return [row[0] for row in self.db_connector.cursor.fetchall()]



    def build_select_query(self, columns):

        return f"SELECT {', '.join(columns)} FROM {self.table_name}"



    def build_where_clause(self, columns, row):

        return " AND ".join(f"{col} = :{i+1}" for i, col in enumerate(columns[:len(row)]))



    def build_order_by_clause(self, columns):

        order_columns = ", ".join(columns[:3])  # Modify if needed

        return f"ORDER BY {order_columns}"





# Main execution

if __name__ == "__main__":

    # Initialize database connection

    db_connector = DatabaseConnector(

        username="your_username",

        password="your_password",

        host="your_host",

        port="your_port",

        service_name="your_service_name"

    )



    # Read CSV file

    csv_handler = CSVHandler("data_file.csv")

    file_data = csv_handler.read_csv()



    # Initialize query builder and get all columns

    table_name = "YOUR_ORACLE_TABLE"

    query_builder = SQLQueryBuilder(db_connector, table_name)

    all_columns = query_builder.get_all_columns()



    result_data = []

    

    for row in file_data:

        # Build dynamic SQL query

        select_query = query_builder.build_select_query(all_columns)

        where_clause = query_builder.build_where_clause(all_columns, row)

        order_by_clause = query_builder.build_order_by_clause(all_columns)



        # Complete SQL query

        sql_query = f"{select_query} WHERE {where_clause} {order_by_clause}"



        # Execute query

        db_connector.cursor.execute(sql_query, row)

        results = db_connector.cursor.fetchall()

        

        # Append query results for writing to file

        result_data.extend(results)



    # Write query results to CSV using CSVHandler class

    csv_handler.write_query_results("query_results.csv", all_columns, result_data)



    # Close database connection

    db_connector.close_connection()

