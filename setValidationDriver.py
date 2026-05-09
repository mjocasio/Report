from GeneralUtilityComparison import GeneralUtilityComparison 
from NameGenerator import NameGenerator
from CSVHandler import CSVHandler
import os
from dotenv import find_dotenv, load_dotenv

def main():
    skipped_schema = "histdba"

    '''    
    inTable = ["ehrp.ps_personal_data","ehrp.ps_gvt_pers_data","ehrp.ps_addresses","ehrp.ps_gvt_job", "ehrp.ps_names","ehrp.ps_gvt_par_remarks","ehrp.ps_gvt_employment"]
    
    vTable = ["v_ehrp.v_ps_personal_data","v_ehrp.v_ps_gvt_pers_data","v_ehrp.v_ps_addresses","v_ehrp.v_ps_gvt_job","v_ehrp.v_ps_names","v_ehrp.v_ps_gvt_par_remarks","v_ehrp.v_ps_gvt_employment"]
    
    skipp = ["skipped_personaldata_recs","skipped_gvtpersdata_recs","Skipped_Ps_Addresses","skipped_gvtjob_recs","skipped_ps_names_recs","Skipped_Gvtparremarks_Tbl","skipped_employment_recs"] 
    '''

    inTable = ["ehrp.ps_gvt_par_remarks"]
    vTable = ["v_ehrp.v_ps_gvt_par_remarks"]
    skipp = ["Skipped_Gvtparremarks_Tbl"] 

    dotenv_path = find_dotenv()
    load_dotenv(dotenv_path)

    userName = os.getenv("SAPuserName")
    password = os.getenv("SAPpassword")
    hostName = os.getenv("SAPhostName")
    port = os.getenv("SAPport")

    # SAP HANA connection details
    hana_config = {
        "username": userName,
        "password": password,
        "hostName": hostName,
        "port": port
    }   

    userName = os.getenv("ORAuserName")
    password = os.getenv("ORApassword")
    hostName = os.getenv("ORAhostName")
    port = os.getenv("ORAport")
    service_name = os.getenv("ORAService_name")

    # Oracle connection details
    oracle_config = {
        "username": userName,
        "password": password,
        "hostName": hostName,
        "port": port,
        "service_name": service_name
    }

    for inRec in zip(inTable, vTable, skipp):
        hana_table = inRec[0]
        fileSAP = NameGenerator(r"C:\python\ReportValidationHana\log", hana_table) 

        skipped_table = inRec[2]
        GeneralUtilityComparison_config = {
            "fileName":fileSAP.getName(),
            "output_directory":fileSAP.getDirectory(),
            "hana_config":hana_config,
            "oracle_config":oracle_config,
            "skipped_schema":skipped_schema,
            "skipped_table":skipped_table,
        }
    
        hana_comparison = GeneralUtilityComparison(**GeneralUtilityComparison_config)
        virtual_table = inRec[1]
            
        if hana_comparison.process_tables(hana_table, virtual_table) == 0:
            continue
                   
if __name__ == "__main__":
    main() 
