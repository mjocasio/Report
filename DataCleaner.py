from datetime import date, datetime
import logging
import re
import unicodedata
class DataCleaner:
    @staticmethod
    def clean_string(value):
       try:
            # 1. datetime FIRST — most specific type check
            if isinstance(value, (datetime, date)):
                return value

            # 2. None SECOND — after type checks
            if value is None:
                return value

            # 3. bytes THIRD
            if isinstance(value, bytes):
                value = value.decode('utf-8', errors='ignore')

            # 4. string LAST
            if isinstance(value, str):
                value = re.sub(r'¿+', '', value)
                value = value.replace('\\', '')
                value = value.encode('ascii', errors='ignore').decode('ascii')

            return value

       except Exception as e:
            logging.debug(f"clean_string failed on value={value!r} error={e}")
            return value

    @staticmethod
    def clean_row(row, columns):

        # Clean the values based on column names

        # Clean only string-type columns if desired (e.g., column names that indicate string values)

        cleaned_row = []

        for col, value in zip(columns, row):

            value = DataCleaner.clean_string(value)

            cleaned_row.append(value)

        return cleaned_row