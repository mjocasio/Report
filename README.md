Author: Michael J. Ocasio
Date: October 03, 2025
Release version: 1.0.0

Project Overview – ReportValidationHANA
ReportValidationHANA

ReportValidationHANA This application is a Python tool that connects to Oracle and SAP HANA databases to pull tables from the EHRP schemas. It first compares the row counts between the source and target tables. If differences are found, it then checks the tables’ indexes or primary keys to identify discrepancies.

Note: Once issues are identified, the process reviews the target table to remove Unicode values that couldn’t be translated from the source. The affected records are saved in a corresponding skip table, which we use to track and correct the data. After corrections, the records from the skip table are inserted back into the target table. 
Note: The failed translation of Unicode values between the EHCM Oracle server and the Parklawn Oracle server is caused by a misconfiguration between the two systems. Specifically, the mapping between tables is lost due to a character set mismatch: EHCM uses UTF-32, while the Parklawn server uses WE8ISO8859P15.

Once this configuration issue is corrected, the validation process can reduce the number of outstanding records to 99.111% accuracy.
Installation

Clone the project from the HHS GitHub repository.
pip install (https://github.com/HHS/OAPS-ETL/tree/ReportValidationHana)


Run the setup file to install dependencies:

python setup.py

Dependencies are listed in requirements.txt.

Usage

Credentials for Oracle and SAP HANA are stored in a .env file.

The .env file is protected and not tracked in GitHub.

Version Control

All project changes are tracked via GitHub, ensuring full version history and collaboration support.