from . import FMSDataStructure
import sharedBE as be
from enum import Enum, auto
import os
import json
from ._version import version

# ----------------------------------------------------------------------------------------------------------------------------------- #
# --------------------------------------- Logic for the Collection of All the Data -------------------------------------------------- #
# ----------------------------------------------------------------------------------------------------------------------------------- #
class DataParts(Enum):
    CERTIFICATIONS = auto()
    LPT = auto()
    FMS_ACCEPTANCE = auto()
    FMS_FUNCTIONAL = auto()
    TV_ASSEMBLY = auto()
    TV_ELECTRICAL = auto()
    TV_TEST = auto()
    HPIV = auto()
    FR = auto()
    MANIFOLD = auto()
    ALL = auto()
    TV_TVAC = auto()
    MISC = auto()

# Get all certifications will be deprecated once the ExactSQL class is fully implemented, and is able to replace the level of traceability 
# this function offers.

# def collect_certification_data(fms_data: FMSDataStructure, certifications_path: str, data_parts: DataParts = DataParts.ALL) -> None:
#     if data_parts == DataParts.ALL or data_parts == DataParts.CERTIFICATIONS:
#         print("Getting Certifications")
#         fms_data.get_all_certifications(local_certifications=certifications_path)

def collect_tv_data(fms_data: FMSDataStructure, tv_assembly: str, tv_summary: str,
                    status_file: str, electrical_data: str, tv_test_path: str, data_parts: DataParts = DataParts.ALL) -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.TV_ASSEMBLY:
        print("Getting TV Assembly Data")
        fms_data.add_tv_assembly_data(tv_assembly=tv_assembly, tv_summary=tv_summary, status_file=status_file)
    if data_parts == DataParts.ALL or data_parts == DataParts.TV_ELECTRICAL:
        print("Getting TV Electrical Data")
        fms_data.add_tv_electrical_data(electrical_data=electrical_data)
    if data_parts == DataParts.ALL or data_parts == DataParts.TV_TEST:
        print("Getting TV Test Results")
        fms_data.add_tv_test_results(tv_test_path=tv_test_path)

def collect_tv_tvac_data(fms_data: FMSDataStructure, tvac_path: str, tv_id: int = 1, data_parts: DataParts = DataParts.ALL) -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.TV_TVAC:
        print("Getting TV TVAC Data")
        for cycle_folder in os.listdir(tvac_path):
            folder_path = os.path.join(tvac_path, cycle_folder)

            if not "cycles" in cycle_folder.lower():
                continue

            cycles = int(cycle_folder.split()[0])
            if cycles == 1000:
                continue

            if cycles == 0:
                cycles = 1000

            print(cycles)

            for csv_file in os.listdir(folder_path):
                if not os.path.basename(csv_file).endswith("csv") and not "data" in csv_file.lower():
                    continue
                
                full_csv_path = os.path.join(folder_path, csv_file)
                tv_sql = fms_data.tv_sql
                tv_sql.cycle_amount = cycles
                tv_sql.tv_id = tv_id
                tv_sql.update_tv_tvac_results(csv_file = full_csv_path, cycle_amount = cycles)

def collect_lpt_data(fms_data: FMSDataStructure, lpt_path: str, data_parts: DataParts = DataParts.ALL) -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.LPT:
        print("Getting LPT Calibration Data")
        fms_data.add_lpt_calibration_data(lpt_path=lpt_path)

def collect_hpiv_data(fms_data: FMSDataStructure, hpiv_path: str, data_parts: DataParts = DataParts.ALL) -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.HPIV:
        print("Getting HPIV Data")
        fms_data.add_hpiv_data(hpiv_path=hpiv_path)

def collect_hpiv_data(fms_data: FMSDataStructure, hpiv_data_packages: list, data_parts: DataParts = DataParts.ALL) -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.HPIV:
        print("Getting HPIV Data")
        fms_data.add_hpiv_data(hpiv_data_packages=hpiv_data_packages)

def collect_fr_data(fms_data: FMSDataStructure, anode_fr_path: str, cathode_fr_path: str, data_parts: DataParts = DataParts.ALL) -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.FR:
        print("Getting FR Test Data")
        fms_data.add_fr_test_data(anode_fr_path=anode_fr_path, cathode_fr_path=cathode_fr_path)

def add_fr_testing_tools(fms_data: FMSDataStructure, data_parts: DataParts = DataParts.ALL, tools_path: str = "useful_data/trs_tools_fr.json") -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.MISC:
        print("Getting FR Tools")
        tools = {}
        all_tools = []
        path = os.path.join(fms_data.absolute_data_dir, tools_path)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                tools = json.load(f)
        if tools:
            all_tools: list[dict[str, str]] = []
            for i in tools:
                all_tools.extend(tools[i])

            be.tools.update_test_tools(tools = all_tools)
            be.tools.print_table()

