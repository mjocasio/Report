from collections import defaultdict
import csv
import logging
from flask import Flask, flash,  render_template, request, redirect, send_file, url_for, abort, session
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps, lru_cache
from CSVHandler import CSVHandler
from NameGenerator import NameGenerator
from datetime import date, datetime
from Connection_Module import HanaExecutionError, OracleDatabase, SAPHANADatabase
from hdbcli import dbapi
import cx_Oracle
import os, json
from RetrieveOracleRecords import RetrieveOracleRecords
from dotenv import find_dotenv, load_dotenv
import pandas as pd
import re
import io
import openpyxl

app = Flask(__name__)
app.secret_key = "super_secret_key"

# ================================
# LOAD HANA METADATA ONCE (CACHE)
# ================================

# SAP HANA connection details
userName = os.getenv("SAPuserName")
password = os.getenv("SAPpassword")
hostName = os.getenv("SAPhostName")
port = os.getenv("SAPport")

hana_config = {
    "username":userName,
    "password":password,
    "hostName":hostName,
    "port":port
}

# Oracle connection details
userName = os.getenv("ORAuserName")
password = os.getenv("ORApassword")
hostName = os.getenv("ORAhostName")
port = os.getenv("ORAport")
service_name = os.getenv("ORAService_name")

oracle_config = {
    "username":userName,
    "password":password,
    "hostName":hostName,
    "port":port,
    "service_name":service_name
}
        
def map_data_type(oracle_data_type, length, precision, scale):
    """Map Oracle data type to SAP HANA data type."""
    hana_data_type = DATA_TYPE_MAPPING.get(oracle_data_type.upper(), "NVARCHAR")
    print(f"{oracle_data_type}+ ' '+{hana_data_type}+' ' +{precision}  + ' '  + {scale}")

    if oracle_data_type.upper() in ["VARCHAR2", "NVARCHAR2", "CHAR", "NCHAR"]:
        return f"{hana_data_type}({length})"
    elif oracle_data_type.upper() == "NUMBER":
        if precision and scale is not None:
            if scale == 0:
            # Whole numbers: Use INTEGER or BIGINT if within range
                return "INTEGER" if precision <= 10 else "BIGINT"
            else:
            # Decimal numbers: Use DECIMAL(p, s)
                return f"DECIMAL({precision}, {scale})"
        elif precision:  # Only precision provided
            return "BIGINT" if precision > 10 else "INTEGER"
        else:
            # Generic NUMBER without precision and scale: Use DECIMAL
            return "INTEGER"
    elif oracle_data_type.upper() == "TIMESTAMP(6)":
        if scale > 0:
            return "TIMESTAMP"
    else:
        return hana_data_type

 #  Oracle to HANA data type mapping
    DATA_TYPE_MAPPING = {
        "VARCHAR2": "NVARCHAR",
        "NUMBER": "INTEGER",
        "DATE": "DATE",
        "NCLOB": "NCLOB",
        "BLOB": "BLOB",
        "CHAR": "CHAR",
        "NCHAR": "NCHAR",
        "NVARCHAR2": "NVARCHAR",
        "TIMESTAMP(6)": "TIMESTAMP",
    }

