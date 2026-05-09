import csv
class CSVHandler:
    def __init__(self, file_path):
        self.file_path = file_path

    def read_csv(self):
        file_data = []
        with open(self.file_path, mode='r', newline='') as file:
            reader = csv.DictReader(file)            
            for row in reader:
                # Append each row as a dictionary
                file_data.append(row)
        return file_data

    def read_file(self):    
        where_keys = []
        where_values = []
        with open(self.file_path, 'r') as file:
            lines = file.readlines()
            # Read the header
            header = lines[0].strip()
            where_keys = [key.strip() for key in header.split(",")]
        
            # Read data rows
            for line in lines[1:]:
                line = line.strip()
                if not line:  # Skip empty lines
                    continue
                values = [value.strip() for value in line.split(",")]
                if len(values) != len(where_keys):
                    raise ValueError(f"Row does not match header column count: {line}")
                #where_values.append(values)
        return where_keys, values

    def read_dict(self):
        """
        Reads the WHERE clause keys and values from a CSV file with a header row and returns them as a list of dictionaries.
        Args:
            file_path (str): Path to the input file.

        Returns:
            list: A list of dictionaries, where each dictionary represents a row with column names as keys.
        """
        where_dicts = []
        try:
            with open(self.file_path, 'r') as file:
                reader = csv.DictReader(file)
                # Read rows and create dictionary for each row
                for row in reader:
                    where_dicts.append(row)
        except FileNotFoundError: 
            raise
        except PermissionError: 
            raise
        except Exception as e: 
            raise
        return where_dicts
    
    def write_query_results(self, result_file_path, headers, data):
        with open(result_file_path, mode='w', encoding='utf-8', newline='') as result_file:
            csv_writer = csv.writer(result_file)
            # Write headers first
            csv_writer.writerow(headers)
            # Write each row of data
            for row in data:
                csv_writer.writerow(row)

    def write_to_file(self, query):
        with open(self.file_path, "a", encoding='utf-8') as file:
            file.write(query + ";\n")

    def write_query_results(self, query_results):
        with open(self.file_path, "a", encoding='utf-8') as file:
            for row in query_results:
                file.write(",".join(map(str, row)) + "\n")

    def write_to_text_file(self, headers,data, delimiter=","):
        """
        Write the comparison results to a text file with a specified delimiter.

        :param data: List of tuples containing mismatched records.
        :param filename: Name of the text file to save results.
        :param delimiter: Delimiter to separate fields in the output file (default: pipe '|').
        """
        
         # Output file       
        with open(self.file_path , 'w') as file:
            file.write(delimiter.join(map(str, headers)) + "\n")
            for row in data:
                file.write(delimiter.join(map(str, row)) + "\n")
        print(f"Results written to '{self.file_path}' successfully.")

    def write_dups_text_file(self, headers,data, delimiter=","):
        """
        Write the comparison results to a text file with a specified delimiter.

        :param data: List of tuples containing mismatched records.
        :param filename: Name of the text file to save results.
        :param delimiter: Delimiter to separate fields in the output file (default: pipe '|').
        """
        
         # Output file       
        with open(self.file_path , 'w') as file:
            file.write(delimiter.join(map(str, headers)) + "\n")
            for row in data:
                file.write(delimiter.join(map(str, row[:-1])) + "\n")
        print(f"Results written to '{self.file_path}' successfully.")

    def write_dups(self, headers ,data):
        """
        Write the comparison results to a text file.

        :param data: List of tuples containing duplicate records.
        :param filename: Name of the text file to save results.
        """        
        # Output file
        try:       
            with open(self.file_path , 'w') as file:
                file.write(headers + "\n")
                for row in data:
                    file.write(row + "\n")
            print(f"Results Dups written to '{self.file_path}' successfully.")
        except FileNotFoundError: 
            raise
        except PermissionError: 
            raise
        except Exception as e: 
            raise
        