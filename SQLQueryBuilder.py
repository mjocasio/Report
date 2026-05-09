from datetime import date, datetime

class SQLQueryBuilder:
    def __init__(self, schema_name, table_name):
        self.schema_name = schema_name
        self.table_name = table_name

    def generate_select_statement(self, columns, where_clause):
        return f"SELECT ROWID, {', '.join(columns)} \n\n FROM {self.schema_name}.{self.table_name} \n\n WHERE {where_clause} \n\n"

    def generate_select_statement_norowid(self, columns, where_clause):
        return f"SELECT {', '.join(columns)} \n\n FROM {self.schema_name}.{self.table_name} \n\n WHERE {where_clause} \n\n"
    
    def generate_insert_select_statement(self, schema_name, target_table, columns, where_clause):
        select_clause = self.generate_select_statement_norowid(columns, where_clause)
        insert_clause = f"INSERT INTO {schema_name}.{target_table} ({', '.join(columns)})"
        return f"{insert_clause} {select_clause}"
    
    def generate_delete_statement(self, hana_table, where_clause):
        delete_clause = f"DELETE FROM {hana_table} WHERE {where_clause}"
        return f"{delete_clause}"
    
    def format_effdt(date_string):
        """
        Converts and formats effdt to 'YYYY-MM-DD'.
            Args:
                date_string (str): Date string from the CSV (effdt).
            Returns:
                str: Formatted date as 'YYYY-MM-DD'.
        """

        # Try to parse the date in any format (adjust the format if needed)
        if not isinstance(date_string, date):
            try:
                date_obj = datetime.strptime(date_string,'%Y-%m-%d')
            except ValueError:
                try:
                    date_obj = datetime.strptime(date_string,'%Y-%m-%d %H:%M:%S')
                except ValueError:
                    raise
            return 'TO_DATE(\'' + date_obj.strftime('%Y-%m-%d') + '\', \'YYYY-MM-DD\')'
        
    def build_where_clause(self, where_keys):
        """
        Builds WHERE clauses dynamically based on the dictionary data.
        Args:
            where_dicts (list): List of dictionaries, where each dictionary represents a row with column names as keys.
        Returns:
            list: List of WHERE clauses for each row.
        """
        where_clauses = []
        for row in where_keys:
            where_clause = []
            for key, value in row.items():
                # If the key is 'effdt', format the value as a date
                if key == 'EFFDT':
                    try:
                        value = SQLQueryBuilder.format_effdt(value)
                    except ValueError:
                        raise
                    where_clause.append(f"{key} = {value}")
                else:
                    where_clause.append(f"{key} = '{value}'")
            # Join all conditions with AND
            where_clauses.append(" AND ".join(where_clause))
        return where_clauses
