from __future__ import annotations

# --- Standard Library ---
import base64
import io
import os
import re
import subprocess
import threading
from collections import defaultdict
from datetime import datetime

# --- Third-Party Libraries ---
import fitz
import pythoncom
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import savgol_filter
from sklearn.linear_model import LinearRegression
from PIL import Image
from IPython.display import display, Image 
import ipywidgets as widgets
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from docx2pdf import convert

# --- Local Imports ---
from .general_utils import (
    load_from_json,
    save_to_json,
    show_modal_popup,
    FMSProgressStatus,
    FunctionalTestType,
    FMSProgressStatus,
    FMSFlowTestParameters, 
    FMSMainParameters
)

from .fms_query import FMSQuery
 
from ..db import (
    FMSMain,
    FMSFunctionalTests,
    FMSFunctionalResults,
    FMSAcceptanceTests,
    FMSTestResults,
    FMSLimits,
    LPTCoefficients,
    FMSTvac,
    FMSFRTests,
)

# --- Typing / Forward Declarations ---
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..fms_data_structure import FMSDataStructure
    from sqlalchemy.orm import Session


class FMSTesting:
    """
    Handles the FMS Acceptance Testing procedures, including data retrieval, processing, and report generation.

    Attributes
    ----------
    # Core database and query objects
    session : SQLAlchemy Session
        ORM session for database operations.
    fms : FMSDataStructure
        Main data handler.
    fms_sql : FMS_SQL_Logic
        SQL logic interface.
    fms_query : FMSQuery
        Query interface for FMS data.

    # File paths and UI
    word_template_path : str
        Path to Word template for report generation.
    save_path : str
        Directory to save generated reports.
    test_directory : str
        Directory containing test data.
    vibration_directory : str
        Directory containing vibration test data.
    test_folders : list[str]
        Folders in the test directory.
    vibration_folders : list[str]
        Folders in the vibration directory.
    output : Widget
        Output widget for logs/messages.
    container : Widget
        Main UI container.
    template_path : str
        Word template path for reports.

    # Test procedure and TVAC
    main_parameters : list
        Measured/relevant parameters.
    fms_limits : dict
        Limits for FMS tests.
    fms_status : str
        Progress status of tests.
    functional_test_type : FunctionalTestType
        Functional test type.
    tvac_loop : Enum
        Current TVAC phase.
    tvac_type : str
        TVAC testing phase label.
    current_test_type : str
        Currently processed test type.
    current_subdict : dict
        Current sub-dictionary within the test type.
    current_property_index : int
        Index of the current property.
    test_types : list[str]
        All test types in the procedure.
    draft_fms_ids : list[int]
        FMS IDs with started acceptance testing.
    current_temp : str
        Current temperature phase in TVAC.
    unit_map : dict
        Mapping of properties to units.

    # Report context and history
    context : dict
        Report generation context.
    main_test_results : dict
        Stores main test results for database upload.
    test_info : dict
        Acceptance test procedure information.
    all_test_info : list[dict]
        All 'test_info' dictionaries for started FMS tests.
    author : str
        Report author (Windows environment).
    fms_id : int
        Currently processed FMS ID.

    Methods
    -------
    __init__(...)
        Initializes FMSTesting with required attributes.

    # Utility
    get_unit(property_name)
        Retrieves the unit for a given property.
    encode_image(image)
        Encodes an image to base64 string.
    decode_image(base64_string)
        Decodes base64 string to image (BytesIO).
    convert_docx_to_image_bytes(docx_path)
        Converts DOCX to image in BytesIO.
    crop_image_bytes(image_bytes, dims)
        Crops image given byte data and dimensions.

    # UI / widgets
    initialize_header()
        Sets up header UI components.
    update_tp1_dropdown()
        Updates dropdown for TP1 files.
    field(name, value, **kwargs)
        Creates standardized field dictionary for widget styling.

    # Test retrieval
    get_test_info(fms_id)
        Fetches acceptance test information for a given FMS ID.
    get_hpiv_images()
        Retrieves HPIV images for current FMS and TVAC phase.
    get_vibration_images()
        Retrieves vibration images for current FMS and axis.
    get_functional_plots()
        Generates functional test plots.

    # Test analysis
    check_tvac(property_name)
        Checks if a property belongs to a TVAC phase.
    get_opening_temperature()
        Determines opening temperature from TV slope data.
    get_tv_info()
        Retrieves TV power & temperature combinations.
    check_compliance(value, limits)
        Checks if a value complies with limits.
    check_all_compliance()
        Checks compliance for all test results.

    # Context generation for reports
    get_tvac_context()
        Adds TVAC data to report context.
    get_power_budget_context()
        Adds power budget data to context.
    get_physical_properties_context()
        Adds physical property data to context.
    get_leftover_context()
        Adds remaining data to context.
    generate_context()
        Generates complete report context.

    # Test execution and report generation
    generate_property_fields(property_name)
        Generates UI fields for a given property.
    get_power_budget_fields()
        Generates UI fields for power budget section.
    get_conclusion_field()
        Generates conclusion field UI component.
    get_annex_a()
        Generates UI fields for Annex A components.
    get_recommendations()
        Generates UI & interactions for recommendations.
    get_observations()
        Generates UI & interactions for observations.
    test_procedure()
        Main procedure for testing steps and UI.
    start_testing()
        Initiates the testing procedure UI.
    save_current_state()
        Saves current procedure state to the database.
    update_database()
        Updates database after report generation.
    get_new_filename()
        Generates new filename based on FMS ID and previous reports.
    """

    def __init__(self, session: "Session", fms: "FMSDataStructure",
                 word_template_path: str = r"FMSAcceptanceTests\fms_test_draft.docx",  
                 save_path: str = r"\\be.local\Doc\DocWork\99999 - FMS industrialisation\40 - Engineering\03 - Data flow\FMS Acceptance Test Reports"):
        
        self.session: Session = session()
        self.fms = fms
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.img_path = os.path.join(current_dir, "images", "bradford_logo.jpg")
        self.fms_id = None
        self.save_path = save_path
        self.main_parameter_values = [i.value for i in FMSMainParameters] if FMSMainParameters else []
        self.test_directory = r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\70 - Testing"
        self.vibration_directory = r"\\be.local\Doc\DocWork\23026 - SSP - FMS LLI\70 - Testing"
        self.test_folders = os.listdir(self.test_directory)
        self.vibration_folders = os.listdir(self.vibration_directory)
        self.output = widgets.Output()
        self.container = widgets.VBox()
        self.tvac_loop = None
        self.template_path = word_template_path
        self.tvac_type = None
        self.continue_list = []
        self.current_test_type: FunctionalTestType = None
        self.current_subdict = None
        self.current_property_index = 0
        self.test_types = []
        self.draft_fms_ids = []
        self.context = {}
        self.fms_query = FMSQuery(session=session)
        self.main_test_results = defaultdict(dict)
        self.test_info = self.fms.load_procedure(procedure_name="fms_test_draft")
        self.all_test_info: list[FMSAcceptanceTests] = (
            self.session.query(FMSAcceptanceTests)
            .filter(FMSAcceptanceTests.report_generated == False)
            .order_by(FMSAcceptanceTests.id.asc())
            .all()
        )
        author = load_from_json("author") 
        if author:
            self.author = author
        else:
            username = subprocess.check_output(
            ["powershell", "-Command", "(Get-WmiObject Win32_UserAccount -Filter \"Name='$env:USERNAME'\").FullName"],
            text=True
            ).strip()
            name_parts = username.split(' ')
            first_name = name_parts[0] if len(name_parts) > 0 else ""
            last_name = name_parts[-1] if len(name_parts) > 1 else ""
            self.author = first_name[0].upper() + "." + last_name.capitalize()
            save_to_json(self.author, "author")

        if self.all_test_info:
            self.draft_fms_ids = [t.fms_id for t in self.all_test_info]
            self.fms_id = self.draft_fms_ids[0]
            self.test_info = self.all_test_info[0].raw_json if self.all_test_info[0].raw_json else self.test_info
        self.tvac_map = {
            FunctionalTestType.ROOM: "22°C",
            FunctionalTestType.COLD: "-15°C",
            FunctionalTestType.HOT: "70°C"
        }
        self.current_temp = None
        self.initialize_header()
        display(self.container)
        self.unit_map = {
            "bonding": {"limit": "mOhm", "actual": "mOhm"},
            "isolation": {"limit": "MOhm", "actual": "GOhm"},
            "capacitance": {"limit": "nF", "actual": "nF"},
            "resistance": {"limit": "Ohm", "actual": "Ohm"},
            "locations": {"limit": "mm", "actual": "mm"},
            "mass": {"limit": "g", "actual": "g"},
            "hpiv_opening_power": {"limit": "W", "actual": "W"},
            "hpiv_hold_power": {"limit": "W", "actual": "W"},
            "opening_response": {"limit": "ms", "actual": "ms"},
            "closing_response": {"limit": "ms", "actual": "ms"},
            "voltage": {"limit": "V", "actual": "V"},
            "leak": {"limit": "scc/s GHe", "actual": "scc/s GHe"},
            "pressure": {"limit": "bar", "actual": "bar"},
            "proof_pressure": {"limit": "barA", "actual": "barA"},
            "inductance": {"limit": "mH", "actual": "mH"}
        }

    def get_unit(self, subdict: str, prop_key: str, unit_type: str = "actual") -> str:
        """
        Retrieves the unit for a given property key.
        Args:
            subdict (str): Sub-dictionary name within the test type.
            prop_key (str): Property key to look up.
            unit_type (str): Type of unit to retrieve ('actual' or 'limit').
        Returns:
            str: The unit corresponding to the property key.
        """
        if "proof" in prop_key:
            return self.unit_map.get("proof_pressure").get(unit_type, "")
        if prop_key in self.unit_map:
            return self.unit_map[prop_key].get(unit_type, "")
        if subdict and subdict in self.unit_map:
            return self.unit_map[subdict].get(unit_type, "")
        for k in self.unit_map:
            if k in prop_key:
                return self.unit_map[k].get(unit_type, "")
        return ""

    def initialize_header(self) -> None:
        """
        Initializes the header section of the FMS Acceptance Testing UI.
        """
        self.all_fms_field = widgets.Dropdown(
            options=self.draft_fms_ids,
            description="Select Open FMS Test:",
            style={'description_width': '180px'},
            layout=widgets.Layout(width="350px"),
            value=self.fms_id if self.fms_id else None
        )

        home_button = widgets.Button(
            description="Home",
            button_style='primary',
            icon='home'
        )
        def on_home_click(b):
            self.output.clear_output()
            self.start_testing()

        def on_fms_change(change):
            self.output.clear_output()
            if change['name'] == 'value':
                selected_fms_id = change['new']
                self.fms_id = selected_fms_id if selected_fms_id else None
                self.start_testing()

        self.all_fms_field.observe(on_fms_change, names='value')

        output = widgets.Output()
        self.top_container = widgets.HBox([home_button, self.all_fms_field])
        home_button.on_click(on_home_click)

        if not self.all_test_info:
            self.top_container.children = [home_button]

        logo = widgets.Image(value=open(self.img_path, "rb").read(), format='jpg', width=300, height=100)

        display(widgets.VBox([logo, self.top_container]))

    def get_test_info(self, fms_id: str) -> dict:
        """
        Retrieves the acceptance test procedure and status for a given FMS ID.
        Args:
            fms_id (str): The FMS ID to retrieve test information for.
        Returns:
            dict: The acceptance test procedure information.
        """
        existing_entry: FMSAcceptanceTests = (
            self.session.query(FMSAcceptanceTests)
            .filter_by(fms_id=fms_id)
            .first()
        )
        # test_info = load_from_json(f"back_up_{fms_id}")
        # return test_info
        if existing_entry:
            self.fms_limits = existing_entry.fms_main.limits.limits if existing_entry.fms_main and existing_entry.fms_main.limits and existing_entry.fms_main.limits.limits else {}
            self.current_property_index = existing_entry.current_property_index or 0
            self.current_test_type = existing_entry.current_test_type or None
            self.current_subdict = existing_entry.current_subdict or None
            return existing_entry.raw_json if existing_entry.raw_json else {}
        test_info = self.fms.load_procedure(procedure_name="fms_test_draft")
        fms_entry = self.session.query(FMSMain).filter_by(fms_id=fms_id).first()
        test_info["hpiv_id"] = fms_entry.hpiv_id if fms_entry else None
        test_info["tv_id"] = fms_entry.tv_id if fms_entry else None
        test_info["lpt_id"] = fms_entry.lpt_id if fms_entry else None
        test_info["anode_fr_id"] = fms_entry.anode_fr_id if fms_entry else None
        test_info["cathode_fr_id"] = fms_entry.cathode_fr_id if fms_entry else None
        test_info["gas_type"] = fms_entry.gas_type if fms_entry else None
        test_info["gas"] = "Xenon" if fms_entry and fms_entry.gas_type and "xe" in fms_entry.gas_type.lower() else "Krypton"
        test_info["ratio"] = fms_entry.manifold[0].ac_ratio_specified if fms_entry and fms_entry.manifold else None
        test_info["author"] = self.author
        lpt: list[LPTCoefficients] = fms_entry.manifold[0].lpt[0].coefficients if fms_entry and fms_entry.manifold and fms_entry.manifold[0].lpt else None
        if lpt:
            for coef in lpt:
                val = coef.parameter_value
                if abs(val) < 0.0001 and val != 0:
                    val = f"{val:.3E}"
                else:
                    val = f"{val:.5f}"
                test_info[coef.parameter_name] = val
            previous_limits = self.session.query(FMSLimits).order_by(FMSLimits.id.desc()).first()
            if previous_limits:
                self.fms_limits = previous_limits.limits
        return test_info

    def encode_image(self, image_input: str | io.BytesIO) -> str:
        """
        Encodes an image (file path or BytesIO) to a base64 string.
        Args:
            image_input (str | io.BytesIO): The image file path or BytesIO object.
        Returns:
            str: The base64 encoded string of the image.
        """
        if isinstance(image_input, io.BytesIO):
            encoded_string = base64.b64encode(image_input.getvalue()).decode('utf-8')
        elif isinstance(image_input, str):
            with open(image_input, "rb") as img_file:
                encoded_string = base64.b64encode(img_file.read()).decode('utf-8')
        else:
            raise TypeError("image_input must be a file path or a BytesIO object")
        return encoded_string

    def decode_image(self, encoded_string: str) -> io.BytesIO:
        image_bytes = base64.b64decode(encoded_string)
        return io.BytesIO(image_bytes)
    
    def convert_docx_to_image_bytes(self, docx_path: str, temp_pdf_path: str = "temp_output.pdf") -> io.BytesIO:
        """
        Converts a DOCX file to an image in BytesIO.
        Args:
            docx_path (str): Path to the DOCX file.
            temp_pdf_path (str): Temporary path for the intermediate PDF file.
        Returns:
            io.BytesIO: The image in BytesIO format.
        """
        with self.output:
            convert(docx_path, temp_pdf_path)
        doc = fitz.open(temp_pdf_path)
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=300)
        img_bytes = io.BytesIO(pix.tobytes("png"))
        os.remove(temp_pdf_path)
        return img_bytes

    def update_tp1_dropdown(self, files: list[str], current_axis: str, dropdown, temp_pdf_path: str = "temp_output.pdf") -> None:
        """
        Updates the TP1 dropdown options based on the provided files and current axis.
        Args:
            files (list[str]): List of file paths to check.
            current_axis (str): The current axis to look for in the files.
            dropdown (widgets.Dropdown): The dropdown widget to update.
            temp_pdf_path (str): Temporary path for the intermediate PDF file.
        """
        def _worker():
            pythoncom.CoInitialize()
            tp1_file = None
            for path in files:
                convert(path, temp_pdf_path)
                doc = fitz.open(temp_pdf_path)
                page = doc.load_page(0)
                text = page.get_text()
                lines = text.split('\n')
                axis_line = next((line for line in lines if f"tp1_{current_axis}:" in line.lower()), None)
                if axis_line:
                    tp1_file = path
                    break
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)

            # Build dropdown options with labels
            options = []
            for f in files:
                base = os.path.basename(f).split(".")[0]
                if f == tp1_file:
                    label = f"{base} (TP1_{current_axis})"
                else:
                    label = base
                options.append((label, f))

            dropdown.options = options

        thread = threading.Thread(target=_worker)
        thread.start()

    def crop_image_bytes(self, image_bytes: io.BytesIO, left: int, top: int, right: int, bottom: int) -> io.BytesIO:
        """
        Crops an image given byte data and dimensions.
        Args:
            image_bytes (io.BytesIO): The image in BytesIO format.
            left (int): Left coordinate.
            top (int): Top coordinate.
            right (int): Right coordinate.
            bottom (int): Bottom coordinate.
        Returns:
            io.BytesIO: The cropped image in BytesIO format.
        """
        img = Image.open(image_bytes)
        cropped = img.crop((left, top, right, bottom))
        cropped_bytes = io.BytesIO()
        cropped.save(cropped_bytes, format='png')
        cropped_bytes.seek(0)
        return cropped_bytes

    def save_current_state(self, next_step: bool = False, current_property_index: int = None, current_test_type: str = None, current_subdict: dict = None) -> None:
        """
        Saves the current state of the testing procedure to the database.
        Args:
            next_step (bool): Whether the state is saved because the procedure is moving to the next step.
            current_property_index (int, optional): The current property index.
            current_test_type (str, optional): The current test type.
            current_subdict (dict, optional): The current sub-dictionary.
        """
        existing_entry = self.session.query(FMSAcceptanceTests).filter_by(fms_id=self.fms_id).first()
        if existing_entry:
            existing_entry.raw_json = self.test_info
            if current_property_index is not None:
                existing_entry.current_property_index = current_property_index
            if current_test_type is not None:
                existing_entry.current_test_type = current_test_type
            existing_entry.current_subdict = current_subdict
        else:
            new_entry = FMSAcceptanceTests(fms_id=self.fms_id, raw_json=self.test_info)
            self.session.add(new_entry)
        if next_step:
            if len(self.main_test_results) > 0:
                existing_entries = self.session.query(FMSTestResults).filter_by(fms_id=self.fms_id).all()
                existing_limits = self.session.query(FMSLimits).filter_by(fms_id=self.fms_id).first()
                if existing_limits:
                    existing_limits.limits = self.fms_limits
                for entry in existing_entries:
                    parameter_name = entry.parameter_name
                    if parameter_name in self.main_test_results:
                        entry.parameter_value = self.main_test_results[parameter_name].get('value') if isinstance(self.main_test_results[parameter_name].get('value'), (int, float)) else None
                        entry.parameter_json = self.main_test_results[parameter_name].get('value') if not isinstance(self.main_test_results[parameter_name].get('value'), (int, float)) else None
                        entry.parameter_unit = self.main_test_results[parameter_name].get('unit')
                        entry.lower = self.main_test_results[parameter_name].get('lower', False)
                        entry.equal = self.main_test_results[parameter_name].get('equal', True)
                        entry.larger = self.main_test_results[parameter_name].get('larger', False)
                        entry.within_limits = self.main_test_results[parameter_name].get('within_limits')
                for param, values in self.main_test_results.items():
                    new_result = FMSTestResults(
                        fms_id=self.fms_id,
                        parameter_name=param,
                        parameter_value=values.get('value') if isinstance(values.get('value'), (int, float)) else None,
                        parameter_json=values.get('value') if not isinstance(values.get('value'), (int, float)) else None,
                        parameter_unit=values.get('unit'),
                        lower=values.get('lower', False),
                        equal=values.get('equal', True),
                        larger=values.get('larger', False),
                        within_limits=values.get('within_limits')
                    )
                    self.session.add(new_result)
        self.session.commit()

    def field(self, description: str, field_width: str = "400px", label_width: str = "160px", height: str = "30px") -> dict:
        return dict(description=description,
                    layout=widgets.Layout(width=field_width, height=height),
                    style={'description_width': label_width})
    
    def start_testing(self) -> None:
        """
        Starts the FMS Acceptance Testing procedure UI.
        """
        self.container.children = []
        self.output.clear_output()

        self.fms_id_widget = widgets.Text(
            value=self.test_info.get('fms_id', None) if not self.fms_id else self.fms_id,
            **self.field("FMS ID:"),
        )

        author = widgets.Text(
            value=self.author,
            disabled=True,
            **self.field("Author:"),
        )

        tvac_box = widgets.Checkbox(
            value=self.test_info.get('tvac', False),
            **self.field("Perform TVAC?:")
        )

        vibration_box = widgets.Checkbox(
            value=self.test_info.get('vibration', False),
            **self.field("Perform Vibration?:")
        )
        def on_field_change(change: dict) -> None:
            self.test_info['author'] = author.value
            self.test_info['vibration'] = vibration_box.value
            self.test_info['tvac'] = tvac_box.value

        self.fms_id_widget.observe(on_field_change, names='value')
        tvac_box.observe(on_field_change, names='value')
        vibration_box.observe(on_field_change, names='value')

        def on_button_click(b) -> None:
            """
            Handles the start button click event to initiate the testing procedure.
            Sets the FMS ID, validates input, retrieves test info, and starts the test procedure.
            """
            self.output.clear_output()
            self.fms_id = self.fms_id_widget.value
            with self.output:
                if not self.fms_id_widget.value or not re.match(r'^\d{2}-\d{3}$', str(self.fms_id_widget.value)):
                    print("Please enter a valid FMS ID (##-###).")
                    return
            if not self.fms_id in self.all_fms_field.options:
                self.all_fms_field.options = list(self.all_fms_field.options) + [self.fms_id]
                self.all_fms_field.value = self.fms_id
                if not self.all_fms_field in self.top_container.children:
                    self.top_container.children = list(self.top_container.children) + [self.all_fms_field]
            self.test_info = self.get_test_info(self.fms_id)
            self.test_types = [k for k in self.test_info.keys() if isinstance(self.test_info[k], dict) and not "data" in k] + ["conclusion", "observations", "recommendations", "annex_a"]

            self.test_info["fms_id"] = self.fms_id
            if not self.current_test_type:
                test_type = self.test_types[0]
            else:
                test_type = self.current_test_type
            with self.output:
                print(self.fms_id)
            self.test_procedure(current_test_type=test_type, current_property_index=self.current_property_index, current_subdict=self.current_subdict)
            tv_info_thread = threading.Thread(target=self.get_tv_info)
            tv_info_thread.start()
            self.save_current_state(current_test_type=self.current_test_type, current_property_index=self.current_property_index, current_subdict=self.current_subdict)

        start_button = widgets.Button(description="Start Procedure", button_style='success', icon='arrow-right')
        start_button.on_click(on_button_click)

        title = widgets.HTML(value="<h2>FMS Acceptance Testing</h2>")

        form = widgets.VBox(
            [
                title,
                widgets.VBox([self.fms_id_widget, author, widgets.HBox([tvac_box, vibration_box])]),
                start_button,
                self.output
            ],
            layout=widgets.Layout(align_items="flex-start", padding="10px", spacing="10px")
        )

        self.container.children = [form]

    def skip_limit_keys(self, index: int, props: list, previous: bool = False) -> int:
        """
        Skips limit-related keys in a list of properties.
        Args:
            index (int): Current index in the properties list.
            props (list): List of property keys.
            previous (bool): If True, skips backwards; otherwise, skips forwards.
        Returns:
            int: The new index after skipping limit-related keys.
        """
        if previous:
            while index >= 0:
                key = props[index]
                if key.startswith("min_") or key.startswith("max_") or key.endswith("_tol") or key.startswith("nominal_"):
                    index -= 1
                else:
                    break
            return max(index, 0)
        else:
            while index < len(props):
                key = props[index]
                if key.startswith("min_") or key.startswith("max_") or key.endswith("_tol") or key.startswith("nominal_"):
                    index += 1
                else:
                    break
            return min(index, len(props) - 1)
        
    def get_hpiv_images(self, test_type: str = None, subdict: str = None) -> widgets.Widget:
        """
        Retrieves HPIV images for the current FMS and TVAC phase.
        Args:
            test_type (str): The test type to retrieve images for.
            subdict (str): The sub-dictionary within the test type.
        Returns:
            widgets.Widget: A widget containing the HPIV images or a message if not available.
        """
        if not subdict:
            opening_image = self.test_info[test_type].get("hpiv_images", {}).get("hpiv_opening_image", None)
            closing_image = self.test_info[test_type].get("hpiv_images", {}).get("hpiv_closing_image", None)
        else:
            opening_image = self.test_info[test_type].get(subdict, {}).get("hpiv_images", {}).get("hpiv_opening_image", None)
            closing_image = self.test_info[test_type].get(subdict, {}).get("hpiv_images", {}).get("hpiv_closing_image", None)

        def extract_number(filename: str) -> int:
            match = re.search(r'tek(\d+)', filename.lower())
            return int(match.group(1)) if match else float('inf')
        
        if not opening_image or not closing_image:
            test_folder = next((folder for folder in self.test_folders if self.fms_id in folder), None)
            if not self.tvac_loop:
                electrical_folder = next((folder for folder in os.listdir(os.path.join(self.test_directory, test_folder)) 
                                        if "Electrical" in folder), None) if test_folder else None
                if electrical_folder:
                    images = [f for f in os.listdir(os.path.join(self.test_directory, test_folder, electrical_folder)) 
                            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]

                    hpiv_opening_image = min(images, key=extract_number)
                    hpiv_closing_image = max(images, key=extract_number)

                    self.test_info[test_type]["hpiv_images"] = {
                        "hpiv_opening_image": self.encode_image(os.path.join(self.test_directory, test_folder, electrical_folder, hpiv_opening_image)) 
                                            if hpiv_opening_image else None,
                        "hpiv_closing_image": self.encode_image(os.path.join(self.test_directory, test_folder, electrical_folder, hpiv_closing_image)) 
                                            if hpiv_closing_image else None
                    }
            else:
                tvac_folder = next((folder for folder in os.listdir(os.path.join(self.test_directory, test_folder)) if "tvac" in folder.lower()), None)
                if tvac_folder:
                    temp_folder = next((folder for folder in os.listdir(os.path.join(self.test_directory, test_folder, tvac_folder)) if self.current_temp.replace("°C", "") in folder), None)
                    if temp_folder:
                        electrical_folder = next((folder for folder in os.listdir(os.path.join(self.test_directory, test_folder, tvac_folder, temp_folder)) if "electrical" in folder.lower()), None)
                        if electrical_folder:
                            images = [f for f in os.listdir(os.path.join(self.test_directory, test_folder, tvac_folder, temp_folder, electrical_folder)) 
                                    if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))]
                            hpiv_opening_image = min(images, key=extract_number)
                            hpiv_closing_image = max(images, key=extract_number)

                            self.test_info[test_type][subdict]["hpiv_images"] = {
                                "hpiv_opening_image": self.encode_image(os.path.join(self.test_directory, test_folder, tvac_folder, temp_folder, electrical_folder, hpiv_opening_image)) 
                                                    if hpiv_opening_image else None,
                                "hpiv_closing_image": self.encode_image(os.path.join(self.test_directory, test_folder, tvac_folder, temp_folder, electrical_folder, hpiv_closing_image)) 
                                                    if hpiv_closing_image else None
                            }

            self.save_current_state()

        pictures = []
        for key in ["hpiv_opening_image", "hpiv_closing_image"]:
            encoded = self.test_info[test_type]["hpiv_images"].get(key) if not subdict else self.test_info[test_type].get(subdict, {}).get("hpiv_images", {}).get(key)
            if encoded:
                img_bytes = self.decode_image(encoded) 
                pictures.append(widgets.Image(value=img_bytes.read(), format='png', layout=widgets.Layout(width='400px', height='300px')))

        if pictures:
            pictures_widget = widgets.HBox(pictures, layout=widgets.Layout(spacing='20px'))

            return pictures_widget
        else:
            return widgets.HTML(value="<i>No HPIV images available, figure it out :).</i>")
        
    def get_vibration_images(self, prop_key: str, test_type: str) -> widgets.Widget:
        """
        Retrieves vibration images for the current FMS and axis.
        Args:
            prop_key (str): The property key to retrieve images for.
            test_type (str): The test type to retrieve images for.
        Returns:
            widgets.Widget: A widget containing the vibration image or a message if not available.
        """
        image = self.test_info[test_type].get(prop_key, {}).get("image", "")
        current_axis = prop_key[-1]
        if image:
            path = self.test_info[test_type].get(prop_key, {}).get("path", "")
            file_name = os.path.basename(path) if path else ""
        else:
            file_name = ""

        vibration_folder = next((folder for folder in self.vibration_folders if self.fms_id in folder), None)
        folder = None
        dropdown = widgets.Dropdown(
            options=[],
            style={'description_width': '250px'},
            layout=widgets.Layout(width="500px"),
            value=None
        )

        if vibration_folder:
            self.test_info["nlr_document"] = os.path.basename(vibration_folder)
            if not "setup" in prop_key:
                data_folder = next((folder for folder in os.listdir(os.path.join(self.vibration_directory, vibration_folder)) if "vibration data" in folder.lower()), None)
                if data_folder:
                    if "overlay" in prop_key:
                        folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, data_folder)) if "comparison" in f.lower()), None)
                        if folder:
                            options = sorted([f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, data_folder, folder)) if f"({current_axis})" in f.lower()], key = lambda x: int(x.split("_")[-1].split(".")[0]))
                            dropdown.options = [(os.path.basename(f).split(".")[0], f) for f in options if f.lower().endswith(('.docx'))]
                            dropdown.description = f"Overlay Image RS on {current_axis}-axis:"
                            dropdown.value = None if not image else file_name
                            # files = [os.path.join(self.vibration_directory, vibration_folder, data_folder, folder, f)
                            # for f in options if f.lower().endswith('.docx')]
                            # self.update_tp1_dropdown(files, current_axis, dropdown)
                    elif "rs" in prop_key:
                        folders = [f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, data_folder)) if "ts-" in f.lower() and "rs" in f.lower() and f"({current_axis})" in f.lower()]
                        if folders:
                            sorted_folders = sorted(folders, key = lambda x: int(os.path.basename(x).split(" ")[0].split("-")[-1]))
                            pre_rs_folder = sorted_folders[0]
                            post_rs_folder = sorted_folders[-1]
                            if "pre" in prop_key:
                                folder = pre_rs_folder
                            elif "post" in prop_key:
                                folder = post_rs_folder
                            acceleration_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, data_folder, folder)) if "acceleration" in f.lower()), None)
                            if acceleration_folder:
                                folder = os.path.join(folder, acceleration_folder)
                                options = [f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, data_folder, folder)) if f.lower().endswith(('.docx')) and (f"{current_axis}_+{current_axis}" in f.lower()\
                                           or f"{current_axis}_-{current_axis}" in f.lower())]
                                dropdown.options = [(os.path.basename(f).split(".")[0], f) for f in options]
                                dropdown.description = f"Select RS Image for {current_axis}-axis:"
                                dropdown.value = None if not image else file_name

                    elif "random_vibration" in prop_key:
                        parent_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, data_folder)) if "random" in f.lower() and f"({current_axis})" in f.lower()), None)
                        if parent_folder:
                            measurement_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, data_folder, parent_folder)) if "measurement" in f.lower()), None)
                            if measurement_folder:
                                folder = os.path.join(parent_folder, measurement_folder)
                                options = [f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, data_folder, folder)) if f.lower().endswith(('.docx')) and (f"{current_axis}_+{current_axis}" in f.lower()\
                                           or f"{current_axis}_-{current_axis}" in f.lower())]
                                dropdown.options = [(os.path.basename(f).split(".")[0], f) for f in options]
                                dropdown.description = f"Select Random Vibration Image for {current_axis}-axis:"
                                dropdown.value = None if not image else file_name
            else:
                picture_folder = next((folder for folder in os.listdir(os.path.join(self.vibration_directory, vibration_folder)) if "pictures" in folder.lower()), None)
                if picture_folder:
                    if current_axis == 'x':
                        x_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, picture_folder)) if "x-axis" in f.lower()), None)
                        if x_folder:
                            before_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, picture_folder, x_folder)) if "before test" in f.lower()), None)
                            if before_folder:
                                folder = os.path.join(x_folder, before_folder)
                    elif current_axis == 'y':
                        y_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, picture_folder)) if "y-axis" in f.lower()), None)
                        if y_folder:
                            before_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, picture_folder, y_folder)) if "before test" in f.lower()), None)
                            if before_folder:
                                folder = os.path.join(y_folder, before_folder)
                    elif current_axis == 'z':
                        z_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, picture_folder)) if "z-axis" in f.lower()), None)
                        if z_folder:
                            before_folder = next((f for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, picture_folder, z_folder)) if "before test" in f.lower()), None)
                            if before_folder:
                                folder = os.path.join(z_folder, before_folder)

                    if folder:
                        dropdown.options = [
                            (os.path.basename(f).split(".")[0], f)
                            for f in os.listdir(os.path.join(self.vibration_directory, vibration_folder, picture_folder, folder))
                            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.gif'))
                        ]
                        dropdown.description = f"Select Image for {current_axis}-axis:"
                        dropdown.value = None if not image else file_name

            def on_image_change(change: dict) -> None:
                """
                Handles the image selection change event.
                Retrieves and displays the selected image.
                Args:
                    change (dict): The change event dictionary (built-in from observer).
                """
                nonlocal image, file_name
                self.output.clear_output()
                if change['name'] == 'value' and change['new']:
                    selected_image_path = change['new']
                    if os.path.basename(selected_image_path) == file_name:
                        return
                    file_name = os.path.basename(selected_image_path)
                    if "setup" in prop_key:
                        form.children = [dropdown, widgets.HTML(value="<i>Loading image, please wait...</i>")]
                        full_path = os.path.join(self.vibration_directory, vibration_folder, picture_folder, folder, selected_image_path)
                        self.test_info[test_type][prop_key]["image"] = self.encode_image(full_path)
                        self.test_info[test_type][prop_key]["path"] = full_path
                        self.save_current_state()

                        image_widget = widgets.Image(
                            value=self.decode_image(self.test_info[test_type][prop_key]["image"]).read(),
                            format='png',
                            layout=widgets.Layout(max_width='600px', max_height='600px')
                        )
                    else:
                        full_path = os.path.join(self.vibration_directory, vibration_folder, data_folder, folder, selected_image_path)
                        form.children = [dropdown, widgets.HTML(value="<i>Processing image, please wait...</i>")]
                        docx_image_bytes = self.convert_docx_to_image_bytes(full_path)
                        cropped_image_bytes = self.crop_image_bytes(docx_image_bytes, left=300, top=100, right=3300, bottom=2065)

                        self.test_info[test_type][prop_key]["image"] = self.encode_image(cropped_image_bytes)
                        self.test_info[test_type][prop_key]["path"] = full_path
                        self.save_current_state()

                        image_widget = widgets.Image(
                            value=cropped_image_bytes.read(),
                            format='png',
                            layout=widgets.Layout(max_width='1000px', max_height='1000px')
                        )

                    form.children = [dropdown, image_widget]

            if folder:
                dropdown.observe(on_image_change, names='value')

            form = widgets.VBox([dropdown], layout=widgets.Layout(spacing='10px'))
            if image:
                img_bytes = self.decode_image(image)
                if "setup" in prop_key:
                    image_widget = widgets.Image(
                        value=img_bytes.read(),
                        format='png',
                        layout=widgets.Layout(max_width='600px', max_height='600px')
                    )
                else:
                    image_widget = widgets.Image(
                        value=img_bytes.read(),
                        format='png',
                        layout=widgets.Layout(max_width='1000px', max_height='1000px')
                    )
                form.children = [dropdown, image_widget]

            return form
        else:
            form = widgets.HTML(value="<i>No vibration images available, figure it out :).</i>")
            self.test_info[test_type][prop_key]["image"] = "None"
            self.test_info[test_type][prop_key]["path"] = "None"
            self.save_current_state()
            return form

    def get_functional_plots(self, prop_key: str, test_type: str, form: widgets.Widget = None, subdict: str = None) -> widgets.Widget:
        """
        Retrieves functional test plots for the current FMS.
            Generates plots for open loop, closed loop, slope, FR and TVAC tests.
        Args:
            prop_key (str): The property key to retrieve plots for.
            test_type (str): The test type to retrieve plots for.
            form (widgets.Widget): The form widget to add plots to.
            subdict (str): The sub-dictionary within the test type.
        Returns:
            widgets.Widget: A widget containing the functional test plot.
        """
        if form is None:
            form = widgets.VBox(layout=widgets.Layout(spacing="50px"))
        self.fms_query.load_all_tests(fms_id=self.fms_id)

        def get_container():
            return self.test_info[test_type] if not self.tvac_loop else self.test_info[test_type][subdict]

        def get_extra_plots():
            return get_container().setdefault('extra_plots', [])

        def get_used_tests():
            container = get_container()
            primary = container.get(prop_key, {}).get('test_id')
            extras = [p['test_id'] for p in container.get('extra_plots', []) if p['prop_key'] == prop_key]
            return set(filter(None, [primary] + extras))

        def add_extra_plot_entry(test_id: str, image: bytes = None):
            get_extra_plots().append({'test_id': test_id, 'image': image, 'prop_key': prop_key, 'title': ""})
            self.save_current_state()

        def remove_extra_plot_entry(test_id: str):
            extra_plots = get_extra_plots()
            get_container()['extra_plots'] = [p for p in extra_plots if p['test_id'] != test_id]
            used_tests = get_container().get('used_tests', [])
            if test_id in used_tests:
                used_tests.remove(test_id)
            get_container()['used_tests'] = used_tests
            self.save_current_state()

        test_map: dict[str, list[FMSFunctionalTests | FMSTvac | FMSFRTests]] = {
            'low_closed_loop_plot': [f for f in self.fms_query.get_closed_loop_tests() if f.test_type == FunctionalTestType.LOW_CLOSED_LOOP],
            'low_slope_plot': [f for f in self.fms_query.get_slope_tests() if f.test_type == FunctionalTestType.LOW_SLOPE],
            'fr_performance_plot': self.fms_query.get_fr_tests(),
            'tvac_summary_plot': self.fms_query.get_tvac_tests(),
            'high_closed_loop_plot': [f for f in self.fms_query.get_closed_loop_tests() if f.test_type == FunctionalTestType.HIGH_CLOSED_LOOP],
            'high_slope_plot': [f for f in self.fms_query.get_slope_tests() if f.test_type == FunctionalTestType.HIGH_SLOPE],
            'high_open_loop_plot': [f for f in self.fms_query.get_open_loop_tests() if f.test_type == FunctionalTestType.HIGH_OPEN_LOOP],
            'low_open_loop_plot': [f for f in self.fms_query.get_open_loop_tests() if f.test_type == FunctionalTestType.LOW_OPEN_LOOP],
        }

        function_map = {
            'slope': self.fms_query.open_loop_test_query,
            'open_loop': self.fms_query.open_loop_test_query,
            'closed_loop': self.fms_query.closed_loop_test_query,
            'fr': self.fms_query.fr_test_query,
            'tvac': self.fms_query.tvac_cycle_query
        }

        container = get_container()

        if not prop_key == "tvac_summary_plot":
            all_options = [(f"{t.test_id} - {t.trp_temp} [degC], {t.inlet_pressure} [barA]", t.test_id)
                        for t in test_map.get(prop_key, []) if (t.temp_type == self.tvac_loop if self.tvac_loop else True)]
        else:
             all_options = [(t.test_id, t.test_id) for t in test_map.get(prop_key, [])]

        if not self.tvac_loop and all_options:
            all_options = [all_options[0]]
        elif self.tvac_loop == FunctionalTestType.ROOM and len(all_options) > 1:
            all_options = all_options[1:]

        extra_plot_button = widgets.Button(description="Add Extra Plot", button_style='info', icon='plus')

        def update_extra_plot_button(delete: bool = False) -> None:
            primary_selected = bool(container.get(prop_key, {}).get('test_id'))
            used = get_used_tests()
            available = [val for _, val in all_options if val not in used]
            children = [child for child in form.children]
            if primary_selected and available:
                if extra_plot_button not in children:
                    children.append(extra_plot_button)
            elif extra_plot_button in children and delete:
                children.remove(extra_plot_button)
            form.children = children

        def create_plot_block(is_primary: bool = False, preset_test_id: str = None, preset_image: bytes = None) -> widgets.Widget:
            """
            Creates a plot selection block for the functional test plots.
            Provides all test runs for the current property as options.
            Args:
                is_primary (bool): Whether the block is for the primary plot.
                preset_test_id (str): The preset test ID to select.
                preset_image (bytes): The preset image bytes to display.
            Returns:
                widgets.Widget: The plot selection block widget.
            """
            used = get_used_tests()
            dropdown_options = [("", "")]
            for opt, val in all_options:
                if is_primary or val not in used or val == preset_test_id:
                    dropdown_options.append((opt, val))
            if preset_test_id and preset_test_id not in [v for _, v in dropdown_options]:
                dropdown_options.append((preset_test_id, preset_test_id))

            dropdown = widgets.Dropdown(
                options=dropdown_options,
                description="Select Test:",
                style={'description_width': '120px'},
                layout=widgets.Layout(width="450px"),
                value=preset_test_id or ""
            )

            image_widget = widgets.Image(layout=widgets.Layout(width='800px', height='600px'))
            if preset_image:
                image_widget.value = preset_image.read()
                image_widget.format = 'png'

            delete_button = widgets.Button(description="DELETE", button_style='danger', icon='trash')

            initial_children = [dropdown]
            if is_primary and preset_image:
                initial_children.append(image_widget)
            if not is_primary and preset_test_id:
                initial_children += [image_widget, delete_button]

            container_widget = widgets.VBox(initial_children, layout=widgets.Layout(spacing="10px"))

            def remove_block(_=None):
                if not is_primary:
                    remove_extra_plot_entry(dropdown.value)
                form.children = [child for child in form.children if child is not container_widget]
                update_extra_plot_button(delete=True)

            delete_button.on_click(remove_block)

            def on_change(change: dict) -> None:
                """
                Handles the test selection change event.
                    Retrieves and displays the selected plot.
                Args:
                    change (dict): The change event dictionary (built-in from observer).
                """
                selected_test_id = change['new']
                key = next(k for k in function_map if k in prop_key)
                if is_primary:
                    if not selected_test_id:
                        container[prop_key] = {}
                        container_widget.children = [dropdown]
                    else:
                        image_bytes = function_map[key](selected_test_id, plot=False) if not "open_loop" in key else function_map[key](selected_test_id, test_type='open_loop', plot=False)
                        encoded = self.encode_image(image_bytes) if image_bytes else None
                        container[prop_key] = {'test_id': selected_test_id, 'image': encoded}
                        children = [dropdown]
                        if image_bytes:
                            image_widget.value = image_bytes.read()
                            image_widget.format = 'png'
                            children.append(image_widget)
                        container_widget.children = children
                    form.children = [container_widget]
                else:
                    if not selected_test_id:
                        remove_block()
                        return
                    existing = next((p for p in get_extra_plots() if p['test_id'] == selected_test_id), None)
                    image_bytes = function_map[key](selected_test_id, plot=False) if not "open_loop" in key else function_map[key](selected_test_id, test_type='open_loop', plot=False)
                    encoded = self.encode_image(image_bytes) if image_bytes else None
                    if existing:
                        existing['image'] = encoded
                    else:
                        add_extra_plot_entry(selected_test_id, encoded)
                    children = [dropdown]
                    if image_bytes:
                        image_widget.value = image_bytes.read()
                        image_widget.format = 'png'
                        children.append(image_widget)
                    children.append(delete_button)
                    container_widget.children = children
                self.save_current_state()
                update_extra_plot_button()

            dropdown.observe(on_change, names='value')
            return container_widget

        def add_extra_plot(b) -> None:
            new_block = create_plot_block(is_primary=False)
            children = list(form.children)
            idx = children.index(extra_plot_button) if extra_plot_button in children else len(children)
            children.insert(idx, new_block)
            form.children = children
            update_extra_plot_button()

        extra_plot_button.on_click(add_extra_plot)

        primary_dict = container.get(prop_key, {})
        primary_bytes = self.decode_image(primary_dict.get('image')) if primary_dict.get('image') else None
        form.children = [create_plot_block(is_primary=True, preset_test_id=primary_dict.get('test_id'), preset_image=primary_bytes)]

        for extra in get_extra_plots():
            if extra['prop_key'] == prop_key:
                extra_bytes = self.decode_image(extra.get('image')) if extra.get('image') else None
                children = list(form.children)
                children.append(create_plot_block(is_primary=False, preset_test_id=extra['test_id'], preset_image=extra_bytes))
                form.children = children

        update_extra_plot_button()
        return form
    
    def check_tvac(self, test_type: str) -> None:
        if "tvac_results" in test_type:
            self.tvac_type = test_type.split("_")[-1]
            self.tvac_loop = next((i for i in FunctionalTestType if self.tvac_type in i.value), None)
            self.current_temp = self.tvac_map[self.tvac_loop]

    def get_opening_temperature(self, temperature: np.array, flow_rate: np.array, tv_power: np.array) -> tuple[float | None, float]:
        """
        Determines the opening temperature and corresponding TV power from the provided data.
            Smoothens provided temperature and flow rate data, and calculates the opening temperature by finding the first 'inflection'.
        Args:
            temperature (np.array): Array of temperature data.
            flow_rate (np.array): Array of flow rate data.
            tv_power (np.array): Array of TV power data.
        Returns:
            tuple[float | None, float]: The opening temperature and corresponding TV power.
        """
        temperature = temperature.tolist()
        flow_rate = flow_rate.tolist()
        tv_power = tv_power.tolist()
        n_points = len(temperature)

        savgol_window = min(n_points - 1 if n_points % 2 == 0 else n_points, max(15, n_points // 10))
        y_smooth = savgol_filter(flow_rate, window_length=savgol_window, polyorder=2)
        x_smooth = temperature

        slope_window = max(10, len(x_smooth) // 50)
        slopes = []
        for i in range(len(x_smooth) - slope_window):
            X = np.array(x_smooth[i:i + slope_window]).reshape(-1, 1)
            y = np.array(y_smooth[i:i + slope_window])
            model = LinearRegression().fit(X, y)
            slopes.append(model.coef_[0])

        slopes = [0] * (slope_window // 2) + slopes + [0] * (len(x_smooth) - len(slopes) - slope_window // 2)

        max_slope = max(slopes)
        threshold = max_slope * 0.005
        start_index = int(len(slopes) * 0.6)
        inflection_index = next((i for i in range(start_index, len(slopes)) if slopes[i] > threshold), None)

        opening_temperature = temperature[inflection_index] if inflection_index is not None else None
        opening_power = tv_power[inflection_index]
        return opening_temperature, opening_power

    def get_tv_info(self) -> None:
        """
        Retrieves and calculates relevant combinations of TV temperature and TV power,
            at key points in FMS flow testing.
        """

        self.fms_query.load_all_tests(fms_id=self.fms_id)
        open_loop_tests = self.fms_query.get_open_loop_tests()
        keys_list = [
            "tv_full_open",
            "tv_full_open_power",
            "hot_tv_full_open",
            "hot_tv_full_open_power",
            "hot_low_tv_temp",
            "hot_low_tv_power_check",
            "hot_low_tv_temp_check",
            "hot_high_tv_temp",
            "hot_high_tv_power_check",
            "hot_high_tv_temp_check",
            "cold_tv_full_open",
            "cold_tv_full_open_power",
            "cold_low_tv_temp",
            "cold_low_tv_power_check",
            "cold_low_tv_temp_check",
            "cold_high_tv_temp",
            "cold_high_tv_power_check",
            "cold_high_tv_temp_check",
            "room_tv_full_open",
            "room_tv_full_open_power",
            "room_low_tv_temp",
            "room_low_tv_power_check",
            "room_low_tv_temp_check",
            "room_high_tv_temp",
            "room_high_tv_power_check",
            "room_high_tv_temp_check"
        ]

        if not all(self.test_info.get(key, None) for key in keys_list):
            test_types = [FunctionalTestType.ROOM, FunctionalTestType.HOT, FunctionalTestType.COLD, FunctionalTestType.ROOM]
            for idx, temp_type in enumerate(test_types):
                low_open_loop_tests = [t for t in open_loop_tests if t.test_type == FunctionalTestType.LOW_OPEN_LOOP and t.temp_type == temp_type]
                if low_open_loop_tests:
                    if idx == 0:
                        relevant_test = sorted(low_open_loop_tests, key=lambda x: x.date)[0] 
                        tvac_key = ""
                        high_relevant_test = None
                    else:
                        relevant_test = low_open_loop_tests[-1]
                        high_open_loop_tests = [t for t in open_loop_tests if t.test_type == FunctionalTestType.HIGH_OPEN_LOOP and t.temp_type == temp_type]
                        high_relevant_test = high_open_loop_tests[-1] if high_open_loop_tests else None
                        tvac_key = temp_type.value.split("_")[0] + "_"
                    if relevant_test:
                        results: list[FMSFunctionalResults] = relevant_test.functional_results
                        if results: 
                            df = pd.DataFrame([{
                                'parameter_name': res.parameter_name,
                                'parameter_value': res.parameter_value,
                            } for res in results])
                            params = [FMSFlowTestParameters.AVG_TV_POWER.value,
                                    FMSFlowTestParameters.TOTAL_FLOW.value,
                                    FMSFlowTestParameters.TV_PT1000.value]

                            df_filtered = df[df['parameter_name'].isin(params)]
                            tv_power = df_filtered.loc[df_filtered['parameter_name'] == FMSFlowTestParameters.AVG_TV_POWER.value, 'parameter_value'].to_numpy()
                            total_flow = df_filtered.loc[df_filtered['parameter_name'] == FMSFlowTestParameters.TOTAL_FLOW.value, 'parameter_value'].to_numpy()
                            pt1000 = df_filtered.loc[df_filtered['parameter_name'] == FMSFlowTestParameters.TV_PT1000.value, 'parameter_value'].to_numpy()
                            tv_full_open_idx = np.argmax(total_flow)
                            tv_full_open = pt1000[tv_full_open_idx]
                            tv_full_open_power = np.max(tv_power)
                            self.test_info[f"{tvac_key}tv_full_open"] = round(tv_full_open,1)
                            self.test_info[f"{tvac_key}tv_full_open_power"] = round(tv_full_open_power,2)
                            if not idx == 0:
                                low_tv_temp = pt1000[0]
                                self.test_info[f"{tvac_key}low_tv_temp"] = round(low_tv_temp,1)
                                opening_temp, opening_power = self.get_opening_temperature(pt1000, total_flow, tv_power)
                                self.test_info[f"{tvac_key}low_tv_temp_check"] = round(opening_temp,1)
                                self.test_info[f"{tvac_key}low_tv_power_check"] = round(opening_power,2)
                        if high_relevant_test:
                            high_results: list[FMSFunctionalResults] = high_relevant_test.functional_results
                            if high_results:
                                high_df = pd.DataFrame([{
                                    'parameter_name': res.parameter_name,
                                    'parameter_value': res.parameter_value,
                                } for res in high_results])
                                high_df_filtered = high_df[high_df['parameter_name'].isin(params)]
                                high_tv_power = high_df_filtered.loc[high_df_filtered['parameter_name'] == FMSFlowTestParameters.AVG_TV_POWER.value, 'parameter_value'].to_numpy()
                                high_total_flow = high_df_filtered.loc[high_df_filtered['parameter_name'] == FMSFlowTestParameters.TOTAL_FLOW.value, 'parameter_value'].to_numpy()
                                high_pt1000 = high_df_filtered.loc[high_df_filtered['parameter_name'] == FMSFlowTestParameters.TV_PT1000.value, 'parameter_value'].to_numpy()
                                high_tv_temp = high_pt1000[0]
                                self.test_info[f"{tvac_key}high_tv_temp"] = round(high_tv_temp,1)
                                high_opening_temp, high_opening_power = self.get_opening_temperature(high_pt1000, high_total_flow, high_tv_power)
                                self.test_info[f"{tvac_key}high_tv_temp_check"] = round(high_opening_temp,1)
                                self.test_info[f"{tvac_key}high_tv_power_check"] = round(high_opening_power,2)

        else:
            for key in keys_list:
                self.test_info[key] = round(self.test_info[key], 2) if "power" in key else round(self.test_info[key], 1)

    def get_power_budget_fields(self, prop_key: str, prop_dict: dict, test_type: str) -> widgets.VBox:
        """
        Generates power budget input fields for the specified property key and test type.
        Args:
            prop_key (str): The property key to generate fields for.
            prop_dict (dict): The property dictionary containing power budget data.
            test_type (str): The test type to generate fields for.
        Returns:
            widgets.VBox: A VBox widget containing the power budget input fields.
        """
        monitoring_value = self.test_info[test_type][prop_key].get("monitoring", None)
        nominal_value = self.test_info[test_type][prop_key].get("nominal", None)
        peak_value = self.test_info[test_type][prop_key].get("peak", None)

        field_width = "180px"
        label_width = "250px"

        monitoring_field = widgets.FloatText(
            value=monitoring_value,
            **self.field("Monitoring Power [W]", label_width, field_width)
        )
        nominal_field = widgets.FloatText(
            value=nominal_value,
            **self.field("Nominal Power [W]", label_width, field_width)
        )
        peak_field = widgets.FloatText(
            value=peak_value,
            **self.field("Peak Power [W]", label_width, field_width)
        )

        top_field = widgets.HBox(
            [monitoring_field, nominal_field, peak_field],
            layout=widgets.Layout(
                justify_content="flex-start",
                width="100%",
                gap="40px",
                flex_wrap="wrap"
            )
        )

        form_items = [top_field]
        components = self.test_info[test_type][prop_key].get("components", {})

        def update_val(change: dict, key: str, field: widgets.FloatText, component_name: str | None = None) -> None:
            """
            Updates the power budget values in the test info dictionary.
            Args:
                change (dict): The change event dictionary (built-in from observer).
                key (str): The key to update in the test info dictionary.
                field (widgets.FloatText): The field widget that triggered the change.
                component_name (str | None): The name of the component to update, if applicable.
            """
            nonlocal components
            if component_name:
                idx = next((i for i, comp in enumerate(components) if comp["component"] == component_name), None) if component_name else None
                if idx is not None:
                    components[idx][key] = field.value
                    self.test_info[test_type][prop_key]["components"] = components
                    self.save_current_state()
            else:
                self.test_info[test_type][prop_key][key] = field.value
                self.save_current_state()

        for child in top_field.children:
            if "Monitoring" in child.description:
                child.observe(lambda change, key="monitoring", field=monitoring_field: update_val(change, key, field), names="value")
            elif "Nominal" in child.description:
                child.observe(lambda change, key="nominal", field=nominal_field: update_val(change, key, field), names="value")
            elif "Peak" in child.description:
                child.observe(lambda change, key="peak", field=peak_field: update_val(change, key, field), names="value")

        for component_dict in components:
            component_name = component_dict["component"]
            description = component_name

            if "min_power" in component_dict and "max_power" in component_dict:
                min_power = component_dict["min_power"]
                max_power = component_dict["max_power"]

                min_field = widgets.FloatText(
                    value=min_power,
                    **self.field(f"{description} Min Power [W]", label_width, field_width)
                )
                max_field = widgets.FloatText(
                    value=max_power,
                    **self.field(f"{description} Peak Power [W]", label_width, field_width)
                )

                component_field = widgets.HBox(
                    [min_field, max_field],
                    layout=widgets.Layout(
                        justify_content="flex-start",
                        width="100%",
                        gap="40px",
                        flex_wrap="wrap"
                    )
                )

                min_field.observe(lambda change, key="min_power", component_name=component_name, field=min_field: update_val(change, key, field, component_name), names="value")
                max_field.observe(lambda change, key="max_power", component_name=component_name, field=max_field: update_val(change, key, field, component_name), names="value")

            else:
                power_value = component_dict.get("power", None)
                component_field = widgets.FloatText(
                    value=power_value,
                    **self.field(f"{description} Power [W]", label_width, field_width)
                )
                component_field.observe(lambda change, key="power", component_name=component_name, field=component_field: update_val(change, key, field, component_name), names="value")

            form_items.append(component_field)

        form = widgets.VBox(
            form_items,
            layout=widgets.Layout(
                width="100%",
                align_items="flex-start",
                gap="15px",
                overflow_x="auto"
            )
        )

        return form

    def get_conclusion_field(self) -> widgets.VBox:
        """
        Generates a conclusion input field for the test info.
        Returns:
            widgets.VBox: A VBox widget containing the conclusion input field.
        """

        conclusion_text = self.test_info.get("conclusion", "")
        conclusion_area = widgets.Textarea(
            value=conclusion_text,
            placeholder="Enter conclusion here...",
            description="Conclusion:",
            layout=widgets.Layout(width="75%", height="60px"),
            style={'description_width': '100px'}
        )

        def update_conclusion(change):
            if change['name'] == 'value':
                self.test_info["conclusion"] = change['new']
                self.save_current_state()

        conclusion_area.observe(update_conclusion, names='value')

        return widgets.VBox([conclusion_area, widgets.VBox([], layout=widgets.Layout(height="20px"))])

    def get_annex_a(self, annex_a_start: int = 0, property_nav: widgets.Dropdown | None = None):
        """
        Generates widgets for navigating and editing Annex A components.
        Args:
            annex_a_start (int): The starting index for the Annex A components.
            property_nav (widgets.Dropdown | None): The dropdown widget for navigating components.
        Returns:
            widgets.VBox: A VBox widget containing the Annex A component navigation and editing widgets.
        """
        annex_a_components = self.test_info.get("annex_a", [])
        current_idx = annex_a_start

        component_box = widgets.VBox(layout=widgets.Layout(margin="10px"))

        def build_component_widget(idx: int) -> None:
            component_dict = annex_a_components[idx]
            fields = []
            property_nav.value = idx
            for key, value in component_dict.items():
                description = " ".join(word.capitalize() for word in key.split("_")) + ":"

                if "date" in key.lower():
                    if value:
                        try:
                            parsed_date = datetime.strptime(value, "%Y-%m-%d").date()
                        except ValueError:
                            parsed_date = datetime.strptime(value, "%d-%m-%Y").date()
                    else:
                        parsed_date = None

                    field = widgets.DatePicker(
                        value=parsed_date,
                        **self.field(description, "500px", "150px")
                    )
                else:
                    field = widgets.Textarea(
                        value=value if value else "",
                        **self.field(description, "500px", "150px")
                    )

                def make_observer(field_key, f):
                    def observer(change):
                        if change['name'] == 'value':
                            annex_a_components[idx][field_key] = (
                                f.value.strftime("%d-%m-%Y") if isinstance(f, widgets.DatePicker) and f.value else f.value
                            )
                            self.test_info["annex_a"] = annex_a_components
                            self.save_current_state()
                    return observer

                field.observe(make_observer(key, field), names='value')
                fields.append(field)

            component_box.children = fields

        def all_fields_filled() -> bool:
            for f in component_box.children:
                if isinstance(f, widgets.Textarea) and not f.value.strip():
                    with self.output:
                        self.output.clear_output()
                        print("Please fill in all fields before proceeding to the next component.")
                    return False
                if isinstance(f, widgets.DatePicker) and not f.value:
                    with self.output:
                        self.output.clear_output()
                        print("Please fill in all fields before proceeding to the next component.")
                    return False
            return True

        def on_next(_) -> None:
            nonlocal current_idx
            if not all_fields_filled():
                return  
            current_idx = (current_idx + 1) % len(annex_a_components)
            build_component_widget(current_idx)

        def on_prev(_) -> None:
            nonlocal current_idx
            current_idx = (current_idx - 1) % len(annex_a_components)
            build_component_widget(current_idx)

        prev_btn = widgets.Button(description="Previous", button_style='danger', icon='arrow-left')
        next_btn = widgets.Button(description="Next", button_style='info', icon='arrow-right')
        prev_btn.on_click(on_prev)
        next_btn.on_click(on_next)
        nav_box = widgets.HBox([prev_btn, next_btn], layout=widgets.Layout(margin="10px 0px 0px 0px"))

        if annex_a_components:
            build_component_widget(current_idx)

        return widgets.VBox([component_box, nav_box])
    
    def get_recommendations(self) -> widgets.VBox:
        """
        Generates a recommendations input field for the test info.
        Returns:
            widgets.VBox: A VBox widget containing the recommendations input field.
        """
        recommendation_text = self.test_info.get('recommendations', "")
        recommendation_area = widgets.Textarea(
            value=recommendation_text,
            placeholder="Enter recommendations here...",
            description="Recommendations:",
            layout=widgets.Layout(width="75%", height="60px"),
            style={'description_width': '120px'}
        )
        def update_recommendations(change: dict) -> None:
            if change['name'] == 'value':
                self.test_info['recommendations'] = change['new']
                self.save_current_state()

        recommendation_area.observe(update_recommendations, names='value')
        return widgets.VBox([recommendation_area, widgets.VBox([],layout=widgets.Layout(height="20px"))])

    def get_observations(self) -> widgets.VBox:
        """
        Generates dynamic observation input fields for the test info.
        Returns:
            widgets.VBox: A VBox widget containing the observation input fields.
        """
        observations_list = self.test_info.get("observations", [])
        observation_widgets = []

        if not observations_list:
            observations_list = [{"text": ""}]
            self.test_info["observations"] = observations_list

        def rebuild_ui() -> None:
            # Re-number all textareas
            textareas = [w for w in observation_widgets if isinstance(w, widgets.Textarea)]
            for idx, field in enumerate(textareas):
                field.description = f"Observation {idx + 1}:"
            self.observation_box.children = observation_widgets + [self.add_button]
            _update_add_button_state()

        def _update_add_button_state() -> None:
            textareas = [w for w in observation_widgets if isinstance(w, widgets.Textarea)]
            self.add_button.disabled = not (textareas and textareas[-1].value.strip())

        def make_update_observation(field) -> callable:
            def update_observation(change: dict) -> None:
                if change['name'] == 'value':
                    textareas = [w for w in observation_widgets if isinstance(w, widgets.Textarea)]
                    idx = textareas.index(field)
                    self.test_info["observations"][idx]["text"] = change['new']
                    self.save_current_state()
                    _update_add_button_state()
            return update_observation

        def make_delete_button(field: widgets.Textarea, button: widgets.Button) -> callable:
            def delete_observation(_):
                textareas = [w for w in observation_widgets if isinstance(w, widgets.Textarea)]
                idx = textareas.index(field)
                del self.test_info["observations"][idx]
                observation_widgets.remove(field)
                observation_widgets.remove(button)
                self.save_current_state()
                rebuild_ui()
            return delete_observation

        # Preload observations
        for idx, obs in enumerate(observations_list):
            field = widgets.Textarea(
                value=obs["text"],
                placeholder="Enter observation here...",
                layout=widgets.Layout(width="75%", height="60px"),
                style={'description_width': '120px'}
            )
            field.observe(make_update_observation(field), names='value')
            observation_widgets.append(field)

            if idx > 0:  # all non-first observations get delete buttons
                btn = widgets.Button(
                    description="Delete",
                    button_style='danger',
                    icon='trash',
                    layout=widgets.Layout(width="100px")
                )
                btn.on_click(make_delete_button(field, btn))
                observation_widgets.append(btn)

        def add_observation(_) -> None:
            field = widgets.Textarea(
                value="",
                placeholder="Enter observation here...",
                layout=widgets.Layout(width="75%", height="60px"),
                style={'description_width': '120px'}
            )
            field.observe(make_update_observation(field), names='value')

            btn = widgets.Button(
                description="Delete",
                button_style='danger',
                icon='trash',
                layout=widgets.Layout(width="100px")
            )
            btn.on_click(make_delete_button(field, btn))

            self.test_info["observations"].append({"text": ""})
            observation_widgets.extend([field, btn])
            self.save_current_state()
            rebuild_ui()

        self.add_button = widgets.Button(description="Add Observation", button_style='info', icon='plus')
        self.add_button.on_click(add_observation)

        self.observation_box = widgets.VBox()
        rebuild_ui()
        return self.observation_box

    def generate_property_fields(self, prop_key: str, prop_dict: dict, test_type: str, subdict: str | None = None) -> widgets.VBox:
        """
        Generates input fields for a given property key and test type.
        Args:
            prop_key (str): The property key to generate fields for.
            prop_dict (dict): The property dictionary containing data.
            test_type (str): The test type to generate fields for.
            subdict (str | None): An optional sub-dictionary key.
        Returns:
            widgets.VBox: A VBox widget containing the generated input fields.
        """
        elements = []

        if test_type == "power_budgets":
            return self.get_power_budget_fields(prop_key, prop_dict, test_type)

        if prop_key.endswith("images") and "hpiv" in prop_key:
            return self.get_hpiv_images(test_type=test_type, subdict=subdict)
        
        if "plot" in prop_key and not prop_key == 'extra_plots' and (test_type == 'functional_performance' or "tvac_results" in test_type or "tvac_summary" in test_type):
            return self.get_functional_plots(prop_key, test_type) if not self.tvac_loop else self.get_functional_plots(prop_key, test_type, subdict=subdict)

        if test_type == "vibration_results":
            return self.get_vibration_images(prop_key, test_type)

        if not isinstance(prop_dict, dict) and not isinstance(prop_dict, list):
            value = prop_dict
            max_key = f"max_{prop_key}"
            min_key = f"min_{prop_key}"
            tolerance_key = f"{prop_key}_tol"
            nominal_key = f"nominal_{prop_key}"

            if not subdict:
                max_value = self.test_info.get(test_type, {}).get(max_key)
                min_value = self.test_info.get(test_type, {}).get(min_key)
                tolerance_value = self.test_info.get(test_type, {}).get(tolerance_key)
                nominal_value = self.test_info.get(test_type, {}).get(nominal_key)
            else:
                max_value = self.test_info.get(test_type, {}).get(subdict, {}).get(max_key)
                min_value = self.test_info.get(test_type, {}).get(subdict, {}).get(min_key)
                tolerance_value = self.test_info.get(test_type, {}).get(subdict, {}).get(tolerance_key)
                nominal_value = self.test_info.get(test_type, {}).get(subdict, {}).get(nominal_key)

            prop_dict = {"value": value}
            limits = {}
            if min_value is not None:
                limits["min"] = min_value
            if max_value is not None:
                limits["max"] = max_value
            if tolerance_value is not None:
                limits["tolerance"] = tolerance_value
            if nominal_value is not None:
                limits["nominal"] = nominal_value
            if limits:
                prop_dict["limits"] = limits

        if "value" in prop_dict:
            if prop_key == "high_pressure_ext_leak_low" or prop_key == "high_pressure_ext_leak_high":
                description = "Low Pressure Ext Leak" if prop_key == "high_pressure_ext_leak_low" else "High Pressure Ext Leak"
            else:
                description = prop_key.replace('_', ' ').title()
            equal_value = "="
            if subdict:
                if subdict == 'isolation':
                    equal_value = ">"
                elif subdict == 'capacitance':
                    equal_value = "<"
                elif subdict == 'external_leakage':
                    equal_value = "<"
            unit = self.get_unit(subdict, prop_key, "actual")
            limit_unit = self.get_unit(subdict, prop_key, "limit") or unit
            val_field = widgets.FloatText(
                value=prop_dict.get("value", None),
                **self.field("", "150px", "200px")
            )
            equal_field = widgets.Dropdown(
                options=["<", "=", ">"],
                value=equal_value,
                **self.field(f"{description} [{unit}]", "300px", "200px")
            )
            elements.append(widgets.HBox([equal_field, val_field]))

            def update_val(change: dict, key: str = prop_key, field: widgets.FloatText = val_field) -> None:
                """
                Updates the value in the test info dictionary.
                Args:
                    change (dict): The change event dictionary (built-in from observer).
                    key (str): The key to update in the test info dictionary.
                    field (widgets.FloatText): The field widget that triggered the change.
                """
                value = field.value
                if not subdict:
                    self.test_info[test_type][key] = value
                else:
                    self.test_info[test_type][subdict][key] = value

                self.main_test_results[key] = {"value": value, "unit": unit, 'lower': equal_field.value == "<", 'equal': equal_field.value == "=", 'larger': equal_field.value == ">"}
                self.save_current_state()
            val_field.observe(update_val, names="value")

            def update_limits(label: str, change: dict, key: str = prop_key, field: widgets.FloatText = val_field) -> None:
                """
                Updates the limit values in the test info dictionary and FMS limits.
                Args:
                    label (str): The label of the limit being updated (e.g., "min", "max", "tolerance", "nominal").
                    change (dict): The change event dictionary (built-in from observer).
                    key (str): The key to update in the test info dictionary.
                    field (widgets.FloatText): The field widget that triggered the change.
                """
                value = field.value
                if not subdict:
                    self.test_info[test_type][key] = value
                else:
                    self.test_info[test_type][subdict][key] = value

                raw_key = "_".join([i for i in key.split("_")[1:]])
                limit_dict = self.fms_limits.get(raw_key, {})
                if limit_dict:
                    if not label == "tolerance":
                        limit_dict[label] = value
                    else:
                        nominal_key = "nominal_" + raw_key
                        nominal_value = self.test_info[test_type].get(subdict, {}).get(nominal_key) if subdict else self.test_info[test_type].get(nominal_key)
                        limit_dict["min"] = nominal_value - (nominal_value * value / 100)
                        limit_dict["max"] = nominal_value + (nominal_value * value / 100)

                if self.tvac_loop:
                    tvac_key = f"{self.tvac_type}_{raw_key}"
                    tvac_limit_dict = self.fms_limits.get(tvac_key, {})
                    if tvac_limit_dict:
                        if not label == "tolerance":
                            tvac_limit_dict[label] = value
                        else:
                            nominal_key = "nominal_" + raw_key
                            nominal_value = self.test_info[test_type].get(subdict, {}).get(nominal_key) if subdict else self.test_info[test_type].get(nominal_key)
                            tvac_limit_dict["min"] = nominal_value - (nominal_value * value / 100)
                            tvac_limit_dict["max"] = nominal_value + (nominal_value * value / 100)

                self.save_current_state()
            limits = prop_dict.get("limits", {})
            limit_fields = []
            for name, lbl in [("nominal", "Nominal"), ("tolerance", "Tolerance (%)"), ("min", "Min"), ("max", "Max")]:
                if name in limits:
                    limit_field = widgets.FloatText(
                        value=limits[name],
                        **self.field(f"{lbl} [{limit_unit}]" if not name == "tolerance" else f"{lbl} [%]", "300px", "150px")
                    )
                    key_name = f"{name}_{prop_key}" if name in ["nominal", "tolerance", "min", "max"] else name
                    limit_field.observe(lambda c, label=name, k=key_name, f=limit_field: update_limits(label, c, k, f), names="value")
                    limit_fields.append(limit_field)
            if limit_fields:
                elements.append(widgets.HBox(limit_fields))

        elif "locations" in prop_dict or "nominal" in prop_dict:
            loc_list = prop_dict if isinstance(prop_dict, list) else prop_dict.get("locations", [])
            unit = self.get_unit(subdict, "locations", "actual") or "mm"

            for loc in loc_list:
                nominal = loc.get("nominal", {})
                tol = loc.get("tolerances", {"x_tol": 0, "y_tol": 0, "z_tol": 0})

                nom_x = widgets.FloatText(value=nominal.get("x", 0), **self.field(f"Nom X [{unit}]", "300px", "120px"))
                nom_y = widgets.FloatText(value=nominal.get("y", 0), **self.field(f"Nom Y [{unit}]", "300px", "120px"))
                nom_z = widgets.FloatText(value=nominal.get("z", 0), **self.field(f"Nom Z [{unit}]", "300px", "120px"))

                tol_x = widgets.FloatText(value=tol.get("x_tol", 0), **self.field(f"Tol X [{unit}]", "300px", "120px"))
                tol_y = widgets.FloatText(value=tol.get("y_tol", 0), **self.field(f"Tol Y [{unit}]", "300px", "120px"))
                tol_z = widgets.FloatText(value=tol.get("z_tol", 0), **self.field(f"Tol Z [{unit}]", "300px", "120px"))

                act_x = widgets.FloatText(value=loc.get("x", nominal.get("x", 0)), **self.field(f"Actual X [{unit}]", "300px", "120px"))
                act_y = widgets.FloatText(value=loc.get("y", nominal.get("y", 0)), **self.field(f"Actual Y [{unit}]", "300px", "120px"))
                act_z = widgets.FloatText(value=loc.get("z", nominal.get("z", 0)), **self.field(f"Actual Z [{unit}]", "300px", "120px"))

                def update_loc(change=None):
                    loc["x"], loc["y"], loc["z"] = act_x.value, act_y.value, act_z.value
                    loc["nominal"] = {"x": nom_x.value, "y": nom_y.value, "z": nom_z.value}
                    loc["tolerances"] = {"x_tol": tol_x.value, "y_tol": tol_y.value, "z_tol": tol_z.value}
                    self.main_test_results[prop_key] = {
                        'value': [loc['x'], loc['y'], loc['z']],
                        'unit': unit
                    }
                    self.save_current_state()

                for f in [act_x, act_y, act_z, nom_x, nom_y, nom_z, tol_x, tol_y, tol_z]:
                    f.observe(update_loc, names="value")

                elements.append(widgets.VBox([widgets.HBox([nom_x, nom_y, nom_z]),
                                            widgets.HBox([tol_x, tol_y, tol_z]),
                                            widgets.HBox([act_x, act_y, act_z])]))
        if "remark" in prop_dict:
            remark_field = widgets.Text(
                value=prop_dict.get("remark", ""), **self.field("Remark", "300px", "150px", "150px")
            )
            remark_field.observe(lambda c: prop_dict.__setitem__("remark", remark_field.value), names="value")
            elements.append(widgets.VBox(layout=widgets.Layout(height="50px")))
            elements.append(remark_field)

        return widgets.VBox(elements)
              
    def test_procedure(self, current_test_type: str = None, current_property_index: int = 0, current_subdict: str = None) -> None:
        """
        Main method to generate the test procedure UI.
        Args:
            current_test_type (str): The current test type being viewed.
            current_property_index (int): The index of the current property being viewed.
            current_subdict (str): The current sub-dictionary key, if applicable.
        """
        self.output.clear_output()
        self.container.children = []
        # Cache for property widgets to prevent flicker
        self._property_widgets_cache = {}

        test_type_dropdown = widgets.Dropdown(
            options=[(tt.replace('_',' ').title(), tt) for tt in self.test_types],
            value=current_test_type,
            description="Select Test Type:",
            style={'description_width': '180px'},
            layout=widgets.Layout(width="380px")
        )

        title_html = widgets.HTML(value=f"<h2>{current_test_type.replace('_',' ').title()}</h2>")
        subtitle_html = widgets.HTML(value="")
        form_box = widgets.VBox(spacing=5)

        prev_btn = widgets.Button(description="Previous Property", button_style='warning', icon='arrow-left')
        next_btn = widgets.Button(description="Next Property", button_style='success', icon='arrow-right')
        nav_box = widgets.HBox([prev_btn, next_btn], spacing=10)

        meta_keys = ['max_', 'min_', '_tol', 'nominal_', 'used_tests', 'extra_plots']
        property_nav = widgets.Dropdown(
            options=[],
            description="Property:",
            style={'description_width': '120px'},
            layout=widgets.Layout(width="350px")
        )

        def get_property_widget(test_type: str, prop_key: str, subdict: str | None = None) -> widgets.VBox:
            key = (test_type, prop_key, subdict)
            if key not in self._property_widgets_cache:
                if subdict:
                    prop_dict = self.test_info[test_type][subdict][prop_key]
                else:
                    prop_dict = self.test_info[test_type][prop_key]
                self._property_widgets_cache[key] = self.generate_property_fields(prop_key, prop_dict, test_type, subdict)
            return self._property_widgets_cache[key]

        def on_property_nav_change(change: dict) -> None:
            nonlocal current_property_index, current_test_type
            self.output.clear_output()
            self.tvac_loop = None
            self.tvac_type = None
            self.current_temp = None
            self.check_tvac(current_test_type)
            if change['name'] == 'value':
                selected_key = change['new']
                if not current_test_type == "annex_a":
                    props, subdict_map = self.flatten_props(current_test_type)
                    if selected_key in props:
                        current_property_index = props.index(selected_key)
                        build_form()
                else:
                    build_form(annex_a_start=selected_key)

        property_nav.observe(on_property_nav_change, names='value')

        def build_form(previous: bool = False, annex_a_start: int = 0) -> None:
            """
            Builds the form for the current property.
            Args:
                previous (bool): Whether to navigate to the previous property.
                annex_a_start (int): The starting index for Annex A components.
            """
            nonlocal current_property_index, current_test_type, current_subdict
            self.tvac_loop = None
            self.tvac_type = None
            self.current_temp = None
            self.check_tvac(current_test_type)
            props, subdict_map = self.flatten_props(current_test_type)
            if not props:
                next_btn.description = "Next Property"
                next_btn.button_style = 'success'
                if current_test_type == "conclusion":
                    property_nav.options = []
                    widget = self.get_conclusion_field()
                elif current_test_type == "observations":
                    property_nav.options = []
                    widget = self.get_observations()
                elif current_test_type == "annex_a":
                    property_nav.options = [(i["component"].title(), idx) for idx, i in enumerate(self.test_info['annex_a'])]
                    property_nav.value = annex_a_start
                    next_btn.description = "Finish"
                    next_btn.button_style = 'info'
                    widget = self.get_annex_a(annex_a_start, property_nav)
                elif current_test_type == "recommendations":
                    property_nav.options = []
                    widget = self.get_recommendations()
                else:
                    widget = widgets.HTML(value=f"<b>No properties found for {current_test_type}</b>")
                title_html.value = f"<h2>{current_test_type.replace('_',' ').title()}</h2>"
                subtitle_html.value = ""
                form_box.children = [widget]
                return

            current_property_index = max(0, min(current_property_index, len(props) - 1))
            current_property_index = self.skip_limit_keys(current_property_index, props, previous)

            while 0 <= current_property_index < len(props):
                key = props[current_property_index]
                if key.startswith("max_") or key.startswith("min_") or key.endswith("_tol") or key.startswith("nominal_"):
                    current_property_index = current_property_index - 1 if previous else current_property_index + 1
                else:
                    break

            if current_property_index >= len(props):
                idx = self.test_types.index(current_test_type)
                if idx < len(self.test_types) - 1:
                    current_test_type = self.test_types[idx + 1]
                    test_type_dropdown.value = current_test_type
                    props, subdict_map = self.flatten_props(current_test_type)
                    current_property_index = 0
                    return build_form(previous=False)
                else:
                    current_property_index = len(props) - 1  
            elif current_property_index < 0:
                idx = self.test_types.index(current_test_type)
                if idx > 0:
                    current_test_type = self.test_types[idx - 1]
                    test_type_dropdown.value = current_test_type
                    props, subdict_map = self.flatten_props(current_test_type)
                    current_property_index = len(props) - 1
                    return build_form(previous=True)
                else:
                    current_property_index = 0  

            prop_key = props[current_property_index]
            if prop_key in subdict_map:
                parent_key = subdict_map[prop_key]
                current_subdict = parent_key
            else:
                current_subdict = None

            widget = get_property_widget(current_test_type, prop_key, current_subdict)
            title_html.value = f"<h2>{current_test_type.replace('_',' ').title()}</h2>" if not "tvac_results" in current_test_type else f"<h2>{current_test_type.replace('_',' ').replace(self.tvac_type, self.current_temp).title()}</h2>"
            subtitle_html.value = f"<h4>{current_subdict.replace('_',' ').title() + ' - ' if current_subdict else ''}{prop_key.replace('_',' ').title()}</h4>"
            property_nav.options = [(props[i].replace('_',' ').title(), props[i]) for i in range(len(props)) if not any(mk in props[i] for mk in meta_keys)]
            property_nav.value = prop_key
            form_box.children = [widget, widgets.VBox([], layout=widgets.Layout(height="100px"))]
            
            if self.test_types.index(current_test_type) == len(self.test_types) - 1 and current_property_index == len(props) - 1:
                next_btn.description = "Finish"
                next_btn.button_style = 'info'
            else:
                next_btn.description = "Next Property"
                next_btn.button_style = 'success'

        def on_next(b):
            nonlocal current_property_index, current_test_type, current_subdict
            if next_btn.description == "Finish":
                form_box.children = []
                self.output.clear_output()
                # if not self.check_compliance(current_test_type, current_property_index, current_subdict):
                #     return
                self.generate_context()
                return
            if not self.check_compliance(current_test_type, current_property_index, current_subdict):
                return
            self.output.clear_output()
            props, subdict_map = self.flatten_props(current_test_type)
            if current_property_index < len(props) - 1:
                current_property_index += 1
            else:
                idx = self.test_types.index(current_test_type)
                if idx < len(self.test_types) - 1:
                    current_test_type = self.test_types[idx + 1]
                    test_type_dropdown.value = current_test_type
                    props, subdict_map = self.flatten_props(current_test_type)
                    current_property_index = 0
                else:
                    current_property_index = len(props) - 1
            if current_property_index < len(props) - 1:
                current_property_index = self.skip_limit_keys(current_property_index, props)
            build_form()

        def on_prev(b):
            nonlocal current_property_index, current_test_type
            self.output.clear_output()
            current_property_index -= 1
            if current_property_index < 0:
                idx = self.test_types.index(current_test_type)
                if idx > 0:
                    current_test_type = self.test_types[idx - 1]
                    test_type_dropdown.value = current_test_type
                    props, subdict_map = self.flatten_props(current_test_type)
                    current_property_index = len(props) - 1
                else:
                    current_property_index = 0
            props, subdict_map = self.flatten_props(current_test_type)
            current_property_index = self.skip_limit_keys(current_property_index, props, previous=True)
            build_form(previous=True)

        def on_dropdown_change(change: dict) -> None:
            nonlocal current_test_type, current_property_index
            self.output.clear_output()
            if change['name'] == 'value':
                current_test_type = change['new']
                current_property_index = 0
                build_form()

        prev_btn.on_click(on_prev)
        next_btn.on_click(on_next)
        test_type_dropdown.observe(on_dropdown_change, names='value')

        build_form()
        self.container.children = [widgets.VBox([], layout=widgets.Layout(height="50px")), test_type_dropdown, title_html, nav_box, widgets.VBox([], layout=widgets.Layout(height="10px")), property_nav, subtitle_html, form_box, self.output]

    def flatten_props(self, current_test_type: str) -> tuple[list[str], dict[str, str]]:
        """
        Flattens the properties of the current test type into a list, for easier access.
        Args:
            current_test_type (str): The current test type to flatten properties for.
        Returns:
            tuple[list[str], dict[str, str]]: A tuple containing a list of property keys and a mapping of sub-dictionary keys.
        """ 
        props = []
        subdict_map = {}
        if isinstance(self.test_info[current_test_type], dict):
            for k, v in self.test_info[current_test_type].items():
                if isinstance(v, dict) and not any(subk in v for subk in ("value", "locations", "remark", "limits", "nominal", "image", "path"))\
                      and not k.endswith("images") and not k.endswith("plot"):
                    for subk, subv in v.items():
                        if not subk == 'extra_plots' and not "power_budget" in current_test_type:
                            props.append(subk)
                            subdict_map[subk] = k
                else:
                    if not k == 'extra_plots':
                        props.append(k)
        return props, subdict_map

    def check_compliance(self, current_test_type: str, current_property_index: int, current_subdict: dict) -> bool:
        """
        Checks if the current property complies with the prescribed limits.
        Args:
            current_test_type (str): The current test type being viewed.
            current_property_index (int): The index of the current property being viewed.
            current_subdict (dict): The current sub-dictionary key, if applicable.
        Returns:
            bool: True if the property complies, False otherwise.
        """
        def fail(msg):
            with self.output:
                self.output.clear_output()
                print(f"[Compliance Error] {prop_key}: {msg}")
            return False

        def get_value(keys, default=None):
            ref = self.test_info.get(current_test_type, {})
            for k in keys:
                if ref is None:
                    return default
                ref = ref.get(k, None)
            return ref if ref is not None else default

        if current_test_type == "conclusion":
            if not self.test_info.get("conclusion", "").strip():
                return fail("Conclusion cannot be empty.")
            return True

        if current_test_type == "observations":
            observations = self.test_info.get("observations", [])
            if not observations or all(not obs.get("text", "").strip() for obs in observations):
                return fail("At least one observation must be provided.")
            return True

        if current_test_type == "recommendations":
            if not self.test_info.get("recommendations", "").strip():
                return fail("Recommendations cannot be empty.")
            return True

        props, subdict_map = self.flatten_props(current_test_type)
        prop_key = props[current_property_index]

        parent_key = subdict_map.get(prop_key)
        property = self.test_info[current_test_type][parent_key][prop_key] if parent_key else self.test_info[current_test_type][prop_key]


        if not isinstance(property, dict):
            min_value = self.fms_limits.get(prop_key, {}).get("min")
            max_value = self.fms_limits.get(prop_key, {}).get("max")

            value = property
            unit = self.get_unit(current_subdict, prop_key, "actual")
            if unit == "GOhm":
                value = value * 1e9
            if value is None:
                return fail("value is None")
            if value == 0:
                return fail("value is zero, want to continue?")
            if min_value is not None and value < min_value:
                return fail(f"value {value} below minimum limit {min_value}")
            if max_value is not None and value > max_value:
                return fail(f"value {value} above maximum limit {max_value}")
            if max_value is not None and min_value is not None:
                if not (min_value <= value <= max_value):
                    return fail(f"value {value} out of range ({min_value}–{max_value})")

        elif isinstance(property, dict) and not any(k in property for k in ("components", "locations")):
            for sub_key, sub_value in property.items():
                if sub_key.endswith(("_tol")) or sub_key.startswith(("max_", "min_", "nominal_")):
                    continue

                if isinstance(sub_value, (int, float)):
                    tol = property.get(f"{sub_key}_tol")
                    nom = property.get(f"nominal_{sub_key}")
                    if tol is not None and nom is not None:
                        low, high = nom - tol, nom + tol
                        if not (low <= sub_value <= high):
                            return fail(f"{sub_key} value {sub_value} out of tolerance range ({low}–{high})")

                if sub_value == 0:
                    return fail(f"{sub_key} value is zero, want to continue?")
                if not sub_value and sub_key != "remark":
                    return fail(f"{sub_key} value is None")

        elif "locations" in property:
            for idx, loc in enumerate(property["locations"], 1):
                nominal, tolerances = loc.get("nominal", {}), loc.get("tolerances", {})
                for axis in ("x", "y", "z"):
                    val, nom, tol = loc.get(axis), nominal.get(axis), tolerances.get(f"{axis}_tol")
                    if None in (val, nom, tol):
                        return fail(f"location #{idx} axis {axis.upper()} value is None")
                    low, high = nom - tol, nom + tol
                    if not (low <= val <= high):
                        return fail(f"location #{idx} axis {axis.upper()} value {val} out of range ({low}–{high})")

        elif "components" in property:
            required_keys = ("monitoring", "nominal", "peak")
            for key in required_keys:
                val = property.get(key)
                if val is None:
                    return fail(f"{key} power is None")
                if val == 0:
                    return fail(f"{key} power is zero, want to continue?")

            for component in property["components"]:
                comp_name = component.get("component", "Unnamed Component")
                for key in ("power", "min_power", "max_power"):
                    val = component.get(key)
                    if val is None and key in component:
                        return fail(f"{comp_name} {key} is None")
                    if val == 0:
                        return fail(f"{comp_name} {key} is zero, want to continue?")

        self.save_current_state(next_step=True, current_property_index=current_property_index, current_test_type=current_test_type, current_subdict=current_subdict)
        return True

    def get_tvac_context(self, template: DocxTemplate) -> None:
        """
        Adds all the test results obtained in the TVAC phases to the report context.
        Args:
            template (DocxTemplate): The document template to add images to.
        """
        tvac_map = {
            "tvac_results_hot": "hot",
            "tvac_results_cold": "cold",
            "tvac_results_room": "room",
        }

        for key, prefix in tvac_map.items():
            tvac_data = self.test_info.get(key, {})
            if not isinstance(tvac_data, dict):
                continue

            for test_type, props in tvac_data.items():
                if not isinstance(props, dict):
                    continue

                for prop_key, prop_value in props.items():
                    context_key = f"{prefix}_{prop_key}"
                    if isinstance(prop_value, dict) and "image" in prop_value:
                        image_bytes = self.decode_image(prop_value["image"])
                        self.context[context_key] = InlineImage(template, image_bytes, width=Mm(145))
                    elif isinstance(prop_value, dict) and prop_key == "hpiv_images":
                        opening_image = prop_value.get("hpiv_opening_image", "")
                        closing_image = prop_value.get("hpiv_closing_image", "")
                        opening_bytes = self.decode_image(opening_image)
                        self.context[f"{prefix}_hpiv_opening_image"] = InlineImage(template, opening_bytes, width = Mm(80))
                        closing_bytes = self.decode_image(closing_image)
                        self.context[f"{prefix}_hpiv_closing_image"] = InlineImage(template, closing_bytes, width = Mm(80))
                    elif isinstance(prop_value, list) and prop_key == "extra_plots":
                        extra_plots = []
                        for plot_dict in prop_value:
                            plot_image = plot_dict.get("image")
                            if plot_image:
                                plot_bytes = self.decode_image(plot_image)
                                plot_dict["image"] = InlineImage(template, plot_bytes, width=Mm(145))
                                extra_plots.append(plot_dict)
                        self.context[context_key] = extra_plots
                    else:
                        self.context[context_key] = prop_value
                        if context_key in self.main_parameter_values:
                            self.main_test_results[context_key] = prop_value
            del self.test_info[key]

    def get_power_budget_context(self) -> None:
        """
        Extracts power budget information from the test info and adds it to the report context.
        """
        power_budgets = []
        def get_component_dict(budget_dict, component_name):
            component_dict = next((comp for comp in budget_dict.get("components", []) if comp.get("component") == component_name), None)
            for i in self.context:
                if i in component_dict.get("min_description", ""):
                    component_dict["min_description"] = component_dict["min_description"].replace(f"{{{i}}}", str(self.context[i]))
                if i in component_dict.get("max_description", ""):
                    component_dict["max_description"] = component_dict["max_description"].replace(f"{{{i}}}", str(self.context[i]))
            return component_dict

        for budget_type, budget_dict in self.test_info.get("power_budgets", {}).items():
            hpiv_dict = get_component_dict(budget_dict, "HPIV")
            hpiv_hold = hpiv_dict.get("min_power", 0) if hpiv_dict else 0
            hpiv_peak = hpiv_dict.get("max_power", 0) if hpiv_dict else 0
            tv_dict = get_component_dict(budget_dict, "TV")
            tv_steady = tv_dict.get("min_power", 0) if tv_dict else 0
            tv_peak = tv_dict.get("max_power", 0) if tv_dict else 0
            lpt_dict = get_component_dict(budget_dict, "LPT")
            lpt_power = lpt_dict.get("power", 0) if lpt_dict else 0
            nominal_power = budget_dict.get("nominal", 0)
            monitoring_power = budget_dict.get("monitoring", 0)
            peak_power = budget_dict.get("peak", 0)
            power_dict = {
                "hpiv_hold": hpiv_hold,
                "hpiv_peak": hpiv_peak,
                "tv_steady": tv_steady,
                "tv_peak": tv_peak,
                "lpt": lpt_power,
                "nominal": nominal_power,
                "monitoring": monitoring_power,
                "peak": peak_power
            }
            budget_key_parts = budget_type.split("_")
            budget_key = "power_budget_" + budget_key_parts[0]
            self.main_test_results[budget_key] = power_dict
            power_budgets.append(budget_dict)
        self.context["power_budgets"] = power_budgets
        del self.test_info["power_budgets"]

    def get_physical_properties_context(self) -> None:
        """
        Extracts physical properties from the test info and adds them to the report context.
        """
        physical_props = self.test_info.get("physical_properties", {})
        mass = physical_props.get("mass", 0)
        self.context["mass"] = mass
        for location, values in physical_props.items():
            if isinstance(values, dict):
                locations_dict = values["locations"]
                for ldict in locations_dict:
                    ldict["nominal"] = [ldict.get("nominal", {})]
                self.context[location] = locations_dict
                remark = values.get("remark", "")
                self.context[f"{location}_remark"] = remark

        del self.test_info["physical_properties"]

    def get_leftover_context(self, template: DocxTemplate) -> None:
        """
        Processes any remaining items in the test info and adds them to the report context.
        Args:
            template (DocxTemplate): The document template for image embedding.
        """
        def process_dict(d):
            for k, v in d.items():
                if isinstance(v, dict):
                    if k == "hpiv_images":
                        opening_img = self.decode_image(v.get("hpiv_opening_image", ""))
                        closing_img = self.decode_image(v.get("hpiv_closing_image", ""))
                        self.context["hpiv_opening_image"] = InlineImage(template, opening_img, width=Mm(80))
                        self.context["hpiv_closing_image"] = InlineImage(template, closing_img, width=Mm(80))
                        continue

                    if k == "extra_plots" and isinstance(v, list):
                        extra_plots = []
                        for plot_dict in v:
                            plot_image = plot_dict.get("image")
                            if plot_image:
                                plot_bytes = self.decode_image(plot_image)
                                plot_dict["image"] = InlineImage(template, plot_bytes, width=Mm(145))
                                extra_plots.append(plot_dict)
                        self.context["extra_plots"] = extra_plots
                        continue

                    if "image" in v and isinstance(v["image"], str):
                        img_bytes = self.decode_image(v["image"])
                        if not "setup" in k:
                            self.context[k] = InlineImage(template, img_bytes, width=Mm(145))
                        else:
                            self.context[k] = InlineImage(template, img_bytes, width=Mm(80))
                        for sub_k, sub_v in v.items():
                            if sub_k != "image":
                                self.context[sub_k] = sub_v
                        continue

                    process_dict(v)

                else:
                    self.context[k] = v

        for key, value in self.test_info.items():
            if isinstance(value, dict):
                process_dict(value)
            else:
                self.context[key] = value

    def check_all_compliance(self) -> bool:
        """
        Stepwise compliance check: shows one popup at a time.
        Returns True if all parameters compliant or user chose to continue; False otherwise.
        """
        parameters = list(self.context.items())
        passed_dict = {}
        all_passed = True
        index = 0
        all_test_results = self.session.query(FMSTestResults).filter_by(fms_id=self.fms_id).all()
        test_results_dict = {
            res.parameter_name: {"unit": res.parameter_unit, "lower": res.lower, "larger": res.larger} for res in all_test_results
        }
        if "max_hpiv_opening_response" in test_results_dict:    
            with self.output:
                print('WAAAT')
        def format_scientific(parameter, value):
            if not isinstance(value, float):
                return

            if (0 < abs(value) < 1e-4) or (abs(value) >= 1e10):
                s = f"{value:.2E}"
                s = s.replace("e", "E")
                self.context[parameter] = s

        def handle_fail(parameter):
            passed_dict[f"{parameter}_c"] = "F"
            self.continue_list.append(parameter)
            check_next()

        def check_next():
            nonlocal index, all_passed

            if index >= len(parameters):
                self.context.update(passed_dict)
                return

            parameter, value = parameters[index]
            index += 1  

            if isinstance(value, list) and len(value) >= 1 and "nominal" in value[0] and "tolerances" in value[0]:
                for idx, loc in enumerate(value, 1):
                    for axis in ("x", "y", "z"):
                        val = loc.get(axis)
                        nominal = loc.get("nominal", [{}])[0].get(axis)
                        tol = loc.get("tolerances", {}).get(f"{axis}_tol")

                        if nominal is None or tol is None:
                            continue

                        low, high = nominal - tol, nominal + tol
                        if val is None or not (low <= val <= high) and not parameter in self.continue_list:
                            all_passed = False
                            show_modal_popup(
                                f"[Compliance Error] {parameter} location #{idx} axis {axis.upper()}: "
                                f"value {val} out of tolerance range ({low}–{high}).\n"
                                f"Do you want to continue anyway?",
                                lambda param=parameter: handle_fail(param)
                            )
                            return
                if all_passed:
                    passed_dict[f"{parameter}_c"] = "C"

                check_next()
                return
            
            if isinstance(value, (dict, list)):
                check_next()
                return

            if "remark" in parameter.lower():
                check_next()
                return
            
            if not bool(value):
                with self.output:
                    print(f"[Compliance Error] {parameter}: value is None or invalid.")
                all_passed = False
                check_next()
                return

            limits = self.fms_limits.get(parameter, {})
            min_value = limits.get("min")
            max_value = limits.get("max")
            unit = test_results_dict.get(parameter, {}).get("unit", "")
            format_scientific(parameter, value)
            if parameter in test_results_dict and not test_results_dict.get(parameter, {}).get("equal", False):
                lower = test_results_dict[parameter].get("lower")
                larger = test_results_dict[parameter].get("larger")
                if lower:
                    s = "&lt; " + str(self.context[parameter])
                    self.context[parameter] = s
                if larger:
                    s = "> " + str(self.context[parameter])
                    self.context[parameter] = s
            if unit == "GOhm":
                value = value * 1e9
            if min_value is not None and value < min_value and parameter not in self.continue_list:
                all_passed = False
                show_modal_popup(
                    f"[Compliance Error] {parameter}: value {value} below minimum {min_value}.\nDo you want to continue anyway?",
                    lambda param=parameter: handle_fail(param)
                )
                return

            if max_value is not None and value > max_value and parameter not in self.continue_list:
                all_passed = False
                show_modal_popup(
                    f"[Compliance Error] {parameter}: value {value} above maximum {max_value}.\nDo you want to continue anyway?",
                    lambda param=parameter: handle_fail(param)
                )
                return

            passed_dict[f"{parameter}_c"] = "C"
            # if new_value:
            #     self.context[parameter] = new_value
            check_next() 

        check_next()

        return all_passed

    def get_new_filename(self) -> str:
        """
        Generates a new unique filename for the report based on existing entries in the database.
        Returns:
            str: The generated filename.
        """
        all_filenames = [i.test_doc_ref if i.test_doc_ref else "" for i in self.session.query(FMSMain).all()]
        numbers = []
        for name in all_filenames:
            match = re.findall(r"\b\d{4}\b", name)
            if match:
                numbers.extend(map(int, match))

        new_num = str(max(numbers) + 1 if numbers else 1).zfill(4)
        doc_ref = f"FMS-LP-BE-RP-{new_num}"
        filename = f"{doc_ref}-i1-0 - {self.fms_id} LP FMS Test Report.docx"
        self.context["doc_ref"] = doc_ref
        return filename
            
    def generate_context(self) -> None:
        """
        Generates the report context, the report itself and saves the resulting Word document.
        """
        with self.output:
            print("Checking compliance and generating report structure...")

        template = DocxTemplate(self.template_path)
        self.test_info["project"] = "23026"
        self.test_info["ratio"] = 13
        self.backup_test_info = self.test_info.copy()
        save_to_json(self.backup_test_info, f"back_up_{self.fms_id}")
        self.get_tvac_context(template)
        self.get_power_budget_context()
        self.context["annex_a"] = self.test_info.get("annex_a", [])
        del self.test_info["annex_a"]
        self.get_physical_properties_context()
        self.get_leftover_context(template)

        date = datetime.now()
        date_header = date.strftime("%#d.%b.%Y").upper()
        date_front = date.strftime("%B %d, %Y")
        self.context.pop("date", None)
        self.context["date_header"] = date_header
        self.context["date_front"] = date_front

        if not self.check_all_compliance():
            with self.output:
                print("Compliance check failed. Report generation aborted.")
            return

        word_filename = self.get_new_filename()

        all_keys = template.get_undeclared_template_variables()
        missing_keys = [k for k in all_keys if k not in self.context]

        if missing_keys:
            print("Missing keys in context:")
            for key in missing_keys:
                with self.output:
                    print(f"  - {key}")
            return

        template.render(self.context)

        os.makedirs(self.save_path, exist_ok=True)
        final_word_path = os.path.join(self.save_path, word_filename)
        template.save(final_word_path)

        self.update_database()

        self.all_fms_field.options = [i.fms_id for i in self.all_test_info if not i.fms_id == self.fms_id]
        self.all_fms_field.value = None
        self.fms_id = ""
        self.test_info = self.fms.load_procedure(procedure_name="fms_test_draft")
        self.current_test_type = self.test_types[0]
        self.current_property_index = 0
        self.current_subdict = None
        self.start_testing()
        with self.output:
            print(f"Word report saved: {final_word_path}")

    def update_database(self) -> None:
        """
        Updates the database to mark the testing as completed and report as generated.
        """
        fms_entry = self.session.query(FMSMain).filter_by(fms_id=self.fms_id).first()
        if not fms_entry:
            with self.output:
                print(f"[Database Error] FMS ID {self.fms_id} not found in database.")
            return

        acceptance_test = fms_entry.acceptance_tests[0] if fms_entry.acceptance_tests else None
        if acceptance_test:
            acceptance_test.report_generated = True
            acceptance_test.date_created = datetime.now()

        fms_entry.status = FMSProgressStatus.TESTING_COMPLETED
        self.session.commit()