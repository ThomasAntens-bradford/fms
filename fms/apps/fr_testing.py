from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from sqlalchemy.orm import Session

import os
import ipywidgets as widgets
from .. import FMSDataStructure
from ..db import AnodeFR, CathodeFR  
from ..utils.general_utils import field, show_modal_popup
import sharedBE as be
from .query import ManifoldQuery
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np
import ipywidgets as widgets
from IPython.display import display
from sqlalchemy.orm import load_only
import traceback

class FRTesting:
    def __init__(self, local = True):
        self.local = local
        self.fms = FMSDataStructure(local = local)
        self.session: "Session" = self.fms.Session()
        self.fr_sql = self.fms.fr_sql
        self.fr_data = self.fms.fr_data
        self._output = widgets.Output()
        self.mq = ManifoldQuery(session = self.session, local = local)
        self.img_path = os.path.join(os.path.dirname(__file__), "images", "bradford_logo.jpg")

        self.get_flow_restrictors()
        self.logo = widgets.Image(value=open(self.img_path, "rb").read(), format='jpg', width=300, height=100)
        
    def get_flow_restrictors(self) -> None:
        """
        Retrieves all anode and cathode flow restrictors from the database that are not allocated to any set.
        """
        self.fr_dict = {}
        self.fr_entry_dict = {}
        try:
            all_anodes = self.session.query(AnodeFR).all()
            all_cathodes = self.session.query(CathodeFR).all()
            for fr in all_anodes:
                columns = [c.name for c in AnodeFR.__table__.columns]
                values = [getattr(fr, c) for c in columns]
                self.fr_dict[fr.fr_id] = {"serial_number": fr.fr_id, 'fr': "Anode", **dict(zip(columns, values))}
                self.fr_entry_dict[fr.fr_id] = fr
            for fr in all_cathodes:
                columns = [c.name for c in CathodeFR.__table__.columns]
                values = [getattr(fr, c) for c in columns]
                self.fr_dict[fr.fr_id] = {"serial_number": fr.fr_id, 'fr': "Cathode", **dict(zip(columns, values))}
                self.fr_entry_dict[fr.fr_id] = fr

        except Exception as e:
            print(f"Error retrieving flow restrictor certifications: {e}")
            traceback.print_exc()
        finally:
            if self.session:
                self.session.rollback()

    def get_tool_col(self, tool: str, db_data: list[dict[str, str]], tool_data: dict[str, str] = {}, type: str = "Anode") -> widgets.VBox:
        if tool_data:
            data = next((t for t in db_data if t.get("model") == tool_data.get("model") and t.get("serial_number") == tool_data.get("serial_number")), {})
        else:
            data = {}   

        def date_check(next_date = None, last_date = None):
            today = datetime.today()
            if next_date:
                return None if today >= next_date else next_date
            elif last_date:
                return None if today < last_date else last_date

        model_field = widgets.Dropdown(
            options=list(set([i.get("model") for i in db_data])),
            value=db_data[0].get("model") if not data else data.get("model"),
            **field(f"{' '.join(tool.split('_')).title()}:", label_width='200px', field_width='400px')
        )

        serial_field = widgets.Dropdown(
            options=[i.get("serial_number") for i in db_data if i.get('model') == model_field.value],
            value=db_data[0].get("serial_number") if not data else data.get("serial_number"),
            **field("Serial Number:", label_width='200px', field_width='400px')
        )

        range_field = widgets.Text(
            value=db_data[0].get("equipment_range") if not data else data.get("equipment_range"),
            **field("Equipment Range:", label_width='200px', field_width='400px')
        )

        accuracy_field = widgets.Text(
            value=db_data[0].get("accuracy") if not data else data.get("accuracy"),
            **field("Accuracy:", label_width='200px', field_width='400px')
        )

        next_calibration_date = widgets.DatePicker(
            value=db_data[0].get('next_calibration_date') if not data else data.get("next_calibration_date"),
            **field("Next Calibration:", label_width='200px', field_width='400px')
        )

        if date_check(next_date=next_calibration_date.value) is None:
            next_calibration_date.value = None

        last_calibration_date = widgets.DatePicker(
            value=db_data[0].get('last_calibration_date') if not data else data.get("last_calibration_date"),
            **field("Last Calibration:", label_width='200px', field_width='400px')
        )

        if date_check(last_date=last_calibration_date.value) is None:
            last_calibration_date.value = None

        def on_last_date_change(change):
            if not bool(date_check(last_date=last_calibration_date.value)):
                print("Last calibration date cannot be in the future!")
                last_calibration_date.value = None
        
        def on_next_date_change(change):
            if not bool(date_check(next_date=next_calibration_date.value)):
                print("Next calibration date cannot be in the past!")
                next_calibration_date.value = None  

        def update_data(model: str, serial: str):
            tool_data = next(
                i for i in db_data
                if i.get('model') == model and i.get('serial_number') == serial
            )

            range_field.value = tool_data.get('equipment_range', '')
            accuracy_field.value = tool_data.get('accuracy', '')
            next_calibration = tool_data.get('next_calibration_date')
            last_calibration = tool_data.get('last_calibration_date')

            next_calibration_date.value = date_check(next_date=next_calibration)
            last_calibration_date.value = date_check(last_date=last_calibration)

        def on_model_change(change):
            if not change['new']:
                return

            new_model = change['new']
            serials = [i.get('serial_number') for i in db_data if i.get('model') == new_model]

            serial_field.options = serials
            serial_field.value = serials[0]

            update_data(new_model, serials[0])

        def on_serial_change(change):
            if not change['new']:
                return

            update_data(model_field.value, change['new'])

        model_field.observe(on_model_change, names='value')
        serial_field.observe(on_serial_change, names='value')
        last_calibration_date.observe(on_last_date_change, names='value')
        next_calibration_date.observe(on_next_date_change, names='value')

        if tool == "mass_flow_sensor" and type == "Anode" and not bool(data):
            model_field.value = next(i.get('model') for i in db_data if "200SCCM" in i.get("model"))
        elif tool == "mass_flow_sensor" and type == "Cathode" and not bool(data):
            model_field.value = next(i.get('model') for i in db_data if "20SCCM" in i.get("model"))

        col = widgets.VBox(
            [
                model_field,
                serial_field,
                range_field,
                accuracy_field,
                next_calibration_date,
                last_calibration_date,
            ],
            layout=widgets.Layout(align_items="stretch")
        )

        return col
    
    def make_tool_grid(self, tool_grid_cols, max_cols_per_row=3, row_gap='25px', col_gap='20px'):
        rows = []
        for i in range(0, len(tool_grid_cols), max_cols_per_row):
            row_items = tool_grid_cols[i:i + max_cols_per_row]
            row = widgets.VBox([widgets.HBox(
                row_items,
                layout=widgets.Layout(
                    display='flex',
                    flex_flow='row nowrap',
                    justify_content='flex-start',
                    gap=col_gap  
                )),
                widgets.VBox(layout = widgets.Layout(height = row_gap))]
            )
            rows.append(row)

        tool_grid = widgets.VBox(
            rows,
            layout=widgets.Layout(
                display='flex',
                flex_flow='column nowrap',
                gap=row_gap  
            )
        )
        return tool_grid
        
    def get_fr_test_tools(self, tools: list[dict[str, str]] = [], type: str = "Anode") -> widgets.VBox:

        default_tools = [
            'temperature_recorder',
            'mass_flow_sensor',
            'inlet_pressure_controller',
            'outlet_pressure_controller'
        ]
        db_data = be.tools.group_tools_by_description(local = self.local)
        tool_grid_cols = []
        tool_map = {}
        for i in default_tools:
            data = db_data.get(i, [])
            tool_data = next(t for t in tools if t.get("description") == i) if bool(tools) else {}
            col = self.get_tool_col(tool=i, db_data=data, tool_data=tool_data, type=type)
            tool_grid_cols.append(col)
            tool_map[i] = col

        tool_grid = self.make_tool_grid(tool_grid_cols)
        return tool_grid, tool_map

    def _check_value(self, value: float, key: str, flow_rate_idx: int | None, flow_rate: bool = False, type: str = "Anode"):
        if not flow_rate:
            all_values = [i.get(key, None) for i in self.fr_dict.values() if bool(i.get(key, None)) and i.get("fr") == type]
        else:
            all_values = [i.get("flow_rates", [])[flow_rate_idx] for i in self.fr_dict.values() if bool(i.get("flow_rates", [])) and i.get("fr") == type]

        std = np.std(all_values)
        avg = np.average(all_values)
        norm = (value - avg) / std
        with self._output:
            print(norm)
        return abs(norm) <= 2.5, avg

    def _update_value(self, value: float, key: str, model: AnodeFR | CathodeFR, flow_rate_idx: float | None = None, flow_rate: bool = False):
        if not flow_rate:
            self.fr_dict[model.fr_id][key] = value
            if hasattr(model, key):
                setattr(model, key, value)
        else:
            if not self._retest:
                flow_rates = self.fr_dict[model.fr_id]["flow_rates"]
                if not flow_rates:
                    flow_rates = [0, 0, 0, 0]
                flow_rates[flow_rate_idx] = value
                setattr(model, "flow_rates", flow_rates)
            else:
                extra_tests = self.fr_dict[model.fr_id].get("extra_tests", {})
                if extra_tests is None:
                    extra_tests = {}
                test_key = self._test_widget.value
                flow_rates = extra_tests.get(test_key, [0, 0, 0, 0])
                flow_rates[flow_rate_idx] = value
                extra_tests[test_key] = flow_rates
                setattr(model, "extra_tests", extra_tests)
                self.fr_dict[model.fr_id]["extra_tests"] = extra_tests
        self.session.commit()


    def _clear_widget(self, widget: widgets.Widget, old_value: float = None):
        widget.value = old_value if old_value else 0


    def _clear_fields(self):
        self._loading = True
        self._temperature_widget.value = 0
        self._radius_widget.value = 0
        self._orifice_widget.value = 0
        self._thickness_widget.value = 0
        for w in self._flow_widgets:
            w.value = 0
        self._remark_field.value = ""
        self._loading = False
        self._button_box.children = (self._check_button,)
        self._test_widget.options = []
        self._test_widget.value = None


    def _update_serial_options(self, change):
        anode_selected = change["new"] == "Anode"

        if change["old"] == "Anode":
            self.last_anode = self._serial_number_widget.value
        else:
            self.last_cathode = self._serial_number_widget.value

        new_options = [
            i for i in self.fr_dict
            if self.fr_dict[i]['fr'] == ("Anode" if anode_selected else "Cathode")
        ]

        self._serial_number_widget.value = None
        self._serial_number_widget.options = new_options

        if anode_selected:
            self._serial_number_widget.value = self.last_anode if self.last_anode in new_options else None
        else:
            self._serial_number_widget.value = self.last_cathode if self.last_cathode in new_options else None

        if self._serial_number_widget.value is None:
            self._clear_fields()


    def _on_serial_change(self, change):
        if self._loading:
            return

        fr_id = change['new']
        self._loading = True
        self._button_box.children = (self._check_button,)

        if fr_id and fr_id in self.fr_dict:
            fr_data = self.fr_dict[fr_id]
            self._temperature_widget.value = fr_data.get('temperature', 0) or 0
            self._radius_widget.value = fr_data.get('radius', 0) or 0
            self._orifice_widget.value = fr_data.get('orifice_diameter', 0) or 0
            self._thickness_widget.value = fr_data.get('thickness', 0) or 0
            self._operator_widget.value = fr_data.get('operator') or self.fms.operator
            self._drawing_widget.value = fr_data.get('drawing') or (
                self.fr_data.anode_drawing if self._fr_widget.value == "Anode" else self.fr_data.cathode_drawing
            )

            flow_rates = fr_data.get('flow_rates', [0, 0, 0, 0])
            for widget, value in zip(self._flow_widgets, flow_rates):
                widget.value = value or 0

            extra_tests = fr_data.get("extra_tests", {})
            if extra_tests:
                main_test_num = [i for i in range(len(extra_tests) + 1) if f"test_{i+1}" not in extra_tests][0]
                options = [(f"Test {i+1} (main)" if i == main_test_num else f"Test {i+1}", f"test_{i+1}") for i in range(len(extra_tests) + 1)]
                value = f"test_{main_test_num + 1}"
                self._set_test_widget_options_and_value(options, value)
            else:
                self._set_test_widget_options_and_value([(f"Test 1 (main)", "test_1")], "test_1")
                if self._set_as_main_button in self._test_button_row.children:
                    self._test_button_row.children = tuple(list(self._test_button_row.children)[:-1])

            self._remark_field.value = fr_data.get("remark", "") or ""
        else:
            self._clear_fields()

        self._loading = False

    def _on_field_change(self, change, widget: widgets.Widget):
        self._output.clear_output()
        old_value = change["old"]

        if self._loading:
            return

        if not self._serial_number_widget.value:
            with self._output:
                print("Please select a valid Serial Number before making changes.")
            return

        try:
            fr_id = self._serial_number_widget.value
            anode = self._fr_widget.value == "Anode"
            parameter = self._widget_key_map.get(widget, "")
            value = widget.value

            flow_rate_idx = None
            flow_rate = False
            if "flow_rate" in parameter:
                flow_rate_idx = self._flow_widgets.index(widget)
                flow_rate = True

            fr_model = self.session.query(AnodeFR if anode else CathodeFR).filter_by(fr_id=fr_id).first()
            if fr_model and bool(value):
                passed, avg = self._check_value(
                    value, parameter, flow_rate_idx, flow_rate,
                    type="Anode" if anode else "Cathode"
                )

                if not passed:
                    with self._output:
                        show_modal_popup(
                            f"The value for {parameter.replace('_', ' ').title()}: {value:.4f} seems a bit out of proportion to the rest of the flow restrictors,\n"
                            f"which have an average {parameter.replace('_', ' ').title()} of {avg:.4f}.\n\n"
                            "Do you want to keep this value?",
                            continue_action=lambda: self._update_value(value, parameter, fr_model, flow_rate_idx, flow_rate),
                            cancel_action=lambda: self._clear_widget(widget, old_value=old_value)
                        )
                else:
                    self._update_value(value, parameter, fr_model, flow_rate_idx, flow_rate)

        except Exception as e:
            with self._output:
                print(f"Error updating FR data: {e}")
        finally:
            if self.session:
                self.session.rollback()

    def _on_check_clicked(self, b):
        with self._output:
            self._output.clear_output()

            if not self._serial_number_widget.value:
                print("Please select a valid Serial Number before checking measurements.")
                return

            pressures = [1.0, 1.5, 2.0, 2.4]
            flow_rates = [w.value for w in self._flow_widgets]

            temperature = self._temperature_widget.value
            orifice = self._orifice_widget.value
            fr_entry = self.fr_entry_dict.get(self._serial_number_widget.value, None)

            if all(f > 0 for f in flow_rates) and temperature and orifice:
                image_output = widgets.Output()
                comparison_image_output = widgets.Output()

                with image_output:
                    self.plot_fr_results(
                        pressures,
                        flow_rates,
                        self._fr_widget.value,
                        self._widget_key_map.inverse["gas_type"].value if hasattr(self._widget_key_map, "inverse") else None,
                        temperature
                    )

                with comparison_image_output:
                    self.mq.fr_flow_analysis(
                        certification="-".join(fr_entry.fr_id.split("-")[:-1]),
                        fr_entry=self.fr_entry_dict.get(self._serial_number_widget.value, None),
                        fr_type=self._fr_widget.value,
                        return_models=False,
                        plot=True
                    )

                display(
                    widgets.VBox([
                        self._remark_field,
                        widgets.VBox([], layout=widgets.Layout(height="50px")),
                        widgets.VBox([image_output, comparison_image_output])
                    ])
                )

                if len(self._button_box.children) == 1:
                    submit_button = widgets.Button(button_style='primary', **field("Submit Results"))
                    submit_button.on_click(self._on_submit_clicked)
                    self._button_box.children = (self._check_button, submit_button)
            else:
                print("Please enter valid flow rates, pressures, orifice diameter and temperature to plot the results.")

    def _on_submit_clicked(self, b):
        with self._output:
            self._output.clear_output()

            if not self._serial_number_widget.value:
                print("Please select a valid Serial Number before submitting results.")
                return

            pressures = [1.0, 1.5, 2.0, 2.4]
            flow_rates = [w.value for w in self._flow_widgets]

            temperature = self._temperature_widget.value
            orifice = self._orifice_widget.value
            fr_id = self._serial_number_widget.value

            if any(not w.value for col in self._tool_map.values() for w in col.children):
                print("Please make sure every field for every tool is filled in correctly.")
                return

            if all(f > 0 for f in flow_rates) and temperature and orifice:
                self.fr_sql.fr_test_results = self.fr_dict[fr_id]
                self.fr_sql.fr_test_results["date"] = datetime.now().isoformat()
                self.fr_sql.fr_test_results["remark"] = self._remark_field.value
                self.fr_sql.fr_test_results["gas_type"] = self._gas_type_widget.value

                reference_orifice = (
                    self.fr_data.anode_reference_orifice
                    if self._fr_widget.value == "Anode"
                    else self.fr_data.cathode_reference_orifice
                )

                self.fr_sql.fr_test_results["deviation"] = round(
                    (orifice - reference_orifice) / reference_orifice * 100, 2
                )

                tool_keep_keys = ["description", "serial_number", "model"]
                tool_keys = [
                    "model",
                    "serial_number",
                    "equipment_range",
                    "accuracy",
                    "next_calibration_date",
                    "last_calibration_date"
                ]

                tool_list = [
                    {
                        "description": desc,
                        **{tool_keys[idx]: w.value for idx, w in enumerate(col.children)}
                    }
                    for desc, col in self._tool_map.items()
                ]

                self.fr_sql.fr_test_results["tools"] = [
                    {key: value for key, value in data.items() if key in tool_keep_keys}
                    for data in tool_list
                ]

                self.fr_sql.fr_test_results["operator"] = self._operator_widget.value
                self.fr_sql.update_fr_test_results()
                be.tools.update_test_tools(tools_data = tool_list)

                print(f"FR test results for {fr_id} have been updated in the database.")
            else:
                print("Please enter valid flow rates, pressures, orifice diameter and temperature before submitting results.")

    def _on_retest_clicked(self, b):
        with self._output:
            self._output.clear_output()

            if not self._serial_number_widget.value:
                print("Please select a valid Serial Number before performing a re-test.")
                return

            fr_id = self._serial_number_widget.value

            fr_entry = self.fr_entry_dict.get(fr_id, None)
            if fr_entry:
                if not all(bool(i) for i in fr_entry.flow_rates):
                    with self._output:
                        self._output.clear_output()
                        print("This FR has not been fully tested yet. Please perform the initial test first.")
                    return
                
                extra_tests = fr_entry.extra_tests
                if extra_tests and not all(bool(i) for i in extra_tests.get(f"test_{len(extra_tests) + 1}", [0,0,0,0])):
                    with self._output:
                        self._output.clear_output()
                        print("Please complete the ongoing re-test before starting a new one.")
                    return
                elif len(self._test_widget.options) > 1 and not extra_tests:
                    with self._output:
                        self._output.clear_output()
                        print("Please complete the current re-test before starting a new re-test.")
                    return

                new_test_number = [int(i[1].split("_")[-1]) for i in self._test_widget.options][-1] + 1
                options = list(self._test_widget.options) + [(f"Test {new_test_number}", f"test_{new_test_number}")]
                value = f"test_{new_test_number}"
                self._set_test_widget_options_and_value(options, value)
                self._retest = True
                if not self._set_as_main_button in self._test_button_row.children:
                    self._test_button_row.children += (self._set_as_main_button,)
                self._test_number = self._test_widget.value

                for w in self._flow_widgets:
                    w.value = 0

    def _set_test_widget_options_and_value(self, options: list[tuple[str, str]], value: str):
        self._test_widget.unobserve(self._on_test_number_changed, names='value')
        self._test_widget.options = options
        self._test_widget.value = value
        self._test_widget.observe(self._on_test_number_changed, names='value')

    def _on_test_number_changed(self, change):
        with self._output:
            # self._output.clear_output()

            if not self._serial_number_widget.value:
                print("Please select a valid Serial Number before changing test number.")
                return
            
            fr_id = self._serial_number_widget.value
            fr_entry = self.fr_entry_dict.get(fr_id, None)
            extra_tests = fr_entry.extra_tests or {}
            self._test_number = change["new"]
            if not extra_tests:
                self._retest = False
                self._on_serial_change({'new': self._serial_number_widget.value})
                return

            elif self._test_number not in extra_tests:
                self._retest = False
                self._on_serial_change({'new': self._serial_number_widget.value})
                if self._set_as_main_button in self._test_button_row.children:
                    self._test_button_row.children = tuple(list(self._test_button_row.children)[:-1])
                return

            if fr_entry:
                flow_rates = extra_tests.get(self._test_number, [0, 0, 0, 0])
                self._retest = True

                for widget, value in zip(self._flow_widgets, flow_rates):
                    widget.unobserve_all()
                    widget.value = value or 0
                    widget.observe(lambda x, w=widget: self._on_field_change(x, widget=w), names='value')

                if not self._set_as_main_button in self._test_button_row.children:
                    self._test_button_row.children += (self._set_as_main_button,)

    def _set_test_as_main(self, b):
        with self._output:
            self._output.clear_output()

            if not self._serial_number_widget.value:
                print("Please select a valid Serial Number before setting test as main.")
                return
            
            fr_id = self._serial_number_widget.value
            fr_entry = self.fr_entry_dict.get(fr_id, None)
            extra_tests = fr_entry.extra_tests.copy()
            main_test_num = [f"test_{i+1}" for i in range(len(extra_tests) + 1) if f"test_{i+1}" not in extra_tests][0] if extra_tests else 0

            if fr_entry and extra_tests and self._test_number in extra_tests:
                main_flow_rates = fr_entry.flow_rates.copy()
                retest_flow_rates = extra_tests.get(self._test_number, [0, 0, 0, 0]).copy()

                if not len(retest_flow_rates) == 4 or not all(bool(i) for i in retest_flow_rates):
                    print("The selected re-test does not have complete flow rate data. Cannot set as main test.")
                    return

                fr_entry.flow_rates = retest_flow_rates
                extra_tests[main_test_num] = main_flow_rates
                del extra_tests[self._test_number]
                fr_entry.extra_tests = extra_tests
                self.session.commit()

                self.fr_dict[fr_id]["flow_rates"] = retest_flow_rates
                self.fr_dict[fr_id]["extra_tests"] = extra_tests
                self.fr_entry_dict[fr_id] = fr_entry

                options = [(f"Test {i+1} (main)" if i+1 == int(self._test_number.split('_')[-1])\
                                               else f"Test {i+1}", f"test_{i+1}") for i in range(len(self._test_widget.options))]
                value = self._test_number
                self._set_test_widget_options_and_value(options, value)
                self._retest = False

                self._test_button_row.children = tuple(list(self._test_button_row.children)[:-1])
                print(extra_tests, fr_entry.flow_rates, fr_entry.extra_tests)

                print(f"Re-test {self._test_number} has been set as the main test for FR {fr_id}.")
            else:
                print("Error setting re-test as main. Please ensure the re-test data is available.")

    def flow_test_inputs(self) -> None:
        """
        Displays the UI for the FR flow testing inputs.
            - Select FR type (Anode/Cathode)
            - Select serial number from available unallocated FRs
            - Input temperature, gas type, radius
            - Input pressures and corresponding flow rates
            - Remark field
        Methods
        -----------
            clear_fields(): Clears all input fields.
            update_serial_options(change): Updates serial number options based on selected FR type.
            on_serial_change(change): Updates input fields based on selected serial number.
            on_field_change(change): Clears output when any input field changes.
            on_check_clicked(b): Validates the input measurements and displays results.
            on_submit_clicked(b): Submits the measurements to the database.
        """
        label_width = '180px'
        field_width = '350px'
        self._loading = False

        self.pressures = []
        self.flow_rates = []
        self.measurement_widgets = []
        self.last_anode = ""
        self.last_cathode = ""

        navigation_widget = widgets.ToggleButtons(
            options=["FR Test Inputs", "Test Tools"],
            value="FR Test Inputs",
            description="Select View:",
            layout=widgets.Layout(width='400px', margin='0px 0px 20px 0px'),
            style={'description_width': 'initial'}
        )

        self._fr_widget = widgets.Dropdown(
            options=["Anode", "Cathode"],
            value="Anode",
            **field("Select FR Type")
        )

        self._operator_widget = widgets.Text(
            value=self.fms.operator,
            **field("Operator:"),
            disabled=True
        )

        self._drawing_widget = widgets.Text(
            value=self.fr_data.anode_drawing,
            **field("Drawing Ref:")
        )

        self._serial_number_widget = widgets.Dropdown(
            **field("Serial Number:"),
            options=[i for i in self.fr_dict if self.fr_dict[i]['fr'] == "Anode"] if self.fr_dict else [],
            value=self.fr_id if getattr(self, "fr_id", None) else None
        )

        self._temperature_widget = widgets.BoundedFloatText(**field("Temperature [°C]:"), value=0, min=0, max=50)
        operator_row = widgets.HBox([self._operator_widget, self._drawing_widget, self._temperature_widget])

        self._gas_type_widget = widgets.Dropdown(**field("Gas Type:"), options=["Xe", "Kr"])
        self._radius_widget = widgets.BoundedFloatText(**field("Radius [mm]:"), min=0, step=0.001)
        self._thickness_widget = widgets.BoundedFloatText(**field("Thickness [mm]:"), min=0, step=0.001)
        self._orifice_widget = widgets.BoundedFloatText(**field("Orifice Diameter [mm]:"), min=0, step=0.0001)

        dimension_row = widgets.HBox([self._orifice_widget, self._radius_widget, self._thickness_widget])
        serial_row = widgets.HBox([self._fr_widget, self._serial_number_widget, self._gas_type_widget])

        self._test_widget = widgets.Dropdown(
            **field("Select Test Number:"),
            options=[],
            value=None
        )
        self._test_widget.observe(self._on_test_number_changed, names='value')

        pressure_1 = widgets.BoundedFloatText(**field("Pressure [barA]:"), min=0, value=1.0, disabled=True)
        flow_rate_1 = widgets.BoundedFloatText(**field("Flow Rate [mg/s]:"), min=0, step=0.01)
        pressure_15 = widgets.BoundedFloatText(**field("Pressure [barA]:"), min=0, value=1.5, disabled=True)
        flow_rate_15 = widgets.BoundedFloatText(**field("Flow Rate [mg/s]:"), min=0, step=0.01)
        pressure_2 = widgets.BoundedFloatText(**field("Pressure [barA]:"), min=0, value=2.0, disabled=True)
        flow_rate_2 = widgets.BoundedFloatText(**field("Flow Rate [mg/s]:"), min=0, step=0.01)
        pressure_24 = widgets.BoundedFloatText(**field("Pressure [barA]:"), min=0, value=2.4, disabled=True)
        flow_rate_24 = widgets.BoundedFloatText(**field("Flow Rate [mg/s]:"), min=0, step=0.01)

        self._flow_widgets = [flow_rate_1, flow_rate_15, flow_rate_2, flow_rate_24]

        add_test_button = widgets.Button(button_style='info', **field("Perform Re-test", field_width = "150px"))
        add_test_button.on_click(lambda b: self._on_retest_clicked(b))

        self._set_as_main_button = widgets.Button(button_style='warning', **field("Set as Main Test", field_width = "150px"))
        self._set_as_main_button.on_click(lambda b: self._set_test_as_main(b))

        self._test_button_row = widgets.HBox([self._test_widget, add_test_button])

        row_1 = widgets.HBox([pressure_1, flow_rate_1])
        row_15 = widgets.HBox([pressure_15, flow_rate_15])
        row_2 = widgets.HBox([pressure_2, flow_rate_2])
        row_24 = widgets.HBox([pressure_24, flow_rate_24])

        self._remark_field = widgets.Textarea(
            description="Remark:",
            layout=widgets.Layout(width='500px', height='150px'),
            style={'description_width': '150px'},
            placeholder="Enter any remarks here..."
        )

        self._check_button = widgets.Button(button_style='success', **field("Check Measurements"))
        self._button_box = widgets.HBox([self._check_button])

        tool_grid, tool_map = self.get_fr_test_tools()
        self._tool_map = tool_map
        tools_container = widgets.VBox([tool_grid])

        self._widget_key_map = {
            self._gas_type_widget: "gas_type",
            self._temperature_widget: "temperature",
            self._radius_widget: "radius",
            self._orifice_widget: "orifice_diameter",
            self._thickness_widget: "thickness",
            flow_rate_1: "flow_rate_1",
            flow_rate_15: "flow_rate_15",
            flow_rate_2: "flow_rate_2",
            flow_rate_24: "flow_rate_24"
        }

        for widget in [self._gas_type_widget, self._temperature_widget, self._radius_widget,
                        self._orifice_widget, self._thickness_widget] + self._flow_widgets:
            widget.observe(lambda x, w=widget: self._on_field_change(x, widget=w), names='value')

        self._serial_number_widget.observe(self._on_serial_change, names='value')
        self._fr_widget.observe(self._update_serial_options, names='value')

        self._check_button.on_click(self._on_check_clicked)
        submit_button = widgets.Button(button_style='primary', **field("Submit Results"))
        submit_button.on_click(self._on_submit_clicked)

        title = widgets.HTML("<h2>Flow Restrictor Testing</h2>")

        flow_input_children = [
            self._test_button_row,
            operator_row,
            serial_row,
            dimension_row,
            row_1,
            row_15,
            row_2,
            row_24,
            widgets.VBox([], layout=widgets.Layout(height="50px")),
            self._button_box
        ]

        inner_form = widgets.VBox(flow_input_children)

        def on_navigation_change(change):
            if navigation_widget.value == "Test Tools":
                inner_form.children = (tools_container,)
            else:
                inner_form.children = flow_input_children

        navigation_widget.observe(on_navigation_change)

        form = widgets.VBox(
            [   
                self.logo,
                title,
                navigation_widget,
                inner_form,
                self._output
            ],
            layout=widgets.Layout(spacing=15)
        )

        display(form)

    def plot_fr_results(self, pressures: list, flow_rates: list, type: str, extra_tests: list[dict[str, list]] = [], gas_type: str = "Xe", temperature: float = None):
        """
        Plot the flow rates against pressures for the FR test results.
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(pressures, flow_rates, marker='o', linestyle='--', color='b')
        ax.set_title(f'Flow Rate {gas_type} in {type} Flow Restrictor vs Pressure @ {temperature}°C')
        ax.set_xlabel('Pressure [bar]')
        ax.set_ylabel(f'Flow Rate [mg/s {gas_type}]')
        ax.grid(True)

        plt.show()