# Standard library
import os
import re
import time
import threading
import traceback
from datetime import datetime
from pathlib import Path

# Third-party
from tqdm import tqdm
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker, Session

# Local packages – database models
from .db import (
    Base,
    FMSMain,
    TVCertification,
    TVStatus,
    TVTestRuns,
)

# Local packages – utilities
from .utils.tv import TVData, TVLogicSQL
from .utils.hpiv import HPIVData, HPIVLogicSQL
from .utils.lpt_manifold import ManifoldData, ManifoldLogicSQL
from .utils.fr import FRData, FRLogicSQL
from .utils.fms import FMSData, FMSLogicSQL
from .utils.general_utils import load_from_json, save_to_json
from .utils.enums import TVParts

# Local packages – queries and processing
from .utils.certification_listener import CertificationListener
from .utils.textract import TextractReader


#TODO discuss which new measurements are going to be done by SK, and include those, or which measurements in general
#TODO safran p/n
#TODO capture point in MAIT for fms flow testing, discussion
#TODO think about piece parts batch traceability
#TODO tools and test operator for TV
#TODO 

#TODO thermal valve measurement report, extract measurements
#TODO add 'dashboard' especially showing what data has come in and any errors regarding the processing
#TODO maybe add table for tolerances, from the drawings
#TODO session start logic, make robust against connectivity issues
#TODO allocation queries e.g. to re-allocate sets to another fms.

