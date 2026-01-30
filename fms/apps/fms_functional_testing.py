"""
This is another Jupyter Notebook tool with as purpose to register the FMS Functional Tests in the database.
The user can select the FMS ID, indicate the type of test in [FR Test, Slope Test, Open Loop Test, Closed Loop Test and TVAC Test Log].

The registration of these functional tests, from my point of view, can be done in two ways:
    1)  Using this tool, but needs user input.
    2)  By having one of the servers listen (or fetch every few {insert time-delta}) to designated folders where
        the results of the tests are stored; but this needs consistency in folder naming.

My preference goes to number 2, but here is the tool anyway as I had already sort of implemented that.

@author: tantens
"""


from __future__ import annotations
from typing import TYPE_CHECKING
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
import numpy as np
import pandas as pd
from IPython.display import display
import ipywidgets as widgets

#:- Local Imports:-
from ..utils.general_utils import (
    show_modal_popup,
    field
)

from ..utils.enums import (
    FMSProgressStatus,
    FunctionalTestType,
    FMSProgressStatus,
    FMSFlowTestParameters, 
    FMSMainParameters
)
from sharedBE import operator
import sharedBE as be
from .query.fms_query import FMSQuery
from .. import FMSDataStructure
from ..utils.fms import FMSLogicSQL
from ..db import (
    FMSMain,
    FMSFunctionalTests,
    FMSFunctionalResults,
    FMSTvac,
    FMSFRTests,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

class FunctionalTestTool(FMSQuery):

    def __init__(self, local: bool = True):
        super().__init__()

        self.fms = FMSDataStructure(local = local)
        self.session = self.fms.Session()
        self.fms_sql = self.fms.fms_sql

    def show_test_input_field(self, session: "Session", fms_sql: "FMSLogicSQL") -> None:
        """
        Create a clean input field for TV test remarks with properly styled widgets.
        Also adds a dropdown field with suggestions for the FMS ID and gas type.
        Args:
            session (Session): SQLAlchemy session for database queries.
            fms_sql (FMS_SQL_Logic): SQL Handling class instance to update with the extracted test results.
        """
        label_width = '150px'
        field_width = '600px'
        self.gas_type = None

        def field(description):
            return {
                'description': description,
                'style': {'description_width': label_width},
                'layout': widgets.Layout(width=field_width, height='50px')
            }
        
        if session:
            fms_suggestions = session.query(FMSMain).filter(FMSMain.fms_id != None).all()
            fms_id_suggestions = [fms.fms_id for fms in fms_suggestions if fms.fms_id]
        else:   
            fms_id_suggestions = []

        fms_id_widget = widgets.Combobox(
            **field("FMS ID:"),
            options=fms_id_suggestions,
            ensure_option=False,
            placeholder='Type or select...'
        )

        # Gas type selection
        gas_type_widget = widgets.Dropdown(
            options=['Xe', 'Kr'],
            value='Xe',
            description='Gas type:',
            style={'description_width': label_width},
            layout=widgets.Layout(width=field_width, height='50px')
        )

        # Test type input
        test_widget = widgets.Dropdown(
            options=['open_loop', 'slope', 'closed_loop', 'fr_characteristics', 'tvac_cycle'],
            value=self.test_type,
            description='Test Type:',
            style={'description_width': label_width},
            layout=widgets.Layout(width=field_width, height='50px')
        )

        # Submit button
        submit_button = widgets.Button(
            description="Continue",
            button_style="success",
            layout=widgets.Layout(width='150px', margin='10px 0px 0px 160px')  # align under field
        )

        output = widgets.Output()

        # Form layout
        form = widgets.VBox([
            widgets.HBox([fms_id_widget]),
            widgets.HBox([gas_type_widget]),
            widgets.HBox([test_widget]),
            submit_button,
            output
        ], layout=widgets.Layout(padding='10px 0px 10px 0px'))

        display(form)
        submitted = {'done': False}
        confirmed_once = {'clicked': False}
        submit_button._click_handlers.callbacks.clear()
        # Submission handler
        def on_submit_clicked(b):
            with output:
                if submitted['done']:
                    return
                output.clear_output()
                if not confirmed_once['clicked']:
                    confirmed_once['clicked'] = True
                    print("Click again to confirm.")
                    return

                self.test_type = test_widget.value.strip()
                self.selected_fms_id = fms_id_widget.value
                self.gas_type = gas_type_widget.value

                # Validate FMS ID format: ##-###
                if not self.selected_fms_id or not re.match(r'^\d{2}-\d{3}$', str(self.selected_fms_id)):
                    print("Error: FMS ID must be in the format ##-### (e.g., 25-050).")
                    confirmed_once['clicked'] = False
                    return

                submitted['done'] = True
                confirmed_once['clicked'] = False
                if self.test_type in ["open_loop", "slope", "closed_loop", "fr_characteristics"]:
                    self.extract_slope_data()
                else:
                    self.extract_tvac_from_csv()

                print("Test Results have been Submitted!")

                fms_sql.functional_test_results = self.functional_test_results
                fms_sql.test_id = self.test_id
                fms_sql.selected_fms_id = self.selected_fms_id
                fms_sql.inlet_pressure = self.inlet_pressure
                fms_sql.outlet_pressure = self.outlet_pressure
                fms_sql.temp_type = self.temperature_type
                fms_sql.temperature = self.temperature
                fms_sql.units = self.units
                fms_sql.test_type = self.test_type
                fms_sql.gas_type = self.gas_type
                fms_sql.response_regions = self.response_regions
                fms_sql.response_times = self.response_times
                fms_sql.flow_power_slope = self.flow_power_slope.copy()
                if self.test_type.endswith('open_loop') or self.test_type.endswith('slope') or self.test_type.endswith('closed_loop'):
                    fms_sql.update_flow_test_results()
                elif self.test_type == "fr_characteristics":
                    fms_sql.update_fr_characteristics_results()
                else:
                    fms_sql.update_tvac_cycle_results()
                if not self.test_type == "tvac_cycle":
                    self.fms_test_remark_field(fms_sql)

        submit_button.on_click(on_submit_clicked)

    def fms_test_remark_field(self, fms_sql: "FMSLogicSQL") -> None:
        """
        Create a clean input field for FMS test remarks with properly styled widgets.
        Args:
            fms_sql (FMSLogicSQL): SQL Handling class instance to update the remark in the database.
        """
        label_width = '150px'
        field_width = '600px'
        
        title = widgets.HTML("<h3>Add a remark if necessary</h3>")

        def field(description):
            return {
                'description': description,
                'style': {'description_width': label_width},
                'layout': widgets.Layout(width=field_width, height='40px')
            }

        # Remark input
        remark_widget = widgets.Textarea(**field("Remark:"))

        # Submit button
        submit_button = widgets.Button(
            description="Submit Remark",
            button_style="success",
            layout=widgets.Layout(width='150px', margin='10px 0px 0px 160px')  # align under field
        )

        submitted = {'done': False}
        output = widgets.Output()

        # Form layout
        form = widgets.VBox([
            title,
            widgets.HTML('<p>Results are submitted, examine the plots and add a remark if necessary.</p>'
            ),
            widgets.HBox([remark_widget]),
            submit_button,
            output
        ], layout=widgets.Layout(
            border='1px solid #ccc',
            padding='20px',
            width='fit-content',
            gap='15px',
            background_color="#f9f9f9"
        ))

        display(form)

        if self.test_type.endswith('open_loop') or self.test_type.endswith('closed_loop') or "slope" in self.test_type:
            look_up_table = FMSFunctionalTests
            if self.test_type.endswith('closed_loop'):
                self.plot_closed_loop(serial=self.selected_fms_id, gas_type=self.gas_type)
            else:
                self.tv_slope = None
                self.plot_open_loop(serial=self.selected_fms_id, gas_type=self.gas_type)
                if self.flow_power_slope:
                    self.check_tv_slope(**self.flow_power_slope)

        elif self.test_type == "fr_characteristics":
            session = fms_sql.Session()
            look_up_table = FMSFRTests
            fms_entry = session.query(FMSMain).filter(FMSMain.fms_id == self.selected_fms_id).first()
            if fms_entry:
                manifold = fms_entry.manifold
                if manifold:
                    self.ratio = manifold[0].ac_ratio_specified

            self.plot_fr_characteristics(serial=self.selected_fms_id, gas_type=self.gas_type)
        else:
            look_up_table = FMSTvac
            self.plot_tvac_cycle(serial=self.selected_fms_id)

        # Submission handler
        def on_submit_clicked(b):
            with output:
                output.clear_output()
                remark = remark_widget.value.strip()
                if not remark:
                    print("No remark submitted.")
                    return
                session = fms_sql.Session()
                last_entry = (
                    session.query(look_up_table)
                    .filter_by(fms_id=self.selected_fms_id)
                    .order_by(look_up_table.id.desc())
                    .first()
                )
                if last_entry:
                    prev_remark = last_entry.remark or ""
                    if remark == prev_remark:
                        print("Already submitted!")
                    else:
                        last_entry.remark = remark
                        session.commit()
                        print("Remark Submitted!")
                else:
                    print("No test run entry found for this FMS.")
                session.close()

        submit_button.on_click(on_submit_clicked)