def add_fms_testing_tools(fms_data: FMSDataStructure, data_parts: DataParts = DataParts.ALL, tools_path: str = "useful_data/tools_fms.json") -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.MISC:
        print("Getting FMS Tools")
        tools = {}
        path = os.path.join(fms_data.absolute_data_dir, tools_path)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                tools = json.load(f)
        if tools:
            be.tools.update_test_tools(tools = tools)
            be.tools.print_table()

def add_procedures(data_parts: DataParts = DataParts.ALL):
    if data_parts == DataParts.ALL or data_parts == DataParts.MISC:
        print("Getting Procedures")
        procedures_path = os.path.join(os.path.dirname(__file__), "apps", "json_files")
        templates_path = os.path.join(os.path.dirname(__file__), "apps", "templates")
        for json_file in os.listdir(procedures_path):
            procedure_name = json_file.split(".")[0]
            template_path = next((os.path.join("templates", f) for f in os.listdir(templates_path) if procedure_name in os.path.basename(f)), "")
            if not template_path:
                print(f"Could not find report template for {procedure_name}")
                continue
            
            json_path = os.path.join(procedures_path, json_file)
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    json_ = json.load(f)
            

            be.procedures.update_procedure_script(
                script_name = procedure_name,
                new_script = json_,
                code_version = version,
                report_path = template_path,
                project = "23026"
            )
        
        be.procedures.print_table()
            

def collect_manifold_data(fms_data: FMSDataStructure, status_file: str, data_parts: DataParts = DataParts.ALL) -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.MANIFOLD:
        print("Getting Manifold Assembly Data")
        fms_data.add_manifold_assembly_data(status_file=status_file)

def collect_fms_data(fms_data: FMSDataStructure, fms_main_files: list, status_file: str, test_path: str, data_parts: DataParts = DataParts.ALL, fms_ids: list[str] = []) -> None:
    if data_parts == DataParts.ALL or data_parts == DataParts.FMS_ACCEPTANCE:
        print("Getting FMS Main Test Data")
        fms_data.add_fms_main_test_data(fms_main_files=fms_main_files, fms_status_path=status_file)
        fms_data.fms_sql.update_limit_database()
    if data_parts == DataParts.ALL or data_parts == DataParts.FMS_FUNCTIONAL:
        print("Getting FMS Functional Test Data")
        fms_data.add_fms_functional_test_data(test_path=test_path, fms_ids=fms_ids)

def collect_all_data(include_data: list[DataParts], local = True,
        local_certifications: str = "",
        tv_assembly: str = "",
        tv_summary: str = "",
        status_file: str = "",
        electrical_data: str = "",
        tv_test_path: str = "",
        anode_fr_path: str = "",
        cathode_fr_path: str = "",
        hpiv_data_packages: str = "",
        lpt_path: str = "",
        fms_main_files: str = "",
        test_path: str = "",
        fms_ids: list[str] = [],
        absolute_data_dir: str = ""
    ) -> None:
    if not absolute_data_dir:
        fms_data = FMSDataStructure(local=local)
    else:
        fms_data = FMSDataStructure(local=local, absolute_data_dir=absolute_data_dir)

    for data_part in include_data:
        # collect_certification_data(fms_data, local_certifications, data_part)
        collect_tv_data(fms_data, tv_assembly, tv_summary, status_file, electrical_data, tv_test_path, data_part)
        collect_tv_tvac_data(fms_data, tvac_path=os.path.join(fms_data.test_path, "TV#12 Life Cycle Endurance Test"), tv_id=12, data_parts = data_part)
        collect_lpt_data(fms_data, lpt_path, data_part)
        collect_hpiv_data(fms_data, hpiv_data_packages, data_part)
        collect_fr_data(fms_data, anode_fr_path, cathode_fr_path, data_part)
        add_fr_testing_tools(fms_data, data_part)
        collect_manifold_data(fms_data, status_file, data_part)
        collect_fms_data(fms_data, fms_main_files, status_file, test_path, data_part, fms_ids=fms_ids)
        add_fms_testing_tools(fms_data=fms_data, data_parts=data_part)
        add_procedures(data_parts=data_part)

# ----------------------------------------------------------------------------------------------------------------------------------- #
# ---------------------------------------------- Logic for Listening to Data  ------------------------------------------------------- #
# ----------------------------------------------------------------------------------------------------------------------------------- #

if __name__ == "__main__":
    collect_all_data(include_data=[DataParts.FMS_FUNCTIONAL], fms_ids = ["24-100", "24-101", "24-102", "24-188", "24-189", "24-190"] + [f"25-{i:03d}" for i in range(45, 150)])