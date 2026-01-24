# Future imports
from __future__ import annotations

# Standard library
import os
import re
import shutil
from datetime import datetime
from typing import Any

# Third-party imports
import tzlocal
from docxtpl import DocxTemplate
from docx2pdf import convert
from IPython.display import display
import ipywidgets as widgets
from sqlalchemy.orm import Session

# Local imports
from ..utils.general_utils import (
    load_from_json,
    show_modal_popup,
    save_to_json
)
from ..utils.enums import TVProgressStatus, TVParts
from ..db import TVStatus, TVCertification, CoilAssembly

from ..fms_data_structure import FMSDataStructure

class TVAssembly:
    """
    Class to manage the TV Assembly Coil Procedure using interactive widgets.
    Uses a pre-defined JSON structure that describes all steps in the procedure.

    Attributes
    ----------
    session : Session
        SQLAlchemy session for database operations.
    fms : FMSDataStructure
        FMS data structure instance, parent class to relate the class to other parts and their functionalities.
    template_path : str
        Path to the Word document template for the TV assembly procedure.
    doc : DocxTemplate
        DocxTemplate instance for generating the TV assembly procedure document.
    main_path : str
        Main local path that holds all the images and templates. ***REMARK:*** This might be moved to the database itself.
    resistance_goal : int
        Target resistance goal for the coil assembly.
    img_path : str
        Path to the logo image used in the UI.
    save_path : str
        Path to save the generated TV assembly procedure document.
    holder_1_certs : list[TVCertification]
        List of all certifications belonging to the holder 1 part.
    holder_2_certs : list[TVCertification]
        List of all certifications belonging to the holder 2 part.
    steps : dict
        Dictionary that holds all the information for each step,
        loaded from a JSON structure that is saved throughout the procedure.
    output : widgets.Output
        Output widget for displaying messages and logs.
    container : widgets.VBox
        Main container widget for the TV assembly procedure UI.
    all_drafts : list[CoilAssembly]
        List of all 'steps' attributes that have been initiated but not yet completed,
        saved in the database.
    all_steps : list[dict]
        List of all 'steps' dictionaries extracted from the 'all_drafts'.
    tv_id : int
        Current TV ID being processed.
    operator : str
        Bradford Name Code of the operator performing the procedure.
    adhesive_logs : list
        List of adhesive log entries recorded during the procedure.
    start_date_obj : datetime.date
        Start date of the procedure as a date object.
    old_steps : dict
        Dictionary to hold previous steps data for comparison.
    all_tvs_field : widgets.Dropdown
        Dropdown widget to select from all open TV assembly drafts.
    
    Methods
    -------
    save_current_state():
        Saves the current state of the procedure to the database, in JSON format.
    get_steps(tv_id):
        Retrieves the steps dictionary for a given TV ID from the database,
        such that progress is not lost if the procedure is interrupted.
    on_tv_change(change):
        Callback function to handle changes in the selected TV ID from the dropdown.
    initialize_header():
        Initializes the header section of the UI with logo and TV selection dropdown.
    get_document():
        Loads the Word document template for the TV assembly procedure.
    field(description, field_width="400px", label_width="160px", height="30px"):
        Creates a standardized field dictionary for widget styling.
    start_assembly():
        Initializes the assembly procedure UI, allowing the user to input TV ID,
        resistance goal, and start date.
    assembly_procedure():
        Starts the assembly procedure, loading existing steps if available,
        or initializing new steps.
    generate_step_html(description_data, images=[], resistance_check=False):
        Generates an ipywidgets.HTML widget for a step description,
        including handling images and resistance checks.
    display_step_form(step_number: int, measurement_number: int = 0):
        Displays the form for a specific step in the procedure,
        allowing the user to input data and navigate between steps.
    remove_and_continue(step_number: int):
        Remove the last adhesive log entry if it is empty, then continue.
    check_adhesive_values(step_number, measurement_check):
        Checks if all required adhesive log values are filled in for a given step.
    get_adhesive_log(step_number, measurement_number):
        Generates the adhesive log input fields for a given step and measurement.
    get_cure_log(step_number):
        Generates the cure log input fields for a given step.
    get_measurements(step_number):
        Generates the coil resistance measurement input fields for a given step.
    check_measurement_values(step_number):
        Checks if all required measurement values are filled in for a given step.
    get_certifications():
        Retrieves and stores certifications for the used parts in the procedure from the database,
        if already filled in.
    procedure_loop(step_number: int):
        Main loop to display and handle the procedure steps,
        starting from a given step number.
    get_adhesive_values(step_number):
        Adds the adhesive log values to the report context.
    check_cure_log(step_number):
        Adds the cure log values to the report context.
    get_coil_measurements(step_number):
        Adds the coil measurement values to the report context.
    generate_report():
        Generates the TV assembly procedure report as a Word document and converts it to PDF.
    """
    
    def __init__(self, word_template_path: str = r"templates\tv_assembly_procedure.docx", local = True,
                 main_path: str = "TVAssemblyProcedure", save_path: str =  r"\\be.local\Doc\DocWork\20025 - CHEOPS2 Low Power\10 - Documents\PR\TV assembly procedure\As-run\Automated"):
        
        self.fms = FMSDataStructure(local = local)
        self.operator = self.fms.operator
        self.session: "Session" = self.fms.Session()
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.template_path = os.path.join(current_dir, word_template_path)
        self.doc = self.get_document()
        self.context = {}
        self.start_date = None
        self.tv_id = None
        self.main_path = os.path.join(current_dir, main_path)
        self.resistance_goal = None
        self.img_path = os.path.join(current_dir, "images", "bradford_logo.jpg")
        self.save_path = save_path
        self.holder_1_certs: list[TVCertification] = None
        self.holder_2_certs: list[TVCertification] = None
        self.json_files = os.path.join(os.path.dirname(__file__), "json_files")
        # self.steps: dict[str, dict] = self.fms.load_procedure('tv_assembly_steps')
        self.steps: dict[str, dict] = load_from_json('tv_assembly_steps', directory = self.json_files)
        self.output = widgets.Output()
        self.container = widgets.VBox()
        self.all_drafts = (
            self.session.query(CoilAssembly)
            .filter(CoilAssembly.context.is_(None))
            .order_by(CoilAssembly.id.asc())
            .all()
        )
        # for entry in self.all_drafts:
        #     self.session.delete(entry)
        # self.session.commit() 
        # print(all_drafts)
        self.all_steps = [f.steps for f in self.all_drafts] if len(self.all_drafts) >= 1 else []
        if self.all_steps:
            self.tv_id = self.all_steps[0].get('tv_id', None)
            self.steps = self.all_steps[0]
        self.initialize_header()
        self.adhesive_logs = []
        self.start_date_obj = None
        self.old_steps = {}
        if not hasattr(self, 'all_tvs_field'):
            self.all_tvs_field = None
        display(self.container)

    def save_current_state(self) -> None:
        """
        Saves the current state of the procedure to the database, in JSON format.
        """
        try:
            existing_entry = self.session.query(CoilAssembly).filter_by(tv_id=self.tv_id).first()
            if existing_entry:
                existing_entry.steps = self.steps
            else:
                new_entry = CoilAssembly(
                    tv_id=self.tv_id,
                    steps=self.steps
                )
                self.session.add(new_entry)
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            print(f"Error saving current state: {e}")

    def get_steps(self, tv_id: int) -> dict:
        """
        Retrieves the steps dictionary for a given TV ID from the database,
        such that progress is not lost if the procedure is interrupted.
        Args:
            tv_id (int): The TV ID to retrieve steps for.
        Returns:
            dict: The steps dictionary for the given TV ID.
        """
        try:
            # if tv_id == 30:
            #     return load_from_json("tv_assembly_steps_draft")
            entry = self.session.query(CoilAssembly).filter_by(tv_id=tv_id).first()
            if entry:
                return entry.steps
            return load_from_json('tv_assembly_steps', directory = self.json_files)
        except Exception as e:
            print(f"Error retrieving steps for TV ID {tv_id}: {e}")
            return load_from_json('tv_assembly_steps', directory = self.json_files)

    def on_tv_change(self, change: dict) -> None:
        """
        Callback when a new TV is selected from the dropdown.
        Updates the fields without rebuilding the entire UI.
        """
        new_tv_id = self.all_tvs_field.value
        if new_tv_id == self.tv_id:
            return  # No change, avoid flicker

        self.tv_id = new_tv_id
        self.steps = self.get_steps(self.tv_id)

        # Properly handle start date object
        start_date_str = self.steps.get("start_date")
        if start_date_str:
            self.start_date = start_date_str
            self.start_date_obj = datetime.strptime(start_date_str, "%B %d, %Y").date()
        else:
            self.start_date_obj = datetime.now().date()
            self.start_date = self.start_date_obj.strftime("%B %d, %Y")
            self.steps['start_date'] = self.start_date

        # Update resistance goal safely
        res_goal = self.steps.get('resistance_goal', 150)
        if res_goal not in [150, 200]:
            res_goal = 150
            self.steps['resistance_goal'] = res_goal
        self.resistance_goal = res_goal

        # Update widgets without rebuilding everything
        if hasattr(self, 'tv_id_widget') and self.tv_id_widget.value != self.tv_id:
            self.tv_id_widget.value = self.tv_id
        if hasattr(self, 'resistance_goal_widget'):
            self.resistance_goal_widget.value = self.resistance_goal
        if hasattr(self, 'start_date_widget'):
            self.start_date_widget.value = self.start_date_obj

        # Decide which step to resume
        max_step = max(int(k) for k in self.steps.keys() if k.isdigit())
        current_step = next((step for step, data in self.steps.items()
                            if step.isdigit() and not data.get("performed", False)), max_step)
        if current_step and int(current_step) != 32:
            with self.output:
                self.output.clear_output()
                print(f"Resuming from step {current_step} for TV ID {self.tv_id}.")
            self.procedure_loop(step_number=int(current_step))
        else:
            self.start_assembly()  # only the start form

    def initialize_header(self) -> None:
        """
        Initializes the header section of the UI with logo and TV selection dropdown.
        """
        self.all_tvs_field = widgets.Dropdown(
            options=[ (f"TV {s.get('tv_id')}", s.get('tv_id')) for s in self.all_steps if s and s.get('tv_id')],
            description="Select Open TV Assembly:",
            style={'description_width': '180px'},
            layout=widgets.Layout(width="350px"),
            value = self.tv_id
        )

        home_button = widgets.Button(
            description="Home",
            button_style='primary',
            icon='home'
        )
        def on_home_click(b):
            self.output.clear_output()
            self.start_assembly()
        self.header_output = widgets.Output()
        self.top_container = widgets.HBox([home_button, self.all_tvs_field])
        home_button.on_click(on_home_click)

        logo = widgets.Image(value=open(self.img_path, "rb").read(), format='jpg', width=300, height=100)

        display(widgets.VBox([logo, self.top_container, self.header_output]))

        self.all_tvs_field.observe(self.on_tv_change, names='value')

    def get_document(self) -> DocxTemplate:
        return DocxTemplate(self.template_path)

    def field(self, description: str, field_width: str = "400px", label_width: str = "160px", height: str = "30px") -> dict:
        return dict(description=description,
                    layout=widgets.Layout(width=field_width, height=height),
                    style={'description_width': label_width})

    def start_assembly(self) -> None:
        """
        Initializes the assembly procedure UI, allowing the user to input TV ID,
        resistance goal, and start date, with proper validation.
        """
        self.output.clear_output()
        self.container.children = []

        self.tv_id_widget = widgets.BoundedIntText(
            value=self.tv_id if self.tv_id else 1,
            min=1,
            max=10000,
            **self.field("TV ID:")
        )

        self.resistance_goal_widget = widgets.Dropdown(
            options=[150, 200],
            value=self.resistance_goal if self.resistance_goal in [150, 200] else 150,
            **self.field("Resistance Goal (Ohm):")
        )

        self.start_date_widget = widgets.DatePicker(
            value=self.start_date_obj if self.start_date_obj else datetime.now().date(),
            **self.field("Start Date:")
        )

        start_btn = widgets.Button(description="Start Procedure", button_style='success', icon='arrow-right')

        def on_start_click(b):
            self.tv_id = self.tv_id_widget.value
            self.resistance_goal = self.resistance_goal_widget.value
            if self.resistance_goal not in [150, 200]:
                with self.output:
                    print("Invalid resistance goal! Must be 150 or 200.")
                return
            self.start_date_obj = self.start_date_widget.value
            self.start_date = self.start_date_obj.strftime("%B %d, %Y") if self.start_date_obj else None
  
            if self.resistance_goal not in [150, 200]:
                with self.output:
                    print("Resistance goal must be 150 or 200 Ω!")
                return
            if not self.start_date_obj:
                with self.output:
                    print("Please select a start date.")
                return
        
            if not self.all_tvs_field.value == self.tv_id:
                self.all_tvs_field.unobserve(self.on_tv_change)
                options = list(self.all_tvs_field.options) + [(f"TV {self.tv_id}", self.tv_id)]
                self.all_tvs_field.options = options
                self.all_tvs_field.value = self.tv_id
                self.all_tvs_field.observe(self.on_tv_change)

            self.steps = self.get_steps(self.tv_id)
            self.steps['tv_id'] = self.tv_id
            self.steps['resistance_goal'] = self.resistance_goal
            self.steps['start_date'] = self.start_date
            self.save_current_state()
            self.assembly_procedure()

        start_btn.on_click(on_start_click)

        form_children = widgets.VBox([
            widgets.HTML("<h2>TV Coil Assembly Procedure</h2>"),
            self.tv_id_widget,
            self.resistance_goal_widget,
            self.start_date_widget,
            start_btn,
            self.output
        ], layout=widgets.Layout(align_items='flex-start', padding='10px'))

        self.container.children = [form_children]

    def assembly_procedure(self) -> None:
        """
        Begins the assembly procedure with validation and safe step handling.
        """
        self.container.children = []
        self.output.clear_output()

        # Basic validation before starting
        if not self.tv_id or not isinstance(self.tv_id, int):
            with self.header_output:
                print("Please select a valid TV ID.")
            return
        if not self.resistance_goal or self.resistance_goal < 1:
            with self.header_output:
                print("Please enter a valid resistance goal (>0).")
            return
        if not self.start_date_obj:
            with self.header_output:
                print("Please select a start date.")
            return

        # Update context & steps
        self.context = {
            'tv_id': self.tv_id,
            'start_date': self.start_date,
            'resistance_goal': self.resistance_goal
        }
        self.steps['tv_id'] = self.tv_id
        self.steps['start_date'] = self.start_date
        self.steps['resistance_goal'] = self.resistance_goal

        self.save_current_state()

        # Load existing assembly if it exists
        assembly_check = self.session.query(CoilAssembly).filter(
            CoilAssembly.tv_id == self.tv_id, CoilAssembly.context.isnot(None)
        ).first()
        if assembly_check:
            self.steps = assembly_check.steps
            self.context = assembly_check.context
            self.adhesive_logs = assembly_check.adhesive_logs
            self.resistance_goal = self.steps.get('resistance_goal', 150)
            self.old_steps = self.steps.copy()
            self.start_date = self.context.get('start_date', self.start_date)
            self.start_date_obj = datetime.strptime(self.start_date, "%B %d, %Y").date() if self.start_date else datetime.now().date()
            self.get_certifications()
            return

        # Determine starting step
        max_step = max([int(k) for k in self.steps.keys() if k.isdigit()], default=32)
        start_step = next(
            (step for step, data in self.steps.items() if step.isdigit() and not data.get("performed", False)),
            str(max_step)
        )

        if start_step == max_step:
            self.get_certifications()
            return
        if start_step != "32":
            self.output.clear_output()
            with self.output:
                print(f"Resuming from step {start_step} for TV ID {self.steps.get('tv_id')}.")
            self.procedure_loop(step_number=int(start_step))
            return

        self.display_step_form(step_number=32)

    def generate_step_html(self, description_data: str | list[str], images: list[str] = [], resistance_check: bool = False) -> widgets.HTML:
        """
        Generates an ipywidgets.HTML widget for a step description.
        - description_data: str or list of strings. List items can contain "{imgN}" placeholders.
        - images: list of image paths corresponding to "{imgN}" placeholders.
        - resistance_check: bool indicating if resistance check is needed.
        Returns: widgets.HTML
        Ensures at most two images are displayed next to each other, keeping their aspect ratio,
        and allows enlarging images by clicking them.
        """
        html_content = ""
        img_buffer = []

        def flush_images():
            nonlocal html_content
            while img_buffer:
                group = img_buffer[:2]
                img_buffer[:2] = []
                html_content += "<div style='display:flex; gap:10px; margin:5px 0;'>"
                for img_tag in group:
                    # If lone image, add min-width to make it bigger
                    if len(group) == 1:
                        img_tag = img_tag.replace(
                            "style='",
                            "style='min-width:350px; "
                        )
                    html_content += img_tag
                html_content += "</div>"

        if isinstance(description_data, list):
            for item in description_data:
                item = item.replace("\n", "<br>")
                item = item.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
                if resistance_check and "{coil_resistance}" in item:
                    item = item.replace("{coil_resistance}", f"{self.resistance_goal} Ω")
                if isinstance(item, str) and item.startswith("{img") and item.endswith("}"):
                    index = int(item.replace("{img", "").replace("}", "")) - 1
                    if index < len(images):
                        img_path = images[index]
                        # Make image clickable to open full-size
                        img_tag = (
                            f"<a href='{self.main_path}/{img_path}' target='_blank'>"
                            f"<img src='{self.main_path}/{img_path}' alt='img{index+1}' "
                            f"style='height:auto; border:1px solid #ccc; border-radius:8px; cursor:pointer;'>"
                            f"</a>"
                        )
                        img_buffer.append(img_tag)
                else:
                    flush_images()
                    html_content += f"<p style='margin:5px 0;'>{item}</p>"
            flush_images()
        else:
            description_data = description_data.replace("\n", "<br>")
            description_data = description_data.replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
            if resistance_check and "{coil_resistance}" in description_data:
                description_data = description_data.replace("{coil_resistance}", f"{self.resistance_goal} Ω")
            html_content = f"<p>{description_data}</p>"

        return widgets.HTML(value=html_content)

    def display_step_form(self, step_number: int, measurement_number: int = 0) -> None:
        """
        Displays the form for a specific step in the procedure,
        allowing the user to input data and navigate between steps.
        Args:
            step_number (int): The current step number to display.
            measurement_number (int): The current measurement number for adhesive logs.
        """
        step_data = self.steps[str(step_number)]
        description = step_data["description"]
        operator = step_data["operator"] if step_data.get("operator", "") and not (step_data.get("operator", "") == self.operator) else self.operator
        remark = step_data["remark"]
        date_value = step_data.get("date")
        images = step_data.get("images", [])
        adhesive_log = step_data.get("adhesive_log", False)
        previous_operator = self.steps.get(str(step_number - 1), {}).get("operator", "") if step_number > 32 else ""
        cure_log = step_data.get("cure_log", False)
        resistance_check = step_data.get("resistance_check", False)
        measure_resistance = step_data.get("measure_coil_resistance", False)


        if isinstance(date_value, str):
            try:
                date_value = datetime.strptime(date_value, "%B %d, %Y").date()
            except ValueError:
                date_value = datetime.now().date()
        elif date_value is None:
            date_value = datetime.now().date()

        title = widgets.HTML(value=f"<h3>Step {step_number} Instruction</h3>")
        action_title = widgets.HTML(value=f"<h3>Actions/Remarks</h3>")
        description_data = step_data["description"]

        description_field = self.generate_step_html(description_data, images, resistance_check)

        performed_box = widgets.Checkbox(
            value=self.steps.get(str(step_number), {}).get("performed", False),
            disabled=False,
            **self.field("Step Performed", label_width="100px"),
            indent=True
        )

        date_picker = widgets.DatePicker(
            **self.field("Date:", field_width="300px", label_width="100px"),
            value=date_value
        )

        operator_input = widgets.Text(
            value=operator,
            disabled=True,
            placeholder='Enter your Bradford Name Code (e.g. TAS)',
            **self.field("Operator:", field_width="400px", label_width="100px")
        )

        remark_input = widgets.Textarea(
            value=remark,
            placeholder='Enter any remarks here...',
            **self.field("Remark:", field_width="500px", label_width="100px", height="80px")
        )

        next_step_button = widgets.Button(description="Next Step", button_style='info', icon='arrow-right')
        previous_step_button = widgets.Button(description="Previous Step", button_style='warning', icon='arrow-left')

        def on_field_change(change):
            date_value = date_picker.value.strftime("%B %d, %Y") if date_picker.value else None
            self.steps[str(step_number)]["date"] = date_value
            self.steps[str(step_number)]["operator"] = operator_input.value.strip()
            self.steps[str(step_number)]["remark"] = remark_input.value.strip()
            self.save_current_state()
        
        date_picker.observe(on_field_change, names='value')
        operator_input.observe(on_field_change, names='value')
        remark_input.observe(on_field_change, names='value')
        performed_box.observe(on_field_change, names='value')

        def on_next_step_click(b):
            self.output.clear_output()
            date_value = date_picker.value.strftime("%B %d, %Y") if date_picker.value else None
            date_object = date_picker.value
            if date_object and not date_object >= self.start_date_obj:
                with self.output:
                    print(date_object, self.start_date_obj)
                    print("Date can not be before the start date.")
                return
            if not performed_box.value:
                with self.output:
                    print("Please confirm that you have performed the step.")
                return
            if not operator_input.value.strip() or len(operator_input.value.strip()) < 3 or not isinstance(operator_input.value, str):
                with self.output:
                    print("Please enter your Bradford Name Code (at least 3 characters).")
                return
            operator = operator_input.value.strip()
            if not self.operator or (self.operator and self.operator != operator):
                self.operator = operator_input.value.strip()
            self.steps[str(step_number)]["performed"] = True
            self.steps[str(step_number)]["date"] = date_picker.value.strftime("%B %d, %Y") if date_picker.value else None
            self.steps[str(step_number)]["operator"] = operator_input.value.strip()
            self.steps[str(step_number)]["remark"] = remark_input.value.strip()
            if adhesive_log:
                for log in adhesive_log:
                    log['date'] = date_picker.value.strftime("%B %d, %Y") if date_picker.value else None
                    log['operator'] = operator_input.value.strip()
            if cure_log:
                for key, value in self.steps[str(step_number)]['cure_log'].items():
                    if not value:
                        with self.output:
                            print(f"Please fill in: {key.replace('_', ' ').title()}.")
                        return
                
                start_datetime_str = self.steps[str(step_number)]['cure_log'].get('start_datetime', "")
                end_datetime_str = self.steps[str(step_number)]['cure_log'].get('end_datetime', "")
                start_datetime_obj = datetime.strptime(start_datetime_str, "%B %d, %Y %H:%M") if start_datetime_str else None
                end_datetime_obj = datetime.strptime(end_datetime_str, "%B %d, %Y %H:%M") if end_datetime_str else None
                
                if start_datetime_obj and end_datetime_obj:
                    diff_hours = (end_datetime_obj - start_datetime_obj).total_seconds() / 3600.0
                    if diff_hours < 1.5:
                        with self.output:
                            print("Cure time must be at least 1.5 hours.")
                        return
            self.save_current_state()
            if measure_resistance and not self.check_measurement_values(step_number):
                    return
            if adhesive_log and not self.check_adhesive_values(step_number):
                return
            self.procedure_loop(step_number=step_number + 1)

        def on_previous_step_click(b):
            self.output.clear_output()
            if step_number == 32:
                self.start_assembly()
            else:
                self.procedure_loop(step_number=step_number - 1)
            
            on_field_change(None)

        previous_step_button.on_click(on_previous_step_click)

        next_step_button.on_click(on_next_step_click)

        buttons_box = widgets.VBox(
            [previous_step_button, next_step_button],
            layout=widgets.Layout(
                width='400px',  # match the operator_input width
                margin='50px 0 0 100px'
            )
        )

        if adhesive_log:
            log_fields = self.get_adhesive_log(step_number, measurement_number)
        else:
            log_fields = widgets.VBox()

        if cure_log:
            cure_log_fields = self.get_cure_log(step_number)
        else:
            cure_log_fields = widgets.VBox()

        if measure_resistance:
            measurement_fields = self.get_measurements(step_number)
        else:
            measurement_fields = widgets.VBox()

        fields_box = widgets.VBox(
            [action_title, performed_box, date_picker, operator_input, remark_input, log_fields, cure_log_fields, measurement_fields, buttons_box, self.output],
            layout=widgets.Layout(
                align_items="flex-start",
                width="fit-content",
                overflow = "visible"
            )
        )

        step_keys = [int(k) for k in self.steps.keys() if k.isdigit()]
        max_step = max(step_keys)

        go_to_step_field = widgets.Dropdown(
            value=step_number,  # just the integer step number
            options=[(f"Step {i}", i) for i in range(32, max_step + 1)],
            **self.field("Go to Step:", field_width="200px", label_width="80px")
        )

        def on_go_to_step_change(change):
            if change['name'] == 'value' and change['new'] != step_number:
                new_step = change['new']  # already an integer
                self.output.clear_output()
                self.procedure_loop(step_number=new_step)

        go_to_step_field.observe(on_go_to_step_change, names='value')

        form = widgets.VBox([
            go_to_step_field,
            widgets.HBox([
                widgets.VBox([title, description_field], layout=widgets.Layout(width="70%")),
                widgets.VBox([
                    fields_box
                ], layout=widgets.Layout(
                    align_items="flex-start",  # ensures left alignment
                    width="100%"
                ))
            ], layout=widgets.Layout(
                align_items="flex-start",
                padding="10px",
                spacing="10px",
                width="100%"
            ))
        ], layout=widgets.Layout(
            align_items="flex-start",
            padding="10px",
            spacing="10px",
            width="100%"
        ))

        self.container.children = [form]

    def remove_and_continue(self, step_number: int) -> None:
        """Remove the last adhesive log entry if it is empty, then continue."""
        logs = self.steps[str(step_number)]['adhesive_log']
        if logs:
            logs.pop(-1)
            self.steps[str(step_number)]['adhesive_log'] = logs
            self.save_current_state()
        self.procedure_loop(step_number + 1)

    def check_adhesive_values(self, step_number: int, measurement_check: bool = False) -> bool:
        """
        Checks if all required adhesive log values are filled in and within limits for a given step.
        Args:
            step_number (int): The step number to check.
            measurement_check (bool): If True, only check for missing values without range checks.
        Returns:
            bool: True if all required values are filled in, False otherwise.
        """
        part_a_min = 3.88
        part_a_max = 4.12
        part_b_min = 0.291
        part_b_max = 0.309
        logs = self.steps[str(step_number)]['adhesive_log']
        valid_logs = []

        for idx, log in enumerate(logs):
            coc_value = log.get("coc", "").strip()
            part_a_mass = log.get("part_a_mass", 0.0)
            part_b_mass = log.get("part_b_mass", 0.0)
            exp_date = log.get("exp_date", "")
            exp_date_obj = None

            popup_count = 0
            for key, value in log.items():
                if not (value or value != 0) and not key == "idx":
                    with self.output:
                        if idx == 0:
                            print(f"Please fill in: {key.replace('_', ' ').title()}.")
                            return False
                        else:
                            if popup_count == 0 and not measurement_check:
                                show_modal_popup(f"{key.replace('_', ' ').title()} is missing for measurement {idx + 1}, do you want to continue?\
                                                  The log will not show up in the report.",
                                                lambda: self.remove_and_continue(step_number))
                            popup_count += 1
                            return False

            if exp_date:
                exp_date_obj = datetime.strptime(exp_date, "%B %d, %Y").date()

            # check if entry is an "extra" with all default values
            if not any([coc_value, part_a_mass, part_b_mass, exp_date]):
                return False

            # otherwise perform checks
            if coc_value and not re.match(r"^C\d{2}-\d{4}$", coc_value):
                with self.output:
                    show_modal_popup(f"COC must be in format C##-#### for measurement {idx + 1}, or do you want to continue? In this case the log\
                                      will not show up in the report.",
                lambda: self.remove_and_continue(step_number))
                return False

            if not measurement_check:
                if part_a_mass and not (part_a_min <= part_a_mass <= part_a_max):
                    show_modal_popup(f"Part A Mass must be between 3.88g and 4.12g for measurement {idx + 1}, do you want to continue?",
                                    lambda: self.procedure_loop(step_number + 1))
                    return False

                if part_b_mass and not (part_b_min <= part_b_mass <= part_b_max):
                    show_modal_popup(f"Part B Mass must be between 0.291g and 0.309g for measurement {idx + 1}, do you want to continue?",
                                    lambda: self.procedure_loop(step_number + 1))
                    return False

                if exp_date_obj and exp_date_obj < datetime.now().date():
                    show_modal_popup(f"Expiration Date must be a future date for measurement {idx + 1}, do you want to continue?",
                                    lambda: self.procedure_loop(step_number + 1))
                    return False

            valid_logs.append(log)

        self.steps[str(step_number)]['adhesive_log'] = valid_logs
        return True
    
    def get_adhesive_log(self, step_number: int, measurement_number: int = 0) -> widgets.VBox:
        """
        Generates the adhesive log input fields for a given step.
        Args:
            step_number (int): The step number to generate fields for.
            measurement_number (int): The current measurement number to display.
        Returns:
            widgets.VBox: The container with adhesive log input fields.
        """
        title = widgets.HTML(value=f"<h4>Adhesive / Potting Material Log (Measurement: {measurement_number + 1})</h4>")
        material = widgets.HTML(value="<b>Material: IQ-CAST 9852-TBL</b>")
        current_logs = self.steps[str(step_number)].get("adhesive_log", [])

        log_data = current_logs[measurement_number]

        coc_field = widgets.Text(
            value=log_data.get("coc", ""),
            placeholder='(format C##-####)',
            **self.field("COC Number:", field_width="300px", label_width="120px")
        )

        prep_datetime_str = log_data.get("prep_datetime")
        dt_local_aware = None
        if prep_datetime_str:
            dt_naive = datetime.strptime(prep_datetime_str, "%B %d, %Y %H:%M")
            dt_local_aware = dt_naive.replace(tzinfo=tzlocal.get_localzone())

        prep_datetime_field = widgets.DatetimePicker(
            value=dt_local_aware,
            **self.field("Preparation Date/Time:", field_width="300px", label_width="170px")
        )

        exp_date_str = log_data.get("exp_date", "")
        exp_date_value = datetime.strptime(exp_date_str, "%B %d, %Y").date() if exp_date_str else None
        exp_date_field = widgets.DatePicker(
            value=exp_date_value,
            **self.field("Expiration Date:", field_width="300px", label_width="120px")
        )

        temperature_field = widgets.BoundedFloatText(
            value=float(log_data.get("temperature", 0)),
            min=-50.0, max=150.0, step=0.1,
            **self.field("Temperature (°C):", field_width="300px", label_width="120px")
        )

        humidity_field = widgets.BoundedFloatText(
            value=float(log_data.get("humidity", 0)),
            min=0.0, max=100.0, step=0.1,
            **self.field("Humidity (%):", field_width="300px", label_width="120px")
        )

        part_a_mass_field = widgets.BoundedFloatText(
            value=float(log_data.get("part_a_mass", 0)),
            min=0.0, max=1000.0, step=0.1,
            **self.field("Part A Mass (g):", field_width="300px", label_width="120px")
        )

        part_b_mass_field = widgets.BoundedFloatText(
            value=float(log_data.get("part_b_mass", 0)),
            min=0.0, max=1000.0, step=0.1,
            **self.field("Part B Mass (g):", field_width="300px", label_width="120px")
        )

        add_measurement_button = widgets.Button(
            description="Add Measurement",
            button_style='warning',
            icon='plus'
        )

        switch_measurement_button = widgets.Button(
            description="Switch Measurement",
            button_style='info',
            icon='exchange-alt'
        )

        def on_measurement_switch(b) -> None:
            next_measurement = (measurement_number + 1) % len(current_logs)
            self.display_step_form(step_number=step_number, measurement_number=next_measurement)

        switch_measurement_button.on_click(on_measurement_switch)

        def on_add_measurement_click(b) -> None:
            current_logs = self.steps[str(step_number)].get("adhesive_log", [])
            if not self.check_adhesive_values(step_number, measurement_check = True):
                with self.output:
                    self.output.clear_output()
                    print("Please fill in all fields correctly before adding a new measurement.")
                    return
            if len(current_logs) >= 5:
                with self.output:
                    self.output.clear_output()
                    print("Maximum of 5 adhesive measurements reached.")
                return
            new_log = {
                "idx": f"_{len(current_logs) + 1}",
                "coc": "",
                "prep_datetime": None,
                "exp_date": None,
                "temperature": 0.0,
                "humidity": 0.0,
                "part_a_mass": 0.0,
                "part_b_mass": 0.0,
                "date": self.steps[str(step_number)].get("date"),
                "operator": self.steps[str(step_number)].get("operator")
            }
            current_logs[-1]["idx"] = f"_{len(current_logs)}" if len(current_logs) > 1 else ""
            current_logs.append(new_log)
            self.steps[str(step_number)]["adhesive_log"] = current_logs
            self.save_current_state()
            self.display_step_form(step_number=step_number, measurement_number=len(current_logs)-1)

        add_measurement_button.on_click(on_add_measurement_click)

        def on_field_change(change: dict) -> None:
            prep_datetime_value = prep_datetime_field.value.strftime("%B %d, %Y %H:%M") if prep_datetime_field.value else None
            exp_date_value = exp_date_field.value.strftime("%B %d, %Y") if exp_date_field.value else None
            self.steps[str(step_number)]["adhesive_log"][measurement_number]["coc"] = coc_field.value.strip()
            self.steps[str(step_number)]["adhesive_log"][measurement_number]["prep_datetime"] = prep_datetime_value
            self.steps[str(step_number)]["adhesive_log"][measurement_number]["exp_date"] = exp_date_value
            self.steps[str(step_number)]["adhesive_log"][measurement_number]["temperature"] = temperature_field.value
            self.steps[str(step_number)]["adhesive_log"][measurement_number]["humidity"] = humidity_field.value
            self.steps[str(step_number)]["adhesive_log"][measurement_number]["part_a_mass"] = part_a_mass_field.value
            self.steps[str(step_number)]["adhesive_log"][measurement_number]["part_b_mass"] = part_b_mass_field.value
            self.save_current_state()
        
        for field in [coc_field, prep_datetime_field, exp_date_field, temperature_field, humidity_field, part_a_mass_field, part_b_mass_field]:
            field.observe(on_field_change, names='value')

        log_box = widgets.VBox([
            title,
            material,
            widgets.HBox([prep_datetime_field], layout=widgets.Layout(width="auto", padding="0 0 0 0")),
            widgets.HBox([coc_field, exp_date_field], layout=widgets.Layout(width="auto", padding="0 0 0 0", spacing="10px")),
            widgets.HBox([temperature_field, humidity_field], layout=widgets.Layout(width="auto", padding="0 0 0 0", spacing="10px")),
            widgets.HBox([part_a_mass_field, part_b_mass_field], layout=widgets.Layout(width="auto", padding="0 0 0 0", spacing="10px")),
            widgets.HBox([add_measurement_button, switch_measurement_button] if len(current_logs) > 1 else [add_measurement_button], layout=widgets.Layout(width="auto", padding="0 0 0 0", spacing="10px")),
        ], layout=widgets.Layout(width="100%", overflow="visible", padding="10px 0 0 20px"))

        return log_box

    def get_cure_log(self, step_number: int) -> widgets.VBox:
        """
        Generates the cure log input fields for a given step.
        Args:
            step_number (int): The step number to generate fields for.
        Returns:
            widgets.VBox: The container with cure log input fields.
        """
        start_time = self.steps[str(step_number)]["cure_log"].get("start_datetime")
        end_time = self.steps[str(step_number)]["cure_log"].get("end_datetime")

        start_dt = datetime.strptime(start_time, "%B %d, %Y %H:%M") if start_time else None
        end_dt = datetime.strptime(end_time, "%B %d, %Y %H:%M") if end_time else None

        start_dt_local = start_dt.replace(tzinfo=tzlocal.get_localzone()) if start_dt else None
        end_dt_local = end_dt.replace(tzinfo=tzlocal.get_localzone()) if end_dt else None

        start_dt_picker = widgets.DatetimePicker(
            value=start_dt_local,
            **self.field("Cure Start Date/Time:", field_width="300px", label_width="170px")
        )

        end_dt_picker = widgets.DatetimePicker(
            value=end_dt_local,
            **self.field("Cure End Date/Time:", field_width="300px", label_width="170px")
        )

        description = self.steps[str(step_number)]["cure_log"].get("description", "")
        description_field = widgets.HTML(value=f"<h4>{description.replace('\n', '<br>')}</h4>" if description else "<h4>Cure Log</h4>")

        def on_field_change(change):
            start_dt_value = start_dt_picker.value.strftime("%B %d, %Y %H:%M") if start_dt_picker.value else ""
            end_dt_value = end_dt_picker.value.strftime("%B %d, %Y %H:%M") if end_dt_picker.value else ""
            self.steps[str(step_number)]["cure_log"]["start_datetime"] = start_dt_value
            self.steps[str(step_number)]["cure_log"]["end_datetime"] = end_dt_value
            self.save_current_state()

        start_dt_picker.observe(on_field_change, names='value')
        end_dt_picker.observe(on_field_change, names='value')

        log_box = widgets.VBox([
            description_field,
            widgets.HBox([start_dt_picker], layout=widgets.Layout(width="auto", padding="0 0 0 0")),
            widgets.HBox([end_dt_picker], layout=widgets.Layout(width="auto", padding="0 0 0 0"))
        ], layout=widgets.Layout(width="100%", overflow="visible", padding="10px 0 0 20px"))

        return log_box
    
    def get_measurements(self, step_number: int) -> widgets.VBox:
        """
        Generates the coil resistance measurement input fields for a given step.
        Args:
            step_number (int): The step number to generate fields for.
        Returns:
            widgets.VBox: The container with measurement input fields.
        """
        step_data = self.steps[str(step_number)]["measure_coil_resistance"]

        # --- Extract data ---
        multimeter_model = step_data.get("multimeter", "")
        multimeter_serial = step_data.get("multimeter_serial", "")
        calibration_multi_date = step_data.get("calibration_multi", "")
        calibration_multi_date_value = datetime.strptime(calibration_multi_date, "%B %d, %Y").date() if calibration_multi_date else None

        measured_200 = step_data.get("measured_200", "")
        measured_150 = step_data.get("measured_150", "")
        all_res = step_data.get("all_res", "")

        isolation_meter = step_data.get("isolation", "")
        isolation_serial = step_data.get("isolation_serial", "")
        isolation_calibration_date = step_data.get("calibration_isolation", "")
        isolation_calibration_date_value = datetime.strptime(isolation_calibration_date, "%B %d, %Y").date() if isolation_calibration_date else None

        inductance_150 = step_data.get("inductance_150") if "inductance_150" in step_data else None
        inductance_200 = step_data.get("inductance_200") if "inductance_200" in step_data else None
        capacitance = step_data.get("capacitance") if "capacitance" in step_data else None
        lcr_meter = step_data.get("lcr_meter") if "inductance" in step_data else None
        lcr_serial = step_data.get("lcr_meter_serial") if "inductance" in step_data else None
        lcr_calibration_date = step_data.get("calibration_lcr", "") if "inductance" in step_data else ""
        lcr_calibration_date_value = datetime.strptime(lcr_calibration_date, "%B %d, %Y").date() if lcr_calibration_date else None

        # --- Create fields ---
        resistance_field = widgets.BoundedFloatText(
            value=float(measured_200) if isinstance(measured_200, (int, float)) and self.resistance_goal == 200 
            else float(measured_150) if isinstance(measured_150, (int, float)) and self.resistance_goal == 150 
            else 0.0,
            min=0.0, max=1000.0, step=0.1,
            **self.field("Flying Lead 1 (Ohm)", field_width="300px", label_width="220px")
        )

        tot_resistance_field = widgets.BoundedFloatText(
            value=float(all_res) if isinstance(all_res, (int, float)) else 0.0,
            min=0.0, max=1e12, step=0.1,
            **self.field("Flying Lead 1-2 (MOhm)", field_width="300px", label_width="220px")
        )

        multimeter_model_field = widgets.Text(
            value=multimeter_model,
            placeholder='e.g. 34401A',
            **self.field("Model:", field_width="300px", label_width="80px")
        )

        multimeter_serial_field = widgets.Text(
            value=multimeter_serial,
            placeholder='Enter Serial',
            **self.field("Serial:", field_width="300px", label_width="80px")
        )

        calibration_multi_date_field = widgets.DatePicker(
            value=calibration_multi_date_value,
            **self.field("Calibration Date:", field_width="300px", label_width="120px")
        )

        isolation_meter_field = widgets.Text(
            value=isolation_meter,
            placeholder='e.g. GPT-9803',
            **self.field("Model:", field_width="300px", label_width="80px")
        )

        isolation_serial_field = widgets.Text(
            value=isolation_serial,
            placeholder='Enter Serial',
            **self.field("Serial:", field_width="300px", label_width="80px")
        )

        isolation_calibration_date_field = widgets.DatePicker(
            value=isolation_calibration_date_value,
            **self.field("Calibration Date:", field_width="300px", label_width="120px")
        )

        # Define these as None to avoid reference issues
        inductance_field = capacitance_field = lcr_meter_field = lcr_serial_field = lcr_calibration_date_field = None

        if inductance_150 is not None if self.resistance_goal == 150 else inductance_200 is not None:
            inductance_value = inductance_150 if self.resistance_goal == 150 else inductance_200
            inductance_field = widgets.BoundedFloatText(
                value=float(inductance_value) if isinstance(inductance_value, (int, float)) else 0.0,
                min=0.0, max=1000.0, step=0.1,
                **self.field("Measured Inductance (μH)", field_width="300px", label_width="220px")
            )

            capacitance_field = widgets.BoundedFloatText(
                value=float(capacitance) if isinstance(capacitance, (int, float)) else 0.0,
                min=0.0, max=1000.0, step=0.1,
                **self.field("Measured Capacitance (nF)", field_width="300px", label_width="220px")
            )

            lcr_meter_field = widgets.Text(
                value=lcr_meter or "",
                placeholder='e.g. HM8118',
                **self.field("LCR Meter:", field_width="300px", label_width="80px")
            )

            lcr_serial_field = widgets.Text(
                value=lcr_serial or "",
                placeholder='Enter LCR Serial',
                **self.field("Serial:", field_width="300px", label_width="80px")
            )

            lcr_calibration_date_field = widgets.DatePicker(
                value=lcr_calibration_date_value,
                **self.field("Calibration Date:", field_width="300px", label_width="120px")
            )

        # --- Validation thresholds ---
        resistance_150 = (135, 145)
        resistance_200 = (185, 195)
        inductance_max = 10e-6
        min_all_res = 100
        capacitance_max = 50e-9

        # --- Change handler ---
        def on_field_change(change: dict) -> None:
            data = self.steps[str(step_number)]['measure_coil_resistance']
            data["multimeter"] = multimeter_model_field.value.strip()
            data["multimeter_serial"] = multimeter_serial_field.value.strip()
            data["calibration_multi"] = calibration_multi_date_field.value.strftime("%B %d, %Y") if calibration_multi_date_field.value else ""
            key = "measured_200" if self.resistance_goal == 200 else "measured_150"
            data[key] = resistance_field.value
            inductance_key = "inductance_200" if self.resistance_goal == 200 else "inductance_150"
            if inductance_field:
                data[inductance_key] = inductance_field.value
            data["all_res"] = tot_resistance_field.value
            data["isolation"] = isolation_meter_field.value.strip()
            data["isolation_serial"] = isolation_serial_field.value.strip()
            data["calibration_isolation"] = isolation_calibration_date_field.value.strftime("%B %d, %Y") if isolation_calibration_date_field.value else ""

            if inductance_field:
                data["inductance"] = inductance_field.value
            if capacitance_field:
                data["capacitance"] = capacitance_field.value
            if lcr_meter_field:
                data["lcr_meter"] = lcr_meter_field.value.strip()
            if lcr_serial_field:
                data["lcr_meter_serial"] = lcr_serial_field.value.strip()
            if lcr_calibration_date_field:
                data["calibration_lcr"] = lcr_calibration_date_field.value.strftime("%B %d, %Y") if lcr_calibration_date_field.value else ""

            measured = resistance_field.value
            if measured:
                if self.resistance_goal == 200:
                    data["pass_200"] = resistance_200[0] <= measured <= resistance_200[1]
                elif self.resistance_goal == 150:
                    data["pass_150"] = resistance_150[0] <= measured <= resistance_150[1]

            if inductance_field and inductance_field.value:
                if self.resistance_goal == 150:
                    data["pass_inductance_150"] = inductance_field.value*1e-6 < inductance_max
                # elif self.resistance_goal == 200:
                #     data["pass_inductance_200"] = inductance_field.value*1e-6 < inductance_max

            if tot_resistance_field.value:
                data["pass_all"] = tot_resistance_field.value > min_all_res

            if capacitance_field and capacitance_field.value:
                data["pass_cap"] = capacitance_field.value < capacitance_max * 1e9

            self.save_current_state()

        # --- Attach observers ---
        fields_to_watch = [
            resistance_field, tot_resistance_field, multimeter_model_field,
            multimeter_serial_field, calibration_multi_date_field,
            isolation_meter_field, isolation_serial_field, isolation_calibration_date_field
        ]
        if inductance_field:
            fields_to_watch.extend([inductance_field, capacitance_field, lcr_meter_field, lcr_serial_field, lcr_calibration_date_field])

        for f in fields_to_watch:
            f.observe(on_field_change, names="value")

        # --- Layout ---
        multimeter_box = widgets.VBox([
            widgets.HTML(value="<h4>Multimeter</h4>"),
            widgets.HBox([
                widgets.VBox([multimeter_model_field, multimeter_serial_field, calibration_multi_date_field]),
                widgets.VBox([resistance_field, tot_resistance_field])
            ])
        ])

        isolation_box = widgets.VBox([
            widgets.HTML(value="<h4>Isolation Meter</h4>"),
            widgets.VBox([isolation_meter_field, isolation_serial_field, isolation_calibration_date_field])
        ])

        form_children = [multimeter_box, isolation_box]

        if inductance_field:
            lcr_box = widgets.VBox([
                widgets.HTML(value="<h4>LCR Meter</h4>"),
                widgets.HBox([
                    widgets.VBox([lcr_meter_field, lcr_serial_field, lcr_calibration_date_field]),
                    widgets.VBox([inductance_field, capacitance_field])
                ])
            ])
            form_children.append(lcr_box)

        return widgets.VBox(form_children, layout=widgets.Layout(gap="10px"))

    def check_measurement_values(self, step_number: int) -> bool:
        """
        Checks if all required measurement values are filled in and within limits for a given step.
        Args:
            step_number (int): The step number to check.
        Returns:
            bool: True if all required values are filled in and within limits, False otherwise.
        """
        step_data: dict[str, Any] = self.steps[str(step_number)]["measure_coil_resistance"]
        resistance_goal = self.resistance_goal
        measured_200 = step_data.get("measured_200", None)
        measured_150 = step_data.get("measured_150", None)
        inductance_150 = step_data.get("inductance_150", None)
        inductance_200 = step_data.get("inductance_200", None)
        all_res = step_data.get("all_res", None)
        capacitance = step_data.get("capacitance", None)


        resistance_150 = (135, 145)
        resistance_200 = (185, 195)
        min_all_res = 100
        capacitance_max = 50e-9
        inductance_max = 10e-6

        for key, value in step_data.items():
            if value is None or value == "":
                with self.output:
                    print(f"Please fill in: {key.replace('_', ' ').title()}.")
                return False

        if resistance_goal == 200:
            if measured_200 is None or not (resistance_200[0] <= measured_200 <= resistance_200[1]):
                show_modal_popup(f"Measured resistance for 200 Ohm goal must be between {resistance_200[0]} and {resistance_200[1]} Ohm, do you want to continue?", lambda: self.procedure_loop(step_number+1))
                return False
        elif resistance_goal == 150:
            if measured_150 is None or not (resistance_150[0] <= measured_150 <= resistance_150[1]):
                show_modal_popup(f"Measured resistance for 150 Ohm goal must be between {resistance_150[0]} and {resistance_150[1]} Ohm, do you want to continue?", lambda: self.procedure_loop(step_number+1))
                return False
            if inductance_150 is None or not (inductance_150 < inductance_max * 1e6):
                show_modal_popup(f"Measured inductance for 150 Ohm goal must be less than 10 μH, do you want to continue?", lambda: self.procedure_loop(step_number+1))
                return False

        if all_res is None or not (all_res > min_all_res):
            show_modal_popup(f"Total resistance must be larger than {min_all_res} MOhm, do you want to continue?", lambda: self.procedure_loop(step_number+1))
            return False
        
        if capacitance is not None and not (capacitance < capacitance_max * 1e9):
            show_modal_popup(f"Measured capacitance must be less than {capacitance_max * 1e9} nF, do you want to continue?", lambda: self.procedure_loop(step_number+1))
            return False

        return True
    
    def get_certifications(self) -> None:
        """
        Displays the certification UI form for holders and materials
        used in the assembly process.
        """

        LABEL_WIDTH = "160px"
        FIELD_WIDTH = "400px"
        QTY_LABEL_WIDTH = "80px"
        QTY_FIELD_WIDTH = "150px"

        missing_steps = [i for i in range(32, 74) if not self.steps.get(str(i), {}).get("performed", False)]
        if missing_steps:
            with self.header_output:
                for step in missing_steps:
                    print(f"Step {step} has not been performed yet. Please complete all steps before finalizing.")
            return

        if not self.holder_1_certs:
            self.holder_1_certs = self.session.query(TVCertification).filter_by(part_name = TVParts.HOLDER_1.value).all()
        if not self.holder_2_certs:
            self.holder_2_certs = self.session.query(TVCertification).filter_by(part_name = TVParts.HOLDER_2.value).all()
        certs_1 = list(set(cert.certification for cert in self.holder_1_certs))
        certs_2 = list(set(cert.certification for cert in self.holder_2_certs))

        # --- Holder fields ---
        holder_1_field = widgets.Combobox(
            value=self.steps.get("holder_1", ""),
            options=certs_1,
            placeholder='C##-####',
            **self.field("Holder 1:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        holder_1_rev_field = widgets.Text(
            value=self.steps.get("rev_1", "3"),
            **self.field("Rev.:", field_width="130px", label_width="60px")
        )
        holder_1_qty = widgets.BoundedIntText(
            value=int(self.steps.get("qty_1", 1)),
            min=0, max=1000, step=1,
            **self.field("Qty:", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        holder_2_field = widgets.Combobox(
            value=self.steps.get("holder_2", ""),
            options=certs_2,
            placeholder='C##-####',
            **self.field("Holder 2:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        holder_2_rev_field = widgets.Text(
            value=self.steps.get("rev_2", "3"),
            **self.field("Rev.:", field_width="130px", label_width="60px")
        )
        holder_2_qty = widgets.BoundedIntText(
            value=int(self.steps.get("qty_2", 1)),
            min=0, max=1000, step=1,
            **self.field("Qty:", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        # --- NiCr Wire ---
        nicr_wire_field = widgets.Text(
            value=self.steps.get("wire", ""),
            placeholder='C##-####',
            **self.field("NiCr Wire:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        nicr_qty_field = widgets.BoundedIntText(
            value=int(self.steps.get("qty_wire", 1)),
            min=0, max=1000, step=1,
            **self.field("Qty (m):", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        # --- IQ-Cast ---
        iq_cast_field = widgets.Text(
            value=self.steps.get("cast", ""),
            placeholder='C##-####',
            **self.field("IQ-Cast 9852-TBL:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        iq_cast_qty_field = widgets.BoundedIntText(
            value=int(self.steps.get("qty_cast", 15)),
            min=0, max=1000, step=1,
            **self.field("Qty (ml):", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        # --- Kapton Tape ---
        kapton_tape_field = widgets.Text(
            value=self.steps.get("tape", ""),
            placeholder='C##-####',
            **self.field("Kapton Tape:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        kapton_qty_field = widgets.BoundedIntText(
            value=int(self.steps.get("qty_tape", 1)),
            min=0, max=1000, step=1,
            **self.field("Qty:", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        # --- Contact ---
        contact_field = widgets.Text(
            value=self.steps.get("contact", ""),
            placeholder='C##-####',
            **self.field("Contact:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        contact_qty_field = widgets.BoundedIntText(
            value=int(self.steps.get("qty_contact", 2)),
            min=0, max=1000, step=1,
            **self.field("Qty:", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        # --- Sleeve ---
        sleeve_field = widgets.Text(
            value=self.steps.get("sleeve", ""),
            placeholder='C##-####',
            **self.field("Sleeve:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        sleeve_qty_field = widgets.BoundedIntText(
            value=int(self.steps.get("qty_sleeve", 23)),
            min=0, max=1000, step=1,
            **self.field("Qty (mm):", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        # --- Flying Leads ---
        flying_leads_field = widgets.Text(
            value=self.steps.get("leads", ""),
            placeholder='C##-####',
            **self.field("Flying Leads:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        flying_leads_qty_field = widgets.BoundedIntText(
            value=int(self.steps.get("qty_leads", 60)),
            min=0, max=1000, step=1,
            **self.field("Qty (cm):", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        # --- Cable Marker ---
        cable_marker_field = widgets.Text(
            value=self.steps.get("marker", ""),
            placeholder='C##-####',
            **self.field("Cable Marker:", field_width=FIELD_WIDTH, label_width=LABEL_WIDTH)
        )
        cable_marker_qty_field = widgets.BoundedIntText(
            value=int(self.steps.get("qty_marker", 2)),
            min=0, max=1000, step=1,
            **self.field("Qty:", field_width=QTY_FIELD_WIDTH, label_width=QTY_LABEL_WIDTH)
        )

        # --- Step Navigation ---
        max_step = max(int(k) for k in self.steps.keys() if k.isdigit())
        step_number = max_step
        go_to_step_field = widgets.Dropdown(
            value=max_step,
            options=[(f"Step {i}", i) for i in range(32, max_step + 1)],
            **self.field("Go to Step:", field_width="200px", label_width="100px")
        )

        def on_go_to_step_change(change):
            if change['name'] == 'value' and change['new'] != step_number:
                self.output.clear_output()
                self.procedure_loop(step_number=change['new'])

        go_to_step_field.observe(on_go_to_step_change, names='value')

        # --- Field Change Handler ---
        def on_field_change(change: dict) -> None:
            for key, widget in {
                "holder_1": holder_1_field,
                "rev_1": holder_1_rev_field,
                "qty_1": holder_1_qty,
                "holder_2": holder_2_field,
                "rev_2": holder_2_rev_field,
                "qty_2": holder_2_qty,
                "wire": nicr_wire_field,
                "qty_wire": nicr_qty_field,
                "cast": iq_cast_field,
                "qty_cast": iq_cast_qty_field,
                "tape": kapton_tape_field,
                "qty_tape": kapton_qty_field,
                "contact": contact_field,
                "qty_contact": contact_qty_field,
                "sleeve": sleeve_field,
                "qty_sleeve": sleeve_qty_field,
                "leads": flying_leads_field,
                "qty_leads": flying_leads_qty_field,
                "marker": cable_marker_field,
                "qty_marker": cable_marker_qty_field,
            }.items():
                self.steps[key] = widget.value.strip() if isinstance(widget, widgets.Text) else widget.value

            self.save_current_state()

        # Attach observer
        for field in [
            holder_1_field, holder_1_rev_field, holder_1_qty,
            holder_2_field, holder_2_rev_field, holder_2_qty,
            nicr_wire_field, nicr_qty_field,
            iq_cast_field, iq_cast_qty_field,
            kapton_tape_field, kapton_qty_field,
            contact_field, contact_qty_field,
            sleeve_field, sleeve_qty_field,
            flying_leads_field, flying_leads_qty_field,
            cable_marker_field, cable_marker_qty_field
        ]:
            field.observe(on_field_change, names='value')

        # --- Buttons ---
        def on_previous_step_click(b) -> None:
            self.output.clear_output()
            self.procedure_loop(step_number=max_step)
            on_field_change(None)

        def on_generate_report_click(b) -> None:
            self.output.clear_output()
            missing = [name for name, val in {
                "Holder 1": holder_1_field.value,
                "Rev. 1": holder_1_rev_field.value,
                "Qty 1": holder_1_qty.value,
                "Holder 2": holder_2_field.value,
                "Rev. 2": holder_2_rev_field.value,
                "Qty 2": holder_2_qty.value,
                "NiCr Wire": nicr_wire_field.value,
                "Qty Wire": nicr_qty_field.value,
                "IQ-Cast": iq_cast_field.value,
                "Qty Cast": iq_cast_qty_field.value,
                "Kapton Tape": kapton_tape_field.value,
                "Qty Tape": kapton_qty_field.value,
                "Contact": contact_field.value,
                "Qty Contact": contact_qty_field.value,
                "Sleeve": sleeve_field.value,
                "Qty Sleeve": sleeve_qty_field.value,
                "Flying Leads": flying_leads_field.value,
                "Qty Leads": flying_leads_qty_field.value,
                "Cable Marker": cable_marker_field.value,
                "Qty Marker": cable_marker_qty_field.value
            }.items() if not val]

            for certification in [holder_1_field.value, holder_2_field.value, nicr_wire_field.value,
                                  iq_cast_field.value, kapton_tape_field.value,
                                  contact_field.value, sleeve_field.value,
                                  flying_leads_field.value, cable_marker_field.value]:
                if certification and not re.match(r"^C\d{2}-\d{4}$", certification):
                    missing.append(f"Valid format for {certification} (e.g. C12-3456)")
            if missing:
                with self.output:
                    print("Missing required fields:")
                    for m in missing:
                        print(f" - {m}")
            else:
                self.generate_report()

        previous_btn = widgets.Button(description="Previous Step", icon="arrow-left", button_style="warning", width = "150px")
        generate_btn = widgets.Button(description="Generate Report", icon="check", button_style="success", width = "200px")
        previous_btn.on_click(on_previous_step_click)
        generate_btn.on_click(on_generate_report_click)

        # --- Layout Rows ---
        rows = [
            widgets.HBox([holder_1_field, holder_1_rev_field, holder_1_qty]),
            widgets.HBox([holder_2_field, holder_2_rev_field, holder_2_qty]),
            widgets.HBox([nicr_wire_field, nicr_qty_field]),
            widgets.HBox([iq_cast_field, iq_cast_qty_field]),
            widgets.HBox([kapton_tape_field, kapton_qty_field]),
            widgets.HBox([contact_field, contact_qty_field]),
            widgets.HBox([sleeve_field, sleeve_qty_field]),
            widgets.HBox([flying_leads_field, flying_leads_qty_field]),
            widgets.HBox([cable_marker_field, cable_marker_qty_field]),
        ]

        buttons_box = widgets.HBox([previous_btn, generate_btn], layout=widgets.Layout(gap="20px", padding="20px 0"))

        title = widgets.HTML("<h2>Final As-Run Certifications for Annex A</h2>")

        form = widgets.VBox(
            [go_to_step_field, title] + rows + [buttons_box, self.output],
            layout=widgets.Layout(gap="10px", padding="10px")
        )

        self.container.children = [form]

    def procedure_loop(self, step_number: int = 32) -> None:
        """
        Main loop to navigate through the assembly steps.
        Args:
            step_number (int): The current step number to display.
        """
        if step_number > max(int(k) for k in self.steps.keys() if k.isdigit()):
            self.get_certifications()
            return
        self.display_step_form(step_number=step_number)

    def get_adhesive_values(self, step_number: int) -> None:
        """
        Extracts adhesive log values for a given step and appends them to the adhesive_logs list.
        Args:
            step_number (int): The step number to extract values from.
        """
        if not "adhesive_log" in self.steps[str(step_number)]:
            return
        data = [self.steps[str(step_number)]["adhesive_log"]] if not isinstance(self.steps[str(step_number)]["adhesive_log"], list) else self.steps[str(step_number)]["adhesive_log"]
        for entry in data:
            entry["step_number"] = step_number
            string_check = str(entry["step_number"]) + str(entry.get("idx", ""))
            if string_check.endswith('0'):
                entry["idx"] = ""
        self.adhesive_logs.extend(data)

    def check_cure_log(self, step_number: int) -> None:
        """
        Extracts cure log values for a given step and adds them to the context.
        Args:
            step_number (int): The step number to extract values from.
        """
        if not "cure_log" in self.steps[str(step_number)]:
            return
        cure_data = self.steps[str(step_number)]["cure_log"]
        start_date = cure_data.get("start_datetime", "")
        end_date = cure_data.get("end_datetime", "")
        self.context[f"cure_start_{step_number}"] = start_date
        self.context[f"cure_finish_{step_number}"] = end_date

    def get_coil_measurements(self, step_number: int) -> None: 
        """
        Extracts coil resistance measurement values for a given step and adds them to the context.
        Args:
            step_number (int): The step number to extract values from.
        """
        if not "measure_coil_resistance" in self.steps[str(step_number)]:
            return
        meas_data = self.steps[str(step_number)]["measure_coil_resistance"]
        measured_200 = meas_data.get("measured_200", "")
        measured_150 = meas_data.get("measured_150", "")
        all_res = meas_data.get("all_res", "")
        inductance = meas_data.get("inductance", None)
        capacitance = meas_data.get("capacitance", None)

        if self.resistance_goal == 200:
            self.context[f"measured_200_{step_number}"] = measured_200
            self.context[f"pass_200_{step_number}"] = "Pass" if meas_data.get("pass_200", False) else "Fail" 
            self.context[f"pass_150_{step_number}"] = "N/A"
            self.context[f"inductance_200_{step_number}"] = meas_data.get("inductance_200", None)
            self.context[f"pass_inductance_200_{step_number}"] = "N/A"
            # self.context[f"pass_inductance_200_{step_number}"] = "Pass" if meas_data.get("pass_inductance_200", False) else "Fail"
            # self.context[f"pass_inductance_150_{step_number}"] = "N/A"
        elif self.resistance_goal == 150:
            self.context[f"measured_150_{step_number}"] = measured_150
            self.context[f"pass_150_{step_number}"] = "Pass" if meas_data.get("pass_150", False) else "Fail"
            self.context[f"pass_200_{step_number}"] = "N/A"
            self.context[f"inductance_150_{step_number}"] = meas_data.get("inductance_150", None)
            self.context[f"pass_inductance_150_{step_number}"] = "Pass" if meas_data.get("pass_inductance_150", False) else "Fail"
            self.context[f"pass_inductance_200_{step_number}"] = "N/A"

        if all_res != "":
            self.context[f"all_res_{step_number}"] = all_res
            self.context[f"pass_all_{step_number}"] = "Pass" if meas_data.get("pass_all", False) else "Fail"

        if inductance is not None:
            self.context[f"inductance_{step_number}"] = inductance
        if capacitance is not None:
            self.context[f"capacitance_{step_number}"] = capacitance
            self.context[f"pass_cap_{step_number}"] = "Pass" if meas_data.get("pass_cap", False) else "Fail"

        self.context[f"multimeter_{step_number}"] = meas_data.get("multimeter", "")
        self.context[f"multimeter_serial_{step_number}"] = meas_data.get("multimeter_serial", "")
        self.context[f"calibration_multi_{step_number}"] = meas_data.get("calibration_multi", "")
        self.context[f"isolation_{step_number}"] = meas_data.get("isolation", "")
        self.context[f"isolation_serial_{step_number}"] = meas_data.get("isolation_serial", "")
        self.context[f"calibration_isolation_{step_number}"] = meas_data.get("calibration_isolation", "")
        if inductance:
            self.context[f"lcr_{step_number}"] = meas_data.get("lcr_meter", "")
            self.context[f"lcr_serial_{step_number}"] = meas_data.get("lcr_meter_serial", "")
            self.context[f"calibration_lcr_{step_number}"] = meas_data.get("calibration_lcr", "")
        
    def generate_report(self) -> None:
        """
        Generates the final report by compiling all step data and rendering the document.
        """
        with self.output:
            print("Generating final report...")
        self.steps_copy = self.steps.copy()
        numeric_keys = [int(k) for k in self.steps.keys() if k.isdigit()]
        max_step = max(numeric_keys)
        min_step = min(numeric_keys)
        self.adhesive_logs = []
        for step in range(min_step, max_step + 1):
            date_key = f"date_{step}"
            operator_key = f"operator_{step}"
            remark_key = f"remark_{step}"
            date_value = self.steps[str(step)].get("date", "")
            operator_value = self.steps[str(step)].get("operator", "")
            remark_value = self.steps[str(step)].get("remark", "")
            self.context[date_key] = date_value
            self.context[operator_key] = operator_value
            self.context[remark_key] = remark_value
            self.get_adhesive_values(step)
            self.check_cure_log(step)
            self.get_coil_measurements(step)
            del self.steps[str(step)]
        
        self.context["engineer_72"] = self.context["operator_72"]
        self.context["engineer_62"] = self.context["operator_62"]
        self.context["quality_control_73"] = self.context["operator_73"]
        self.context["steps"] = self.adhesive_logs

        for key in self.steps:
            if not key.isdigit():
                self.context[key] = self.steps[key]

        self.render_final_document()

    def render_final_document(self) -> None:
        """
        Renders the final document using the template and saves it as a PDF.
        """
        with self.output:
            self.doc.render(self.context)

        working_dir = os.path.dirname(self.template_path)
        os.makedirs(working_dir, exist_ok=True)

        word_filename = f"As-run-draft ALG-BE-PR-0062 DRAFT4 sn.{self.tv_id}.docx"
        word_path = os.path.join(working_dir, word_filename)
        pdf_path = word_path.replace(".docx", ".pdf")

        self.doc.save(word_path)
        with self.output:
            convert(word_path, pdf_path)

        if os.path.exists(word_path):
            os.remove(word_path)

        os.makedirs(self.save_path, exist_ok=True)
        final_pdf_path = os.path.join(self.save_path, os.path.basename(pdf_path))
        shutil.move(pdf_path, final_pdf_path)

        # delete_json_file(f"tv_assembly_steps_draft_{self.tv_id}")
        with self.output:
            self.output.clear_output()
            print(f"Final report generated and saved to: {final_pdf_path}")
            self.update_database()
            self.container.children = [
                widgets.HTML("<h2>Report generated successfully. You can continue working on another TV or close the window.</h2>")
            ]

            self.all_tvs_field.unobserve(self.on_tv_change, names='value')
            self.all_tvs_field.options = [i for i in self.all_tvs_field.options if i[1] != self.tv_id]
            self.all_tvs_field.value = None
            self.all_tvs_field.observe(self.on_tv_change, names='value')

    def update_database(self) -> None:
        """
        Updates the database with the final assembly data,
        including coil assembly steps, context, adhesive logs, and status.
        """
        try:
            assembly_check = self.session.query(CoilAssembly).filter_by(tv_id=self.tv_id).first()
            existing_cert = self.session.query(TVCertification).filter_by(part_name=TVParts.HOLDER_1.value, tv_id = None).first()
            if existing_cert:
                existing_cert.tv_id = self.tv_id
            existing_cert_2 = self.session.query(TVCertification).filter_by(part_name=TVParts.HOLDER_2.value, tv_id = None).first()
            if existing_cert_2:
                existing_cert_2.tv_id = self.tv_id
            status_entry = self.session.query(TVStatus).filter_by(tv_id=self.tv_id).first()

            if status_entry:
                if status_entry.status == TVProgressStatus.TESTING_COMPLETED:
                    status_entry.status = TVProgressStatus.COIL_MOUNTED
                status_entry.electric_assembly_by = self.context.get("operator_32", "")
                status_entry.coil_resistance = self.resistance_goal
                if self.resistance_goal == 200:
                    status_entry.coil_resistance_measured = float(self.context.get(f"measured_200_72", 0))
                elif self.resistance_goal == 150:
                    status_entry.coil_resistance_measured = float(self.context.get(f"measured_150_72", 0))
                status_entry.coil_inductance = float(self.context.get(f"inductance_72", 0)) if self.context.get(f"inductance_72") else None
                status_entry.coil_capacitance = float(self.context.get(f"capacitance_72", 0)) if self.context.get(f"capacitance_72") else None
                status_entry.coil_completion_date = datetime.now().date()
            if assembly_check:
                assembly_check.steps = self.steps_copy
                assembly_check.context = self.context
                assembly_check.adhesive_logs = self.adhesive_logs
            else:
                new_assembly = CoilAssembly(
                    tv_id=self.tv_id,
                    steps=self.steps_copy,
                    context=self.context,
                    adhesive_logs=self.adhesive_logs
                )
                self.session.add(new_assembly)

            self.session.commit()
        except Exception as e:
            with self.output:
                print("Error updating the database:", e)
            self.session.rollback()
            return
