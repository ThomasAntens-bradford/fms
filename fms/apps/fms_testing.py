from __future__ import annotations
#:- Standard Library:-
import base64
import io
import os
import re
import threading
from collections import defaultdict
from datetime import datetime
import traceback

#:- Third-Party Libraries:-
import fitz
import numpy as np
import pandas as pd
from scipy.signal import savgol_filter
from sklearn.linear_model import LinearRegression
from PIL import Image
from IPython.display import display
import ipywidgets as widgets
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from docx2pdf import convert

#:- Local Imports:-
from ..utils.general_utils import (
    load_from_json,
    save_to_json,
    show_modal_popup
)

from ..utils.enums import (
    FMSProgressStatus,
    FunctionalTestType,
    FMSProgressStatus,
    FMSFlowTestParameters, 
    FMSMainParameters
)

from .query.fms_query import FMSQuery
from .. import FMSDataStructure
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

#:- Typing / Forward Declarations:-
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

class FMSTesting:
    """
    Handles the FMS Acceptance Testing procedures, including data retrieval, processing, and report generation.

    :param session: ORM session for database operations.
    :type session: Session
    :param fms: Main data handler, instantiates the session for the DB.
    :type fms: FMSDataStructure
    :param fms_query: Query interface for FMS data.
    :type fms_query: FMSQuery

    :param word_template_path: Path to Word template for report generation.
    :type word_template_path: str
    :param save_path: Directory to save generated reports.
    :type save_path: str
    :param test_directory: Directory containing test data.
    :type test_directory: str
    :param vibration_directory: Directory containing vibration test data.
    :type vibration_directory: str
    :param test_folders: Folders in the test directory.
    :type test_folders: list[str]
    :param vibration_folders: Folders in the vibration directory.
    :type vibration_folders: list[str]
    :param output: Output widget for logs/messages.
    :type output: Widget
    :param container: Main UI container.
    :type container: Widget
    :param template_path: Word template path for reports.
    :type template_path: str

    :param main_parameters: Measured/relevant parameters.
    :type main_parameters: list
    :param fms_limits: Limits for FMS tests.
    :type fms_limits: dict
    :param fms_status: Progress status of tests.
    :type fms_status: str
    :param functional_test_type: Functional test type.
    :type functional_test_type: FunctionalTestType
    :param tvac_loop: Current TVAC phase.
    :type tvac_loop: Enum
    :param tvac_type: TVAC testing phase label.
    :type tvac_type: str
    :param current_test_type: Currently processed test type.
    :type current_test_type: str
    :param current_subdict: Current sub-dictionary within the test type.
    :type current_subdict: dict
    :param current_property_index: Index of the current property.
    :type current_property_index: int
    :param test_types: All test types in the procedure.
    :type test_types: list[str]
    :param draft_fms_ids: FMS IDs with started acceptance testing.
    :type draft_fms_ids: list[int]
    :param current_temp: Current temperature phase in TVAC.
    :type current_temp: str
    :param unit_map: Mapping of properties to units.
    :type unit_map: dict

    :param context: Report generation context.
    :type context: dict
    :param main_test_results: Stores main test results for database upload.
    :type main_test_results: dict
    :param test_info: Acceptance test procedure information.
    :type test_info: dict
    :param all_test_info: All 'test_info' dictionaries for started FMS tests.
    :type all_test_info: list[dict]
    :param author: Report author (Windows environment).
    :type author: str
    :param fms_id: Currently processed FMS ID.
    :type fms_id: int

    .. methods::
    :param __init__(...): Initializes FMSTesting with required attributes
    :param get_unit(property_name): Retrieves the unit for a given property
    :param encode_image(image): Encodes an image to base64 string
    :param ecode_image(base64_string): Decodes base64 string to image (BytesIO)
    :param convert_docx_to_image_bytes(docx_path): Converts DOCX to image in BytesIO
    :param crop_image_bytes(image_bytes, dims): Crops image given byte data and dimensions
    :param initialize_header(): Sets up header UI components
    :param field(name, value, **kwargs): Creates standardized field dictionary for widget styling
    :param get_test_info(fms_id): Fetches acceptance test information for a given FMS ID
    :param get_hpiv_images(): Retrieves HPIV images for current FMS and TVAC phase
    :param get_vibration_images(): Retrieves vibration images for current FMS and axis
    :param get_functional_plots(): Generates functional test plots
    :param check_tvac(property_name): Checks if a property belongs to a TVAC phase
    :param get_opening_temperature(): Determines opening temperature from TV slope data
    :param get_tv_info(): Retrieves TV power & temperature combinations
    :param check_compliance(value, limits): Checks if a value complies with limits
    :param check_all_compliance(): Checks compliance for all test results
    :param get_tvac_context(): Adds TVAC data to report context
    :param get_power_budget_context(): Adds power budget data to context
    :param get_physical_properties_context(): Adds physical property data to context
    :param get_leftover_context(): Adds remaining data to context
    :param generate_context(): Generates complete report context
    :param generate_property_fields(property_name): Generates UI fields for a given property
    :param get_power_budget_fields(): Generates UI fields for power budget section
    :param get_conclusion_field(): Generates conclusion field UI component
    :param get_annex_a(): Generates UI fields for Annex A components
    :param get_recommendations(): Generates UI & interactions for recommendations
    :param get_observations(): Generates UI & interactions for observations
    :param test_procedure(): Main procedure for testing steps and UI
    :param start_testing(): Initiates the testing procedure UI
    :param save_current_state(): Saves current procedure state to the database
    :param update_database(): Updates database after report generation
    :param get_new_filename(): Generates new filename based on FMS ID and previous reports
    """


    def __init__(self, word_template_path: str = r"templates\fms_test_draft.docx", local = True,
                 save_path: str = r"\\be.local\Doc\DocWork\99999 - FMS industrialisation\40 - Engineering\03 - Data flow\FMS Acceptance Test Reports"):
        
        self.fms = FMSDataStructure(local = local)
        self.author = self.fms.author
        self.session: "Session" = self.fms.Session()
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.img_path = os.path.join(self.current_dir, "images", "bradford_logo.jpg")
        self.fms_id = None
        self.save_path = save_path
        self.main_parameter_values = [i.value for i in FMSMainParameters] if FMSMainParameters else []
        self.test_directory = self.fms.test_path
        self.vibration_directory = r"\\be.local\Doc\DocWork\23026 - SSP - FMS LLI\70 - Testing"
        self.test_folders = os.listdir(self.test_directory)
        self.vibration_folders = os.listdir(self.vibration_directory)
        self.output = widgets.Output()
        self.header_output = widgets.Output()
        self.container = widgets.VBox()
        self.tvac_loop = None
        self.template_path = os.path.join(self.current_dir, word_template_path)
        self.tvac_type = None
        self.continue_list = []
        self.current_test_type: FunctionalTestType = None
        self.current_subdict = None
        self.current_property_index = 0
        self.test_types = []
        self.draft_fms_ids = []
        self.context = {}
        self.fms_query = FMSQuery(local = local)
        self.main_test_results = defaultdict(dict)
        self.draft_json_dir = os.path.join(self.current_dir, "json_files")
        # self.test_info = self.fms.load_procedure(procedure_name="fms_test_draft")
        self.test_info = load_from_json("fms_test_draft", directory = self.draft_json_dir)
        self.all_test_info: list[FMSAcceptanceTests] = (
            self.session.query(FMSAcceptanceTests)
            .filter(FMSAcceptanceTests.report_generated == False)
            .order_by(FMSAcceptanceTests.id.asc())
            .all()
        )
        
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
        display(self.header_output)

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

    def check_acceptance_test_results(self, fms_id: str) -> None:
        """
        Retrieves acceptance test data of the given FMS if present and updates the test_info attribute with it.
        Args:
            fms_id (str): The FMS ID to retrieve test information for.
        """    
        fms_entry = self.session.query(FMSMain).filter_by(fms_id=fms_id).first()
        if not fms_entry:
            return
        
        def set_test_values(d: dict, value_map: dict) -> None:
            for k, v in d.items():
                if k in value_map:
                    d[k] = value_map[k]
                elif isinstance(v, dict):
                    set_test_values(v, value_map)
        
        test_results = fms_entry.test_results
        value_map = {}
        if test_results:
            cols = ("parameter_name", "parameter_value", "parameter_json")

            for result in test_results:
                param_name, param_value, param_json = (getattr(result, c) for c in cols)
                if bool(param_json) and param_name in self.test_info["physical_properties"]:
                    for i, axis in enumerate(["x", "y", "z"]):
                        self.test_info["physical_properties"][param_name][axis] = param_json[i]

                elif 'power_budget' in param_name and bool(param_json):
                    power_budget_dict = self.test_info["power_budgets"][param_name]
                    components = power_budget_dict["components"]
                    power_budget_dict["nominal"] = param_json.get("nominal", 0)
                    power_budget_dict["peak"] = param_json.get("peak", 0)
                    power_budget_dict["monitoring"] = param_json.get("monitoring", 0)
                    for component in components:
                        if component.get("component").lower() == "hpiv":
                            component["min_power"] = param_json.get("hpiv_hold", 0)
                            component["max_power"] = param_json.get("hpiv_peak", 0)
                        elif component.get("component").lower() == "tv":
                            component["min_power"] = param_json.get("tv_steady", 0)
                            component["max_power"] = param_json.get("tv_peak", 0)
                        elif component.get("component").lower() == "lpt":
                            component["power"] = param_json.get("lpt", 0)

                else:
                    value_map[param_name] = param_value
                    
            set_test_values(d = self.test_info, value_map = value_map)


        return

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
        def get_limits_from_db():
            fms_limits_check = self.session.query(FMSLimits).filter_by(fms_id = fms_id).first()
            if fms_limits_check:
                fms_limits = fms_limits_check.limits
            else:
                previous_limits = self.session.query(FMSLimits).order_by(FMSLimits.id.desc()).first()
                with self.header_output:
                    print(previous_limits.fms_id)
                if previous_limits:
                    fms_limits = previous_limits.limits
                else:
                    fms_limits = self.fms.fms_data.fms_limits
            return fms_limits
            
        if existing_entry:
            self.fms_limits = get_limits_from_db()
            self.current_property_index = existing_entry.current_property_index or 0
            self.current_test_type = existing_entry.current_test_type or None
            self.current_subdict = existing_entry.current_subdict or None
            return existing_entry.raw_json if existing_entry.raw_json else {}
        
        # test_info = self.fms.load_procedure(procedure_name="fms_test_draft")
        test_info = load_from_json("fms_test_draft", directory = self.draft_json_dir)
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
        self.fms_limits = get_limits_from_db()
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
        return img_bytes, temp_pdf_path

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
            existing_limits = self.session.query(FMSLimits).filter_by(fms_id=self.fms_id).first()
            if existing_limits:
                existing_limits.limits = self.fms_limits
            else:
                new_limits = FMSLimits(
                    fms_id = self.fms_id,
                    limits = self.fms_limits
                )
                self.session.add(new_limits)
            if len(self.main_test_results) > 0:
                existing_entries = self.session.query(FMSTestResults).filter_by(fms_id=self.fms_id).all()
                existing_parameters = []
                for entry in existing_entries:
                    parameter_name = entry.parameter_name
                    if parameter_name in self.main_test_results:
                        existing_parameters.append(parameter_name)
                        entry.parameter_value = self.main_test_results[parameter_name].get('value') if\
                              isinstance(self.main_test_results[parameter_name].get('value'), (int, float)) else None
                        entry.parameter_json = self.main_test_results[parameter_name].get('value') if \
                            not isinstance(self.main_test_results[parameter_name].get('value'), (int, float)) else None
                        entry.parameter_unit = self.main_test_results[parameter_name].get('unit')
                        entry.lower = self.main_test_results[parameter_name].get('lower', False)
                        entry.equal = self.main_test_results[parameter_name].get('equal', True)
                        entry.larger = self.main_test_results[parameter_name].get('larger', False)
                        entry.within_limits = self.main_test_results[parameter_name].get('within_limits')
                        
                for param, values in self.main_test_results.items():
                    if param in existing_parameters:
                        continue
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
            if not self.all_fms_field.value == self.fms_id:
                self.all_fms_field.value = self.fms_id

            self.test_info = self.get_test_info(self.fms_id)
            self.test_types = [k for k in self.test_info.keys() if isinstance(self.test_info[k], dict)\
                                and not "data" in k] + ["conclusion", "observations", "recommendations", "annex_a"]

            self.test_info["fms_id"] = self.fms_id
            if not self.current_test_type:
                test_type = self.test_types[0]
            else:
                test_type = self.current_test_type

            self.check_acceptance_test_results(fms_id = self.fms_id)
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
                try:
                    electrical_folder = next((folder for folder in os.listdir(os.path.join(self.test_directory, test_folder)) 
                                            if "Electrical" in folder), None) if test_folder else None
                except Exception as e:
                    traceback.print_exc()
                    return
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
                try:
                    tvac_folder = next((folder for folder in os.listdir(os.path.join(self.test_directory, test_folder)) if "tvac" in folder.lower()), None)
                except Exception as e:
                    traceback.print_exc()
                    return
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
                try:
                    data_folder = next((folder for folder in os.listdir(os.path.join(self.vibration_directory, vibration_folder)) if "vibration data" in folder.lower()), None)
                except Exception as e:
                    print(f"Cannot find vibration images for {self.fms_id} in {self.vibration_directory}")
                    return
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
                        docx_image_bytes, temp_path = self.convert_docx_to_image_bytes(full_path)
                        cropped_image_bytes = self.crop_image_bytes(docx_image_bytes, left=300, top=100, right=3300, bottom=2065)
                        os.remove(temp_path)


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

        def add_extra_plot_entry(test_id: str, image: bytes = None, show_response_times: bool = False):
            get_extra_plots().append({'test_id': test_id, 'image': image, 'prop_key': prop_key, 'title': "", 'show_response_times': show_response_times})
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

        def create_plot_block(is_primary: bool = False, preset_test_id: str = None, preset_image: bytes = None, preset_show_response: bool = False) -> widgets.Widget:
            """
            Creates a plot selection block for the functional test plots.
            Provides all test runs for the current property as options.
            Args:
                is_primary (bool): Whether the block is for the primary plot.
                preset_test_id (str): The preset test ID to select.
                preset_image (bytes): The preset image bytes to display.
                preset_show_response (bool): The preset response times checkbox state.
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

            response_times_checkbox = widgets.Checkbox(
                value=preset_show_response,
                description="Show Response Times:",
                indent=False
            )

            image_widget = widgets.Image(layout=widgets.Layout(width='800px', height='600px'))
            if preset_image:
                image_widget.value = preset_image.read() if hasattr(preset_image, 'read') else preset_image
                image_widget.format = 'png'

            delete_button = widgets.Button(description="DELETE", button_style='danger', icon='trash')

            # Always include checkbox for closed loop
            initial_children = [dropdown]
            if 'closed_loop' in prop_key:
                initial_children.append(response_times_checkbox)
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
                selected_test_id = change['new']
                key = next(k for k in function_map if k in prop_key)
                show_response_times = response_times_checkbox.value if 'closed_loop' in key else None

                if is_primary:
                    if not selected_test_id:
                        container[prop_key] = {}
                        container_widget.children = [dropdown, response_times_checkbox] if 'closed_loop' in prop_key else [dropdown]
                    else:
                        if "closed_loop" in key:
                            image_bytes = function_map[key](selected_test_id, plot=False, show_response_times=show_response_times)
                        else:
                            image_bytes = function_map[key](selected_test_id, plot=False) if not "open_loop" in key else function_map[key](selected_test_id, test_type='open_loop', plot=False)
                        encoded = self.encode_image(image_bytes) if image_bytes else None
                        container[prop_key] = {
                            'test_id': selected_test_id,
                            'image': encoded,
                            'show_response_times': show_response_times
                        }
                        children = [dropdown]
                        if 'closed_loop' in prop_key:
                            children.append(response_times_checkbox)
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
                        if 'closed_loop' in key:
                            existing['show_response_times'] = show_response_times
                    else:
                        add_extra_plot_entry(selected_test_id, encoded, show_response_times)
                    children = [dropdown]
                    if 'closed_loop' in prop_key:
                        children.append(response_times_checkbox)
                    if image_bytes:
                        image_widget.value = image_bytes.read()
                        image_widget.format = 'png'
                        children.append(image_widget)
                    children.append(delete_button)
                    container_widget.children = children
                self.save_current_state()
                update_extra_plot_button()

            def on_checkbox_change(change: dict) -> None:
                if "closed_loop" in prop_key and dropdown.value:
                    selected_test_id = dropdown.value
                    image_bytes = function_map['closed_loop'](selected_test_id, plot=False, show_response_times=change['new'])
                    encoded = self.encode_image(image_bytes) if image_bytes else None
                    if is_primary:
                        container[prop_key] = {'test_id': selected_test_id, 'image': encoded, 'show_response_times': change['new']}
                    else:
                        existing = next((p for p in get_extra_plots() if p['test_id'] == selected_test_id), None)
                        if existing:
                            existing['image'] = encoded
                            existing['show_response_times'] = change['new']
                    image_widget.value = image_bytes.read()
                    image_widget.format = 'png'
                    self.save_current_state()

            dropdown.observe(on_change, names='value')
            response_times_checkbox.observe(on_checkbox_change, names='value')
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
        primary_show = primary_dict.get('show_response_times', False)
        form.children = [create_plot_block(is_primary=True, preset_test_id=primary_dict.get('test_id'),
                                        preset_image=primary_bytes, preset_show_response=primary_show)]

        for extra in get_extra_plots():
            if extra['prop_key'] == prop_key:
                extra_bytes = self.decode_image(extra.get('image')) if extra.get('image') else None
                extra_show = extra.get('show_response_times', False)
                children = list(form.children)
                children.append(create_plot_block(is_primary=False, preset_test_id=extra['test_id'],
                                                preset_image=extra_bytes, preset_show_response=extra_show))
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
        slope_tests = self.fms_query.get_slope_tests()
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
                low_open_loop_tests = [t for t in slope_tests if t.test_type == FunctionalTestType.LOW_SLOPE and t.temp_type == temp_type]
                if low_open_loop_tests:
                    if idx == 0:
                        relevant_test = sorted(low_open_loop_tests, key=lambda x: x.date)[0] 
                        tvac_key = ""
                        high_relevant_test = None
                    else:
                        relevant_test = low_open_loop_tests[-1]
                        high_open_loop_tests = [t for t in slope_tests if t.test_type == FunctionalTestType.HIGH_SLOPE and t.temp_type == temp_type]
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
            step=0.01,
            **self.field("Monitoring Power [W]", label_width, field_width)
        )
        nominal_field = widgets.FloatText(
            value=nominal_value,
            step=0.01,
            **self.field("Nominal Power [W]", label_width, field_width)
        )
        peak_field = widgets.FloatText(
            value=peak_value,
            step=0.01,
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
                    step=0.01,
                    **self.field(f"{description} Min Power [W]", label_width, field_width)
                )
                max_field = widgets.FloatText(
                    value=max_power,
                    step=0.01, 
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
                    step=0.01,
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

            def format_limit_key(key: str) -> str:
                if not self.tvac_loop:
                    return key
                return key.replace(f"{self.tvac_type}_", "")
            
            def set_limit_value(key: str, value: float):
                limit_dict_db = self.fms_limits.get(prop_key, None)
                if not bool(limit_dict_db):
                    return value
                
                limit_value = limit_dict_db.get(key, None)
                if not limit_value:
                    return value

                if not limit_value == value:
                    return limit_value

                return value
            
            max_key = format_limit_key(f"max_{prop_key}")
            min_key = format_limit_key(f"min_{prop_key}")
            tolerance_key = format_limit_key(f"{prop_key}_tol")
            nominal_key = format_limit_key(f"nominal_{prop_key}")

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
                limits["min"] = set_limit_value("min", min_value)
            if max_value is not None:
                limits["max"] = set_limit_value("max", max_value)
            if tolerance_value is not None:
                limits["tolerance"] = set_limit_value("tolerance", tolerance_value)
            if nominal_value is not None:
                limits["nominal"] = set_limit_value("nominal", nominal_value)
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
                **self.field("", "185px", "250px")
            )
            equal_field = widgets.Dropdown(
                options=["<", "=", ">"],
                value=equal_value,
                **self.field(f"{description} [{unit}]", "350px", "250px")
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

                self.main_test_results[key] = {"value": value, "unit": unit, 'lower': equal_field.value == "<",\
                                                'equal': equal_field.value == "=", 'larger': equal_field.value == ">"}
                self.save_current_state()

            val_field.observe(update_val, names="value")

            def update_limits(limit_key: str, change: dict, key: str = prop_key, field: widgets.FloatText = val_field) -> None:
                """
                Updates the limit values in the test info dictionary and FMS limits.
                
                :param limit_key: The label of the limit being updated (e.g., "min", "max", "tolerance", "nominal").
                :type limit_key: str
                :param change: The change event dictionary (built-in from observer).
                :type change: dict
                :param key: The key to update in the test info dictionary.
                :type key: str
                :param field: The field widget that triggered the change
                :type field: widgets.FloatText
                
                """
                
                value = field.value
                if not subdict:
                    self.test_info[test_type][key] = value
                else:
                    self.test_info[test_type][subdict][key] = value

                raw_key = "_".join([i for i in key.split("_")[1:]]) if not limit_key == "tolerance" else "_".join([i for i in key.split("_")[:-1]])
                limit_dict = self.fms_limits.get(raw_key, {})
                with self.header_output:
                    print(limit_key, prop_key, limit_dict)
                if limit_dict:
                    if not limit_key == "tolerance" and not limit_key == "nominal":
                        limit_dict[limit_key] = value
                    else:
                        nominal_key = format_limit_key("nominal_" + raw_key)
                        tolerance_key = raw_key + "_tol"
                        nominal_value = self.test_info[test_type].get(subdict, {}).get(nominal_key) if subdict else self.test_info[test_type].get(nominal_key)
                        tolerance_value = self.test_info[test_type].get(subdict, {}).get(tolerance_key) if subdict else self.test_info[test_type].get(tolerance_key)
                        limit_dict["min"] = nominal_value - (nominal_value * tolerance_value / 100)
                        limit_dict["max"] = nominal_value + (nominal_value * tolerance_value / 100)
                        limit_dict["nominal"] = nominal_value
                        limit_dict["tolerance"] = tolerance_value

                self.save_current_state()

            limits = prop_dict.get("limits", {})
            limit_fields = []
            for name, lbl in [("nominal", "Nominal"), ("tolerance", "Tolerance (%)"), ("min", "Min"), ("max", "Max")]:
                if name in limits:
                    limit_field = widgets.FloatText(
                        value=limits[name],
                        **self.field(f"{lbl} [{limit_unit}]" if not name == "tolerance" else f"{lbl}", "300px", "150px")
                    )
                    key_name = f"{name}_{prop_key}" if name in ["nominal", "min", "max"] else f"{prop_key}_tol"
                    limit_field.observe(lambda c, limit_key=name, k=key_name, f=limit_field: update_limits(limit_key, c, k, f), names="value")
                    limit_fields.append(limit_field)
            if limit_fields:
                elements.append(widgets.HBox(limit_fields))

        elif all(i in prop_dict for i in ["x", "y", "z"]) and "nominal" in prop_dict:
            unit = self.get_unit(subdict, "locations", "actual") or "mm"
            loc = prop_dict
            nominal = loc.get("nominal", {})
            tol = loc.get("tolerances", {"x_tol": 0, "y_tol": 0, "z_tol": 0})

            limit_dict_db = self.fms_limits.get(prop_key)
            axes = ["x", "y", "z"]
            nominal_from_db = {axes[idx]: round((i + j)/2, 3) for idx, (i, j) in enumerate(zip(limit_dict_db["min"], limit_dict_db["max"]))}
            tolerance = {axes[idx]: round(abs((i - j))/2, 3) for idx, (i, j) in enumerate(zip(limit_dict_db["min"], limit_dict_db["max"]))}

            def set_nominal(axis: str, value: float):
                return nominal_from_db.get(axis) if not nominal_from_db.get(axis) == value else value
            
            def set_tolerance(axis: str, value: float):
                return tolerance.get(axis) if not tolerance.get(axis) == value else value

            nom_x = widgets.FloatText(value=set_nominal("x", nominal.get("x", 0)), **self.field(f"Nom X [{unit}]", "300px", "120px"))
            nom_y = widgets.FloatText(value=set_nominal("y", nominal.get("y", 0)), **self.field(f"Nom Y [{unit}]", "300px", "120px"))
            nom_z = widgets.FloatText(value=set_nominal("z", nominal.get("z", 0)), **self.field(f"Nom Z [{unit}]", "300px", "120px"))

            tol_x = widgets.FloatText(value=set_tolerance("x", tol.get("x_tol", 0)), **self.field(f"Tol X [{unit}]", "300px", "120px"))
            tol_y = widgets.FloatText(value=set_tolerance("y", tol.get("y_tol", 0)), **self.field(f"Tol Y [{unit}]", "300px", "120px"))
            tol_z = widgets.FloatText(value=set_tolerance("z", tol.get("z_tol", 0)), **self.field(f"Tol Z [{unit}]", "300px", "120px"))

            act_x = widgets.FloatText(value=loc.get("x", 0), **self.field(f"Actual X [{unit}]", "300px", "120px"))
            act_y = widgets.FloatText(value=loc.get("y", 0), **self.field(f"Actual Y [{unit}]", "300px", "120px"))
            act_z = widgets.FloatText(value=loc.get("z", 0), **self.field(f"Actual Z [{unit}]", "300px", "120px"))

            def update_loc(change=None):
                loc["x"], loc["y"], loc["z"] = act_x.value, act_y.value, act_z.value
                loc["nominal"] = {"x": nom_x.value, "y": nom_y.value, "z": nom_z.value}
                loc["tolerances"] = {"x_tol": tol_x.value, "y_tol": tol_y.value, "z_tol": tol_z.value}
                self.main_test_results[prop_key] = {
                    'value': [loc['x'], loc['y'], loc['z']],
                    'unit': unit
                }
                min_values = [i-j for i,j in zip(loc["nominal"].values(), loc["tolerances"].values())]
                max_values = [i+j for i,j in zip(loc["nominal"].values(), loc["tolerances"].values())]
                self.fms_limits[prop_key]["min"] = min_values
                self.fms_limits[prop_key]["max"] = max_values
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
            title_html.value = f"<h2>{current_test_type.replace('_',' ').title()}</h2>" if not "tvac_results"\
                  in current_test_type else f"<h2>{current_test_type.replace('_',' ').replace(self.tvac_type, self.current_temp).title()}</h2>"
            
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
                self.generate_context()
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
            self.save_current_state(next_step=True, current_property_index=current_property_index, current_test_type=current_test_type, current_subdict=current_subdict)

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
        self.container.children = [widgets.VBox([], layout=widgets.Layout(height="50px")), test_type_dropdown, title_html, nav_box,\
                                    widgets.VBox([], layout=widgets.Layout(height="10px")), property_nav, subtitle_html, form_box, self.output]

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

        limit_keys = ["max", "min", "nominal", "tol"]

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
                        if not bool(image_bytes.getvalue()):
                            continue
                        self.context[context_key] = InlineImage(template, image_bytes, width=Mm(145))
                    elif isinstance(prop_value, dict) and prop_key == "hpiv_images":
                        opening_image = prop_value.get("hpiv_opening_image", "")
                        closing_image = prop_value.get("hpiv_closing_image", "")
                        opening_bytes = self.decode_image(opening_image)
                        if bool(opening_bytes.getvalue()):
                            self.context[f"{prefix}_hpiv_opening_image"] = InlineImage(template, opening_bytes, width = Mm(80))
                        closing_bytes = self.decode_image(closing_image)
                        if bool(closing_bytes.getvalue()):
                            self.context[f"{prefix}_hpiv_closing_image"] = InlineImage(template, closing_bytes, width = Mm(80))
                    elif isinstance(prop_value, list) and prop_key == "extra_plots":
                        extra_plots = []
                        for plot_dict in prop_value:
                            plot_image = plot_dict.get("image")
                            if plot_image:
                                plot_bytes = self.decode_image(plot_image)
                                if bool(plot_bytes.getvalue()):
                                    plot_dict["image"] = InlineImage(template, plot_bytes, width=Mm(145))
                                    extra_plots.append(plot_dict)
                        self.context[context_key] = extra_plots
                    else:
                        if not any(i in prop_key for i in limit_keys):
                            self.context[prop_key] = prop_value
                        else:
                            self.context[context_key] = prop_value

            # if key in self.test_info:
            #     del self.test_info[key]

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
        # del self.test_info["power_budgets"]

    def get_physical_properties_context(self) -> None:
        """
        Extracts physical properties from the test info and adds them to the report context.
        """
        physical_props = self.test_info.get("physical_properties", {})
        mass = physical_props.get("mass", 0)
        self.context["mass"] = mass
        for location, values in physical_props.items():
            if isinstance(values, dict):
                self.context[location] = values
                remark = values.get("remark", "")
                self.context[f"{location}_remark"] = remark

        # del self.test_info["physical_properties"]

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
                        if bool(opening_img.getvalue()):
                            self.context["hpiv_opening_image"] = InlineImage(template, opening_img, width=Mm(80))
                        if bool(closing_img.getvalue()):
                            self.context["hpiv_closing_image"] = InlineImage(template, closing_img, width=Mm(80))
                        continue

                    if k == "extra_plots" and isinstance(v, list):
                        extra_plots = []
                        for plot_dict in v:
                            plot_image = plot_dict.get("image")
                            if plot_image:
                                plot_bytes = self.decode_image(plot_image)
                                if bool(plot_bytes.getvalue()):
                                    plot_dict["image"] = InlineImage(template, plot_bytes, width=Mm(145))
                                    extra_plots.append(plot_dict)
                        self.context["extra_plots"] = extra_plots
                        continue

                    if "image" in v and isinstance(v["image"], str):
                        img_bytes = self.decode_image(v["image"])
                        if not bool(img_bytes.getvalue()):
                            continue
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
        # if "max_hpiv_opening_response" in test_results_dict:    
        #     with self.output:
        #         print('WAAAT')
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

            if isinstance(value, dict) and all(i in value for i in ["x", "y", "z"]) and "nominal" in value and "tolerances" in value:
                loc: dict[str, dict[str, float] | float] = value
                for axis in ("x", "y", "z"):
                    val = loc.get(axis)
                    nominal = loc.get("nominal", {}).get(axis)
                    tol = loc.get("tolerances", {}).get(f"{axis}_tol")

                    if nominal is None or tol is None:
                        continue

                    low, high = nominal - tol, nominal + tol
                    if val is not None and not (low <= val <= high) and not parameter in self.continue_list:
                        all_passed = False
                        with self.output:
                            show_modal_popup(
                                f"[Compliance Error] {parameter} axis {axis.upper()}: "
                                f"value {val:.3f} out of tolerance range ({low:.3f}–{high:.3f}).\n"
                                f"Do you want to continue anyway?",
                                lambda param=parameter: handle_fail(param)
                            )
                        return
                    elif val is None:
                        with self.output:
                            print(f"[Compliance Error] {parameter} axis {axis.upper()}:"
                                    "value is None")
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
            
            if "path" in parameter.lower():
                check_next()
                return
            
            if "nlr_document" in parameter.lower():
                check_next()
                return
            
            if "show_response_times" in parameter.lower():
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
                with self.output:
                    show_modal_popup(
                        f"[Compliance Error] {parameter}: value {value:.3f} below minimum {min_value:.3f}.\nDo you want to continue anyway?",
                        lambda param=parameter: handle_fail(param)
                    )
                return

            if max_value is not None and value > max_value and parameter not in self.continue_list:
                all_passed = False
                with self.output:
                    show_modal_popup(
                        f"[Compliance Error] {parameter}: value {value:.3f} above maximum {max_value:.3f}.\nDo you want to continue anyway?",
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
    
    def _get_closed_loop_context(self) -> None:
        """
        Function that uses the FMSQuery class to collect the closed loop data and formats the data for the report
        """
        self.context["closed_loop_data"] = self.fms_query.closed_loop_analysis(show_table = False)
            
    def generate_context(self) -> None:
        """
        Generates the report context, the report itself and saves the resulting Word document.
        """
        with self.output:
            print("Checking compliance and generating report structure...")

        template = DocxTemplate(self.template_path)
        self.test_info["project"] = "23026"
        save_to_json(self.test_info, f"back_up_{self.fms_id}")
        self.get_tvac_context(template)
        self.get_power_budget_context()
        self.context["annex_a"] = self.test_info.get("annex_a", [])
        self.get_physical_properties_context()
        self.get_leftover_context(template)

        date = datetime.now()
        date_header = date.strftime("%#d.%b.%Y").upper()
        date_front = date.strftime("%B %d, %Y")
        self.context.pop("date", None)
        self.context["date_header"] = date_header
        self.context["date_front"] = date_front
        self._get_closed_loop_context()

        if not self.check_all_compliance():
            with self.output:
                print("Compliance check failed. Report generation aborted.")
            return

        word_filename = self.get_new_filename()

        all_keys = template.get_undeclared_template_variables()
        missing_keys = [k for k in all_keys if k not in self.context]

        if missing_keys:
            message = "It seems like we are missing some data: "
            for idx, key in enumerate(missing_keys):
                if idx == 0:
                    message += key
                    continue
                message += f", {key}"
            with self.output:
                show_modal_popup(message = message, continue_action = lambda: self.finalize_report(template=template, word_filename=word_filename))
            return
        
        self.finalize_report(template=template, word_filename=word_filename)

    def finalize_report(self, template: DocxTemplate, word_filename: str):
        """
        Helper function that finalizes the generation of the Acceptance Test Report.
        
        :param template: docxtpl instance that holds the report template.
        :type template: DocxTemplate
        :param word_filename: filename of the to be generated word report.
        :type word_filename: str

        """
        template.render(self.context)

        os.makedirs(self.save_path, exist_ok=True)
        final_word_path = os.path.join(self.save_path, word_filename)
        template.save(final_word_path)

        self.update_database()

        self.all_fms_field.options = [i.fms_id for i in self.all_test_info if not i.fms_id == self.fms_id]
        self.all_fms_field.value = None
        self.fms_id = ""
        # self.test_info = self.fms.load_procedure(procedure_name="fms_test_draft")
        self.test_info = load_from_json("fms_test_draft", directory = self.draft_json_dir)
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