class FMSDataStructure:
    """
    Main class for managing FMS (Fluidic Management System) data structure.
    
    This class handles the database operations for HPIV, TV, LPT manifold, and FRs
    test data, including listening for new data packages, processing PDF files,
    and updating the database with extracted characteristics.
    
    Attributes
    ----------
        engine: 
            SQLAlchemy database engine.
        Session: 
            SQLAlchemy session factory.
        hpiv_data_packages (str): 
            Path to directory containing HPIV data packages.
        tv_test_runs (str): 
            Path to directory containing TV test runs.
        certifications (str): 
            Path to directory containing certification documents.
        lpt_files (str): 
            Path to directory containing LPT manifold data.
        fms_main_files (str): 
            Path to directory containing FMS main test results.
        excel_extraction (bool): 
            Flag to enable/disable Excel data extraction.
        fms_main_files (str):
            Path to FMS main test results.
        companies (list):
            List of company names for certification filtering.
        base_path (str):
            Base path for certification documents.
        test_path (str):
            Path for FMS testing documents/files.
        anode_fr_path (str):
            Path to anode FR test results Excel file.
        cathode_fr_path (str):
            Path to cathode FR test results Excel file.
        fms_status_path (str):
            Path to FMS status overview Excel file.
        tv_assembly_path (str):
            Path to TV assembly procedure Excel file.
        tv_summary_path (str):
            Path to TV summary database Excel file.
        tv_test_path (str):
            Path to TV test results directory.
        certification_folder (str):
            Path to certification documents folder.
        tv_data (TVData): 
            Instance for handling TV data.
        fr_data (FRData): 
            Instance for handling FR data.
        hpiv_data (HPIVData): 
            Instance for handling HPIV data.
        lpt_data (ManifoldData): 
            Instance for handling LPT manifold data.
        hpiv_sql (HPIVLogicSQL): 
            SQL logic handler for HPIV data.
        tv_sql (TVLogicSQL): 
            SQL logic handler for TV data.
        lpt_sql (ManifoldLogicSQL): 
            SQL logic handler for LPT manifold data.
        fr_sql (FRLogicSQL): 
            SQL logic handler for FR data.
        fms_sql (FMSLogicSQL): 
            SQL logic handler for FMS main data.
        obj_list (list): 
            List of data handler instances.
        lpt_found (bool): 
            Flag indicating if LPT data was found.
        fr_found (bool): 
            Flag indicating if FR data was found.
        hpiv_found (bool): 
            Flag indicating if HPIV data was found.
        certification_listener (CertificationListener): 
            Listener for certification documents.
        all_current_certifications (list): 
            List of all current certification file paths.
        hpiv_test_results (list): 
            List of processed HPIV test results.

    Methods
    -------
    print_table_structures():
        Print the structure of all database tables in the schema.
    listen_to_certifications():
        Start listening for new certification documents,
        using the CertificationListener.
    listen_to_hpiv_data():
        Start listening for new HPIV data packages.
    listen_to_tv_test_results():
        Start listening for new TV test results.
    add_tv_electrical_data():
        Add TV electrical data to the database.
    listen_to_lpt_calibration():
        Start listening for new LPT manifold calibration data.
    add_tv_assembly_data():
        Add TV assembly data from Excel files to the database.
    add_manifold_assembly_data():
        Add manifold assembly data from Excel files to the database.
    add_fr_test_data():
        Add FR test data from Excel files to the database.
    electric_assembly():
        Add TV electric assembly input field data to the database.
    flow_restrictor_testing():
        Add FR flow test input data to the database.
    listen_to_fms_main_results():
        Start listening for new FMS main test results.
    estimate_amazon_invoice_total_cost(files, s3_rate_per_gb=0.023, textract_rate_per_1000=1.50):
        Estimate the total cost of processing PDF files using Amazon S3 and Textract.
    get_all_certifications():
        Process all certification documents and update the database accordingly.
    add_tv_test_results():
        Add TV test results from Excel files to the database.
    add_hpiv_data():
        Add HPIV data from PDF files to the database.
    add_lpt_calibration_data():
        Add LPT manifold calibration data from JSON files to the database.
    add_fms_main_test_data():
        Add FMS main test data from the test reports to the database.
    save_procedure(self, procedure_name, procedure_json):
        Save a procedure JSON to the database.
    load_procedure(self, procedure_name, version):
        Load a procedure JSON from the database.
    get_all_current_data():
        Transfer all current local, de-centralized data into the right structure 
        and update to the database.
    update_procedure(procedure_name):
        Gets a local JSON procedure and uploads it to the database.
    print_table(table_class, limit):
        Print rows of a given table class from the database, to a specified limit.
    """
    # absolute_data_dir: str = r"C:\\Users\\TANTENS\\Documents\\fms_data_collection"
    def __init__(self, excel_extraction: bool = True, test_path: str = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing",
                 absolute_data_dir: str = r"\\be.local\Doc\DocWork\99999 - FMS industrialisation\40 - Engineering\03 - Data flow\fms_data_collection",\
                      local = True) -> None:

        if local:
            local_appdata = Path(os.environ.get("LOCALAPPDATA", os.getcwd()))
            app_data_dir = local_appdata / "FMSDatabase"
            app_data_dir.mkdir(parents=True, exist_ok=True)
            self.db_path = app_data_dir / "FMS_DataStructure.db"
            # Initialize the engine
            self.engine = create_engine(f"sqlite:///{self.db_path}")

        self.Session = sessionmaker(bind=self.engine)
        self.default_manifold_drawing = "20025.10.08-R4"    
        self.excel_extraction = excel_extraction
        self.companies = [
            'sk technology', 'sk', 'veldlaser', 'ceratec', 'pretec', 'veld laser',
            'branl', 'ejay filtration', 'space solutions', 'spacesolutions',
            'keller', 'coremans'
        ]

        self.absolute_data_dir = absolute_data_dir
        
        year = datetime.now().year
        base_path = r"\\be.local\Doc\DocWork\Certificaten Bradford"
        self.test_path = test_path
        self.fms_status_path = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\LP FMS Status Overview_V0.xlsx"
        self.anode_fr_path = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing\LP FMS FR Testing - 6\FMS-LP-BE-TRS-0021-i1-0 - FR Testing - Anode.xlsx"
        self.cathode_fr_path = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing\LP FMS FR Testing - 6\FMS-LP-BE-TRS-0021-i1-0 - FR Testing - Cathode.xlsx"
        self.tv_assembly_path = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing\Thermal Valve Assembly Testing\TV Assembly Procedure_V1.xlsx"
        self.tv_summary_path = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing\Thermal Valve Assembly Testing\Thermal valve database_V2.xlsx"
        self.tv_test_path = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing\Thermal Valve Assembly Testing"
        self.default_certifications_path = os.path.join(absolute_data_dir, "certifications")
        self.certification_folder = os.path.join(base_path, str(year))

        self.hpiv_sql = HPIVLogicSQL(session=self.Session, fms=self)
        
        self.tv_sql = TVLogicSQL(session=self.Session, fms=self)
        
        self.lpt_sql = ManifoldLogicSQL(session=self.Session, fms=self)
        
        self.fr_sql = FRLogicSQL(session=self.Session, fms=self)
        
        self.fms_sql = FMSLogicSQL(session=self.Session, fms=self)
        self.fms_data = FMSData()
        
        self.tv_data = TVData()
        self.fr_data = FRData()
        self.hpiv_data = HPIVData()
        self.manifold_data = ManifoldData()

        self.obj_list = [self.tv_data, self.fr_data, self.hpiv_data, self.manifold_data]
        self.lpt_found = False
        self.fr_found = False
        self.hpiv_found = False

        self.certification_listener = None
        self._check_to_initialize_db()


    def _check_to_initialize_db(self) -> None:
        """
        Checks if the database tables exist; if not, initializes the database.
        """
        inspector = inspect(self.engine)
        tables = inspector.get_table_names()
        if not tables:
            Base.metadata.create_all(self.engine)

    def print_table_structures(self) -> None:
        """
        Print the structure of all database tables.
        
        This method displays the table names and their column definitions
        for all tables in the database schema.
        """
        session = self.Session()
        for table_name, table in Base.metadata.tables.items():
            print(f"\nTable: {table_name}")
            for column in table.columns:
                print(f"  {column.name} ({column.type})")
        session.close()

    def listen_to_certifications(self, certifications: str = "") -> None:
        """
        Start listening for new certification documents.
        This method initializes the CertificationListener to monitor the
        certifications directory for new or modified files.
        """
        if not certifications:
            certifications = self.default_certifications_path
        self.certification_listener = CertificationListener(fms=self, path=certifications, load_json=load_from_json, save_json=save_to_json)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.certification_listener.observer.stop()
            self.certification_listener.observer.join()

    def add_tv_electrical_data(self, electrical_data: str = "") -> None:
        """
        Add TV electrical data to the database.
        Args:
            electrical_data (str): Path to the directory containing TV electrical data.
        """
        if not electrical_data:
            electrical_data = os.path.join(self.absolute_data_dir, "Electrical_data")
        self.tv_sql.add_electrical_data(electrical_data = electrical_data)

    def add_tv_assembly_data(self, tv_assembly: str = "", tv_summary: str = "", status_file: str = "") -> None:
        """
        Add TV assembly data from Excel files to the database.
        Args:
            tv_assembly (str): Path to the TV assembly procedure Excel file.
            tv_summary (str): Path to the TV summary database Excel file.
            status_file (str): Path to the FMS status overview Excel file.
        """
        if not tv_assembly:
            tv_assembly = self.tv_assembly_path
        if not tv_summary:
            tv_summary = self.tv_summary_path
        if not status_file:
            status_file = self.fms_status_path
        self.tv_sql.add_tv_assembly_data(self.excel_extraction, tv_assembly = tv_assembly, tv_summary = tv_summary, status_file = status_file)

    def add_manifold_assembly_data(self, status_file: str = "") -> None:
        """
        Add manifold assembly data from Excel files to the database.
        Args:
            status_file (str): Path to the FMS status overview Excel file.
        """
        if not status_file:
            status_file = self.fms_status_path
        self.lpt_sql.add_manifold_assembly_data(assembly_file=status_file)

    def add_fr_test_data(self, anode_fr_path: str = "", cathode_fr_path: str = "") -> None:
        """
        Add flow restrictor test data from Excel files to the database.
        Args:
            anode_fr_path (str): Path to the anode FR test results Excel file.
            cathode_fr_path (str): Path to the cathode FR test results Excel file.
        """
        if not anode_fr_path and not cathode_fr_path:
            anode_paths = [self.anode_fr_path, r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing\LP FMS FR Testing - 8\XXX - FR Testing - Anode.xlsx"]
            cathode_paths = [self.cathode_fr_path, r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing\LP FMS FR Testing - 8\XXX - FR Testing - Cathode.xlsx"]
            operator = ["JKR", "NRN"]
            
            for anode_path, cathode_path, tester in zip(anode_paths, cathode_paths, operator):
                self.fr_sql.update_fr_test_results(self.excel_extraction, anode_path=anode_path, cathode_path=cathode_path,\
                                                    operator = tester, tools_path = os.path.join(self.absolute_data_dir, "useful_data", "trs_tools_fr.json"))
        else:
            self.fr_sql.update_fr_test_results(self.excel_extraction, anode_path=anode_fr_path, cathode_path=cathode_fr_path,\
                                                tools_path = os.path.join(self.absolute_data_dir, "useful_data", "trs_tools_fr.json"))


    def add_tv_test_results(self, tv_test_path: str = "") -> None:
        """
        Add TV test results from Excel files to the database.
        This method scans the TV test results directory for Excel files,
        extracts relevant test data, and updates the database with the
        extracted data.
        Args:
            tv_test_path (str): Path to the directory containing TV test runs.
        """
        if not tv_test_path:
            tv_test_path = self.tv_test_path

        session: "Session" = self.Session()

        for folder in os.listdir(tv_test_path):
            full_folder: str = os.path.join(tv_test_path, folder)

            if not self._is_tv_test_folder(full_folder, folder):
                continue

            tv_id: int = self._extract_tv_id(folder)
            tv_sql: TVLogicSQL = TVLogicSQL(session=session, fms=self)

            test_files: list[str] = self._collect_tv_test_files(full_folder)
            welded_date = self._get_welded_date(session, tv_id)

            parsed_tests = self._parse_and_sort_tests(test_files)

            (
                status_entry,
                status_welded,
                half_index,
            ) = self._get_weld_split_info(session, tv_id, welded_date, parsed_tests)

            last_pre_weld_opening_temp: float | None = None
            last_opening_temp: float | None = None

            for idx, (test_date, test_file, test_reference) in enumerate(parsed_tests):
                (
                    last_opening_temp,
                    last_pre_weld_opening_temp,
                ) = self._process_single_tv_test(
                    session=session,
                    tv_sql=tv_sql,
                    tv_id=tv_id,
                    idx=idx,
                    test_date=test_date,
                    test_file=test_file,
                    test_reference=test_reference,
                    welded_date=welded_date,
                    status_welded=status_welded,
                    half_index=half_index,
                    last_opening_temp=last_opening_temp,
                    last_pre_weld_opening_temp=last_pre_weld_opening_temp,
                )

            self._update_tv_status_entry(
                status_entry,
                last_opening_temp,
                last_pre_weld_opening_temp,
            )

        session.commit()


    def _is_tv_test_folder(self, full_folder: str, folder: str) -> bool:
        return os.path.isdir(full_folder) and "test valve #" in folder.lower()


    def _extract_tv_id(self, folder: str) -> int:
        return int(folder.split("#")[-1].strip().split(" ")[0])


    def _collect_tv_test_files(self, full_folder: str) -> list[str]:
        test_files: list[str] = [
            os.path.join(full_folder, f)
            for f in os.listdir(full_folder)
            if f.lower().endswith(".xls") and "quench" not in f.lower()
        ]

        for subfolder in os.listdir(full_folder):
            full_subfolder: str = os.path.join(full_folder, subfolder)
            if os.path.isdir(full_subfolder):
                test_files.extend(
                    [
                        os.path.join(full_subfolder, f)
                        for f in os.listdir(full_subfolder)
                        if f.lower().endswith(".xls") and "quench" not in f.lower()
                    ]
                )

        return test_files


    def _get_welded_date(self, session: "Session", tv_id: int):
        cert_check = (
            session.query(TVCertification)
            .filter_by(tv_id=tv_id, part_name=TVParts.WELD.value)
            .first()
        )
        return cert_check.date if cert_check else None


    def _parse_and_sort_tests(
        self, test_files: list[str]
    ) -> list[tuple[datetime.date, str, str]]:
        parsed_tests: list[tuple[datetime.date, str, str]] = []

        for test_file in test_files:
            test_reference: str = os.path.basename(test_file).split("_LP_")[0]
            try:
                test_date = datetime.strptime(
                    test_reference, "%Y_%m_%d_%H-%M-%S"
                ).date()
                parsed_tests.append((test_date, test_file, test_reference))
            except Exception as e:
                print(f"Error parsing date from {test_reference}: {str(e)}")

        parsed_tests.sort(key=lambda x: x[0])
        return parsed_tests


    def _get_weld_split_info(
        self,
        session: "Session",
        tv_id: int,
        welded_date,
        parsed_tests: list[tuple],
    ) -> tuple["TVStatus | None", bool, int | None]:
        status_entry = session.query(TVStatus).filter_by(tv_id=tv_id).first()
        status_welded: bool = status_entry.welded if status_entry else False

        half_index: int | None = None
        if not welded_date and len(parsed_tests) > 1:
            half_index = len(parsed_tests) // 2

        return status_entry, status_welded, half_index


    def _process_single_tv_test(
        self,
        session: "Session",
        tv_sql: "TVLogicSQL",
        tv_id: int,
        idx: int,
        test_date,
        test_file: str,
        test_reference: str,
        welded_date,
        status_welded: bool,
        half_index: int | None,
        last_opening_temp: float | None,
        last_pre_weld_opening_temp: float | None,
    ) -> tuple[float | None, float | None]:

        test_check = (
            session.query(TVTestRuns)
            .filter_by(tv_id=tv_id, test_reference=test_reference)
            .first()
        )

        if test_check:
            return test_check.opening_temp, last_pre_weld_opening_temp

        tv_data = TVData(test_results_file=test_file)
        update: bool = tv_data.extract_tv_test_results_from_excel()
        if not update:
            return last_opening_temp, last_pre_weld_opening_temp

        if welded_date:
            welded: bool = test_date >= welded_date.date()
        else:
            if half_index is not None and status_welded:
                welded = idx >= half_index
            elif status_welded is False:
                welded = False

        tv_sql.tv_id = tv_id
        tv_sql.tv_test_reference = test_reference
        tv_sql.tv_welded = welded
        tv_sql.update_tv_test_results(tv_data)

        if not welded:
            last_pre_weld_opening_temp = tv_data.opening_temperature

        last_opening_temp = tv_data.opening_temperature

        return last_opening_temp, last_pre_weld_opening_temp


    def _update_tv_status_entry(
        self,
        status_entry: "TVStatus | None",
        last_opening_temp: float | None,
        last_pre_weld_opening_temp: float | None,
    ) -> None:
        if not status_entry:
            return

        if last_opening_temp is not None:
            status_entry.opening_temp = last_opening_temp

        if last_pre_weld_opening_temp is not None:
            status_entry.pre_weld_opening_temp = last_pre_weld_opening_temp

    def add_hpiv_data(self, hpiv_data_packages: str = "", output_folder: str = "") -> None:
        """
        Add HPIV data from PDF files to the database.
        This method scans the HPIV data packages directory for PDF files,
        extracts relevant HPIV data, and updates the database with the
        extracted data.
        Args:
            hpiv_data_packages (str): Path to the directory containing HPIV data packages.
            output_folder (str): Path to the output folder for the extracted HPIV reports.
        """
        if not hpiv_data_packages:
            hpiv_data_packages = os.path.join(self.absolute_data_dir, "HPIV_data_packages")
        data_packages = [os.path.join(hpiv_data_packages, f) for f in os.listdir(hpiv_data_packages) if f.lower().endswith('.pdf')]
        if not output_folder:
            output_folder = os.path.join(self.absolute_data_dir, "extracted_HPIV_reports")
            if not os.path.exists(output_folder):
                os.makedirs(output_folder)
        for package in data_packages:
            hpiv_data = HPIVData(pdf_file=package) 
            hpiv_data.extract_hpiv_data(output_folder=output_folder)
            self.hpiv_sql.update_hpiv_characteristics(hpiv_data)
            self.hpiv_sql.update_hpiv_revisions(hpiv_data)

    def add_lpt_calibration_data(self, lpt_path: str = "") -> None:
        """
        Add LPT calibration data from JSON files to the database.
        This method scans the LPT calibration directory for JSON files,
        extracts relevant calibration data, and updates the database with the
        extracted data.
        
        Args:
            lpt_path (str): Path to the directory containing LPT calibration data.
        """
        if not lpt_path:
            lpt_path = os.path.join(self.absolute_data_dir, "LPT_data/LPT_coefficient_data")
        json_files = []
        for root, dirs, files in os.walk(lpt_path):
            for f in files:
                if f.lower().endswith('.json'):
                    json_files.append(os.path.join(root, f))
        self.manifold_data.json_files = json_files
        self.manifold_data.extract_coefficients_from_json()
        self.lpt_sql.update_lpt_calibration(self.manifold_data)
        self.manifold_data.lpt_coefficients = {}
        self.manifold_data.lpt_calibration = {}
        self.manifold_data.json_files = []

    def add_fms_main_test_data(self, fms_main_files: str =  "",
        fms_status_path: str = "") -> None:
        """
        Add FMS main test data from the test reports to the database.
        This method scans the FMS main test results directory for PDF files,
        extracts relevant test data, and updates the database with the
        extracted data.
        Args:
            fms_main_files (str): Path to the directory containing FMS main test results.
            fms_status_path (str): Path to the FMS status overview Excel file.
        """
        if not fms_main_files:
            fms_main_files = os.path.join(self.absolute_data_dir, "FMS_data/test_results")
        if not fms_status_path:
            fms_status_path = self.fms_status_path
    
        main_files = [os.path.join(fms_main_files, f) for f in os.listdir(fms_main_files) if f.lower().endswith('.pdf')]
        for main_file in main_files:
            self.fms_sql.pdf_file = main_file
            self.fms_sql.status_file = fms_status_path
            self.fms_sql.extract_FMS_test_results()
            self.fms_sql.update_fms_main_test_results(update_assembly_data=True, automated_entry=True)

    def add_fms_functional_test_data(self, test_path: str = "", fms_ids: list[str] = []) -> None:
        """
        Add FMS main functional test data from the test reports to the database.
        This method scans the FMS test results directory for Excel files,
        extracts relevant functional test data, and updates the database with the
        extracted data.
        Args:
            test_path (str): Path to the directory containing FMS functional test results.
            fms_id (str): Specific FMS ID to process. If empty, process all.
        """
        if not test_path:
            test_path = self.test_path

        serials: list[str] = (
            fms_ids
            if fms_ids
            else ["24-100", "24-101", "24-102", "24-188", "24-189", "24-190"]
            + [f"25-{i:03d}" for i in range(45, 65)]
        )

        (
            slope_files,
            closed_loop_files,
            fr_files,
            tvac_files,
            open_loop_files,
        ) = self._scan_fms_test_directories(test_path, serials)

        session: "Session" = self.Session()

        for serial in serials:
            fms_check = session.query(FMSMain).filter_by(fms_id=serial).first()
            gas_type: str = fms_check.gas_type if fms_check else "Xe"

            fms_sql: FMSLogicSQL = FMSLogicSQL(session=session, fms=self, fms_id = serial)

            self._process_flow_tests(
                fms_sql,
                gas_type,
                slope_files.get(serial, []),
                open_loop_files.get(serial, []),
                closed_loop_files.get(serial, []),
            )

            self._process_fr_tests(
                fms_sql,
                gas_type,
                fr_files.get(serial, []),
            )

            self._process_tvac_tests(
                fms_sql,
                gas_type,
                serial,
                tvac_files.get(serial, []),
            )

    def _scan_fms_test_directories(
        self,
        test_path: str,
        serials: list[str],
    ) -> tuple[
        dict[str, list[str]],
        dict[str, list[str]],
        dict[str, list[str]],
        dict[str, list[str]],
        dict[str, list[str]],
    ]:
        slope_files: dict[str, list[str]] = {}
        closed_loop_files: dict[str, list[str]] = {}
        fr_files: dict[str, list[str]] = {}
        tvac_files: dict[str, list[str]] = {}
        open_loop_files: dict[str, list[str]] = {}

        for folder in os.listdir(test_path):
            full_f_path: str = os.path.join(test_path, folder)
            if not os.path.isdir(full_f_path):
                continue

            serial: str | None = next((s for s in serials if s in folder), None)
            if not serial:
                continue

            slope_files[serial] = []
            closed_loop_files[serial] = []
            fr_files[serial] = []
            tvac_files[serial] = []
            open_loop_files[serial] = []

            functional_folder = self._first_match(full_f_path, "function", folder_only=True)
            low_folder = self._first_match(functional_folder, "10 bara", folder_only=True)
            high_folder = self._first_match(functional_folder, "190 bara", folder_only=True)

            self._add_files(slope_files[serial], low_folder, ["slope"])
            self._add_files(closed_loop_files[serial], low_folder, ["closed loop"])
            self._add_files(fr_files[serial], low_folder, ["fr", "characteristics", "fr_test"])

            self._add_files(slope_files[serial], high_folder, ["slope"])
            self._add_files(closed_loop_files[serial], high_folder, ["closed loop"])
            self._add_files(fr_files[serial], high_folder, ["fr", "characteristics", "fr_test"])

            tvac_folder = self._first_match(full_f_path, "tvac", folder_only=True)
            if not tvac_folder:
                continue

            tvac_cycle_folder = self._first_match(tvac_folder, "cycl", folder_only=True)
            if tvac_cycle_folder:
                tvac_files[serial].extend(
                    os.path.join(tvac_cycle_folder, f)
                    for f in os.listdir(tvac_cycle_folder)
                    if f.lower().endswith(".csv")
                )

            temp_conditions: list[str] = ["-15 degC", "22 degC", "70 degC"]
            pressures: list[str] = ["10 bara", "190 bara"]

            for temp in temp_conditions:
                for temp_folder in self._all_matches(tvac_folder, temp, folder_only=True):
                    for func_folder in self._all_matches(temp_folder, "function", folder_only=True):
                        for pressure in pressures:
                            for pressure_folder in self._all_matches(
                                func_folder, pressure, folder_only=True
                            ):
                                self._add_files(slope_files[serial], pressure_folder, ["slope"])
                                self._add_files(
                                    closed_loop_files[serial],
                                    pressure_folder,
                                    ["closed loop"],
                                )
                                self._add_files(
                                    open_loop_files[serial],
                                    pressure_folder,
                                    ["open loop"],
                                )

        return (
            slope_files,
            closed_loop_files,
            fr_files,
            tvac_files,
            open_loop_files,
        )


    def _all_matches(
        self,
        path: str | None,
        keyword: str,
        extension: str | None = None,
        folder_only: bool = False,
    ) -> list[str]:
        if not path or not os.path.exists(path):
            return []

        matches: list[str] = []
        for entry in os.listdir(path):
            full_path: str = os.path.join(path, entry)
            if folder_only and not os.path.isdir(full_path):
                continue
            if keyword.lower() in entry.lower():
                if extension and not entry.lower().endswith(extension.lower()):
                    continue
                matches.append(full_path)
        return matches


    def _first_match(
        self,
        path: str | None,
        keyword: str,
        folder_only: bool = False,
    ) -> str | None:
        matches = self._all_matches(path, keyword, folder_only=folder_only)
        return next(iter(matches), None)


    def _add_files(
        self,
        target_list: list[str],
        folder: str | None,
        keywords: list[str],
        ext: str = ".xls",
    ) -> None:
        if not folder:
            return
        for kw in keywords:
            target_list.extend(self._all_matches(folder, kw, extension=ext))


    def _process_flow_tests(
        self,
        fms_sql: "FMSLogicSQL",
        gas_type: str,
        slope: list[str],
        open_loop: list[str],
        closed_loop: list[str],
    ) -> None:
        for slope_test in slope:
            print(slope_test)
            fms_sql.flow_test_file = slope_test
            fms_sql.gas_type = gas_type
            fms_sql.extract_flow_data()
            fms_sql.update_flow_test_results(test_type = "slope")

        for open_loop_test in open_loop:
            print(open_loop_test)
            fms_sql.gas_type = gas_type
            fms_sql.extract_flow_data()
            fms_sql.update_flow_test_results(test_type = "open_loop")

        for closed_loop_test in closed_loop:
            print(closed_loop_test)
            fms_sql.gas_type = gas_type
            fms_sql.extract_flow_data()
            fms_sql.update_flow_test_results(test_type = "closed_loop")

    def _process_fr_tests(
        self,
        fms_sql: "FMSLogicSQL",
        gas_type: str,
        fr_tests: list[str],
    ) -> None:
        for fr_test in fr_tests:
            fms_data = FMSData(
                test_type="fr_characteristics",
                flow_test_file=fr_test,
            )
            fms_data.extract_slope_data()
            fms_data.gas_type = gas_type
            fms_sql.update_fr_characteristics_results(fms_data)


    def _process_tvac_tests(
        self,
        fms_sql: "FMSLogicSQL",
        gas_type: str,
        serial: str,
        tvac_files: list[str],
    ) -> None:
        if not tvac_files:
            return

        print(serial)
        fms_data = FMSData(test_type="tvac_cycle", flow_test_file=None)
        fms_data.csv_files = tvac_files
        fms_data.extract_tvac_from_csv()
        fms_data.gas_type = gas_type
        fms_sql.update_tvac_cycle_results(fms_data)

    def print_table(self, table_class: object, limit: int = None) -> None:
        """
        Print the contents of a database table to the console.
        Args:
            table_class (object): SQLAlchemy ORM class representing the table.
            limit (int, optional): Maximum number of records to print. Defaults to None (print all).
        """
        session = None
        return
        try:
            session = self.Session()
            query = session.query(table_class)

            # Try to order by primary key column if available
            pk_columns = [col.name for col in table_class.__table__.primary_key.columns]
            if limit is not None and pk_columns:
                query = query.order_by(getattr(table_class, pk_columns[0]).desc()).limit(limit)
            elif limit is not None:
                query = query.limit(limit)

            records = query.all()
            if not records:
                print(f"No records found in table {table_class.__tablename__}")
                return

            print(f"\n--- {table_class.__tablename__} ({len(records)} records) ---")
            for record in records:
                attrs = vars(record)
                attrs = {k: v for k, v in attrs.items() if not k.startswith('_')}

                # Exclude specific fields for LPTCalibration
                if table_class.__tablename__ == "lpt_calibration":
                    excluded_fields = {"p_calculated", "temp_calculated", "signal", "resistance"}
                    attrs = {k: v for k, v in attrs.items() if k not in excluded_fields}

                print(", ".join(f"{k}: {v}" for k, v in attrs.items()))
            print(f"--- End of {table_class.__tablename__} ---\n")

        except Exception as e:
            print(f"Error printing table {table_class.__tablename__}: {str(e)}")
            traceback.print_exc()
        finally:
            if session:
                session.close()

if __name__ == "__main__":
    fms = FMSDataStructure(excel_extraction=True)
    # wb = openpyxl.load_workbook(fms.cathode_fr_path)
    # print(wb.sheetnames)
    # fms.get_all_current_data()
    # fms.fms_sql.update_limit_database()
    # fms.print_table(AnodeFR, limit=5)
    # fms.print_table(CathodeFR, limit=5)
    # fms.print_table(FMSTestResults)

    # fms.update_procedure(procedure_name="tv_assembly_steps")
    # session = fms.Session()
    # jsons = session.query(FMSProcedures).filter_by(script_name="tv_assembly_steps").all()
    # for js in jsons:
    #     script = js.script
    #     print(script["72"])

    # fms.listen_to_fms_main_results()
    """
    conda activate base
    python -u "C:/Users/TANTENS/Documents/FMS_data_structure/fms_data_structure.py"
    """