@app.context_processor
def inject_user():
    return dict(username=session.get('username'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    # =========================
    # 1. SHOW FORM (GET)
    # =========================
    if request.method == 'GET':
        return render_template('register.html')

    # =========================
    # 2. PROCESS FORM (POST)
    # =========================
    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        hashed_pw = generate_password_hash(password)

        hana_conn = SAPHANADatabase(**hana_config).connect()

        try:
            cursor = hana_conn.cursor()

            # =========================
            # 1. PREVENT DUPLICATES
            # =========================
            
            cursor.execute("""
                SELECT 1 FROM mocasio_admin.users WHERE username = lower(?)
            """, (username,))

            if cursor.fetchone():
                return "User already exists"
    
            # Insert user
            cursor.execute("""
                INSERT INTO mocasio_admin.users (username, password)
                VALUES (?, ?)
            """, (username, hashed_pw))

            # Get user id
            cursor.execute("""
                SELECT id FROM mocasio_admin.users WHERE username = lower(?)
            """, (username,))
            user_id = cursor.fetchone()[0]

            # Get VIEWER role
            cursor.execute("""
                SELECT id FROM mocasio_admin.roles WHERE name = 'VIEWER'
            """)
            viewer_role_id = cursor.fetchone()[0]

            # Assign role
            cursor.execute("""
                INSERT INTO mocasio_admin.user_roles (user_id, role_id)
                VALUES (?, ?)
            """, (user_id, viewer_role_id))

            hana_conn.commit()
            hana_conn.close()

            return redirect('/login')

        except Exception as e:
            hana_conn.close()
            return f"Error: {str(e)}"
            
@app.route('/login', methods=['GET', 'POST'])
def login():
    # =========================
    # HANDLE POST (LOGIN)
    # =========================
    username = None
    if request.method == 'POST':

        hana_conn = SAPHANADatabase(**hana_config).connect()

        try:
            username = request.form['username'].strip().lower()
            password = request.form['password']

            cursor = hana_conn.cursor()
            cursor.execute("""
                SELECT u.id, u.password, r.name AS role
                FROM mocasio_admin.users u
                JOIN mocasio_admin.user_roles ur ON u.id = ur.user_id
                JOIN mocasio_admin.roles r ON ur.role_id = r.id
                WHERE LOWER(u.username) = LOWER(?)
            """, (username,))

            row = cursor.fetchone()

            if row and check_password_hash(row[1], password):
                session['user_id'] = row[0]
                session['username'] = username
                session['role'] = row[2]
                flash(f"Welcome {username}!", "success")
                return redirect(url_for('home_page')) 
            flash("Invalid credentials", "danger")
            return render_template("login.html")
        except Exception as e:
            flash(f"Error: {str(e)}", "danger")
            return f"Error: {str(e)}"
        finally:
            hana_conn.close()

    # =========================
    # HANDLE GET (SHOW PAGE)
    # =========================
    return render_template('login.html')

@app.route('/logout')
def logout():
    username = session.get('username') 
    session.clear()

    if username:
        flash(f"{username} has successfully logged out!", "info")
    else:
        flash("You have successfully logged out!", "info")
    return redirect('/home')

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'user_id' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return wrapper

def has_permission(permission_name):
    user_id = session.get('user_id')
    hana_conn = SAPHANADatabase(**hana_config).connect()
    try:
        cursor = hana_conn.cursor()

        query = """
            SELECT 1
            FROM mocasio_admin.user_roles ur
            JOIN mocasio_admin.role_permissions rp ON ur.role_id = rp.role_id
            JOIN mocasio_admin.permissions p ON rp.permission_id = p.id
            WHERE ur.user_id = ? AND p.name = ?
        """

        cursor.execute(query, (user_id, permission_name))
        return cursor.fetchone() is not None
    except Exception as e:
        logging.error("Permission error:", e)
        return False
    finally:
        hana_conn.close()

@app.route("/")
@app.route("/home")
def home_page():
    return render_template('home_page.html')

def process_table(owner, table):
    if f"{owner}.{table}" == "EHRP.PS_GVT_PAR_REMARKS":
        hana_select = "emplid, empl_rcd, effdt, effseq, gvt_sf50_remark"
            
        # Dynamic WHERE clauses
        hana_where_clause = "b.emplid = a.emplid and \
            b.empl_rcd = a.empl_rcd and \
            b.effseq = a.effseq AND \
            b.GVT_SF50_REMARK = A.GVT_SF50_REMARK"
            
        #check for HANA Dups rows 
        hana_dup_where_clause = "emplid, empl_rcd, effdt, effseq, gvt_sf50_remark"

        #Skip table
        skipped_table = "Skipped_Gvtparremarks_Tbl"
    elif f"{owner}.{table}" == "EHRP.PS_GVT_EMPLOYMENT" or \
         f"{owner}.{table}" == "EHRP.PS_GVT_PERS_DATA" or \
         f"{owner}.{table}" == "EHRP.PS_GVT_JOB":                        
        
        hana_select = "emplid, empl_rcd, effdt, effseq"
            
        # Dynamic WHERE clauses
        hana_where_clause = "b.emplid = a.emplid and \
             b.empl_rcd = a.empl_rcd and \
             b.effseq = a.effseq"
            
        #check for HANA Dups rows 
        hana_dup_where_clause = "emplid, empl_rcd, effdt, effseq"

        match f"{owner}.{table}":
          case "EHRP.PS_GVT_EMPLOYMENT":
            skipped_table = "skipped_employment_recs"
          case "EHRP.PS_GVT_PERS_DATA":
            skipped_table = "skipped_gvtpersdata_recs"
          case "EHRP.PS_GVT_JOB":
            skipped_table = "skipped_gvtjob_recs"  
    elif f"{owner}.{table}" == "EHRP.PS_NAMES":           
        hana_select = "emplid, effdt"
        hana_where_clause = "b.emplid = a.emplid"
            
        #check for HANA Dups rows
        hana_dup_where_clause = "emplid, effdt"

        skipped_table = "skipped_ps_names_recs"
    elif f"{owner}.{table}" == "EHRP.PS_ADDRESSES":
        hana_select = "emplid, effdt, address_type, eff_status"
            
        # Dynamic WHERE clauses
        hana_where_clause = "b.emplid = a.emplid and \
            b.address_type = a.address_type and \
            b.eff_status = a.eff_status"
            
        #check for HANA Dups rows
        hana_dup_where_clause = "emplid, effdt, address_type, eff_status"

        skipped_table = "Skipped_Ps_Addresses"
    elif f"{owner}.{table}" == "EHRP.PS_PERSONAL_DATA":
        hana_select = "emplid"
            
        # Dynamic WHERE clauses
        hana_where_clause = "b.emplid = a.emplid"
            
        # #check for HANA Dups rows
        hana_dup_where_clause = "emplid"

        skipped_table = "skipped_personaldata_recs"
    elif f"{owner}.{table}" == "EHRP.PS_JPM_JP_ITEMS":
        hana_select = "Jpm_Profile_Id, JPM_CAT_TYPE, \
            jpm_item_key_id, JPM_CAT_ITEM_ID, \
            TO_VARCHAR(EFFDT, 'YYYY-MM-DD')"
            
        # Dynamic WHERE clauses
        hana_where_clause = "B.Jpm_Profile_Id = A.Jpm_Profile_Id  AND \
            B.JPM_CAT_TYPE = A.JPM_CAT_TYPE AND \
            B.JPM_CAT_ITEM_ID = A.JPM_CAT_ITEM_ID"
            
        # #check for HANA Dups rows
        hana_dup_where_clause = "Jpm_Profile_Id, JPM_CAT_TYPE, \
            JPM_CAT_ITEM_ID, TO_VARCHAR(EFFDT, 'YYYY-MM-DD') EFFDT"
            
        skipped_table = "skipped_jpm_jp_items"
    elif f"{owner}.{table}" == "EHRP.PS_JOBCODE_TBL_NEW":
        hana_select = "SETID, JOBCODE, EFFDT, EFF_STATUS"
            
        # Dynamic WHERE clauses
        hana_where_clause = "B.setid = A.setid  AND \
            B.jobcode = A.jobcode AND \
            B.effdt = A.effdt AND \
            B.eff_status = A.eff_status"
            
        # #check for HANA Dups rows
        hana_dup_where_clause = "SETID, JOBCODE, EFFDT, EFF_STATUS"

        skipped_table = "skipped_jobcode_new_recs"

    elif f"{owner}.{table}" == "EHRP.PS_POSITION_DATA_NEW" :
        hana_select = "position_nbr,effdt"
            
        # Dynamic WHERE clauses
        hana_where_clause = "b.position_nbr = a.position_nbr"
            
        # #check for HANA Dups rows
        hana_dup_where_clause = "position_nbr, effdt"

        skipped_table = "skipped_posdata_recs"
    return hana_select, hana_where_clause, hana_dup_where_clause, "HISTDBA", skipped_table

def copy_to_hana(where_clauses, owner, table_name, skipped_schema, skipped_table):
    """
      Copy records from virtual table to HANA target table using WHERE clauses.
      Uses batching for performance and better error handling.
    """

    if not where_clauses:
        logging.warning("No WHERE clauses provided. Skipping copy_to_hana.")
        return

    hana_conn = SAPHANADatabase(**hana_config)

    try:
        hana_conn.connect()
    except Exception as e:
        logging.error(f"Error SAP in connection {e}")
        exit(0)
    
    virtual_schema = f"v_{skipped_schema}"
    virtual_table = f"v_{skipped_table}"

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
            INSERT INTO {owner}.{table_name}
            SELECT *
            FROM {virtual_schema}.{virtual_table}
            WHERE {combined_where}
        """.strip()

        try:
            # Log batch info for debugging
            rows_affected = hana_conn.execute_sql(insert_query)
            total_success += rows_affected or 0
            logging.info(
                f"Batch #{batch_id} inserted rows: {rows_affected or 0}"
            )
        except Exception as e:
            logging.error(f"Batch #{batch_id} failed: {e}")
            total_failed += len(batch)
            logging.error(
                f"\n-- FAILED BATCH #{batch_id} --\nERROR: {e}\n"
            )
            
            # -----------------------------------
            # FALLBACK: row-by-row execution
            # -----------------------------------
            
            for idx, where_clause in enumerate(batch, start=1):
                single_query = f"""
                    INSERT INTO {owner}.{table_name}
                    SELECT *
                    FROM {virtual_schema}.{virtual_table}
                    WHERE {where_clause}
                """.strip()
                try:
                    hana_conn.execute_sql(single_query)
                    logging.info(f"Recovered WHERE #{idx} in batch #{batch_id}")
                    total_success += 1
                except Exception as row_error:
                    total_failed += 1
                    logging.error(
                        f"Row failed in batch #{batch_id}: {row_error}"
                    )
    logging.info(
        f"Copy to HANA completed. Success: {total_success}, Failed: {total_failed}"
    )

def process_duplicates(hana_conn, hana_select, hana_table, hana_dups_where):
    """
     Find Duplicates in the HANA Table
        :param hana_table: Name of table to find duplicates.
        :param select_hana: Select statement to query for dups.
    """
    
    query = f"""
        select {hana_select}, COUNT(*)
        from {hana_table}  a 
        group by {hana_dups_where}
        HAVING COUNT(*) > 1
    """
        
    try:
      return hana_conn.query_data(query)
    except dbapi.Error as err:
      logging.error(f"Error executing query: {err}")
      return 0

def delete_from_hana(hana_conn, hana_table, where_clauses):
    """
      Delete records from HANA table using dynamic WHERE clauses.
    """

    if not where_clauses:
        logging.warning("No WHERE clauses provided. Skipping delete_from_hana.")
        return

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
            DELETE FROM {hana_table}
            WHERE {combined_where}
        """.strip()

        try:
            rows_affected = hana_conn.execute_sql(delete_query)

            total_success += rows_affected or 0

            logging.info(
                f"Batch #{batch_id} deleted rows: {rows_affected or 0}"
            )

        except Exception as e:
            logging.error(f"Batch #{batch_id} delete failed: {e}")
            total_failed += len(batch)

            # -----------------------------------
            # FALLBACK: row-by-row delete
            # -----------------------------------

            for idx, where_clause in enumerate(batch, start=1):
                single_delete = f"""
                    DELETE FROM {hana_table}
                    WHERE {where_clause}
                """.strip()

                try:
                    hana_conn.execute_sql(single_delete)
                    total_success += 1

                    logging.info(
                        f"Recovered DELETE WHERE #{idx} in batch #{batch_id}"
                    )

                except Exception as row_error:
                    total_failed += 1

                    logging.error(
                        f"Delete failed in row #{idx}: {row_error}"
                    )
        logging.info(
            f"Delete from HANA completed. Success: {total_success}, Failed: {total_failed}"
        )

@app.route("/report")
@login_required
def report_page():
    now = datetime.now()
    hana_conn = SAPHANADatabase(**hana_config)

    try:
        hana_conn.connect()

        status, current_row_count, previous_row_count = check_count(hana_conn)
        
        # Replace with your procedure name
        procedure_name = "GET_TABLE_COUNTS_FROM_ITCNP"
        
        select_query = """
                SELECT A.OWNER, A.TABLE_NAME, A.HANA_ROWCOUNT, 
                        A.BIIS_ROWCOUNT AS ORACLE_ROWCOUNT, 
                        A.BIIS_ROWCOUNT -  A.HANA_ROWCOUNT AS DIFFERENCE, 
                        CASE 
                          WHEN A.HANA_ROWCOUNT = A.BIIS_ROWCOUNT 
                            THEN 'YES'
                            ELSE 'NO'
                        END AS "COUNTS_MATCHED?",
                        TO_VARCHAR(SNAPSHOT_TAKEN_DT, 'MM/DD/YYYY') SNAPSHOT_TAKEN_DT
                FROM HISTDBA.ROWKOWNT2_TBL A 
                order by 1, 2
        """
                
        if status:
            # Call the procedure
            hana_conn.execute_proc(procedure_name)
        else:
            #Truncate data from SAP HANA
            query = "TRUNCATE TABLE HISTDBA.ROWKOWNT2_TBL;"
            hana_conn.execute_sql(query)
        
            # Insert data from SAP HANA
            query = "INSERT INTO HISTDBA.ROWKOWNT2_TBL(OWNER, TABLE_NAME) (SELECT SCHEMA_NAME, TABLE_NAME FROM TABLES WHERE SCHEMA_NAME IN ('AMSUSR', 'EHRP'));"
            hana_conn.execute_sql(query)

            # Replace with your procedure name
            procedure_name = "GET_TABLE_COUNTS_FROM_ITCNP"
            # Call the procedure
            hana_conn.execute_proc(procedure_name)
            
        # Fetch data from SAP HANA
        rows = hana_conn.query_list(select_query)

        outstanding_files = session.get('outstanding_files', {})
        show_once = session.get('show_once', False)

        for row in rows:
            key = f"{row['OWNER']}.{row['TABLE_NAME']}"
            file_path = outstanding_files.get(key)

            outstanding_rows = []

            if show_once and file_path and os.path.exists(file_path):
                try:
                    with open(file_path, 'r') as f:
                        reader = csv.DictReader(f)
                        outstanding_rows = list(reader)
                except Exception as e:
                    logging.error(f"Error reading file {file_path}: {e}")

            # attach to row
            row['OUTSTANDING_ROWS'] = outstanding_rows

        html = render_template(
            "report_page.html",
            now=now,
            rows=rows
        )

        # -------------------------
        # SAVE SNAPSHOT
        # -------------------------
        snapshot_dir = os.path.join(os.path.dirname(__file__), "snapshots")
        os.makedirs(snapshot_dir, exist_ok=True)

        file_name = f"report_{now.strftime('%Y%m%d_%H%M%S')}.html"
        file_path = os.path.join(snapshot_dir, file_name)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(html)

        if show_once:
           session.pop('outstanding_files', None)
           session.pop('show_once', None)
        return html
    except Exception as e:
        return f"Error retrieving data: {str(e)}"
        # Render the table with data
    finally:
        hana_conn.close()

def check_count(conn):
    """
    hanaTable (str): Name of the Current table.
    Returns:
        bool: True if row counts between current load and yesterday one are equal,
              False otherwise.
    """
    hana_table = "ehrp.ps_gvt_job"

    # SQL query to get row counts for today and yesterday
    query = f"""
        SELECT COUNT(*)
        FROM {hana_table};
    """

    current_row_count = conn.query_one(query)

    # Get the absolute path to the directory where the current script resides
    script_dir = os.path.abspath(os.path.dirname(__file__))
    file_path = os.path.join(script_dir, 'row_count.txt')
    
    # Save today's count to a local file
    with open(file_path, "r+") as file:
        int_value, file_date_str = file.read().split(",")  # Read yesterday's count
        previous_row_count = int(int_value.strip())
        file_date = datetime.strptime(file_date_str.strip(), "%Y-%m-%d").date()
        current_date = datetime.now().date()

    if (
       current_date > file_date
       and previous_row_count == current_row_count
    ):
       return False, current_row_count, previous_row_count
    elif current_date == file_date:
        return True, current_row_count, previous_row_count
    else:
        with open(file_path, "w") as file:
            file.write(f"{current_row_count}, {current_date}")
        return True

def migrate_table(oracle_conn, hana_conn, source_schema, table_name, target_schema):

    # Step 1: metadata
    metadata = get_table_metadata(oracle_conn, source_schema, table_name)

    if not metadata:
        return "No metadata found"

    # Step 2: check if exists
    if table_exists(hana_conn, target_schema, table_name):
        return f"Table {table_name} already exists in HANA"

    # Step 3: generate SQL
    create_sql = generate_create_table(target_schema, table_name, metadata)

    #print(create_sql)  # debug

    # Step 4: execute
    execute_create_table(hana_conn, create_sql)

    return f"Table {table_name} created successfully in {target_schema}"

def execute_create_table(hana_conn, create_sql):

    cursor = hana_conn.cursor()

    cursor.execute(create_sql)
    hana_conn.commit()

def table_exists(hana_conn, schema, table):

    cursor = hana_conn.cursor()

    cursor.execute("""
        SELECT 1
        FROM TABLES
        WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?
    """, (schema.upper(), table.upper()))

    return cursor.fetchone() is not None

def map_oracle_to_hana(data_type, length=None, precision=None, scale=None):
    """
    Maps Oracle data types to SAP HANA data types.
    base documentation: https://help.sap.com/docs/HANA_SMART_DATA_INTEGRATION/71c4a6e6b4dc4a5ab3e17bb1d7e98104/13d9b4114c4c4f058d95ac4902240dd2.html
    """

    dt = data_type.upper()

    # =========================
    # CHARACTER TYPES
    # =========================
    if dt in ("VARCHAR2", "NVARCHAR2"):
        return f"NVARCHAR({length or 5000})"

    elif dt == "CHAR":
        return f"NCHAR({length or 1})"

    elif dt == "NCHAR":
        return f"NCHAR({length or 1})"

    # =========================
    # NUMERIC TYPES
    # =========================
    elif dt in ("NUMBER", "INTEGER"):
        # Integer
        if length == 1:
            return "TINYINT"
        elif length == 2:
            return "SMALLINT"
        elif length <= 9:
            return "INTEGER"
        elif length <= 18:
            return "BIGINT"
        elif length > 18:
            return f"DECIMAL({length})"
        elif scale > precision:
            return "DOUBLE"
        elif scale > 0 and scale <= precision:
            return f"DECIMAL({length})"
        elif scale < 0 and precision-scale <= 4:
            return "SMALLINT"
        elif scale < 0 and 4 < precision-scale <= 9:
            return "INTEGER"
        elif scale < 0 and 9 < precision-scale <= 18:
            return "BIGINT"
        elif scale < 0 and precision-scale > 18:
            return "DECIMAL(22)"
        else:
            return f"DECIMAL(22)"
    elif dt in ("BINARY_DOUBLE"):
          return "DOUBLE"
    elif dt == "FLOAT":
        if length == 0:
          return "DOUBLE"
        elif length <= 24:
          return "REAL"
        elif length <= 126:
          return "DOUBLE" 
    elif dt == "BINARY_FLOAT":
        return "REAL"

    # =========================
    # DATE / TIME
    # =========================
    elif dt == "DATE":
        return "TIMESTAMP"
    elif dt.startswith("TIMESTAMP"):
        return "SECONDDATE"

    # =========================
    # BINARY
    # =========================
    elif dt in ("BLOB", "BFILE", "LONG RAW"):
        return "BLOB"
    elif dt == "LONG":
        return "CLOB"
    elif dt in ("CLOB", "NCLOB"):
        return "NCLOB"
    elif dt == "RAW":
        return "VARBINARY"
    elif dt == "INTERVAL":
        return "VARCHAR"

    # =========================
    # FALLBACK
    # =========================
    else:
        return "NVARCHAR(5000)"

def get_table_metadata(schema, table):
    """
    Retrieve column metadata from Oracle for a given table.

    Returns:
        List of tuples:
        (column_name, data_type, data_length, data_precision, data_scale, nullable)
    """

    oracle_conn = OracleDatabase(**oracle_config)
    
    oracle_conn.connect()
    if oracle_conn.validate_connection():

      logging.info("Oracle database connection is valid.")

    query = """
        SELECT 
            COLUMN_NAME,
            DATA_TYPE,
            DATA_LENGTH,
            DATA_PRECISION,
            DATA_SCALE,
            NULLABLE
        FROM ALL_TAB_COLUMNS
        WHERE OWNER = :1
          AND TABLE_NAME = :2
        ORDER BY COLUMN_ID
    """

    try:
        rows = oracle_conn.execute_query(query, (
            schema.upper(),
            table.upper()
        ))

        return rows or []

    except Exception as e:
        print(f"Error retrieving metadata: {str(e)}")
        raise

def generate_alter_table(schema, table, metadata, hana_conn):

    cursor = hana_conn.cursor()

    cursor.execute("""
        SELECT COLUMN_NAME 
        FROM TABLE_COLUMNS
        WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?
    """, (schema.upper(), table.upper()))

    existing_cols = {row[0] for row in cursor.fetchall()}

    alter_statements = []

    for col in metadata:
        col_name = col[0]
        data_type = col[1]
        length = col[2]
        precision = col[3]
        scale = col[4]

        if col_name not in existing_cols:
            hana_type = map_oracle_to_hana(data_type, length, precision, scale)

            stmt = f'ALTER TABLE "{schema}"."{table}" ADD ("{col_name}" {hana_type})'
            alter_statements.append(stmt)

    return alter_statements

def generate_create_table(target_schema, table_name, metadata):
    """
    Generate clean SAP HANA CREATE TABLE statement
    """

    columns = []

    # max column length (for alignment only, NOT inside quotes)
    max_len = max(len(col[0]) for col in metadata)

    for col in metadata:
        col_name = col[0].strip().replace('"', '')
        hana_type = map_oracle_to_hana(col[1], col[2], col[3], col[4])

        col_sql = f'"{col_name}"'

        col_sql = f'    {col_sql.ljust(max_len)} {hana_type}'

        if col[5] == 'N':
            col_sql += " NOT NULL"

        columns.append(col_sql)

        # join columns cleanly
        columns_sql = ",\n".join(columns)

    # -----------------------------
    # FINAL SQL (NO TRIPLE QUOTES)
    # -----------------------------
    create_sql = (
        f'CREATE COLUMN TABLE "{target_schema}"."{table_name}" (\n'
        f'{columns_sql}\n'
        f');'
    )

    return create_sql

def get_oracle_tables(schema):
    oracle_conn = OracleDatabase(**oracle_config)
    
    oracle_conn.connect()
    if oracle_conn.validate_connection():

      logging.info("Oracle database connection is valid.")

      query = """
        SELECT TABLE_NAME 
        FROM ALL_TABLES 
        WHERE OWNER = :schema
        ORDER BY TABLE_NAME
      """

      tables = oracle_conn.execute_query(query, {"schema": schema})
      return tables
    else:
      logging.error("Oracle connection failed.")
      return []

def get_hana_tables(schema):
    hana_conn = SAPHANADatabase(**hana_config)
    hana_conn.connect()

    query = """
        SELECT SCHEMA_NAME, TABLE_NAME, TABLE_TYPE 
        FROM SYS.TABLES 
        WHERE SCHEMA_NAME = 'YOUR_SCHEMA_NAME'
        ORDER BY ORDER BY TABLE_NAME;
    """

    try:
        tables = hana_conn.query_data(query, (schema,))
        return tables
    except Exception as e:
        message = f"Query SAP HANA Tables failed: {str(e)}"
        logging.error("Query SAP HANA Tables failed.")
        return []

def generate_create_sql(source_schema, source_table, metadata):
    """
    Generates SAP HANA CREATE TABLE SQL from Oracle metadata.
    """

    columns_sql = []

    for col in metadata:

        col_name = col[0].upper()
        data_type = col[1].upper()
        length = col[2] if len(col) > 2 else None

        # -----------------------------
        # VARCHAR / CHAR TYPES
        # -----------------------------
        if "CHAR" in data_type:

            # Default safety length
            col_length = length if length and length > 0 else 30

            col_def = f'"{col_name}" VARCHAR({col_length})'

        # -----------------------------
        # NUMBER TYPE HANDLING
        # -----------------------------
        elif data_type in ["NUMBER", "NUMERIC"]:

            precision = col[2] if len(col) > 2 else None
            scale = col[3] if len(col) > 3 else 0

            if scale and int(scale) > 0:
                col_def = f'"{col_name}" DECIMAL({precision},{scale})'
            else:
                col_def = f'"{col_name}" INTEGER'

        # -----------------------------
        # DATE TYPE FIX (IMPORTANT - YOUR ISSUE)
        # -----------------------------
        elif "DATE" in data_type:
            col_def = f'"{col_name}" DATE'

        elif "TIMESTAMP" in data_type:
            col_def = f'"{col_name}" SECONDDATE'

        # -----------------------------
        # CLOB / TEXT
        # -----------------------------
        elif "CLOB" in data_type or "TEXT" in data_type:
            col_def = f'"{col_name}" NCLOB'

        # -----------------------------
        # DEFAULT FALLBACK
        # -----------------------------
        else:
            col_def = f'"{col_name}" VARCHAR(255)'

        columns_sql.append(col_def)

    # -----------------------------
    # BUILD FINAL CREATE TABLE
    # -----------------------------
    sql = f'CREATE COLUMN TABLE "{source_schema}"."{source_table}" (\n'
    sql += ",\n".join(columns_sql)
    sql += "\n);"

    return sql

def save_table_structure(schema, table, hana_columns):
    """
    Generates CREATE TABLE SQL from existing SAP HANA table
    and saves it to a .sql file.
    """

    if not hana_columns:
        return None

    column_defs = []

    for col in hana_columns:
        col_name = col["name"]
        dtype = col["type"]
        length = col.get("length")
        scale = col.get("scale")
        nullable = col.get("nullable", "TRUE")
        
        # -----------------------------
        # Rebuild datatype
        # -----------------------------
        if dtype in ["VARCHAR", "NVARCHAR"]:
            col_def = f'"{col_name}" {dtype}({length})'

        elif dtype in ["DECIMAL", "NUMERIC"]:
            col_def = f'"{col_name}" {dtype}({length},{scale})'

        elif dtype == "INTEGER":
            col_def = f'"{col_name}" INTEGER'

        elif dtype == "DATE":
            col_def = f'"{col_name}" DATE'

        elif dtype == "SECONDDATE":
            col_def = f'"{col_name}" SECONDDATE'

        elif dtype == "TIMESTAMP":
            col_def = f'"{col_name}" TIMESTAMP'

        else:
            col_def = f'"{col_name}" {dtype}'

        if nullable == "FALSE":
            col_def += " NOT NULL"
        
        column_defs.append(col_def)

    # -----------------------------
    # Build CREATE TABLE
    # -----------------------------
    create_sql = f'CREATE COLUMN TABLE "{schema}"."{table}" (\n'
    create_sql += ",\n".join(column_defs)
    create_sql += "\n);"

    # -----------------------------
    # Save to file
    # -----------------------------
    output_dir = "outputs"
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    file_path = os.path.join(
        output_dir,
        f"{schema}_{table}_backup_{timestamp}.sql"
    )

    with open(file_path, "w") as f:
        f.write(create_sql)

    return file_path

def requires_rebuild_from_metadata_diff(diff):
    """
        Generic rule:
        Any column position mismatch = structural change = rebuild preview required
    """
    for x in diff.get("position_mismatch", []):
        if x.get("oracle_position") != x.get("hana_position"):
            return True
    return False

def requires_rebuild(diff):
    position = diff.get("position_mismatch", [])
    if not position:
        return False
    # ANY insert not at end = rebuild
    for x in position:
        oracle_pos = x.get("oracle_position")
        hana_pos = x.get("hana_position")
        # if not simple append
        if hana_pos is not None and oracle_pos != hana_pos:
            return True
    return False

@app.route('/migrate', methods=['GET', 'POST'])
@login_required
def migrate_page():

    # -----------------------------
    # STATE
    # -----------------------------

    selected_schema = request.form.get('schema') if request.method == 'POST' else None
    selected_table = request.form.get('table') if request.method == 'POST' else None
    target_schema = request.form.get('target_schema') if request.method == 'POST' else None

    action = request.form.get('action') if request.method == 'POST' else None

    tables = []
    metadata = []
    create_sql = None
    message = None
    rebuild_required = False
    diff = None
    hana_cols = []


    # -----------------------------
    # LOAD TABLES WHEN SCHEMA SELECTED
    # -----------------------------
    if selected_schema:
        tables = get_oracle_tables(selected_schema)
        
        if not tables:
            message = f"No tables found for schema {selected_schema}"

    # -----------------------------
    # LOAD METADATA WHEN TABLE SELECTED
    # -----------------------------
    if selected_schema and selected_table:
        metadata = get_table_metadata(selected_schema, selected_table)
        hana_conn = SAPHANADatabase(**hana_config)
        hana_conn.connect()

        try:
            hana_cols = get_hana_columns(hana_conn, selected_schema, selected_table)
            if hana_cols:
                diff = compare_columns(metadata, hana_cols)
                rebuild_required = requires_rebuild_from_metadata_diff(diff)
        except Exception as e:
            diff = {}
            rebuild_required = False

    # =====================================================
    # ACTION: PREVIEW SQL
    # =====================================================
    if action == 'preview':

        if rebuild_required:

            create_sql = generate_create_table(
                target_schema,
                selected_table,
                metadata
            )
            message = "REBUILD REQUIRED - STRUCTURE CHANGE DETECTED"
        else:
            create_sql = generate_create_sql(
                target_schema,
                selected_table,
                metadata
            )
            message = "ALTER COMPATIBLE - SAFE TO MIGRATE"

    # =====================================================
    # ACTION: MIGRATE (EXECUTE IN HANA)
    # =====================================================
    elif action == 'migrate':
        if rebuild_required:
            return render_template(
                "migrate_page.html",
                message="MIGRATION BLOCKED - REBUILD REQUIRED (use preview)",
                tables=tables,
                metadata=metadata,
                selected_schema=selected_schema,
                selected_table=selected_table,
                create_sql=None
            )

        create_sql = generate_create_sql(
            target_schema,
            selected_table,
            metadata
        )
    
        hana_conn = SAPHANADatabase(**hana_config)
        try:
            # Use your wrapper connection
            hana_conn.connect()
            hana_conn.execute_sql(create_sql)
            message = f"Table {selected_table} created successfully."
        except HanaExecutionError as e:
            if str(e.code) == "288":
                hana_cols = get_hana_columns(hana_conn, target_schema, selected_table)
                file_path = save_table_structure(
                    target_schema,
                    selected_table,
                    hana_cols 
                )
                message = f"""
                    Table {selected_table} already exists.
                    Backup CREATE script saved to:
                    {file_path}
                """
            else:
                message = f"HANA Error [{e.code}]: {e.message}"
        # GENERIC FALLBACK
        except Exception as e:
            message = f"Unexpected error: {str(e)}"

    # =====================================================
    # ACTION: COMPARE (NEW ENGINE)
    # =====================================================
    elif action == 'compare':

        return redirect(url_for(
            'compare',
            schema=selected_schema,
            table=selected_table
        ))

    # -----------------------------
    # RENDER PAGE
    # -----------------------------
    return render_template(
        'migrate_page.html',
        tables=tables,
        metadata=metadata,
        selected_schema=selected_schema,
        selected_table=selected_table,
        create_sql=create_sql,
        message=message
    )
    
@app.route("/findTableColumns")
@login_required
def findTableColumns_page():
    if 'user_id' not in session:
        return redirect('/login')
    return render_template('findTableColumns_page.html')

def load_metadata_map(hana_conn):
    query = """
    
    SELECT
    COLUMN_NAME,
    DATA_TYPE_NAME,
    LENGTH,
    SCALE
    FROM (
        SELECT
            COLUMN_NAME,
            DATA_TYPE_NAME,
            LENGTH,
            SCALE,
            OCCURRENCES,
            ROW_NUMBER() OVER (
                PARTITION BY COLUMN_NAME
                ORDER BY OCCURRENCES DESC, LENGTH DESC
            ) AS RN
        FROM (
            SELECT
                COLUMN_NAME,
                DATA_TYPE_NAME,
                LENGTH,
                SCALE,
                COUNT(*) AS OCCURRENCES
            FROM SYS.TABLE_COLUMNS
            WHERE TABLE_NAME NOT LIKE '%V_%'
            GROUP BY
                COLUMN_NAME,
                DATA_TYPE_NAME,
                LENGTH,
                SCALE)
        )
    WHERE RN = 1
    """
    hana_conn.connect()

    rows = hana_conn.query_list(query)

    metadata_map = {}

    for row in rows:
        col = row["COLUMN_NAME"]
        dtype = row["DATA_TYPE_NAME"]
        length = row["LENGTH"]
        scale = row["SCALE"]

        if dtype in ["NVARCHAR", "VARCHAR", "CHAR"]:
            metadata_map[col.upper()] = f"VARCHAR({length})"

        elif dtype == "DECIMAL":
            metadata_map[col.upper()] = f"DECIMAL({length},{scale})"

        elif dtype in ["INTEGER", "BIGINT"]:
            metadata_map[col.upper()] = "INTEGER"

        elif dtype == "DATE":
            metadata_map[col.upper()] = "DATE"

        elif dtype == "TIMESTAMP":
            metadata_map[col.upper()] = "TIMESTAMP"

        elif dtype == "SECONDDATE":
            metadata_map[col.upper()] = "SECONDDATE"

        else:
            metadata_map[col.upper()] = dtype

    return metadata_map

@lru_cache(maxsize=1)
def get_hana_metadata_cached(hana_conn):
    if not hasattr(app, "hana_metadata_cache"):
        return load_metadata_map(hana_conn)

def detect_hana_type(series: pd.Series):
    # Drop nulls for analysis
    s = series.dropna()

    # If empty column
    if s.empty:
        return "NVARCHAR(255)"

    # -------------------------
    # INTEGER
    # -------------------------
    if pd.api.types.is_integer_dtype(s):
        return "INTEGER"

    # -------------------------
    # DECIMAL
    # -------------------------
    if pd.api.types.is_float_dtype(s):
        max_val = s.abs().max()
        precision = len(str(int(max_val))) + 5   # buffer
        scale = 5
        return f"DECIMAL({precision},{scale})"

    # -------------------------
    # DATE / TIMESTAMP
    # -------------------------
    if pd.api.types.is_datetime64_any_dtype(s):
        # Check if time exists
        if (s.dt.time != pd.Timestamp("00:00:00").time()).any():
            return "SECONDDATE"   # or TIMESTAMP
        else:
            return "DATE"

    # -------------------------
    # STRING ANALYSIS
    # -------------------------
    if pd.api.types.is_object_dtype(s):

        # Try detect datetime in string
        try:
            parsed = pd.to_datetime(s, errors='raise')
            if (parsed.dt.time != pd.Timestamp("00:00:00").time()).any():
                return "SECONDDATE"
            return "DATE"
        except:
            pass

        # Try detect numeric stored as text
        if s.astype(str).str.match(r'^-?\d+$').all():
            return "INTEGER"

        if s.astype(str).str.match(r'^-?\d+\.\d+$').all():
            return "DECIMAL(15,5)"

        # Otherwise treat as string
        max_len = s.astype(str).str.len().max()

        if max_len <= 5000:
            return f"NVARCHAR({max_len})"
        else:
            return "NCLOB"

    # Default fallback
    return "NVARCHAR(500)"

def parse_hana_format(fmt):

    if fmt is None:
        return "NVARCHAR(8)"

    raw = str(fmt).upper().strip()

    # =====================================================
    # 1. EXTRACT BASE TYPE + INSTRUCTION FROM SAME STRING
    # =====================================================

    instruction = raw
    fmt_clean = raw

    # =====================================================
    # 2. VARCHAR OVERRIDES
    # =====================================================

    # VARCHAR (assign X characters ...)
    match = re.search(r"VARCHAR.*ASSIGN\s*(\d+)\s*CHAR", raw)
    if match:
        return f"VARCHAR({match.group(1)})"

    match = re.search(r"ASSIGN\s*(\d+)\s*CHAR", raw)
    if match:
        return f"VARCHAR({match.group(1)})"

    # plain VARCHAR fallback
    if "VARCHAR" in raw:
        return "VARCHAR(30)"

    # =====================================================
    # 3. NUMERIC RULES
    # =====================================================

    if "NUMERIC" in raw or "DECIMAL" in raw:

        # no decimal override
        if any(x in raw for x in [
            "NO DECIMAL",
            "NO DECIMALS",
            "NO DECIMAL PLACES",
            "WITHOUT DECIMAL"
        ]):
            return "INTEGER"

    # =====================================================
    # 2. EXTRACT "X DECIMAL PLACES"
    # =====================================================
    match = re.search(r"(\d+)\s*DECIMAL", raw)
    if match:
        scale = int(match.group(1))

        # default precision if not specified
        precision = 18  # safe SAP HANA default

        return f"DECIMAL({precision},{scale})"

    # =====================================================
    # 4. DATE / TIME
    # =====================================================

    if "SECONDDATE" in raw:
        return "SECONDDATE"

    if "TIMESTAMP" in raw:
        return "TIMESTAMP"

    if "DATE" or 'Date' in raw:
        return "DATE"

    # =====================================================
    # 5. DEFAULT
    # =====================================================

    return "NVARCHAR(8)"

def clean_name(name):
    return re.sub(r'[^A-Za-z0-9_]', '', name).upper()

def get_hana_type(fieldname, format_value, metadata_map=None):

    fieldname = clean_name(fieldname)

    if metadata_map is None:
        metadata_map = {}

    # 1. RAG override (optional)
    meta = metadata_map.get(fieldname, {})
    if isinstance(meta, dict) and "type" in meta:
        return meta["type"]

    # 2. parse FORMAT directly (single source of truth)
    return parse_hana_format(format_value)

def get_db_hana_type(fieldname, format_value, metadata_map=None):

    fieldname = clean_name(fieldname)

    if metadata_map is None:
        metadata_map = {}

    # =====================================================
    # 1. RAG / EXISTING SCHEMA (HIGHEST PRIORITY)
    # =====================================================
    if fieldname in metadata_map:
        return metadata_map[fieldname]

    # =====================================================
    # 2. FORMAT PARSING (FALLBACK ONLY)
    # =====================================================
    return parse_hana_format(format_value)

def generate_table_from_metadata(df, full_table_name, metadata_map):
    """
    Generate clean SAP HANA CREATE TABLE from uploaded metadata
    """

    columns = []

    # max length for alignment (clean)
    max_len = max(len(clean_name(r["FIELDNAME"])) for _, r in df.iterrows())

    for _, row in df.iterrows():

        fieldname = clean_name(row["FIELDNAME"]).replace('"', '')
        hana_type = get_hana_type(fieldname, row["FORMAT"], metadata_map)

        # -----------------------------
        # CLEAN COLUMN FORMAT
        # -----------------------------
        col_sql = f'"{fieldname}"'

        # spacing only for readability (NOT inside quotes)
        spacing = " " * (max_len - len(fieldname) + 2)

        col_sql = f'    "{fieldname}"'.ljust(max_len + 6) + f' {hana_type}'

        columns.append(col_sql)

    # clean join
    columns = sorted(columns)
    columns_sql = ",\n".join(columns)

    # -----------------------------
    # FINAL SQL (NO TABS, NO LIST WRAP ISSUES)
    # -----------------------------
    create_sql = (
        f'CREATE COLUMN TABLE {full_table_name} (\n'
        f'{columns_sql}\n'
        f');'
    )

    return create_sql

def escape_sql(text):
    if not text:
        return ""
    return str(text).replace("'", "''")


def extract_format_details(fmt):
    if not fmt:
        return ""

    fmt = fmt.upper()

    # VARCHAR / NVARCHAR
    m = re.search(r'(VAR)?N?CHAR\((\d+)\)', fmt)
    if m:
        return f"Max {m.group(2)} characters."

    # DECIMAL
    m = re.search(r'DECIMAL\((\d+),(\d+)\)', fmt)
    if m:
        return f"{m.group(2)} decimal places."

    # INTEGER
    if "INT" in fmt:
        return "Integer value."

    # DATE
    if "DATE" in fmt:
        return "Date."

    # TIMESTAMP
    if "TIMESTAMP" in fmt:
        return "Timestamp."

    return ""

def generate_comment_sql(df, schema, table_name, table_comment=None):
    comments = []

    full_table = f"{schema}.{table_name}"

    # Table comment
    if table_comment:
        comments.append(
            f"COMMENT ON TABLE {full_table} IS '{escape_sql(table_comment)}';"
        )

    # Column comments
    for _, row in df.iterrows():
        col = row.get("FIELDNAME", "").strip()
        name_desc = str(row.get("NAME", "")).strip()
        fmt = row.get("FORMAT", "")

        if not col:
            continue

        extra = extract_format_details(fmt)

        comment_text = name_desc if name_desc else col

        if extra:
            comment_text += f". {extra}"

        comments.append(
                f"COMMENT ON COLUMN {full_table}.{col} IS '{comment_text}';"
        )
        """
        comments.append(
            f"EXEC 'COMMENT ON COLUMN {full_table}.{col} IS ''{escape_sql(comment_text)}''';"
        )
        """

    return "\n".join(comments)

def generate_full_hana_sql(df, full_table_name, metadata_map, schema, table_name, table_comment=None):
    
    # STEP 1: CREATE TABLE (reuse your existing function)
    ddl_sql = generate_table_from_metadata(df, full_table_name, metadata_map)

    # STEP 2: COMMENTS
    comment_sql = generate_comment_sql(df, schema, table_name, table_comment)

    # STEP 3: Combine everything cleanly
    final_sql = (
        "\n\n-- ============================================================\n"
        "-- STEP 1: CREATE TABLE\n"
        "-- ============================================================\n\n"
        f"{ddl_sql}\n\n"
        "-- ============================================================\n"
        "-- STEP 2: TABLE & COLUMN COMMENTS\n"
        "-- ============================================================\n\n"
        f"{comment_sql}"
    )

    return final_sql

def load_metadata_map_from_excel(df):
    metadata_map = {}

    for _, row in df.iterrows():
        field = clean_name(row.get("FIELDNAME", ""))
        fmt = row.get("FORMAT")

        if not field:
            continue

        metadata_map[field] = parse_hana_format(fmt)

    return metadata_map

def parse_metadata(text):
    text = safe_str(text)
    text = text.replace("\n", " ")
    text = text.replace("\xa0", " ")
    text = " ".join(text.split()).upper()
    result = {"schema": None, "table": None, "role": None}
    m = re.search(r"TABLE\s+NAMED\s+([A-Z0-9_]+\.[A-Z0-9_]+)", text)
    if m:
        schema, table = m.group(1).split(".")
        result["schema"] = schema
        result["table"] = table
    m = re.search(r"ROLE\s+([A-Z0-9_]+)", text)
    if m:
        result["role"] = m.group(1)
    return result

def clean_comment(header_text):
    text = safe_str(header_text)
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    text = text.replace("'", "''")

    return text.strip()

def extract_metadata_text(file, filename):
    filename = filename.lower()
    # -------------------------
    # XLSX (openpyxl)
    # -------------------------
    try:
        if filename.endswith(".xlsx"):
            wb = openpyxl.load_workbook(file, data_only=True)
            ws = wb.active
            return str(ws["A1"].value or "")
        # -------------------------
        # XLS (xlrd via pandas)
        # -------------------------
        elif filename.endswith(".xls"):
            df = pd.read_excel(file, engine="xlrd", header=None)
            return str(df.iloc[0, 0] or "")
        # -------------------------
        # CSV
        # -------------------------
        elif filename.endswith(".csv"):
            df = pd.read_csv(file, header=None, dtype=str, encoding="latin1")
            return str(df.iloc[0, 0] or "")
        return ""
    except Exception as e:
        raise HanaExecutionError(
            code="CSV_PARSE",
            message=str(e),
            sql=filename
    )

def find_header_row(df):
    for i in range(len(df)):
        row_text = " ".join(safe_str(v) for v in df.iloc[i].values).upper()
        if "FIELDNAME" in row_text and "FORMAT" in row_text:
            return i
    return None

def clean_name(val):
    return re.sub(r'[^A-Z0-9_]', '_', safe_str(val).upper())

def safe_str(val):
    return str(val or "").strip()

def table_exists(hana_conn, schema, table):
    sql = f"""
    SELECT COUNT(*) AS CNT
    FROM SYS.TABLES
    WHERE SCHEMA_NAME = '{schema}'
      AND TABLE_NAME = '{table}'
    """
    return hana_conn.query_list(sql)[0]["CNT"] > 0

def role_exists(hana_conn, role):
    sql = f"""
    SELECT COUNT(*) AS CNT
    FROM SYS.ROLES
    WHERE ROLE_NAME = '{role}'
    """
    return hana_conn.query_list(sql)[0]["CNT"] > 0

def clean_sql(stmt):
    lines = stmt.split("\n")
    cleaned = []

    for line in lines:
        line = line.strip()

        # remove SQL comments
        if line.startswith("--"):
            continue

        if line:
            cleaned.append(line)

    return " ".join(cleaned).strip()

def clean_sql_comment(text):
    if not text:
        return ""

    text = str(text)

    # remove new lines
    text = text.replace("\n", " ").replace("\r", " ")

    # collapse spaces
    text = " ".join(text.split())

    # escape single quotes for SQL
    text = text.replace("'", "''")

    return text

def generate_insert_sql(df, schema, table):

    cols = list(df.columns)

    sql_list = []

    for _, row in df.iterrows():

        values = []
        for c in cols:

            v = row[c]

            if pd.isna(v):
                values.append("NULL")
            elif isinstance(v, str):
                values.append(f"'{v.replace("'", "''")}'")
            else:
                values.append(f"'{v}'")

        sql = f"""
        INSERT INTO "{schema}"."{table}"
        ({", ".join([f'"{c}"' for c in cols])})
        VALUES ({", ".join(values)})
        """

        sql_list.append(sql)

    return sql_list

def map_row(cols, mapping):

    row = {}

    for i, col_def in enumerate(mapping):

        col_name = col_def["TARGET_COLUMN"]

        value = cols[i].strip() if i < len(cols) else None

        row[col_name] = value

    # system field
    row["LOAD_DATE"] = "CURRENT_DATE"

    return row

def get_hana_columns(hana_conn, schema, table):

    query = f"""
    SELECT COLUMN_NAME, DATA_TYPE_NAME, LENGTH, SCALE, IS_NULLABLE
    FROM SYS.TABLE_COLUMNS
    WHERE SCHEMA_NAME = '{schema}'
      AND TABLE_NAME = '{table}'
    ORDER BY POSITION
    """

    rows = hana_conn.query_list(query)

    return [
        {
            "name": r["COLUMN_NAME"],
            "type": r["DATA_TYPE_NAME"],
            "length": r["LENGTH"],
            "scale": r["SCALE"],
            "is_nullable": r["IS_NULLABLE"]
        }
        for r in rows
    ]

def is_valid_date(val):
    if val is None:
        return False

    val = str(val).strip()

    formats = [
        "%Y-%m-%d",              # DATE
        "%Y-%m-%d %H:%M:%S",     # TIMESTAMP (HANA standard)
        "%Y-%m-%dT%H:%M:%S",     # ISO format
        "%H:%M:%S",             # TIME only
        "%Y-%m-%d %H:%M"        # partial timestamp
    ]

    for fmt in formats:
        try:
            datetime.strptime(val, fmt)
            return True
        except:
            continue

    return False

def is_valid_int(val):
    try:
        int(val)
        return True
    except:
        return False

def is_valid_decimal(val):
    try:
        float(val)
        return True
    except:
        return False

def validate_dataframe(df, hana_metadata):

    valid_rows = []
    bad_rows = []

    for idx, row in df.iterrows():

        row_values = list(row)
        row_errors = []

        for col_idx, meta in enumerate(hana_metadata):

            col_name = meta["name"]
            col_type = meta["type"]
            val = row_values[col_idx] if col_idx < len(row_values) else ""

            # =========================
            # TYPE VALIDATION
            # =========================

            if col_type in ["DATE", "SECONDDATE", "TIMESTAMP"]:
                if val and not is_valid_date(val):
                    row_errors.append(f"{col_name}: invalid DATE → {val}")

            elif col_type in ["INTEGER", "BIGINT"]:
                if val and not is_valid_int(val):
                    row_errors.append(f"{col_name}: invalid INT → {val}")

            elif col_type in ["DECIMAL", "SMALLDECIMAL"]:
                if val and not is_valid_decimal(val):
                    row_errors.append(f"{col_name}: invalid DECIMAL → {val}")

        # =========================
        # SPLIT GOOD / BAD
        # =========================
        if row_errors:
            bad_rows.append({
                "row": idx,
                "errors": row_errors,
                "data": row_values
            })
        else:
            valid_rows.append(row_values)

    return valid_rows, bad_rows

def convert_value(v):
    if pd.isna(v):
        return None

    # strip whitespace
    if isinstance(v, str):
        v = v.strip()

        if v == "":
            return None

        return v  # keep as string (let HANA convert if needed)

    return v

def analyze_row_lengths(file_path, delimiter="|"):

    length_groups = defaultdict(list)
    bad_rows = []

    with open(file_path, "r", encoding="latin1", errors="ignore") as f:
        lines = [line.strip() for line in f if line.strip()]

    for idx, line in enumerate(lines, start=1):

        cols = next(csv.reader(io.StringIO(line), delimiter=delimiter))
        col_len = len(cols)

        length_groups[col_len].append(idx)

        # flag suspicious rows (adjust threshold if needed)
        if col_len < 13 or col_len > 16:
            bad_rows.append({
                "row": idx,
                "length": col_len,
                "raw": line
            })

    # =====================================================
    # PRINT SUMMARY
    # =====================================================
    print("\n📊 ROW LENGTH DISTRIBUTION:")
    for length, rows in sorted(length_groups.items()):
        print(f"Length {length}: {len(rows)} rows")

    # =====================================================
    # WRITE LOG FILE
    # =====================================================
    os.makedirs("logs", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    log_file = f"logs/row_length_analysis_{timestamp}.csv"

    with open(log_file, "w", newline="", encoding="utf-8") as f:

        writer = csv.writer(f)

        writer.writerow(["row", "length", "raw"])

        for b in bad_rows:
            writer.writerow([b["row"], b["length"], b["raw"]])

    print(f"\n📝 Log written to: {log_file}")

    return length_groups, bad_rows

def is_date(val):
    try:
        pd.to_datetime(val, errors="raise")
        return True
    except:
        return False
    
def get_default_value(col_type: str):
    if not col_type:
        return None

    t = col_type.upper()

    # =========================
    # STRING TYPES
    # =========================
    if "NVARCHAR" in t:
        return ""
    elif "VARCHAR" in t:
        return ""
    elif "CHAR" in t:
        return ""
    elif "NCHAR" in t:
        return ""
    elif "NCLOB" in t:
        return ""
    elif "CLOB" in t:
        return ""

    # =========================
    # INTEGER TYPES
    # =========================
    elif "TINYINT" in t:
        return 0
    elif "SMALLINT" in t:
        return 0
    elif "INTEGER" in t or "INT" in t:
        return 0
    elif "BIGINT" in t:
        return 0

    # =========================
    # DECIMAL / NUMERIC
    # =========================
    elif "DECIMAL" in t or "NUMERIC" in t or "FLOAT" in t or "REAL" in t:
        return 0.0

    # =========================
    # DATE / TIME TYPES
    # =========================
    elif "DATE" == t or t.endswith("DATE"):
        return None   # or datetime.date(1900, 1, 1)

    elif "TIME" in t and "TIMESTAMP" not in t:
        return None

    elif "TIMESTAMP" in t:
        return None   # or datetime.datetime(1900, 1, 1, 0, 0, 0)

    elif "SECONDDATE" in t:
        return None   # SAP HANA specific timestamp variant

    # =========================
    # BOOLEAN
    # =========================
    elif "BOOLEAN" in t:
        return False

    # =========================
    # FALLBACK
    # =========================
    return None

def find_emplid_index(row):
    for i, val in enumerate(row):
        if val and val.strip().isdigit() and len(val.strip()) >= 6:
            return i
    return None

def normalize_value(value, col_type):

    if value is None:
        return None

    value = value.strip()

    if value == "":
        if "INT" in col_type or "DECIMAL" in col_type:
            return 0
        return None

    try:
        if "INT" in col_type:
            return int(float(value))

        if "DECIMAL" in col_type:
            return float(value)

        return value  # VARCHAR / DATE

    except:
        return None

@app.route("/upload", methods=["GET", "POST"])
def upload_page():

    if request.method == "GET":
        return render_template(
            "upload_page.html",
            pipeline_ready=session.get("pipeline_ready", False)
        )
    
    # =====================================================
    # SAFE ACTION HANDLING (FIXES YOUR ERROR)
    # =====================================================
    action = ""
    if request.method == "POST":
        action = request.form.get("action", "")

    hana_conn = SAPHANADatabase(**hana_config)

    message = None
    table_comparison = []
    final_sql = None
    execution_report = []
    mode = "preview"

    # =====================================================
    # RESET (MUST BE FIRST)
    # =====================================================
    if action == "reset":
        session.pop("structure_path", None)
        session.pop("data_path", None)
        session["pipeline_ready"] = False
        session.pop("target_schema", None)
        session.pop("target_table", None)

        return render_template(
            "upload_page.html",
            message="🔄 Reset complete",
            pipeline_ready=False
        )

    # =====================================================
    # PREVIEW / EXECUTE (STRUCTURE FILE)
    # =====================================================
    if action in ["preview", "execute"]:

        structure_file = request.files.get("structure_file")

        if not structure_file or structure_file.filename == "":
            return render_template("upload_page.html", message="❌ Missing structure file")

        # -------------------------
        # SAVE STRUCTURE FILE
        # -------------------------
        structure_path = os.path.join("data", structure_file.filename)
        structure_file.save(structure_path)
        session["structure_path"] = structure_path
        structure_file.seek(0) 

        filename = structure_file.filename.lower()
        try:
            header_text = extract_metadata_text(structure_file, filename)
            structure_file.seek(0)
        except HanaExecutionError as e:
            return render_template(
                "upload_page.html",
                message=f"❌ [{e.code}] {e.message}",
                pipeline_ready=session.get("pipeline_ready", False)
        )

        # -------------------------
        # READ STRUCTURE FILE
        # -------------------------
        if filename.endswith(".xlsx"):
            df = pd.read_excel(structure_file, engine="openpyxl", dtype=str).fillna("")
        elif filename.endswith(".xls"):
            df = pd.read_excel(structure_file, engine="xlrd", dtype=str).fillna("")
        elif filename.endswith(".csv"):
            file_bytes = structure_file.read()
            if not file_bytes:
                return render_template("upload_page.html", message="❌ CSV file is empty or already consumed")
            df = pd.read_csv(io.StringIO(file_bytes.decode("latin1", errors="ignore")),header=None,
                dtype=str,engine="python")
        else:
            return render_template("upload_page.html", message="❌ Unsupported format")
        header_row = find_header_row(df)

        if header_row is None:
            return render_template("upload_page.html", message="❌ FIELDNAME header not found")

        df = df.iloc[header_row + 1:].copy()
        df = df.iloc[:, :3]
        df.columns = ["NAME", "FIELDNAME", "FORMAT"]
        df = df.fillna("")

        meta = parse_metadata(header_text)

        target_schema = clean_name(meta["schema"])
        target_table = clean_name(meta["table"])
        role = clean_name(meta["role"]) if meta["role"] else ""

        full_table_name = f'"{target_schema}"."{target_table}"'

        # =====================================================
        # STORE SESSION STATE (CRITICAL)
        # =====================================================
        session["target_schema"] = target_schema
        session["target_table"] = target_table
        session["pipeline_ready"] = True

        metadata_map = load_metadata_map_from_excel(df)
        hana_metadata = get_hana_metadata_cached(hana_conn)

        table_comparison = [
            {
                "column": col,
                "source_type": metadata_map.get(col),
                "hana_type": hana_metadata.get(col)
            }
            for col in metadata_map.keys()
        ]

        final_sql = generate_full_hana_sql(
            df,
            full_table_name,
            metadata_map,
            target_schema,
            target_table,
            clean_comment(header_text)
        )

        if role:
            final_sql += f"\nCREATE ROLE {role};"
            final_sql += f"\nGRANT SELECT ON {full_table_name} TO \"{role}\";"

        data_file = request.files.get("data_file")

        if data_file and data_file.filename:
            data_path = os.path.join("load", data_file.filename)
            data_file.save(data_path)
            session["data_path"] = data_path

        # =====================================================
        # EXECUTE MODE
        # =====================================================
        if action == "execute":
            mode = "execute"
            try:
                hana_conn.connect()

                for stmt in final_sql.split(";"):
                    stmt = stmt.strip()
                    if not stmt:
                        continue

                    try:
                        hana_conn.execute_sql(stmt)
                        execution_report.append({
                            "statement": stmt,
                            "status": "SUCCESS",
                            "message": "Executed"
                        })
                    except Exception as e:
                        execution_report.append({
                            "statement": stmt,
                            "status": "ERROR",
                            "message": str(e)
                        })

                hana_conn.close()
                message = "✅ Execution completed"

            except Exception as e:
                message = str(e)

            return render_template(
                "upload_page.html",
                final_sql=final_sql,
                table_data=table_comparison,
                execution_report=execution_report,
                mode="execute",
                message=message,
                pipeline_ready=session.get("pipeline_ready", False)
            )

        # =====================================================
        # PREVIEW MODE
        # =====================================================
        return render_template(
            "upload_page.html",
            final_sql=final_sql,
            table_data=table_comparison,
            mode="preview",
            message="Preview generated",
            pipeline_ready=session.get("pipeline_ready", False)
        )

    # =====================================================
    # LOAD DATA
    # =====================================================
    elif action == "load":
        target_schema = session.get("target_schema")
        target_table = session.get("target_table")

        if not session.get("pipeline_ready", False):
            return render_template(
                "upload_page.html",
                message="❌ Run Preview or Execute first",
                pipeline_ready=False
            )

        data_path = session.get("data_path")

        if not data_path or not os.path.exists(data_path):
            return render_template(
                "upload_page.html",
                message="❌ No data file found",
                pipeline_ready=True
            )

        execution_report = []

        try:
            hana_conn.connect()

            # =========================
            # 1. HANA METADATA
            # =========================
            hana_metadata = get_hana_columns(hana_conn, target_schema, target_table)
            hana_columns = [c["name"].strip().upper() for c in hana_metadata]
            col_types = {
                c["name"].strip().upper(): c["type"].upper()
                for c in hana_metadata
            }

            # =========================
            # 2. FILE STRUCTURE (POSITIONAL SOURCE OF TRUTH)
            # =========================
            file_columns = [
                "OPDIV",
                "STAFFDIV",
                "ORG_CD",
                "EMPLID",
                "EMP_NAME",
                "SUPV_NAME",
                "TW_HRS_WORKED_YTD",
                "TS_HRS_WORKED_YTD",
                "TS_HRS_ALLOWED_YTD",
                "TS_HRS_REMAIN_YTD",
                "TS_HRS_WARN_THRSHLD_YTD",
                "TS_HRS_OVER_YTD",
                "PP_END_DT",
                "PP_END_YEAR",
                "PP_YEAR_NUM",
                "LOAD_DT"
            ]

            file_index = {col: i for i, col in enumerate(file_columns)}
            emplid_expected_pos = file_columns.index("EMPLID")
            EXPECTED = len(file_columns)

            # =========================
            # 2. READ FILE
            # =========================
            filename = data_path.lower()
            rows = []
            
            if filename.endswith(".xlsx"):
                df_raw = pd.read_excel(data_path, engine="openpyxl", dtype=str)
                rows = df_raw.fillna("").values.tolist()

            elif filename.endswith(".xls"):
                df_raw = pd.read_excel(data_path, engine="xlrd", dtype=str)
                rows = df_raw.fillna("").values.tolist()

            elif filename.endswith(".csv") or filename.endswith(".txt"):
                with open(data_path, "r", encoding="latin1", errors="ignore") as f:
                    lines = [line.strip() for line in f if line.strip()]

                for line in lines:
                    cols = next(csv.reader(io.StringIO(line), delimiter="|"))
                    rows.append(cols)

            else:
                return render_template(
                    "upload_page.html",
                    message="❌ Unsupported format",
                    pipeline_ready=True
                )

            # =========================
            # 3. PROCESS ROWS (SAFE POSITIONAL MAPPING)
            # =========================

            clean_rows = []
            bad_rows = []

            # =========================
            # 3. SINGLE SAFE LOOP
            # =========================
            for idx, row in enumerate(rows, start=1):

                row = [c.strip() if c else None for c in row]
                aligned = [None] * EXPECTED
                emplid_pos = find_emplid_index(row)

                if emplid_pos is None:
                    bad_rows.append({"row": idx, "reason": "EMPLID not found", "data": row})
                    continue

                shift = emplid_pos - emplid_expected_pos

                for i, val in enumerate(row):
                    target = i - shift
                    if 0 <= target < EXPECTED:
                        aligned[target] = val

                final_row = []

                for col in hana_columns:

                    # system column override
                    if col == "LOAD_DT":
                        final_row.append(datetime.now())
                        continue

                    file_pos = file_index.get(col)
                    raw_val = aligned[file_pos] if file_pos is not None else None
                    col_type = col_types.get(col, "")
                    value = normalize_value(raw_val, col_type)

                    final_row.append(value)

                clean_rows.append(tuple(final_row))

            # =========================
            # 4. LOG BAD ROWS
            # =========================
            if bad_rows:
                os.makedirs("logs", exist_ok=True)
                log_file = f"logs/reject_rows_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                pd.DataFrame(bad_rows).to_csv(log_file, index=False)
                print(f"📝 Bad rows logged: {log_file}")

            # =========================
            # 5. INSERT
            # =========================
            cols_sql = ", ".join([f'"{c}"' for c in hana_columns])
            placeholders = ", ".join(["?"] * len(hana_columns))

            sql = f'''
                INSERT INTO "{target_schema}"."{target_table}"
                ({cols_sql})
                VALUES ({placeholders})
            '''

            conn = hana_conn.connection
            cursor = conn.cursor()

            batch_size = 1000
            total_inserted = 0

            for i in range(0, len(clean_rows), batch_size):

                batch = clean_rows[i:i + batch_size]

                cursor.executemany(sql, batch)
                total_inserted += len(batch)

                execution_report.append({
                    "batch": f"{i}-{i+len(batch)}",
                    "status": "SUCCESS",
                    "rows": len(batch)
                })

            conn.commit()
            hana_conn.close()

            return render_template(
                "upload_page.html",
                execution_report=execution_report,
                mode="execute",
                message=f"✅ Batch load completed: {total_inserted} rows inserted",
                pipeline_ready=True,
                target_schema=target_schema,
                target_table=target_table
            )

        except Exception as e:
            import traceback
            print(traceback.format_exc())

            return render_template(
                "upload_page.html",
                message=f"❌ Load failed: {str(e)}",
                pipeline_ready=True
            )

# ---------------------------------------------------------
# RECONCILE SINGLE ROW (BUTTON ACTION)
# ---------------------------------------------------------

def normalize_type(col):

    dtype = str(col.get("type", "")).upper()
    length = col.get("length")
    precision = col.get("precision")
    scale = col.get("scale")

    # CHAR TYPES
    if "CHAR" in dtype or "VARCHAR" in dtype:
        return f"VARCHAR({length or 30})"

    # NUMBER TYPES
    elif "NUMBER" in dtype or "INTEGER" in dtype:

        if precision and scale is not None:
            return f"DECIMAL({precision},{scale})"

        elif precision:
            return f"DECIMAL({precision},0)"

        else:
            return "INTEGER"

    # DECIMAL TYPES
    elif "DECIMAL" in dtype or "NUMERIC" in dtype:

        if precision and scale is not None:
            return f"DECIMAL({precision},{scale})"

        return "DECIMAL"

    # DATE
    elif "DATE" in dtype:
        return "DATE"

    # TIMESTAMP
    elif "TIMESTAMP" in dtype:
        return "TIMESTAMP"

    # FALLBACK
    return dtype

def compare_columns(oracle_cols, hana_cols):
    oracle_map = {}
    hana_map = {}

    # -----------------------------
    # Oracle normalize
    # -----------------------------
    for col in oracle_cols:
        name = col[0].upper()
        dtype = col[1].upper()
        length = col[2] if len(col) > 2 else None
        precision = col[3]
        scale = col[4]
        nullable = col[5]

        oracle_map[name] = {
            "type": dtype,
            "length": length,
            "precision": precision,
            "scale": scale,
            "nullable": nullable
        }

    # -----------------------------
    # HANA normalize
    # -----------------------------
    for col in hana_cols:
        name = col["name"].upper()
        dtype = col["type"].upper()

        hana_map[name] = {
            "type": dtype,
            "length": col.get("length"),
            "precision": col.get("length"),
            "scale": col.get("scale"),
            "nullable": col.get("nullable")
        }

    oracle_order = [c[0].upper() for c in oracle_cols]
    hana_order = [c["name"].upper() for c in hana_cols]

    missing_in_hana = []
    extra_in_hana = []
    type_mismatch = []
    nullable_mismatch = []
    position_mismatch = []

    # -----------------------------
    # POSITION (FIXED)
    # -----------------------------
    hana_index = {col: i for i, col in enumerate(hana_order)}

    for i, col in enumerate(oracle_order):
        if col in hana_index:
            if i != hana_index[col]:
                position_mismatch.append({
                    "column": col,
                    "oracle_position": i,
                    "hana_position": hana_index[col]
                })

    # -----------------------------
    # COMPARE ORACLE → HANA
    # -----------------------------
    for col, o in oracle_map.items():
        if col not in hana_map:
            missing_in_hana.append(col)
        else:
            h = hana_map[col]

            if normalize_type(o) != normalize_type(h):
                type_mismatch.append({
                    "column": col,
                    "oracle": normalize_type(o),
                    "hana": normalize_type(h)
                })

            if o["nullable"] != h["nullable"]:
                nullable_mismatch.append({
                    "column": col,
                    "oracle": o["nullable"],
                    "hana": h["nullable"]
                })

    # -----------------------------
    # HANA extra columns
    # -----------------------------
    for col in hana_map:
        if col not in oracle_map:
            extra_in_hana.append(col)

    return {
        "missing_in_hana": missing_in_hana,
        "extra_in_hana": extra_in_hana,
        "type_mismatch": type_mismatch,
        "nullable_mismatch": nullable_mismatch,
        "position_mismatch": position_mismatch
    }
    
def generate_fix_sql(schema, table, diff, oracle_cols):

    oracle_map = {
        col[0].upper(): {
            "type": col[1],
            "length": col[2] if len(col) > 2 else None,
            "precision": col[3] if len(col) > 3 else None,
            "scale": col[4],
            "nullable": col[5]
        }
        for col in oracle_cols
    }

    statements = []

    # -----------------------------
    # ADD missing columns
    # -----------------------------
    for col in diff["missing_in_hana"]:
        oc = oracle_map[col]
        hana_type = oracle_to_hana_type(oc)

        statements.append(
            f'ALTER TABLE "{schema}"."{table}" ADD ("{col}" {hana_type});'
        )

    # -----------------------------
    # DROP candidates (SAFE AS COMMENT ONLY)
    # -----------------------------
    for col in diff["extra_in_hana"]:
        statements.append(
            f'-- DROP candidate: {col} (REVIEW REQUIRED)'
        )

    # -----------------------------
    # TYPE MISMATCH
    # -----------------------------
    for x in diff["type_mismatch"]:
        oc = oracle_map[x["column"]]
        hana_type = oracle_to_hana_type(oc)

        statements.append(
            f'ALTER TABLE "{schema}"."{table}" ALTER ("{x["column"]}" {hana_type});'
        )

    return statements

def oracle_to_hana_type(col):

    dtype = col["type"].upper()
    length = col.get("length")
    precision = col.get("precision")

    if "CHAR" in dtype:
        return f"VARCHAR({length or 30})"

    elif "NUMBER" in dtype:

        if precision:
            return f"DECIMAL({precision},0)"
        else:
            return "INTEGER"

    elif "DATE" in dtype:
        return "DATE"

    else:
        return "VARCHAR(255)"
    
def requires_rebuild(diff):
    position_mismatches = diff.get("position_mismatch", [])
    if not position_mismatches:
        return False
    for x in position_mismatches:
        oracle_pos = x["oracle_position"]
        hana_pos = x["hana_position"]

        # ONLY rebuild if column is NOT just appended at end
        if hana_pos < oracle_pos:
            return True  # inserted in middle → structural shift
    return False

# =====================================================
# COMPARE ROUTE
# =====================================================

@app.route('/compare', methods=['GET', 'POST'])
@login_required
def compare():

    schema = request.form.get("schema") or request.args.get("schema")
    table_filter = request.form.get("table") or request.args.get("table")
    action = request.form.get("action") or request.args.get("action")

    if not schema or not table_filter:
        return render_template("compare.html", results=[])

    oracle_cols = get_table_metadata(schema, table_filter)

    hana_conn = SAPHANADatabase(**hana_config)
    hana_conn.connect()

    hana_cols = get_hana_columns(hana_conn, schema, table_filter)

    diff = compare_columns(oracle_cols, hana_cols)

    if requires_rebuild(diff):
        strategy = "REBUILD_TABLE"
    else:
        strategy = "ALTER_ONLY"

    fix_sql = generate_fix_sql(schema, table_filter, diff, oracle_cols)

    oracle_count = len(oracle_cols)
    hana_count = len(hana_cols)

    results = [{
        "schema": schema,
        "table": table_filter,
        "diff": diff,
        "strategy": strategy,
        "fix_sql": fix_sql,
        "oracle_count": oracle_count,
        "hana_count": hana_count
    }]


    # APPLY FIX
    if action == "apply_fix":
        for stmt in fix_sql:
            hana_conn.execute_sql(stmt)

        return render_template(
            "compare.html",
            results=results,
            message="FIXES APPLIED SUCCESSFULLY"
        )
    
    # EXPORT
    if action == "export":
        try:
            pd.set_option('display.max_colwidth', None)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"{schema}_{table_filter}_schema_migration_{timestamp}.xlsx"

            export_dir = "exports"
            os.makedirs(export_dir, exist_ok=True)

            file_path = os.path.join(export_dir, file_name)

            compare_rows = []

            for item in diff.get("type_mismatch", []):
                compare_rows.append({
                    "COLUMN": item["column"],
                    "ORACLE_TYPE": item["oracle"],
                    "HANA_TYPE": item["hana"],
                    "ISSUE": "TYPE_MISMATCH"
            })

            for col in diff.get("missing_in_hana", []):
                compare_rows.append({
                    "COLUMN": col,
                    "ORACLE_TYPE": "",
                    "HANA_TYPE": "",
                    "ISSUE": "MISSING_IN_HANA"
            })

            for col in diff.get("extra_in_hana", []):
                compare_rows.append({
                    "COLUMN": col,
                    "ORACLE_TYPE": "",
                    "HANA_TYPE": "",
                    "ISSUE": "EXTRA_IN_HANA"
            })

            df_compare = pd.DataFrame(compare_rows)

            strategy = "REBUILD_TABLE" if requires_rebuild(diff) else "ALTER_ONLY"
            fix_sql = generate_fix_sql(schema, table_filter, diff, oracle_cols)

            df_summary = pd.DataFrame([{
                "SCHEMA": schema,
                "TABLE": table_filter,
                "STRATEGY": strategy,
                "STATEMENTS": len(fix_sql)
            }])

            df_actions = pd.DataFrame([
                {
                    "SCHEMA": schema,
                    "TABLE": table_filter,
                    "SQL": stmt,
                    "STATUS": "PENDING",
                    "STRATEGY": strategy
                }
                for stmt in fix_sql
            ])

            df_sql = pd.DataFrame(fix_sql, columns=["SQL"])

            with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
                df_summary.to_excel(writer, index=False, sheet_name="SUMMARY")
                df_compare.to_excel(writer, index=False, sheet_name="COMPARE")
                df_actions.to_excel(writer, index=False, sheet_name="DDL_ACTIONS")
                df_sql.to_excel(writer, index=False, sheet_name="SQL")

            message = f"""
                EXPORT SUCCESSFUL
                TABLE: {schema}.{table_filter}
                FILE: {file_name}
                LOCATION: {"EXPORTS"}
            """

            return render_template(
                "compare.html",
                results=results,
                schema=schema,
                table=table_filter,
                message=message
            )

        except Exception as e:
            return render_template(
                "compare.html",
                results=results,
                message=f"EXPORT FAILED: {str(e)}"
            )
        
    # DEFAULT RETURN (THIS WAS MISSING / BROKEN BEFORE)
    return render_template(
        "compare.html",
        results=results,
        schema=schema,
        table=table_filter
    )
    

@app.route('/reconcile/', methods=['POST'])
@login_required
def reconcile():

    if not has_permission('RECONCILE'):
        abort(403)

    owner = request.form.get("owner")
    table_name = request.form.get("table_name")
    virtual_table = f"v_{owner}.v_{table_name}"
    
    count = int(request.form.get("differences"))

    hana_conn = SAPHANADatabase(**hana_config)

    try:
        hana_conn.connect()
    except Exception as e:
        logging.error(f"Error SAP in connection {e}")
        exit(0)
                                  
    try:
        # SAP HANA procedure that handles comparison between tables
        procedure_name = "HISTDBA.dynamic_comparison_date_adjustment"

        hana_select , hana_where, hana_dups_where, skipped_schema, skipped_table = process_table(owner, table_name)

        fileSAP = NameGenerator(r"C:\python\Reports\log", f"{owner}.{table_name}") 
        recordsHanaMissing = CSVHandler(fileSAP.getName())

        RetrieveOracleRecords_config = {
             "fileName":fileSAP.getName(),
            "output_directory":fileSAP.getDirectory(),
            "oracle_config":oracle_config,
            "source_table":table_name,
            "source_schema":owner,
            "target_table":skipped_table,
            "target_schema":skipped_schema
        }

        if count > 0:
            # call stored procedure 
            headers, mismatched_records = hana_conn.execute_proc_compare(procedure_name, f"v_{owner}.v_{table_name}", f"{owner}.{table_name}", hana_select, hana_where, count) 
            
            if len(mismatched_records) > 0:
                recordsHanaMissing.write_to_text_file(headers,mismatched_records, delimiter=",")
                setProcesRecords = RetrieveOracleRecords(**RetrieveOracleRecords_config)
                
                try:
                  setProcesRecords.setConnection() 
                  where_clauses = setProcesRecords.process_data()
                except Exception as e: 
                  safe_error = str(e).encode('utf-8', errors='replace').decode('utf-8')
                  logging.error(f"Error processing Oracle records: {safe_error}")
                  exit(0)
                
                copy_to_hana(where_clauses, owner, table_name, skipped_schema, skipped_table)
                
                key = f"{owner}.{table_name}"
                full_path = os.path.join(fileSAP.getDirectory(), fileSAP.fileName) 
                   
                outstanding_files = session.get('outstanding_files', {})
                outstanding_files[key] = full_path
                session['outstanding_files'] = outstanding_files
                session['show_once'] = True
        elif count < 0:
            headers, dups = process_duplicates(hana_conn, hana_select, f'{owner}.{table_name}', hana_dups_where)

            if len(dups) > 0:            
                try:
                    setProcesRecords = RetrieveOracleRecords(**RetrieveOracleRecords_config)
                    setProcesRecords.setConnection()
                    where_clauses = setProcesRecords.DeleteRecords(skipped_schema, skipped_table)
                    delete_from_hana(hana_conn, table_name, where_clauses)
                    copy_to_hana(where_clauses)
                except Exception as e: 
                    logging.error(f"Error processing duplicates: {e}")  
                    exit()            
            else:
                logging.info(f"No duplicates found in table '{table_name}'.")

            # Compare tables and get mismatched records from records missing in HANA but not in Oracle
            # with source and target compare tables

            table_name, virtual_table =  virtual_table, f'{owner}.{table_name}' 
            
            headers, mismatched_records = hana_conn.execute_proc_compare(procedure_name, virtual_table, table_name, hana_select, hana_where, abs(count))
                        
            if len(mismatched_records) > 0:
                fileSAPDEL = NameGenerator(r"C:\python\Reports\log", f"{skipped_schema}.{skipped_table}")
                recordsHanaMissing = CSVHandler(fileSAPDEL.getName())
                recordsHanaMissing.write_to_text_file(headers,mismatched_records, delimiter=",")
                  
                setProcesRecords = RetrieveOracleRecords(**RetrieveOracleRecords_config)
                try:
                  setProcesRecords.setConnection()
                  
                  where_clauses = setProcesRecords.DeleteRecords(fileSAPDEL.fileName, skipped_schema, skipped_table)
                  virtual_table, table_name = table_name, virtual_table
                      
                  key = f"{owner}.{table_name}"
                  full_path = os.path.join(fileSAP.getDirectory(), fileSAPDEL.fileName) 
                   
                  outstanding_files = session.get('outstanding_files', {})
                  outstanding_files[key] = full_path
                  session['outstanding_files'] = outstanding_files
                  session['show_once'] = True
                  
                  delete_from_hana(hana_conn, table_name, where_clauses)

                except Exception as e: 
                  logging.error(f"Error deleting Oracle missing records: {e}") 
    except Exception as e:
        return f"Reconcile failed: {str(e)}"
    finally:
        hana_conn.close()

    return redirect(url_for("report_page"))

def main():  
    app.run(debug=True, port=5001)

if __name__ == "__main__":
    main()