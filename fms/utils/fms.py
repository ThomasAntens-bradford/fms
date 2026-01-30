# Standard library imports
import os
import re
import sys
import time
import traceback
from datetime import datetime
from threading import Timer
from enum import Enum

# Third-party imports
import fitz
import ipywidgets as widgets
import numpy as np
import openpyxl
import pandas as pd
from scipy.interpolate import interp1d
from sklearn.linear_model import LinearRegression
from sklearn.metrics import r2_score
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from IPython.display import display
import ipywidgets as widgets
from sqlalchemy import func, or_

# TYPE_CHECKING imports
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ..fms_data_structure import FMSDataStructure

# Local application imports
from ..db import (
    AnodeFR, CathodeFR, FMSFunctionalResults,
    FMSFunctionalTests, FMSFRTests, FMSLimits,
    FMSMain, FMSTestResults, FMSTvac, 
    HPIVCertification, 
    LPTCalibration,
    ManifoldStatus, 
    TVStatus, 
    FRCertification
)
from .enums import (
    FunctionalTestType, 
    LimitStatus,
    FMSProgressStatus,
    FMSFlowTestParameters, 
    FMSMainParameters, 
    FMSTvacParameters
)
from .general_utils import (
    find_intersections, 
    get_slope,
    save_to_json, 
    load_from_json, 
    delete_json_file, 
)

# Optional: modify sys.path for script execution (if running as main)
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

class FMSListener(FileSystemEventHandler):
    """
    File system event handler for monitoring HPIV data packages.

    This class extends FileSystemEventHandler to monitor a specified directory
    for new PDF, XLS, or CSV files containing HPIV test data. When a new file
    is detected, it automatically processes the file to extract test results.

    Attributes:
        path (str): Directory path to monitor for new files.
        observer (Observer): Watchdog observer instance for file monitoring.
        processed (bool): Flag indicating if new data has been processed.
        csv_files (list): List of CSV files to be processed in batch.
        test_type (str): Type of test being processed (e.g., "closed_loop", "open_loop", "slope", "fr_characteristics", "tvac_cycle").
        fms_data (FMS_data): Instance of FMS_data containing the processed test data.
    """

    def __init__(self, fms_data: "FMSData" = None):
        """
        Initialize the HPIV data listener.

        Args:
            path (str, optional): Directory path to monitor. Defaults to "FMS_data".
        """
        self.processed = False
        self.csv_files = []
        self._csv_timer = None
        self.test_type = None
        self.fms_data = fms_data

    def start_listening(self, folder: str = "") -> None:
        self.observer = Observer()
        self.observer.schedule(self, folder, recursive=False)
        self.observer.start()

    def stop_listening(self) -> None:
        if not hasattr(self, "observer"):
            return
        self.observer.stop()
        self.observer.join()

    def _process_csv_batch(self):
        try:
            self.fms_data.csv_files = self.csv_files.copy()
            self.fms_data.test_type = self.test_type
            self.csv_files.clear()
            self.processed = True
        except Exception as e:
            print(f"Error processing batch of CSV files: {e}")
            traceback.print_exc()

    def _schedule_csv_batch(self):
        if self._csv_timer:
            self._csv_timer.cancel()
        self._csv_timer = Timer(1.0, self._process_csv_batch)
        self._csv_timer.start()

    def on_created(self, event) -> None:
        """
        Handle file creation events in the monitored directory.
        """
        if event.is_directory:
            # If folder is dropped, assume it contains CSVs for tvac_cycle
            csv_files_in_folder = []
            for root, _, files in os.walk(event.src_path):
                for file in files:
                    if file.endswith('.csv'):
                        file_path = os.path.join(root, file)
                        csv_files_in_folder.append(file_path)

            if csv_files_in_folder:
                self.csv_files.extend(csv_files_in_folder)
                self.test_type = "tvac_cycle"
                self._schedule_csv_batch()
            return

        filename = os.path.basename(event.src_path)

        if filename.endswith('.xls'):
            # Determine test type from filename
            lower_name = filename.lower()
            if "closed" in lower_name:
                self.test_type = "closed_loop"
            elif "open" in lower_name:
                self.test_type = "open_loop"
            elif "slope" in lower_name:
                self.test_type = "slope"
            elif "fr" in lower_name or "characteristics" in lower_name or "fr characteristics" in lower_name:
                self.test_type = "fr_characteristics"
            else:
                self.test_type = None

            try:
                self.fms_data.flow_test_file = event.src_path
                self.fms_data.test_type = self.test_type
                self.processed = True
            except Exception as e:
                print(f"Error processing XLS file {event.src_path}: {e}")
                traceback.print_exc()

        elif filename.endswith('.csv'):
            # Individual CSV files are treated as tvac_cycle
            self.test_type = "tvac_cycle"
            self.csv_files.append(event.src_path)
            self._schedule_csv_batch()

        elif filename.endswith('.pdf'):
            try:
                self.fms_data.pdf_file = event.src_path
                self.processed = True
            except Exception as e:
                print(f"Error processing PDF file {event.src_path}: {e}")
                traceback.print_exc()

class FMSData:
    """
    Base class for FMS data handling.

    Provides shared functionality for managing FMS data and serves as a base for subclasses
    handling specific FMS data types.

    Attributes:
        General files and test info:
            pdf_file (str): Path to the PDF with FMS test data.
            flow_test_file (str): Path to the flow test XLS file.
            csv_files (list): CSV files for TVAC cycle data.
            status_file (str): Status Excel template.
            vibration_path (str): Path to vibration data.
            project_ref (str): Project reference identifier.
            test_type (str): Type of test being processed.
            test_id (int): Test ID for the current dataset.
            selected_fms_id (int): Selected FMS ID for data processing.
            response_times (dict): Response times for lpt set points.
            response_regions (dict): Response regions in time for lpt set points.
            slope_correction (float): Correction factor w.r.t. the specified inlet pressure.

        Flow test parameters:
            lpt_pressures (list): List of LPT pressures.
            lpt_voltages (list): List of LPT voltages.
            min_flow_rates (list): Minimum flow rates for each pressure/voltage.
            max_flow_rates (list): Maximum flow rates for each pressure/voltage.
            flow_power_slope (dict): Flow power slope data.
            group_by_voltage (bool): Whether to group data by voltage.

        TVAC and temperature:
            temperature_type (str): Type of temperature measurement used.
            tvac_map (dict): Mapping of TVAC parameters.

        FMS parameters and limits:
            fms_main_parameters (list): Main FMS parameter names (FMSMainParameters enum).
            fms_limits (dict): Default limits for FMS parameters.
            test_parameter_names (list): Test parameter names (FMSFlowTestParameters enum).
            inlet_pressure (float): Inlet pressure value.
            outlet_pressure (float): Outlet pressure value.
            intersections (dict): Stores intersection points.
            units (str): Units of measurement.
            range12_low, range24_low (list): 10 [bar] pressure slope limits for 1-2 and 2-4 mg/s flow-rate.
            range12_high, range24_high (list): 190 [bar] pressure slope limits for 1-2 and 2-4 mg/s flow-rate.

    Methods:
        TVAC helpers:
            get_tvac_parameter(base_param, tvac_label)
            extract_tvac_from_csv()
            plot_tvac_cycle(serial)
            plot_tv_closed_loop(title)

        Flow test helpers:
            preprocess_flow_dataframe(trial, df)
            extract_slope_data(separation, trial)
            group_by_lpt_pressures()
            get_flow_power_slope(flows, powers, num_points)
            check_tv_slope(tv_power_12, tv_power_24, flow_rates_12, flow_rates_24,
                        slope12, slope24, intercept12, intercept24)

        Plotting:
            show_test_input_field(session, fms_sql)
            fms_test_remark_field(fms_sql)
            plot_closed_loop(serial, gas_type)
            plot_tv_closed_loop(title)
            plot_open_loop(serial, gas_type)
            plot_fr_characteristics(gas_type, serial)
            plot_fr_voltage(title, gas_type)

        FMS data extraction:
            extract_FMS_test_results()
            extract_power_budget()
            extract_leakage(lines, tvac_label)
            extract_hpiv_performance(lines, tvac_label)
            extract_electrical_results(lines, tvac_label)
            parse_tolerance_line(line)
            parse_actual_line(line)
            normalize(text)
            parse_actual(line)
            parse_measurements(lines)
            parse_serials(lines)
    """

    def __init__(self, pdf_file: str = None, flow_test_file: str = None, test_type: str = None, lpt_pressures: list[float] = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.25, 2.4],
                 lpt_voltages: list[float] = [10, 15, 17, 20, 24, 25, 30, 35], min_flow_rates: list[float] = [0.61, 1.23, 1.51, 1.85, 2.40, 2.43, 3.13, 3.72], 
                 max_flow_rates: list[float] = [0.96, 1.61, 1.9, 2.34, 2.93, 3.07, 3.81, 4.54], csv_files: list[str] = None, 
                 status_file: str = 'Excel_templates/FMS_status_template.xlsx', range12_low: list[float] = [13, 41], range24_low: list[float] = [19, 54],
                 range12_high: list[float] = [25, 95], range24_high: list[float] = [35, 140], initial_flow_rate: float = 0.035, lpt_set_points: list[float] = [1, 1.625, 2.25, 1.625, 1, 0.2]):

        self.flow_test_file = flow_test_file
        self.pdf_file = pdf_file
        self.test_type = test_type
        self.lpt_pressures = lpt_pressures
        self.lpt_set_points = lpt_set_points
        self.lpt_voltages = lpt_voltages
        self.initial_flow_rate = initial_flow_rate
        self.min_flow_rates = min_flow_rates
        self.max_flow_rates = max_flow_rates
        self.fms_main_test_results = {}
        self.functional_test_results = {}
        self.temperature = None
        self.status_file = status_file
        self.range12_low = range12_low
        self.range24_low = range24_low
        self.range12_high = range12_high
        self.range24_high = range24_high
        self.temperature_type = None
        self.flow_power_slope = {}
        self.inlet_pressure = None
        self.selected_fms_id = None
        self.outlet_pressure = None
        self.intersections = {}
        self.units = None
        self.csv_files = csv_files
        self.test_id = None
        self.group_by_voltage = False
        self.project_ref = None
        self.response_times: dict[str, list] = {}
        self.response_regions: dict[str, list] = {}
        self.slope_correction = 1
        self.test_parameter_names = [param.value for param in FMSFlowTestParameters]
        self.vibration_path = ""
        self.tvac_map = {
            'Time': FMSTvacParameters.TIME.value,
            '104 <TRP1> (C)': FMSTvacParameters.TRP1.value,
            '105 <TRP2> (C)': FMSTvacParameters.TRP2.value,
            '106 <TV inlet> (C)': FMSTvacParameters.TV_INLET_TEMP.value,
            '107 <Manifold> (C)': FMSTvacParameters.MANIFOLD_TEMP.value,
            '108 <LPT> (C)': FMSTvacParameters.LPT_TEMP.value,
            '109 <HPIV> (C)': FMSTvacParameters.HPIV_TEMP.value,
            '110 <TV outlet> (C)': FMSTvacParameters.TV_OUTLET_TEMP.value,
            '113 <FMS inlet> (C)': FMSTvacParameters.FMS_INLET_TEMP.value,
            '114 <Anode outlet> (C)': FMSTvacParameters.ANODE_OUTLET_TEMP.value,
            '115 <Cathode outlet> (C)': FMSTvacParameters.CATHODE_OUTLET_TEMP.value,
        }

        self.fms_main_parameters = [param.value for param in FMSMainParameters]

        self.fms_limits = {
            'mass': {'min': 0, 'max': 500},
            'power_budget_cold': {'min': None, 'max': None},
            'power_budget_room': {'min': None, 'max': None},
            'power_budget_hot': {'min': None, 'max': None},
            'room_hpiv_dropout_voltage': {'min': 0, 'max': 4},
            'room_hpiv_pullin_voltage': {'min': 0, 'max': 18},
            'room_hpiv_closing_response': {'min': 0, 'max': 20},
            'room_hpiv_hold_power': {'min': None, 'max': None},
            'room_hpiv_opening_response': {'min': 0, 'max': 20},
            'room_hpiv_opening_power': {'min': None, 'max': None},
            'room_hpiv_inductance': {'min': None, 'max': None},
            'room_tv_inductance': {'min': None, 'max': None},
            'room_hpiv_resistance': {'min': None, 'max': None},
            'room_tv_pt_resistance': {'min': None, 'max': None},
            'room_tv_resistance': {'min': 150-0.1*150, 'max': 150+0.1*150, 'nominal': 150, 'tolerance': 10},
            'room_lpt_resistance': {'min': None, 'max': None},
            'room_tv_high_leak': {'min': 0, 'max': 1e-5},
            'room_tv_low_leak': {'min': 0, 'max': 1e-5},
            'room_tv_low_leak_open': {'min': None, 'max': None},
            'room_hpiv_high_leak': {'min': 0, 'max': 1e-5},
            'room_hpiv_low_leak': {'min': 0, 'max': 1e-5},
            'cold_hpiv_dropout_voltage': {'min': 0, 'max': 4},
            'cold_hpiv_pullin_voltage': {'min': 0, 'max': 18},
            'cold_hpiv_closing_response': {'min': 0, 'max': 20},
            'cold_hpiv_hold_power': {'min': None, 'max': None},
            'cold_hpiv_opening_response': {'min': 0, 'max': 20},
            'cold_hpiv_opening_power': {'min': None, 'max': None},
            'cold_hpiv_inductance': {'min': None, 'max': None},
            'cold_tv_inductance': {'min': None, 'max': None},
            'cold_hpiv_resistance': {'min': None, 'max': None},
            'cold_tv_pt_resistance': {'min': None, 'max': None},
            'cold_tv_resistance': {'min': 150-0.1*150, 'max': 150+0.1*150, 'nominal': 150, 'tolerance': 10},
            'cold_lpt_resistance': {'min': None, 'max': None},
            'cold_tv_high_leak': {'min': 0, 'max': 1e-5},
            'cold_tv_low_leak': {'min': 0, 'max': 1e-5},
            'cold_tv_low_leak_open': {'min': None, 'max': None},
            'cold_hpiv_high_leak': {'min': 0, 'max': 1e-5},
            'cold_hpiv_low_leak': {'min': 0, 'max': 1e-5},
            'hot_hpiv_dropout_voltage': {'min': 0, 'max': 4},
            'hot_hpiv_pullin_voltage': {'min': 0, 'max': 18},
            'hot_hpiv_closing_response': {'min': 0, 'max': 20},
            'hot_hpiv_hold_power': {'min': None, 'max': None},
            'hot_hpiv_opening_response': {'min': 0, 'max': 20},
            'hot_hpiv_opening_power': {'min': None, 'max': None},
            'hot_hpiv_inductance': {'min': None, 'max': None},
            'hot_tv_inductance': {'min': None, 'max': None},
            'hot_hpiv_resistance': {'min': None, 'max': None},
            'hot_tvpt_resistance': {'min': None, 'max': None},
            'hot_tv_resistance': {'min': 150-0.1*150, 'max': 150+0.1*150, 'nominal': 150, 'tolerance': 10},
            'hot_lpt_resistance': {'min': None, 'max': None},
            'hot_tv_pt_resistance': {'min': None, 'max': None},
            'hot_tv_high_leak': {'min': 0, 'max': 1e-5},
            'hot_tv_low_leak': {'min': 0, 'max': 1e-5},
            'hot_tv_low_leak_open': {'min': None, 'max': None},
            'hot_hpiv_high_leak': {'min': 0, 'max': 1e-5},
            'hot_hpiv_low_leak': {'min': 0, 'max': 1e-5},
            'tv_high_leak': {'min': 0, 'max': 1e-5},
            'tv_low_leak': {'min': 0, 'max': 1e-5},
            'hpiv_high_leak': {'min': 0, 'max': 1e-5},
            'hpiv_low_leak': {'min': 0, 'max': 1e-5},
            'inlet_location': {'min': [-23.2, -88.45, 11.6], 'max': [-22.4, -87.75, 12.0]},
            'outlet_anode': {'min': [47.65, 24.6, 11.4], 'max': [49.35, 26.4, 12.2]},
            'outlet_cathode': {'min': [25.55, 24.6, 11.4], 'max': [27.25, 26.4, 12.2]},
            'fms_envelope': {'min': [117.0, 141.4, 25.3], 'max': [119.0, 143.4, 27.3]},
            'tv_housing_bonding': {'min': 0, 'max': 5},
            'bonding_tv_housing': {'min': 0, 'max': 5},
            'tv_housing_hpiv': {'min': 0, 'max': 5},
            'hpiv_housing_tv': {'min': 0, 'max': 5},
            'lpt_housing_bonding': {'min': 0, 'max': 5},
            'bonding_lpt_housing': {'min': 0, 'max': 5},
            'j01_bonding': {'min': 0, 'max': 30},
            'bonding_j01': {'min': 0, 'max': 30},
            'j02_bonding': {'min': 0, 'max': 30},
            'bonding_j02': {'min': 0, 'max': 30},
            'j01_pin_bonding': {'min': 0, 'max': 30},
            'bonding_j01_pin': {'min': 0, 'max': 30},
            'j02_pin_bonding': {'min': 0, 'max': 30},
            'bonding_j02_pin': {'min': 0, 'max': 30},
            'lpt_psig': {'min': 10e6, 'max': None},
            'lpt_psig_rtn': {'min': 10e6, 'max': None},
            'iso_lpt_tsig': {'min': 10e6, 'max': None},
            'iso_lpt_tsig_rtn': {'min': 10e6, 'max': None},
            'lpt_power': {'min': 10e6, 'max': None},
            'lpt_power_rtn': {'min': 10e6, 'max': None},
            'iso_pt_sgn': {'min': 10e6, 'max': None},
            'iso_pt_sgn_rtn': {'min': 10e6, 'max': None},
            'tv_power': {'min': 10e6, 'max': None},
            'tv_power_rtn': {'min': 10e6, 'max': None},
            'hpiv_power': {'min': 10e6, 'max': None},
            'hpiv_power_rtn': {'min': 10e6, 'max': None},
            'cap_lpt_tsig': {'min': 0, 'max': 50},
            'cap_lpt_tsig_rtn': {'min': 0, 'max': 50},
            'cap_pt_sgn': {'min': 0, 'max': 50},
            'cap_pt_sgn_rtn': {'min': 0, 'max': 50},
            'lpt_resistance': {'min': 3442-0.1*3442, 'max': 3442+0.1*3442, 'nominal': 3442, 'tolerance': 10},
            'tv_resistance': {'min': 150-0.1*150, 'max': 150+0.1*150, 'nominal': 150, 'tolerance': 10},
            'tv_pt_resistance': {'min': None, 'max': None},
            'hpiv_resistance': {'min': 43.3-0.1*43.3, 'max': 43.3+0.1*43.3, 'nominal': 43.3, 'tolerance': 10},
            'hpiv_opening_power': {'min': None, 'max': None},
            'hpiv_opening_response': {'min': 0, 'max': 20},
            'hpiv_hold_power': {'min': None, 'max': None},
            'hpiv_closing_response': {'min': 0, 'max': 20},
            'hpiv_pullin_voltage': {'min': 0, 'max': 18},
            'hpiv_dropout_voltage': {'min': 0, 'max': 4},
            'low_pressure_ext_leak': {'min': 0, 'max': 1e-6},
            'high_pressure_ext_leak_low': {'min': 0, 'max': 1e-6},
            'high_pressure_ext_leak_high': {'min': 0, 'max': 1e-6},
        }

    def get_tvac_parameter(self, base_param: str, tvac_label: str) -> str:
        """Helper function to get the appropriate parameter name based on TVAC label"""
        # Map base parameters to their TVAC variants
        param_mapping = {
            FMSMainParameters.HPIV_LOW_LEAK.value: {
                'hot': FMSMainParameters.HOT_HPIV_LOW_LEAK.value,
                'cold': FMSMainParameters.COLD_HPIV_LOW_LEAK.value,
                'room': FMSMainParameters.ROOM_HPIV_LOW_LEAK.value
            },
            FMSMainParameters.HPIV_HIGH_LEAK.value: {
                'hot': FMSMainParameters.HOT_HPIV_HIGH_LEAK.value,
                'cold': FMSMainParameters.COLD_HPIV_HIGH_LEAK.value,
                'room': FMSMainParameters.ROOM_HPIV_HIGH_LEAK.value
            },
            FMSMainParameters.TV_LOW_LEAK.value: {
                'hot': FMSMainParameters.HOT_TV_LOW_LEAK.value,
                'cold': FMSMainParameters.COLD_TV_LOW_LEAK.value,
                'room': FMSMainParameters.ROOM_TV_LOW_LEAK.value
            },
            FMSMainParameters.TV_HIGH_LEAK.value: {
                'hot': FMSMainParameters.HOT_TV_HIGH_LEAK.value,
                'cold': FMSMainParameters.COLD_TV_HIGH_LEAK.value,
                'room': FMSMainParameters.ROOM_TV_HIGH_LEAK.value
            },
            FMSMainParameters.HPIV_OPENING_POWER.value: {
                'hot': FMSMainParameters.HOT_HPIV_OPENING_POWER.value,
                'cold': FMSMainParameters.COLD_HPIV_OPENING_POWER.value,
                'room': FMSMainParameters.ROOM_HPIV_OPENING_POWER.value
            },
            FMSMainParameters.HPIV_OPENING_RESPONSE.value: {
                'hot': FMSMainParameters.HOT_HPIV_OPENING_RESPONSE.value,
                'cold': FMSMainParameters.COLD_HPIV_OPENING_RESPONSE.value,
                'room': FMSMainParameters.ROOM_HPIV_OPENING_RESPONSE.value
            },
            FMSMainParameters.HPIV_HOLD_POWER.value: {
                'hot': FMSMainParameters.HOT_HPIV_HOLD_POWER.value,
                'cold': FMSMainParameters.COLD_HPIV_HOLD_POWER.value,
                'room': FMSMainParameters.ROOM_HPIV_HOLD_POWER.value
            },
            FMSMainParameters.HPIV_CLOSING_RESPONSE.value: {
                'hot': FMSMainParameters.HOT_HPIV_CLOSING_RESPONSE.value,
                'cold': FMSMainParameters.COLD_HPIV_CLOSING_RESPONSE.value,
                'room': FMSMainParameters.ROOM_HPIV_CLOSING_RESPONSE.value
            },
            "hpiv_pullin_voltage": {
                'hot': FMSMainParameters.HOT_HPIV_PULLIN_VOLTAGE.value,
                'cold': FMSMainParameters.COLD_HPIV_PULLIN_VOLTAGE.value,
                'room': FMSMainParameters.ROOM_HPIV_PULLIN_VOLTAGE.value
            },
            "hpiv_dropout_voltage": {
                'hot': FMSMainParameters.HOT_HPIV_DROPOUT_VOLTAGE.value,
                'cold': FMSMainParameters.COLD_HPIV_DROPOUT_VOLTAGE.value,
                'room': FMSMainParameters.ROOM_HPIV_DROPOUT_VOLTAGE.value
            },
            FMSMainParameters.HPIV_RESISTANCE.value: {
                'hot': FMSMainParameters.HOT_HPIV_RESISTANCE.value,
                'cold': FMSMainParameters.COLD_HPIV_RESISTANCE.value,
                'room': FMSMainParameters.ROOM_HPIV_RESISTANCE.value
            },
            FMSMainParameters.TV_RESISTANCE.value: {
                'hot': FMSMainParameters.HOT_TV_RESISTANCE.value,
                'cold': FMSMainParameters.COLD_TV_RESISTANCE.value,
                'room': FMSMainParameters.ROOM_TV_RESISTANCE.value
            },
            FMSMainParameters.TV_PT_RESISTANCE.value: {
                'hot': FMSMainParameters.HOT_TV_PT_RESISTANCE.value,
                'cold': FMSMainParameters.COLD_TV_PT_RESISTANCE.value,
                'room': FMSMainParameters.ROOM_TV_PT_RESISTANCE.value
            },
            FMSMainParameters.LPT_RESISTANCE.value: {
                'hot': FMSMainParameters.HOT_LPT_RESISTANCE.value,
                'cold': FMSMainParameters.COLD_LPT_RESISTANCE.value,
                'room': FMSMainParameters.ROOM_LPT_RESISTANCE.value
            },
            FMSMainParameters.HOT_TV_INDUCTANCE.value: {
                'hot': FMSMainParameters.HOT_TV_INDUCTANCE.value,
                'cold': FMSMainParameters.COLD_TV_INDUCTANCE.value,
                'room': FMSMainParameters.ROOM_TV_INDUCTANCE.value
            },
            FMSMainParameters.HOT_HPIV_INDUCTANCE.value: {
                'hot': FMSMainParameters.HOT_HPIV_INDUCTANCE.value,
                'cold': FMSMainParameters.COLD_HPIV_INDUCTANCE.value,
                'room': FMSMainParameters.ROOM_HPIV_INDUCTANCE.value
            }
        }
        
        if base_param in param_mapping and tvac_label in param_mapping[base_param]:
            return param_mapping[base_param][tvac_label]
        
        return base_param
    
    def extract_tvac_from_csv(self) -> list[dict[str, Any]]:
        """
        Extract TVAC cycle data from CSV files and store in functional_test_results.
        Creates a Pandas DataFrame from the CSV files and processes the data.
        Time is normalized so the earliest timestamp across all CSVs starts at 0 seconds.
        """
        self.tvac_df = pd.DataFrame()
        start_times = []

        for csv_file in self.csv_files:
            df = pd.read_csv(
                csv_file,
                sep=None,
                engine='python',
                encoding='utf-16',
                on_bad_lines='skip'
            )

            if any('name:' in str(col).lower() for col in df.columns):
                df = pd.read_csv(
                    csv_file,
                    sep=None,
                    engine='python',
                    encoding='utf-16',
                    on_bad_lines='skip',
                    skiprows=18
                )

            df.ffill(inplace=True)
            df.drop('Scan', axis=1, inplace=True)

            col_map = {col: self.tvac_map[col] for col in df.columns if col in self.tvac_map}
            df = df[list(col_map.keys())]
            df.rename(columns=col_map, inplace=True)

            time_col = FMSTvacParameters.TIME.value
            df[time_col] = pd.to_datetime(df[time_col].str.replace(r'(?<=\d{2}:\d{2}:\d{2}):', '.', regex=True))

            start_times.append(df[time_col].iloc[0])
            self.tvac_df = pd.concat([self.tvac_df, df], ignore_index=True)

        # Normalize time relative to the earliest timestamp across all CSVs
        t0 = min(start_times)
        self.tvac_df[time_col] = (self.tvac_df[time_col] - t0).dt.total_seconds()

        # Determine test_id based on last CSV file name
        base_name = os.path.basename(self.csv_files[-1])
        date_match = re.search(r'(\d{1,2}_\d{1,2}_\d{4})', base_name)
        time_match = re.findall(r'(\d{1,2}_\d{1,2}_\d{1,2})', base_name)[-1]

        if date_match and time_match:
            raw_string = f"{date_match.group(1)}_{time_match}"
            dt = datetime.strptime(raw_string, "%m_%d_%Y_%H_%M_%S")
            self.test_id = dt.strftime("%Y_%m_%d_%H-%M-%S")
        else:
            self.test_id = base_name

        self.functional_test_results = self.tvac_df.to_dict(orient='records')

        return self.functional_test_results

    def preprocess_flow_dataframe(self, trial: int, df: pd.DataFrame) -> pd.DataFrame:
        """
        Preprocess the flow test DataFrame by cleaning column names and filtering to expected columns.
        Args:
            trial (int): Trial number for parsing attempts.
            df (pd.DataFrame): DataFrame to preprocess.
        Returns:
            pd.DataFrame: Preprocessed DataFrame.
        """
        expected_columns = [
            "Logtime [s]", "Tu [-]", "Ku [-]", "Heater Proportional Gain [-]",
            "Heater Integral Gain [1/s]", "Closed Loop Setpoint [degC]",
            "LPT Voltage [mV]", "LPT Pressure [barA]",
            "Bridge Voltage [mV]/Resistance [ohm]", "LPT Temperature [degC]",
            "Duty Cycle 2 [%]", "Duty Cycle [%]", "Closed Loop Setpoint [barA]",
            "Inlet Pressure [barG]", "PC1 Pressure [barA]",
            "PC1 Pressure Setpoint [barA]", "PC3 Pressure [barA]",
            "PC3 Pressure Setpoint [barA]", "Anode Pressure [barA]",
            "Anode Temperature [degC]", "Anode Mass Flow [mg/s]",
            "Cathode Pressure [barA]", "Cathode Temperature [degC]",
            "Cathode Mass Flow [mg/s]", "Anode-to-Cathode Ration [-]",
            "Vacuum Pressure [mbar]", "TV PT1000 [degC]",
            "Anode Estimated Flow Rate [mg/s]", "Cathode Estimated Flow Rate [mg/s]",
            "AC Gas Select [Kr=17, Xe=18]", "Filtered LPT Temperature [degC]",
            "HPIV Status [Open [1]/Closed [0]]", "TV Power [W]",
            "TV Voltage [Vrms]", "TV Current [Irms]", "Total Mass Flow [mg/s]",
            "Average TV Power [W]"
        ]
        first_col_name = df.columns[0]
        second_col_name = df.columns[1]
        if any('unnamed' in i.lower() for i in df.columns):
            df.drop(columns=[first_col_name], inplace=True)
            df.rename(columns={second_col_name: first_col_name}, inplace=True)
        if len(df.columns) > 37:
            df = df.iloc[:, :37]
        # if self.test_type == "fr_characteristics":
        #     if trial == 0:
        #         self.test_parameter_names.remove(FMSFlowTestParameters.AVG_TV_POWER.value)
        #         expected_columns.remove("Average TV Power [W]")

        # Clean column names: strip whitespace, tabs, commas
        df.columns = df.columns.str.replace(r'[\t\n\r\f\v]', '', regex=True)
        df.columns = df.columns.str.strip().str.rstrip(',')
        # Filter to expected columns
        df = df[[col for col in df.columns if col in expected_columns]]
        return df

    def extract_flow_data(self, separation: str = '\t', trial: int = 0) -> None:
        """
        Extracts the relevant test data from FMS flow tests.
        Creates a Pandas DataFrame from the raw xls file and processes the data,
        converts the dataframe to functional_test_results attribute.
        Args:
            separation (str): Separator used in the CSV file.
            trial (int): Trial number for parsing attempts.
        """
        # Load and preprocess raw data
        df = self._load_csv_file(separation)
        self.test_id = os.path.basename(self.flow_test_file).split('_LP_')[0]
        
        # Preprocess and validate dataframe
        df = self._preprocess_and_validate_dataframe(df, trial, separation)
        if df is None:  # Retry with different separator
            return
        
        # Extract column mapping and units
        df = self._map_columns_and_extract_units(df)
        
        # Filter to required columns
        df = self._filter_required_columns(df, trial, separation)
        if df is None:  # Retry with different separator
            return
        
        df = self._clean_and_prepare_data(df)
        
        df = self._trim_to_valid_test_region(df)
        
        self.functional_test_results = df.to_dict(orient='records')

        self._extract_test_conditions(df)

        self.df = df
        self._process_by_test_type(df)


    def _load_csv_file(self, separation: str) -> pd.DataFrame:
        """Load CSV file with appropriate separator."""
        if separation is None:
            return pd.read_csv(self.flow_test_file, sep=None, engine='python', skiprows=1)
        else:
            return pd.read_csv(self.flow_test_file, sep=separation, skiprows=1)


    def _preprocess_and_validate_dataframe(self, df: pd.DataFrame, trial: int, 
                                        separation: str) -> pd.DataFrame:
        """Preprocess dataframe with initial cleaning."""
        df = self.preprocess_flow_dataframe(trial, df)
        df.drop(df.index[0], inplace=True)
        df.ffill(inplace=True)
        df.dropna(axis=1, how='all', inplace=True)
        return df


    def _map_columns_and_extract_units(self, df: pd.DataFrame) -> pd.DataFrame:
        """Map column names to standard parameters and extract units."""
        param_map = {}
        self.units = {}
        df.columns = df.columns.str.strip().str.rstrip(',')
        
        for idx, col in enumerate(list(df.columns)):
            match = re.search(r'(?P<param>.*?)\s*\[(?P<unit>[^\]]+)\]', col)
            if match:
                unit = match.group('unit').strip()
                self.units[self.test_parameter_names[idx]] = unit
                param_map[col] = self.test_parameter_names[idx]
        
        df.rename(columns=param_map, inplace=True)
        return df


    def _filter_required_columns(self, df: pd.DataFrame, trial: int, 
                                separation: str) -> pd.DataFrame | None:
        """Filter dataframe to only required columns, retry with different separator if needed."""
        fms = FMSFlowTestParameters
        keep_cols = [
            fms.LOGTIME.value, fms.AVG_TV_POWER.value, fms.TOTAL_FLOW.value, 
            fms.TV_CURRENT.value, fms.TV_VOLTAGE.value, fms.TV_POWER.value,
            fms.CLOSED_LOOP_PRESSURE.value, fms.TV_PT1000.value, 
            fms.CATHODE_FLOW.value, fms.ANODE_FLOW.value, fms.INLET_PRESSURE.value, 
            fms.PC3_SETPOINT.value, fms.CATHODE_PRESSURE.value, fms.ANODE_PRESSURE.value, 
            fms.LPT_PRESSURE.value, fms.LPT_VOLTAGE.value, fms.LPT_TEMP.value
        ]
        
        if all(col in df.columns for col in keep_cols):
            return df[keep_cols]
        else:
            print("Not all columns found, trying another separator.")
            trials = [None, ',']
            trial = trial + 1
            if trial >= len(trials):
                raise ValueError("Could not parse the flow test file with expected columns.")
            separation = trials[trial - 1]
            self.extract_flow_data(separation=separation, trial=trial + 1)
            return None


    def _clean_and_prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Convert numeric columns and prepare data types."""
        fms = FMSFlowTestParameters
        
        for col in df.columns:
            if col != fms.LOGTIME.value:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df


    def _trim_to_valid_test_region(self, df: pd.DataFrame) -> pd.DataFrame:
        """Trim dataframe to valid test region based on closed loop pressure."""
        fms = FMSFlowTestParameters
        clp = df[fms.CLOSED_LOOP_PRESSURE.value].to_numpy()
        
        window = 90
        valid_start_indices = np.where(
            np.convolve((clp >= 1).astype(int), np.ones(window, dtype=int), mode="valid") == window
        )[0]
        
        if len(valid_start_indices) > 0:
            start_idx = max(valid_start_indices[0] - 40, 0)
            df = df.iloc[start_idx:].reset_index(drop=True)
        
        # Reset logtime to start from zero
        df[fms.LOGTIME.value] = df[fms.LOGTIME.value] - df[fms.LOGTIME.value].iloc[0]
        
        return df

    def _extract_test_conditions(self, df: pd.DataFrame) -> None:
        """Extract test conditions: pressures, temperature, and adjust test type."""
        fms = FMSFlowTestParameters
        
        # Extract pressures
        self.outlet_pressure = float(df[fms.PC3_SETPOINT.value].iloc[0]) * 1000
        mean_inlet_pressure = df[fms.INLET_PRESSURE.value].mean()
        self.inlet_pressure = round(mean_inlet_pressure / 10) * 10
        self.inlet_pressure = 10 if self.inlet_pressure < 100 else 190
        
        # Extract and classify temperature
        raw_temperature = df[fms.LPT_TEMP.value].mean()
        self._classify_temperature(raw_temperature)
        
        # Adjust test type based on inlet pressure
        self._adjust_test_type_for_pressure()


    def _classify_temperature(self, raw_temperature: float) -> None:
        """Classify temperature into cold/room/hot categories."""
        temperature_check = [-15, 22, 70]
        temperature_types = [FunctionalTestType.COLD, FunctionalTestType.ROOM, FunctionalTestType.HOT]
        
        closest_idx = np.argmin([abs(raw_temperature - t) for t in temperature_check])
        self.temperature = temperature_check[closest_idx]
        self.temperature_type = temperature_types[closest_idx]


    def _adjust_test_type_for_pressure(self) -> None:
        """Adjust test type name based on inlet pressure (high/low)."""
        if self.test_type == 'fr_characteristics':
            return
        
        if self.inlet_pressure > 100:
            self.test_type = 'high_' + self.test_type
        elif self.inlet_pressure < 100:
            self.test_type = 'low_' + self.test_type


    def _process_by_test_type(self, df: pd.DataFrame) -> None:
        """Process data based on specific test type requirements."""
        if self.test_type.endswith('slope') or self.test_type.endswith("open_loop"):
            self._process_slope_or_open_loop_test(df)
        elif self.test_type == 'fr_characteristics':
            self._process_fr_characteristics_test()
        elif self.test_type.endswith("closed_loop"):
            self._process_closed_loop_test(df)
        else:
            self.tv_slope = None


    def _process_slope_or_open_loop_test(self, df: pd.DataFrame) -> None:
        """Process slope or open loop test data."""
        
        # Extract TV power increase points
        self._extract_tv_power_data(df)
        
        # Calculate slope if this is a slope test
        if 'slope' in self.test_type:
            self._calculate_slopes(df)
        else:
            self.tv_slope = None


    def _extract_tv_power_data(self, df: pd.DataFrame) -> None:
        """Extract TV power and time data where power is increasing."""
        fms = FMSFlowTestParameters
        
        increasing_indices = [
            i for i in range(len(df) - 1) 
            if df[fms.AVG_TV_POWER.value].iloc[i + 1] > df[fms.AVG_TV_POWER.value].iloc[i]
        ][50:]
        
        self.tv_powers = [df[fms.AVG_TV_POWER.value].iloc[i] for i in increasing_indices]
        self.tv_times = [df[fms.LOGTIME.value].iloc[i] for i in increasing_indices]


    def _calculate_slopes(self, df: pd.DataFrame) -> None:
        """Calculate TV slope and flow-power slope."""
        fms = FMSFlowTestParameters
        
        # Calculate TV slope (power vs time)
        self.tv_slope = np.mean(np.diff(self.tv_powers) / np.diff(self.tv_times)) * 60
        
        # Calculate flow-power slope
        flows = df[fms.TOTAL_FLOW.value].to_numpy()
        powers = df[fms.AVG_TV_POWER.value].to_numpy()
        self.flow_power_slope = self.get_flow_power_slope(flows, powers)
        
        # Calculate slope correction factor
        mean_inlet_pressure = df[fms.INLET_PRESSURE.value].mean()
        self.slope_correction = self.inlet_pressure / mean_inlet_pressure


    def _process_fr_characteristics_test(self) -> None:
        """Process flow rate characteristics test data."""
        self.group_by_lpt_pressures()
        self.functional_test_results = self.df.to_dict(orient='records')


    def _process_closed_loop_test(self, df: pd.DataFrame) -> None:
        """Process closed loop test data."""
        self.response_times, self.response_regions = self.get_response_times(df=df)

    def get_flow_power_slope(self, flows: list[float], powers: list[float], num_points: int = 3000) -> dict:
        """
        Calculate the flow-power slope for specified ranges of flow rates.
        Args:
            flows (list[float]): List of flow rate values.
            powers (list[float]): List of power values.
            num_points (int): Number of points for smoothing.
        Returns:
            dict: A dictionary containing smoothed power and flow values, slopes, and intercepts for 1-2 mg/s and 2-4 mg/s ranges.
        """
        mask = powers > 0.2
        flows = flows[mask]
        powers = powers[mask]

        def get_region(flow_vals: np.ndarray, power_vals: np.ndarray, lower_bound: float, upper_bound: float) -> tuple[np.ndarray, np.ndarray]:
            below_idx = np.where(flow_vals < lower_bound)[0]
            above_idx = np.where(flow_vals > upper_bound)[0]

            if len(below_idx) == 0:
                start_idx = 0
            else:
                start_idx = below_idx[-1]

            if len(above_idx) == 0:
                end_idx = len(flow_vals) - 1
            else:
                end_idx = above_idx[0]

            power_segment = power_vals[start_idx:end_idx + 1]
            flow_segment = flow_vals[start_idx:end_idx + 1]
            
            flow_segment = np.clip(flow_segment, lower_bound, upper_bound)
            
            return power_segment, flow_segment

        def smooth_and_slope(power_segment: np.ndarray, flow_segment: np.ndarray) -> tuple[np.ndarray, np.ndarray, float, float]:
            if len(power_segment) < 2 or len(flow_segment) < 2:
                return np.array([]), np.array([]), 0, 0

            interp_func = interp1d(power_segment, flow_segment, kind='linear', fill_value="extrapolate")
            power_smooth = np.linspace(power_segment.min(), power_segment.max(), num_points)
            flow_smooth = interp_func(power_smooth)

            model = LinearRegression()
            model.fit(power_smooth.reshape(-1, 1), flow_smooth)
            slope = model.coef_[0]
            intercept = model.intercept_

            return power_smooth, flow_smooth, slope, intercept

        # 1–2 mg/s
        tv_power_12, total_flows_12 = get_region(flows, powers, 1, 2)
        tv_power_12_smooth, total_flows_12_smooth, slope12, intercept12 = smooth_and_slope(tv_power_12, total_flows_12)

        # 2–4 mg/s
        tv_power_24, total_flows_24 = get_region(flows, powers, 2, 4)
        tv_power_24_smooth, total_flows_24_smooth, slope24, intercept24 = smooth_and_slope(tv_power_24, total_flows_24)

        array_dict = {
            'tv_power_12': tv_power_12_smooth,
            'total_flows_12': total_flows_12_smooth,
            'slope12': slope12,
            'intercept12': intercept12,
            'tv_power_24': tv_power_24_smooth,
            'total_flows_24': total_flows_24_smooth,
            'slope24': slope24,
            'intercept24': intercept24
        }

        return array_dict

    def get_response_times(self, df: pd.DataFrame) -> dict[str, list]:
        """Main orchestrator function."""
        log_time, total_flow, lpt_pressure, tv_power, closed_loop_pressure = self._prepare_interpolated_data(df)
        
        response_times = {}
        response_regions = {}
        
        opening_times, tv_on_time = self._calculate_opening_response(log_time, total_flow, tv_power)
        response_times["opening_time"] = opening_times
        
        # Find closed loop start points for each set point
        cl_start_indices, cl_start_times = self._find_closed_loop_starts(
            log_time, closed_loop_pressure, tv_on_time, opening_times
        )
        
        # Calculate response times for each LPT set point
        self._calculate_setpoint_responses(
            log_time, lpt_pressure, cl_start_indices, cl_start_times,
            response_times, response_regions
        )
        
        return response_times, response_regions


    def _prepare_interpolated_data(self, df: pd.DataFrame) -> tuple:
        """Interpolate data to finer time resolution."""
        total_flow = df[FMSFlowTestParameters.TOTAL_FLOW.value].to_numpy()
        log_time = df[FMSFlowTestParameters.LOGTIME.value].to_numpy()
        lpt_pressure = df[FMSFlowTestParameters.LPT_PRESSURE.value].to_numpy()
        tv_power = df[FMSFlowTestParameters.AVG_TV_POWER.value].to_numpy()
        closed_loop_pressure = df[FMSFlowTestParameters.CLOSED_LOOP_PRESSURE.value].to_numpy()

        fine_time = np.linspace(log_time.min(), log_time.max(), len(log_time) * 100)

        total_flow = np.interp(fine_time, log_time, total_flow)
        lpt_pressure = np.interp(fine_time, log_time, lpt_pressure)
        tv_power = np.interp(fine_time, log_time, tv_power)
        closed_loop_pressure = np.interp(fine_time, log_time, closed_loop_pressure)
        
        return fine_time, total_flow, lpt_pressure, tv_power, closed_loop_pressure


    def _calculate_opening_response(self, log_time: np.ndarray, total_flow: np.ndarray, 
                                    tv_power: np.ndarray) -> tuple[list, float]:
        """Calculate opening time response (tau values)."""
        idx_tv_on = np.argmax(tv_power > 1e-5)
        time_tv_on = log_time[idx_tv_on]

        flow_start = total_flow[idx_tv_on]
        flow_end = self.initial_flow_rate
        delta_flow = flow_end - flow_start
        tau_percentages = np.array([0.632, 0.865, 0.95])

        flow_thresholds = flow_start + tau_percentages * delta_flow
        tau_indices = np.searchsorted(total_flow, flow_thresholds, side="left")
        tau_times = log_time[tau_indices] - time_tv_on
        
        return list(tau_times), time_tv_on


    def _find_closed_loop_starts(self, log_time: np.ndarray, closed_loop_pressure: np.ndarray,
                                tv_on_time: float, opening_times: list) -> tuple[list, list]:
        """Find the start indices and times for each closed loop set point."""
        tolerance = 0.005
        max_look_window = 50000
        tau_percentages = np.array([0.632, 0.865, 0.95])
        
        cl_start_indices = []
        cl_start_times = []
        
        for set_idx, set_point in enumerate(self.lpt_set_points):
            if set_idx == 0:
                # First set point starts after opening response
                start_idx = np.argmin(np.abs(log_time - opening_times[-1]/tau_percentages[-1]))
                cl_start_indices.append(start_idx)
                cl_start_times.append(opening_times[-1]/tau_percentages[-1])
            else:
                # Subsequent set points start when previous set point is reached
                search_start = cl_start_indices[set_idx-1]
                search_end = search_start + max_look_window
                
                cl_pressures = closed_loop_pressure[search_start:search_end]
                filtered_log_time = log_time[search_start:search_end]
                
                mask = (cl_pressures >= set_point - tolerance) & (cl_pressures <= set_point + tolerance)
                times = filtered_log_time[mask]
                
                if len(times) > 0:
                    start_index = np.argmin(np.abs(log_time - times[0]))
                    cl_start_indices.append(start_index)
                    cl_start_times.append(log_time[start_index])
        
        return cl_start_indices, cl_start_times


    def _calculate_setpoint_responses(self, log_time: np.ndarray, lpt_pressure: np.ndarray,
                                    cl_start_indices: list, cl_start_times: list,
                                    response_times: dict, response_regions: dict) -> None:
        """Calculate response times for each LPT set point transition."""
        tolerance = 0.005
        max_look_window = 50000
        tau_percentages = np.array([0.632, 0.865, 0.95])
        
        for set_idx, set_point in enumerate(self.lpt_set_points):
            try:
                cl_start_time = cl_start_times[set_idx]
                cl_start_idx = cl_start_indices[set_idx]
            except IndexError:
                continue
            
            # Determine end of analysis window
            if len(cl_start_indices) == len(self.lpt_set_points):
                cl_end_idx = cl_start_indices[set_idx + 1] if set_idx < len(self.lpt_set_points) - 1 else len(log_time) - 1
            else:
                cl_end_idx = min(cl_start_idx + max_look_window, len(log_time) - 1)
            
            # Find when LPT pressure stabilizes at set point
            lpt_start_time = self._find_stabilization_time(
                lpt_pressure, log_time, cl_start_idx, cl_end_idx, set_point, tolerance
            )
            
            # Generate appropriate key name
            key = self._generate_response_key(set_idx, set_point)
            
            # Calculate tau values
            response_regions[key] = (cl_start_time, lpt_start_time)
            tau_list = self._calculate_tau_values(cl_start_time, lpt_start_time, tau_percentages)
            response_times[key] = tau_list


    def _find_stabilization_time(self, lpt_pressure: np.ndarray, log_time: np.ndarray,
                                start_idx: int, end_idx: int, set_point: float, 
                                tolerance: float) -> float:
        """Find when LPT pressure stabilizes within tolerance of set point."""
        segment = lpt_pressure[start_idx:end_idx + 1]
        difference = np.abs(segment - set_point)

        window = 2500
        smoothed_difference = np.convolve(difference, np.ones(window)/window, mode='valid')

        below_tol = np.where(smoothed_difference < tolerance)[0]

        if len(below_tol) > 0:
            lpt_idx = start_idx + below_tol[0] + (window // 2)
        else:
            lpt_idx = end_idx

        return log_time[lpt_idx]


    def _generate_response_key(self, set_idx: int, set_point: float) -> str:
        """Generate appropriate key name for response time."""
        if set_idx == 0:
            return f"response_time_to_{set_point}_barA"
        elif set_idx == len(self.lpt_set_points) - 1:
            return f"closing_time_to_{set_point}_barA"
        else:
            return f"response_{self.lpt_set_points[set_idx-1]}_to_{set_point}_barA"


    def _calculate_tau_values(self, start_time: float, end_time: float, 
                            tau_percentages: np.ndarray) -> list:
        """Calculate tau time constants as percentages of total response time."""
        total_time = end_time - start_time
        tau_list = [tau * total_time for tau in tau_percentages]
        tau_list.append(total_time)  # Add full response time
        return tau_list

    def group_by_lpt_pressures(self) -> None:
        """
        Groups the flow test DataFrame for FR characteristics by the prescribed LPT pressures.
        """
        tolerance_p = 0.001
        lpt_col = FMSFlowTestParameters.LPT_PRESSURE.value
        voltage_col = FMSFlowTestParameters.LPT_VOLTAGE.value
        flow_col = FMSFlowTestParameters.TOTAL_FLOW.value
        logtime = FMSFlowTestParameters.LOGTIME.value

        grouped_rows = []

        for target_p in self.lpt_pressures:
            mask = (self.df[lpt_col] >= target_p - tolerance_p) & (self.df[lpt_col] <= target_p + tolerance_p)
            subset = self.df.loc[mask].sort_values(logtime).copy()

            if subset.empty or logtime not in subset.columns:
                continue

            max_gap = 1.0  
            time_diff = subset[logtime].diff().fillna(0)
            subset = subset[time_diff <= max_gap]

            if subset.empty:
                continue

            # Take the last 10 seconds
            max_t = subset[logtime].iloc[-1]
            last_10s = subset[subset[logtime] >= max_t - 10]

            if last_10s.empty:
                continue

            avg_row = last_10s.mean(numeric_only=True).copy()
            avg_row[lpt_col] = float(target_p)
            grouped_rows.append(avg_row)

        self.df = pd.DataFrame(grouped_rows).reset_index(drop=True)

        if self.df.empty:
            print("No valid FR test found")
            return

        # self.df['ac_ratio'] = self.df[FMSFlowTestParameters.ANODE_FLOW.value] / self.df[FMSFlowTestParameters.CATHODE_FLOW.value]
        self.intersections = find_intersections(
            self.df[voltage_col].to_numpy(),
            self.df[flow_col].to_numpy(),
            self.lpt_voltages,
            self.min_flow_rates,
            self.max_flow_rates
        )

    def extract_FMS_test_results(self) -> None:
        """
        Extract FMS test results from the provided PDF file and status Excel file.
        Populates the component_serials dictionary and other relevant attributes.
        Instantiates the fms_main_test_results attribute with the extracted data.
        """
        pdf_document = fitz.open(self.pdf_file)
        tvac_state = {'count': 0, 'labels': ['hot', 'cold', 'room']}
        
        for page_number in range(len(pdf_document)):
            page = pdf_document[page_number]
            page_text = page.get_text()
            
            # Process different page types
            if page_number == 0:
                self._extract_project_reference(page_text)
            
            if self._is_test_item_definition_page(page_text):
                self._extract_test_item_definition(page_text)
            
            if self._is_test_results_page(page_text, page_number):
                self._extract_test_results_and_status(page_text)
            
            if self._is_electrical_results_page(page_text, page_number):
                page_number = self._extract_electrical_results_with_next_page(
                    pdf_document, page_number, page_text
                )
            
            if self._is_valve_performance_page(page_text, page_number):
                self.extract_hpiv_performance(page_text.strip().split('\n'))
            
            if self._is_pressure_proof_page(page_text, page_number):
                self.extract_leakage(page_text.strip().split('\n'), search_proof_pressure=True)
                page_number += 5
            
            if self._is_tvac_cycle_page(page_text, page_number):
                page_number = self._process_tvac_cycle(
                    pdf_document, page_number, page_text, tvac_state
                )
            
            if self._is_power_budget_page(page_text, page_number):
                page_number = self._extract_power_budget_multipage(
                    pdf_document, page_number, page_text
                )
        
        # Finalize data
        if self.project_ref:
            self.component_serials["project"] = self.project_ref


    def _extract_project_reference(self, page_text: str) -> None:
        """Extract project reference from first page."""
        local_text = page_text.lower().split('\n')
        project_ref = None
        
        for item in local_text:
            match = re.search(r'\b\d{5}\b', item)
            if match:
                project_ref = int(match.group())
                break
        
        self.project_ref = project_ref


    def _is_test_item_definition_page(self, page_text: str) -> bool:
        """Check if page contains test item definition."""
        return '3. test item definition' in page_text.lower()


    def _extract_test_item_definition(self, page_text: str) -> None:
        """Extract gas type and serial number from test item definition."""
        lines = [line for line in page_text.strip().split('\n')]
        
        for i in range(len(lines)):
            line = lines[i].strip().lower()
            next_line = lines[i + 1].strip().lower() if i + 1 < len(lines) else ""
            
            if line == 'serial number':
                self.gas_type = next_line.split(' ')[-1].replace('(', '').replace(')', '').strip()
                self.try_serial = next_line.split(' ')[0]
                break


    def _is_test_results_page(self, page_text: str, page_number: int) -> bool:
        """Check if page contains test results section."""
        return '6. test results' in page_text.lower() and 5 <= page_number <= 20


    def _extract_test_results_and_status(self, page_text: str) -> None:
        """Extract measurements, serials, and status from test results page."""
        lines = [line for line in page_text.strip().split('\n')]
        
        # Parse measurements and serials
        self.parse_measurements(lines)
        self.component_serials = self.parse_serials(lines)
        
        if self.gas_type:
            self.component_serials['gas_type'] = self.gas_type.capitalize()
        
        # Extract status from Excel file
        self._extract_status_from_excel()


    def _extract_status_from_excel(self) -> None:
        """Extract component status information from status Excel file."""
        status_sheet = openpyxl.load_workbook(self.status_file)
        status_sheet = status_sheet["20025.10.AF"]
        
        for row in status_sheet.iter_rows(min_row=2, min_col=1, max_col=65, values_only=True):
            if all(cell is None for cell in row):
                break
            
            serial_number = row[0][:6] if row[0] else None
            model = row[1]
            review = row[2][:2] if row[2] else None
            
            if serial_number != self.component_serials.get('fms_id', ''):
                continue
            
            # Found matching serial, extract all status info
            self._populate_component_status(row, model, review)
            break


    def _populate_component_status(self, row: tuple, model: str, review: str) -> None:
        """Populate component serials with status information from Excel row."""
        delivered = row[62]
        shipment = row[61]
        rfs = row[64]
        scrap_check = row[63]
        
        # Determine status
        status = self._determine_component_status(delivered, shipment, scrap_check)
        
        # Populate serials
        self.component_serials['model'] = model
        self.component_serials['status'] = status
        self.component_serials['rfs'] = rfs
        self.component_serials['drawing'] = f"20025.10.AF-{review}"


    def _determine_component_status(self, delivered: str, shipment: str, 
                                    scrap_check: str) -> FMSProgressStatus | None:
        """Determine component status based on Excel indicators."""
        if scrap_check and str(scrap_check).lower() == 'scrap':
            return FMSProgressStatus.SCRAPPED
        
        if delivered and delivered.lower() == 'c':
            return FMSProgressStatus.DELIVERED
        
        if shipment and shipment.lower() in ('c', 'i') and not (delivered and delivered.lower() == 'c'):
            return FMSProgressStatus.SHIPMENT
        
        return None


    def _is_electrical_results_page(self, page_text: str, page_number: int) -> bool:
        """Check if page contains electrical results."""
        return 'bonding, isolation and capacitance' in page_text.lower() and page_number >= 5


    def _extract_electrical_results_with_next_page(self, pdf_document, page_number: int, 
                                                page_text: str) -> int:
        """Extract electrical results, combining current and next page if needed."""
        lines = [line for line in page_text.strip().split('\n')]
        
        # Check if next page exists and append its content
        if page_number + 1 < len(pdf_document):
            next_page_text = pdf_document[page_number + 1].get_text()
            if next_page_text:
                next_lines = [line for line in next_page_text.strip().split('\n')]
                lines.extend(next_lines)
                page_number += 1
        
        self.extract_electrical_results(lines)
        return page_number


    def _is_valve_performance_page(self, page_text: str, page_number: int) -> bool:
        """Check if page contains valve performance section."""
        return 'valve performance' in page_text.lower() and 5 <= page_number <= 20


    def _is_pressure_proof_page(self, page_text: str, page_number: int) -> bool:
        """Check if page contains pressure proof section."""
        return 'pressure proof pressure' in page_text.lower() and 5 <= page_number <= 25


    def _is_tvac_cycle_page(self, page_text: str, page_number: int) -> bool:
        """Check if page contains TVAC cycle section."""
        return (
            'tvac cycle' in page_text.lower() 
            and 'health check' not in page_text.lower()
            and 'functional performance' not in page_text.lower()
            and 20 <= page_number <= 55
        )


    def _process_tvac_cycle(self, pdf_document, page_number: int, 
                        page_text: str, tvac_state: dict) -> int:
        """Process TVAC cycle data across multiple pages."""
        if tvac_state['count'] > 2:
            return page_number
        
        lines = [line for line in page_text.strip().split('\n')]
        
        # Combine with next page
        if page_number + 1 < len(pdf_document):
            next_page_text = pdf_document[page_number + 1].get_text()
            if next_page_text:
                next_lines = [line for line in next_page_text.strip().split('\n')]
                lines.extend(next_lines)
        
        # Extract TVAC results with appropriate label
        tvac_label = tvac_state['labels'][tvac_state['count']]
        self.extract_leakage(lines, tvac_label)
        self.extract_hpiv_performance(lines, tvac_label)
        self.extract_electrical_results(lines, tvac_label)
        
        tvac_state['count'] += 1
        return page_number + 2


    def _is_power_budget_page(self, page_text: str, page_number: int) -> bool:
        """Check if page contains power budget section."""
        return 'power budget' in page_text.lower() and page_number >= 40


    def _extract_power_budget_multipage(self, pdf_document, page_number: int, 
                                        page_text: str) -> int:
        """Extract power budget data, combining multiple pages if needed."""
        lines = [line for line in page_text.strip().split('\n')]
        table_count = self._count_power_budget_tables(lines)
        
        # Collect lines from additional pages until we have 3 tables
        while table_count < 3 and page_number + 1 < len(pdf_document):
            next_page_text = pdf_document[page_number + 1].get_text()
            if next_page_text:
                next_lines = [line for line in next_page_text.strip().split('\n')]
                lines.extend(next_lines)
                table_count += 1
                page_number += 1
        
        self.extract_power_budget(lines)
        return page_number


    def _count_power_budget_tables(self, lines: list[str]) -> int:
        """Count number of power budget tables in lines."""
        table_count = 0
        for line in lines:
            if 'table' in line.lower() and 'power budget' in line.lower():
                table_count += 1
        return table_count

    def extract_power_budget(self, lines: list[str]) -> None:
        """
        Extract power budget information from the provided lines of text, adds to fms_main_test_results attribute.
        Args:
            lines (list[str]): List of lines from the PDF page containing power budget information.
        """
        power_dict = {
            'hpiv_hold': '',
            'hpiv_peak': '',
            'tv_steady': '',
            'tv_peak': '',
            'lpt': '',
            'monitoring': '',
            'nominal': '',
            'peak': '',
        }
        table_count = 0
        tvac_index = [FMSMainParameters.POWER_BUDGET_ROOM.value, FMSMainParameters.POWER_BUDGET_HOT.value, FMSMainParameters.POWER_BUDGET_COLD.value]
        key = None
        for idx, line in enumerate(lines[:-3]):

            if 'table' in line.lower() and 'power budget' in line.lower():
               table_count += 1
               key = tvac_index[table_count - 1]
               power_budget = power_dict.copy()
               continue

            if 'hpiv' in line.lower() and 'remarks' in lines[idx-1].lower():
                hold = float(lines[idx + 1].strip().lower())
                peak = float(lines[idx + 2].strip().lower())
                power_budget['hpiv_hold'] = hold
                power_budget['hpiv_peak'] = peak

            if 'tv' in line.lower() and 'steady state' in lines[idx+3].lower():
                steady = float(lines[idx + 1].strip().lower())
                peak = float(lines[idx + 2].strip().lower())
                power_budget['tv_steady'] = steady
                power_budget['tv_peak'] = peak

            if 'lpt' in line.lower() and 'peak' in lines[idx - 1].lower():
                power = float(lines[idx + 1].strip().lower())
                power_budget['lpt'] = power

            if 'initialization' in line.lower() and 'monitoring' in lines[idx - 1].lower():
                power = float(lines[idx + 1].strip().lower())
                power_budget['monitoring'] = power

            if 'nominal operation' in line.lower():
                nominal = float(lines[idx + 1].strip().lower())
                power_budget['nominal'] = nominal

            if 'peak power' in line.lower() and 'steady state' in lines[idx - 1].lower():
                peak = float(lines[idx + 1].strip().lower())
                power_budget['peak'] = peak
                self.fms_main_test_results[key] = power_budget

    def extract_leakage(self, lines: list[str], tvac_label: str = None, 
                    search_proof_pressure: bool = False) -> None:
        """
        Extract leakage test results from the provided lines of text, adds to fms_main_test_results attribute.
        Args:
            lines (list[str]): List of lines from the PDF page containing leakage test results.
            tvac_label (str): Optional label indicating the TVAC condition (e.g., 'hot', 'cold', 'room').
            search_proof_pressure (bool): If True, search for proof pressure values.
        """
        equal_value_tracker = {'value': '='}
        
        for i, line in enumerate(lines):
            line_lower = line.strip().lower()
            
            if search_proof_pressure:
                self._extract_proof_pressures(line_lower, i, lines)
            
            self._extract_lp_fms_leakage(line_lower, i, lines, equal_value_tracker)
            self._extract_hp_fms_leakage(line_lower, i, lines, equal_value_tracker)
            self._extract_hpiv_leakage(line_lower, i, lines, tvac_label, equal_value_tracker)
            self._extract_tv_leakage(line_lower, i, lines, tvac_label, equal_value_tracker)


    def _parse_value_with_comparator(self, val: str, equal_value_tracker: dict) -> float | None:
        """
        Parse a value string that may contain comparison operators (<, >, =).
        Updates equal_value_tracker with the found operator.
        """
        equal_values = ['=', '<', '>']
        equal_value = next((ev for ev in equal_values if ev in val), '=')
        equal_value_tracker['value'] = equal_value
        
        val = val.strip().lower().replace(equal_value, '')
        try:
            return float(val.replace('e', 'E')) if val else None
        except ValueError:
            return None


    def _create_result_dict(self, value: float, unit: str, 
                        equal_value_tracker: dict) -> dict:
        """Create a standardized result dictionary with value, unit, and comparators."""
        equal_value = equal_value_tracker['value']
        return {
            "value": value,
            "unit": unit,
            'lower': equal_value == '<',
            'larger': equal_value == '>',
            'equal': equal_value == '='
        }


    def _extract_proof_pressures(self, line_lower: str, i: int, lines: list[str]) -> None:
        """Extract high and low pressure proof pressure values."""
        if 'high pressure proof pressure' in line_lower:
            match = re.search(r"(\d+(?:\.\d+)?)\s*bara", line_lower)
            if match:
                pressure = float(match.group(1))
                self.fms_main_test_results[FMSMainParameters.HIGH_PROOF_PRESSURE.value] = {
                    "value": pressure,
                    "unit": "barA",
                    'lower': False,
                    'larger': False,
                    'equal': True
                }
        
        elif 'low pressure proof pressure' in line_lower:
            match = re.search(r"(\d+(?:\.\d+)?)\s*bara", line_lower)
            if match:
                pressure = float(match.group(1))
                self.fms_main_test_results[FMSMainParameters.LOW_PROOF_PRESSURE.value] = {
                    "value": pressure,
                    "unit": "barA",
                    'lower': False,
                    'larger': False,
                    'equal': True
                }


    def _extract_lp_fms_leakage(self, line_lower: str, i: int, lines: list[str],
                            equal_value_tracker: dict) -> None:
        """Extract LP FMS low pressure section external leakage."""
        if "lp fms – low pressure section" not in line_lower:
            return
        
        act_val = self._parse_value_with_comparator(lines[i + 3], equal_value_tracker)
        self.fms_main_test_results[FMSMainParameters.LOW_PRESSURE_EXT_LEAK.value] = \
            self._create_result_dict(act_val, "scc/s GHe", equal_value_tracker)


    def _extract_hp_fms_leakage(self, line_lower: str, i: int, lines: list[str],
                            equal_value_tracker: dict) -> None:
        """Extract LP FMS high pressure section external leakage (low and high)."""
        if "lp fms – high pressure section" not in line_lower:
            return
        
        act_val_1 = self._parse_value_with_comparator(lines[i + 6], equal_value_tracker)
        self.fms_main_test_results[FMSMainParameters.HIGH_PRESSURE_EXT_LEAK_LOW.value] = \
            self._create_result_dict(act_val_1, "scc/s GHe", equal_value_tracker)
        
        act_val_2 = self._parse_value_with_comparator(lines[i + 7], equal_value_tracker)
        self.fms_main_test_results[FMSMainParameters.HIGH_PRESSURE_EXT_LEAK_HIGH.value] = \
            self._create_result_dict(act_val_2, "scc/s GHe", equal_value_tracker)


    def _extract_hpiv_leakage(self, line_lower: str, i: int, lines: list[str],
                            tvac_label: str | None, equal_value_tracker: dict) -> None:
        """Extract HPIV leakage at low (10 bara) and high (190 bara) pressures."""
        if "hpiv" not in line_lower:
            return
        
        if "10 bara" in lines[i + 1].lower():
            act_val = self._parse_value_with_comparator(lines[i + 3], equal_value_tracker)
            param_key = self.get_tvac_parameter(
                FMSMainParameters.HPIV_LOW_LEAK.value, tvac_label
            ) if tvac_label else FMSMainParameters.HPIV_LOW_LEAK.value
            
            self.fms_main_test_results[param_key] = {
                "value": act_val,
                "unit": "scc/s GHe"
            }
        
        elif "190 bara" in lines[i + 1].lower():
            act_val = self._parse_value_with_comparator(lines[i + 3], equal_value_tracker)
            param_key = self.get_tvac_parameter(
                FMSMainParameters.HPIV_HIGH_LEAK.value, tvac_label
            ) if tvac_label else FMSMainParameters.HPIV_HIGH_LEAK.value
            
            self.fms_main_test_results[param_key] = {
                "value": act_val,
                "unit": "scc/s GHe"
            }


    def _extract_tv_leakage(self, line_lower: str, i: int, lines: list[str],
                        tvac_label: str | None, equal_value_tracker: dict) -> None:
        """Extract TV leakage at low (10 bara) and high (190 bara) pressures."""
        if "tv" not in line_lower or len(line_lower) >= 10:
            return
        
        if "10 bara" in lines[i + 1].lower():
            self._extract_tv_low_leakage(i, lines, tvac_label, equal_value_tracker)
        
        elif "190 bara" in lines[i + 1].lower():
            self._extract_tv_high_leakage(i, lines, tvac_label, equal_value_tracker)


    def _extract_tv_low_leakage(self, i: int, lines: list[str],
                            tvac_label: str | None, equal_value_tracker: dict) -> None:
        """Extract TV low pressure (10 bara) leakage, including open state if TVAC."""
        act_val = self._parse_value_with_comparator(lines[i + 3], equal_value_tracker)
        param_key = self.get_tvac_parameter(
            FMSMainParameters.TV_LOW_LEAK.value, tvac_label
        ) if tvac_label else FMSMainParameters.TV_LOW_LEAK.value
        
        self.fms_main_test_results[param_key] = {
            "value": act_val,
            "unit": "scc/s GHe"
        }
        
        # Extract open state leakage for TVAC tests
        if tvac_label:
            self._extract_tv_open_leakage(i, lines, tvac_label, "10 bara", "low", equal_value_tracker)


    def _extract_tv_high_leakage(self, i: int, lines: list[str],
                                tvac_label: str | None, equal_value_tracker: dict) -> None:
        """Extract TV high pressure (190 bara) leakage, including open state if TVAC."""
        act_val = self._parse_value_with_comparator(lines[i + 3], equal_value_tracker)
        param_key = self.get_tvac_parameter(
            FMSMainParameters.TV_HIGH_LEAK.value, tvac_label
        ) if tvac_label else FMSMainParameters.TV_HIGH_LEAK.value
        
        self.fms_main_test_results[param_key] = {
            "value": act_val,
            "unit": "scc/s GHe"
        }
        
        # Extract open state leakage for TVAC tests
        if tvac_label:
            self._extract_tv_open_leakage(i, lines, tvac_label, "190 bara", "high", equal_value_tracker)


    def _extract_tv_open_leakage(self, start_idx: int, lines: list[str],
                                tvac_label: str, pressure_str: str, 
                                pressure_type: str, equal_value_tracker: dict) -> None:
        """Extract TV open state leakage by searching forward for pressure marker."""
        line_idx = start_idx + 3
        
        while line_idx < len(lines):
            if pressure_str in lines[line_idx].strip().lower():
                act_val = self._parse_value_with_comparator(lines[line_idx + 2], equal_value_tracker)
                self.fms_main_test_results[f"{tvac_label}_tv_{pressure_type}_leak_open"] = {
                    "value": act_val,
                    "unit": "scc/s GHe"
                }
                break
            line_idx += 1

    def extract_hpiv_performance(self, lines: list[str], tvac_label: str = None) -> None:
        """
        Extract HPIV performance test results from the provided lines of text, adds to fms_main_test_results attribute.
        Args:
            lines (list[str]): List of lines from the PDF page containing HPIV performance test results.
            tvac_label (str): Optional label indicating the TVAC condition (e.g., 'hot', 'cold', 'room').
        """
        for i, line in enumerate(lines):
            line_lower = line.strip().lower()
            
            if "hpiv – opening" in line_lower:
                self._extract_hpiv_opening(i, lines, tvac_label)
            
            elif "hpiv – hold" in line_lower:
                self._extract_hpiv_hold(i, lines, tvac_label)
            
            elif "hpiv - closing" in line_lower:
                self._extract_hpiv_closing(i, lines, tvac_label)
            
            elif self._is_hpiv_pullin_dropout_line(i, line_lower, lines):
                self._extract_hpiv_pullin_dropout(i, lines, tvac_label)


    def _parse_hpiv_value(self, val: str) -> float | None:
        """Parse HPIV value string, handling N/A and dashes."""
        val = val.strip().lower().replace('n/a', '').replace('-', '')
        try:
            return float(val) if val else None
        except ValueError:
            return None


    def _extract_hpiv_opening(self, i: int, lines: list[str], tvac_label: str | None) -> None:
        """Extract HPIV opening power and response time."""
        values = lines[i + 1:i + 7]
        power = self._parse_hpiv_value(values[1])
        response = self._parse_hpiv_value(values[4])
        
        power_key = self.get_tvac_parameter(
            FMSMainParameters.HPIV_OPENING_POWER.value, tvac_label
        ) if tvac_label else FMSMainParameters.HPIV_OPENING_POWER.value
        
        response_key = self.get_tvac_parameter(
            FMSMainParameters.HPIV_OPENING_RESPONSE.value, tvac_label
        ) if tvac_label else FMSMainParameters.HPIV_OPENING_RESPONSE.value
        
        self.fms_main_test_results[power_key] = {
            "value": power, "unit": "W"
        }
        self.fms_main_test_results[response_key] = {
            "value": response, "unit": "ms"
        }


    def _extract_hpiv_hold(self, i: int, lines: list[str], tvac_label: str | None) -> None:
        """Extract HPIV hold power."""
        values = lines[i + 1:i + 7]
        hold_power = self._parse_hpiv_value(values[1])
        
        hold_key = self.get_tvac_parameter(
            FMSMainParameters.HPIV_HOLD_POWER.value, tvac_label
        ) if tvac_label else FMSMainParameters.HPIV_HOLD_POWER.value
        
        self.fms_main_test_results[hold_key] = {
            "value": hold_power, "unit": "W"
        }


    def _extract_hpiv_closing(self, i: int, lines: list[str], tvac_label: str | None) -> None:
        """Extract HPIV closing response time."""
        values = lines[i + 1:i + 7]
        close_resp = self._parse_hpiv_value(values[4])
        
        closing_key = self.get_tvac_parameter(
            FMSMainParameters.HPIV_CLOSING_RESPONSE.value, tvac_label
        ) if tvac_label else FMSMainParameters.HPIV_CLOSING_RESPONSE.value
        
        self.fms_main_test_results[closing_key] = {
            "value": close_resp, "unit": "ms"
        }


    def _is_hpiv_pullin_dropout_line(self, i: int, line_lower: str, lines: list[str]) -> bool:
        """Check if this line contains HPIV pull-in/drop-out data."""
        if "hpiv" not in line_lower:
            return False
        
        # Check if "pull-in" appears 12 lines before
        if i < 12:
            return False
        
        return "pull-in" in lines[i - 12].lower()


    def _extract_hpiv_pullin_dropout(self, i: int, lines: list[str], tvac_label: str | None) -> None:
        """Extract HPIV pull-in and drop-out voltages."""
        pullin = self._parse_hpiv_value(lines[i + 2])
        dropout = self._parse_hpiv_value(lines[i + 5])
        
        pullin_key = self.get_tvac_parameter(
            "hpiv_pullin_voltage", tvac_label
        ) if tvac_label else "hpiv_pullin_voltage"
        
        dropout_key = self.get_tvac_parameter(
            "hpiv_dropout_voltage", tvac_label
        ) if tvac_label else "hpiv_dropout_voltage"
        
        self.fms_main_test_results[pullin_key] = {
            "value": pullin, "unit": "V"
        }
        self.fms_main_test_results[dropout_key] = {
            "value": dropout, "unit": "V"
        }

    def extract_electrical_results(self, lines: list[str], tvac_label: str = None) -> None:
        """
        Extract electrical test results from the provided lines of text, adds to fms_main_test_results attribute.
        Args:
            lines (list[str]): List of lines from the PDF page containing electrical test results.
            tvac_label (str): Optional label indicating the TVAC condition (e.g., 'hot', 'cold', 'room').
        """

        i = 0
        elec_param_map = {
            "tv housing and bonding hole": FMSMainParameters.TV_HOUSING_BONDING.value,
            "bonding hole and tv housing": FMSMainParameters.BONDING_TV_HOUSING.value,
            "tv housing and hpiv housing": FMSMainParameters.TV_HOUSING_HPIV.value,
            "hpiv housing and tv housing": FMSMainParameters.HPIV_HOUSING_TV.value,
            "lpt housing and bonding hole": FMSMainParameters.LPT_HOUSING_BONDING.value,
            "bonding hole and lpt housing": FMSMainParameters.BONDING_LPT_HOUSING.value,
            "j01 connector shell and bonding": FMSMainParameters.J01_BONDING.value,
            "bonding hole and j01 connector": FMSMainParameters.BONDING_J01.value,
            "j02 connector shell and bonding": FMSMainParameters.J02_BONDING.value,
            "bonding hole and j02 connector": FMSMainParameters.BONDING_J02.value,
            "j01 chassis pin and bonding hole": FMSMainParameters.J01_PIN_BONDING.value,
            "bonding hole and j01 chassis pin": FMSMainParameters.BONDING_J01_PIN.value,
            "j02 chassis pin and bonding hole": FMSMainParameters.J02_PIN_BONDING.value,
            "bonding hole and j02 chassis pin": FMSMainParameters.BONDING_J02_PIN.value,
            "isolation: lpt p sig": FMSMainParameters.LPT_PSIG.value,
            "isolation: lpt p sig rtn": FMSMainParameters.LPT_PSIGRTN.value,
            "isolation: lpt t sig": FMSMainParameters.ISO_LPT_TSIG.value,
            "isolation: lpt t sig rtn": FMSMainParameters.ISO_LPT_TSIGRTN.value,
            "isolation: lpt pwr": FMSMainParameters.LPT_PWR.value,
            "isolation: lpt pwr rtn": FMSMainParameters.LPT_PWRRTN.value,
            "isolation: pt1000 sgn": FMSMainParameters.ISO_PT_SGN.value,
            "isolation: pt1000 sgn rtn": FMSMainParameters.ISO_PT_SGNRTN.value,
            "isolation: tv pwr": FMSMainParameters.TV_PWR.value,
            "isolation: tv pwr rtn": FMSMainParameters.TV_PWRRTN.value,
            "isolation: hpiv pwr": FMSMainParameters.HPIV_PWR.value,
            "isolation: hpiv pwr rtn": FMSMainParameters.HPIV_PWRRTN.value,
            "capacitance: lpt t sig": FMSMainParameters.CAP_LPT_TSIG.value,
            "capacitance: lpt t sig rtn": FMSMainParameters.CAP_LPT_TSIGRTN.value,
            "capacitance: pt1000 sgn": FMSMainParameters.CAP_PT_SGN.value,
            "capacitance: pt1000 sgn rtn": FMSMainParameters.CAP_PT_SGNRTN.value,
            "lpt t sig": FMSMainParameters.CAP_LPT_TSIG.value,
            "lpt t sig rtn": FMSMainParameters.CAP_LPT_TSIGRTN.value,
            "pt1000 sgn": FMSMainParameters.CAP_PT_SGN.value,
            "pt1000 sgn rtn": FMSMainParameters.CAP_PT_SGNRTN.value,
            "lpt t": FMSMainParameters.LPT_RESISTANCE.value,
            "tv": FMSMainParameters.TV_RESISTANCE.value,
            "tv pt1000": FMSMainParameters.TV_PT_RESISTANCE.value,
            "hpiv": FMSMainParameters.HPIV_RESISTANCE.value,
            "inductance: tv": FMSMainParameters.HOT_TV_INDUCTANCE.value,
            "inductance: hpiv": FMSMainParameters.HOT_HPIV_INDUCTANCE.value,
        }
        current_section = None
        i = 0
        equal_operators = ['=', '<', '>']
        while i < len(lines):
            line = lines[i].strip().lower()

            # Detect section context
            if "table 6" in line or "bonding" in line:
                current_section = "bonding"
            elif "table 7" in line or "isolation" in line:
                current_section = "isolation"
            elif "table 8" in line or "isolation" in line:
                current_section = "isolation"
            elif "table 9" in line or "capacitance" in line:
                current_section = "capacitance"
            elif "table 10" in line or "resistance" in line:
                current_section = "resistance"
            elif "inductance" in line:
                current_section = "inductance"

            equal_value = '='
            if i + 2 < len(lines):
                item = lines[i].strip()
                limit = lines[i + 1].strip()
                actual = lines[i + 2].strip()

                item_key = self.normalize(item)

                if current_section == "resistance" or current_section == "bonding":
                    lookup_key = item_key
                else:
                    lookup_key = f"{current_section}: {item_key}"

                if lookup_key in elec_param_map:
                    base_param = elec_param_map[lookup_key]
                    param = self.get_tvac_parameter(base_param, tvac_label) if tvac_label is not None else base_param

                    actual_val, unit = self.parse_actual(actual)
                    if "resistance" in param:
                        unit = 'Ohm'

                    if "inductance" in param:
                        unit = 'mH'

                    if any(op in actual for op in equal_operators):
                        equal_value = next((ev for ev in equal_operators if ev in actual), '=')

                    self.fms_main_test_results[param] = {
                        "value": actual_val,
                        "unit": unit,
                        'lower': equal_value == '<',
                        'larger': equal_value == '>',
                        'equal': equal_value == '='
                    }

                    i += 4 
                else:
                    i += 1
            else:
                i += 1

    def parse_tolerance_line(self, line: str) -> tuple[float, float]:
        """
        Parses lines like 'Value = 400 ± 5' or 'Value = 12.5 +/- 0.5' → (395.0, 405.0) or (12.0, 13.0)
        Args:
            line (str): The line containing the value and tolerance.
        Returns:
            tuple[float, float]: A tuple containing the minimum and maximum values.
        """
        match = re.match(r".*=\s*([-+]?\d*\.?\d+)\s*[±+/-]+\s*([\d\.]+)", line)
        if match:
            val, tol = map(float, match.groups())
            return round(val - tol, 3), round(val + tol, 3)
        raise ValueError(f"Invalid tolerance format: {line}")

    def parse_actual_line(self, line: str) -> tuple[float, str]:
        """
        Parses lines like '393.2 g' or '12.0 mm' → (393.2, 'g')
        """
        match = re.match(r"([-+]?\d*\.?\d+)\s*([a-zA-Zμ%]+)?", line.strip())
        if match:
            val, unit = match.groups()
            return float(val), (unit or "").strip()
        raise ValueError(f"Could not parse actual value: {line}")

    def normalize(self, text: str) -> str:
        return re.sub(r"[^a-z0-9]", " ", text.lower()).strip()

    def parse_actual(self, actual_str: str) -> tuple[float | None, str | None]:
        """
        Parses an actual value string to extract the numeric value and unit.
        Args:
            actual_str (str): The actual value string (e.g., "393.2 g").
        Returns:
            tuple[float | None, str | None]: A tuple containing the numeric value and unit, or (None, None) if not applicable.
        """
        if not actual_str or "info only" in actual_str.lower():
            return None, None

        match = re.search(r"([\d.]+)", actual_str)
        value = float(match.group(1)) if match else None

        unit_match = re.search(r"[a-zA-ZΩμnfpk]+", actual_str)
        unit = unit_match.group(0) if unit_match else None

        return value, unit
    
    def parse_measurements(self, lines: list[str]) -> None:
        """
        Parses the measurements section from the provided lines of text and populates the fms_main_test_results attribute.
        Args:
            lines (list[str]): List of lines from the PDF page containing measurements.
        """

        i = 0

        section_to_enum = {
            r"mass": FMSMainParameters.MASS.value,
            r"fluidic inlet location": FMSMainParameters.INLET_LOCATION.value,
            r"fluidic anode outlet location": FMSMainParameters.OUTLET_ANODE.value,
            r"fluidic cathode outlet location": FMSMainParameters.OUTLET_CATHODE.value,
            r"lp fms envelope": FMSMainParameters.FMS_ENVELOPE.value
        }

        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            if "Fluidic" in line:
                title = line
                while not title.lower().endswith("location") and not title.lower().endswith("envelope"):
                    i += 1
                    title += " " + lines[i].strip()
                key = title.strip()
            else:
                key = line.strip()
            
            normalized_key = re.sub(r'[^a-z0-9 ]+', '', key.lower())
            for pattern in section_to_enum:
                if re.search(pattern, normalized_key):
                    matched_key = pattern
                    break
                else:
                    matched_key = None

            if matched_key:
                param_enum = section_to_enum[matched_key]

                if "location" in key.lower() or "envelope" in key.lower():
                    limit_lines = lines[i+1:i+4]
                    actual_lines = lines[i+4:i+7]

                    min_list, max_list, actual_list = [], [], []
                    for lim, act in zip(limit_lines, actual_lines):
                        lim_min, lim_max = self.parse_tolerance_line(lim)
                        min_list.append(lim_min)
                        max_list.append(lim_max)
                        actual_list.append(self.parse_actual_line(act)[0])

                    self.fms_main_test_results[param_enum] = {
                        "value": actual_list,
                        "unit": self.parse_actual_line(actual_lines[0])[1]
                    }

                    i += 9  
                else:

                    actual_val, actual_unit = self.parse_actual_line(lines[i+2])

                    self.fms_main_test_results[param_enum] = {
                        "value": actual_val,
                        "unit": actual_unit
                    }

                    i += 4  
            else:
                i += 1

    def parse_serials(self, lines: list[str]) -> dict[str, str]:
        """
        Parses component serial numbers from the provided lines of text.
        Args:
            lines (list[str]): List of lines from the PDF page containing serial numbers.
        Returns:
            dict[str, str]: A dictionary containing component serial numbers.
        """
        serials = {}
        for i in range(len(lines)):
            line = lines[i].strip().lower()
            next_line = lines[i+1].strip() if i + 1 < len(lines) else ""

            if line == "lp fms" and not next_line.lower().startswith("envelope"):
                serials["fms_id"] = next_line
            elif line == "hpiv" or line == "hpiv*":
                serials["hpiv_id"] = f"VS197-{next_line}"
            elif line == "tv" or line == "tv*":
                serials["tv_id"] = next_line
            elif line == "lpt" or line == "lpt*":
                serials["lpt_id"] = next_line
            elif line == "anode fr" or line == "anode fr*":
                serials["anode_fr_id"] = next_line
            elif line == "cathode fr" or line == "cathode fr*":
                serials["cathode_fr_id"] = next_line

        return serials
    
class FMSLogicSQL(FMSData, FMSListener):
    """
    Base class for FMS SQL logic operations.

    Handles interactions with the database session and FMS data processing.
    Listens for new FMS test result files, chooses the correct handling logic and updates the database accordingly.

    Attributes
    ----------
        Session: 
            SQLAlchemy session for database operations.
        fms: 
            FMS instance for handling FMS-specific operations.
        fr_test_results (dict): 
            Dictionary to store functional test results.
        data_folder (str): 
            Folder path where FMS data files are stored.
        assembly_data (dict): 
            Dictionary to store assembly-related data.
        gas_type (str): 
            Type of gas used in the FMS tests.
        flow_power_slope (dict): 
            Dictionary to store flow power slope data.
        remark (str): 
            Remark or note associated with the FMS tests.
        fms_query: 
            Query object for FMS database operations.
        component_serials (dict): 
            Dictionary to store component serial numbers.
        selected_fms_id: 
            Currently selected FMS ID for processing.
        test_type (str): 
            Type of test being processed.
        fms_listener (FMSListener): 
            Listener instance for monitoring directories for new test results or files.
        component_serials (dict): 
            Dictionary to hold component serial numbers.
        functional_tests_listener 
            (FMSListener): Listener instance for monitoring functional test files.
    
    Methods
    ---------
        listen_for_fms_acceptance_reports(): 
            Listens for new FMS main test result files and processes them.
        listen_to_functional_tests(): 
            Listens for new functional test files and processes them.
        update_flow_test_results(fms_data): 
            Updates flow test results in the database with the FMS data class instance.
        check_test_status(): 
            Checks the status of the FMS in the testing sequence.
        update_fr_characteristics_results(): 
            Updates the test results from the FR characterization in the database.
        update_tvac_cycle_results(fms_data): 
            Updates TVAC cycle test results in the database with the FMS data class instance.
        allocate_components(session, fms_entry, component_dict): 
            Allocates components to the FMS entry in the database, using the current FMS ID.
        convert_FR_id(session, type, fr_id, available_anodes, available_cathodes, fms_id):
            Converts ambiguous FR IDs to the appropriate format based on the type (anode or cathode) and availability.
        fms_assembly_input_field(): 
            Creates UI for FMS assembly data input (might become obsolete).
        calculate_ac_ratio(session, anode_id, cathode_id): 
            Calculates the Anode-Cathode ratio for the given FR IDs.
        add_fms_assembly_data(fms_data): 
            Adds the top-level FMS assembly data to the FMSMain table in the database, based on automatic extraction 
            from the test reports or assembly inputs.
        get_limit_status(parameter_name, value, unit, fms_data): 
            Determines whether a parameter is out of limits.
        update_fms_main_test_results(fms_data): 
            Updates the FMS main test results in the database with the FMS data class instance.
            This can be done automatically from the test reports or directly using input from the FMSTesting class procedure.
        update_limit_database(): 
            Updates the FMSLimits table with specified limits for the parameters of the FMS in acceptance testing.
    """

    def __init__(self, session: "Session", fms: "FMSDataStructure"):
        super().__init__()
        self.Session = session
        self.fms = fms
        self.fms_id = None

    def listen_for_fms_acceptance_reports(self, data_folder: str = 'FMS_data') -> None:
        """
        Starts FMSListener class to listen for new FMS main test result files in the specified data folder.
        Upon detecting a new file, it processes the data and updates the database accordingly.
        """

        data_folder = os.path.join(os.getcwd(), data_folder)
        try:
            self.start_listening(folder = data_folder)
            print(f"Started monitoring FMS data in: {data_folder}")
            while True:
                try:
                    if self.processed:
                        self.extract_FMS_test_results()
                        self.add_fms_assembly_data()
                        self.update_fms_main_test_results()
                        self.stop_listening()
                        break

                except Exception as e:
                    print(f"Error in fms listener loop: {str(e)}")
                    print("Listener will continue monitoring...")
                    traceback.print_exc()
                    
        except KeyboardInterrupt:
            print("Stopping fms test results listener...")
            self.stop_listening()
        except Exception as e:
            print(f"Fatal error in fms test results listener: {str(e)}")
            traceback.print_exc()
            # Try to restart the listener after a brief delay
            time.sleep(5)
            print("Attempting to restart listening")
            self.listen_to_fms_main_results(data_folder=data_folder)

    def listen_to_functional_tests(self, data_folder: str = 'FMS_data') -> None:
        """
        Starts FMSListener class to listen for new functional test files in the specified data folder.
        Upon detecting a new file, it processes the data and updates the database accordingly.
        """
        data_folder = os.path.join(os.getcwd(), data_folder)
        try:
            self.start_listening(folder = data_folder)
            print(f"Started monitoring functional tests data in: {data_folder}\n Drop the xls file in the FMS Data folder on the desktop.")
            while True:
                try:

                    if self.processed:
                        self.extract_flow_data()
                        self.stop_listening()
                        break

                except Exception as e:
                    print(f"Error in functional tests listener loop: {str(e)}")
                    print("Listener will continue monitoring...")
                    traceback.print_exc()

        except KeyboardInterrupt:
            print("Stopping functional tests listener...")
            self.stop_listening()
        except Exception as e:
            print(f"Fatal error in functional tests listener: {str(e)}")
            traceback.print_exc()
            # Try to restart the listener after a brief delay
            time.sleep(5)
            print("Attempting to restart functional tests listener...")
            self.listen_to_functional_tests(data_folder=data_folder)

    def update_flow_test_results(self, flow_test_file: str = "", test_type: str = "") -> None:
        """
        Updates flow test results in the database.
        
        This method processes flow test data and updates the corresponding database entries.
        If no file is provided, it uses the attributes from the listening event.
        
        Args:
            flow_test_file (str, optional): Path to the flow test file to process. 
                If empty, uses the current file attributes. Defaults to "".
            test_type (str, optional): Type of flow test to process. 
                Valid values: "slope", "open_loop", "closed_loop".
                If empty, attempts to infer from filename. Defaults to "".
        
        Raises:
            ValueError: If test_type cannot be inferred from filename and is not provided.
            Exception: If database update fails or file parsing errors occur.
        """
        session = None
        if not hasattr(self, "functional_test_results") or not self.functional_test_results:
            if flow_test_file:
                possible_tests = ["slope", "open_loop", "closed_loop"]
                test_type = next((i for i in possible_tests if i in os.path.basename(flow_test_file)), test_type)
                if not bool(test_type):
                    print("The test type cannot be inferred from the filename, please give the test type as input: ['slope', 'open_loop', 'closed_loop']")
                    return
                self.test_type = test_type
                self.extract_flow_data()
            else:
                print("Either provide the flow test file and optionally the test type or use the 'listen_to_functional_tests' method to extract the flow test results.")
                return
        try:
            session = self._get_session()

            self._ensure_fms_main_entry_exists(session)

            self._prepare_flow_power_slope_data()

            if self.functional_test_results and self.selected_fms_id:
                self._update_or_create_functional_test(session)
                self._update_functional_results(session)
                self.check_test_status()
            
        except Exception as e:
            print(f"Error adding fms test data: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

    def _get_session(self):
        """Get database session, handling both callable and instance cases."""
        try:
            return self.Session()
        except:
            return self.Session

    def _ensure_fms_main_entry_exists(self, session: "Session") -> None:
        """Ensure FMS main entry exists in database, create if not."""
        fms_entry = session.query(FMSMain).filter_by(fms_id=self.selected_fms_id).first()
        
        if not fms_entry:
            self._create_new_fms_main_entry(session)

    def _create_new_fms_main_entry(self, session: "Session") -> None:
        """Create a new FMS main entry in the database."""
        tv_check = session.query(TVStatus).filter_by(allocated=self.selected_fms_id).first()
        max_id = session.query(func.max(FMSMain.id)).scalar() or 0
        
        new_fms = FMSMain(
            fms_id=self.selected_fms_id,
            model='FM',
            status=FMSProgressStatus.TESTING,
            drawing='20025.10.AF-R8',
            gas_type=self.gas_type if self.gas_type else 'Xe',
            id=max_id + 1
        )
        
        if tv_check:
            new_fms.tv_id = tv_check.tv_id
        
        session.add(new_fms)

    def _prepare_flow_power_slope_data(self) -> None:
        """Prepare flow power slope data by removing array fields."""
        if self.flow_power_slope:
            # Remove array fields that shouldn't be stored
            self.flow_power_slope.pop('tv_power_12', None)
            self.flow_power_slope.pop('tv_power_24', None)
            self.flow_power_slope.pop('total_flows_12', None)
            self.flow_power_slope.pop('total_flows_24', None)
        else:
            self.flow_power_slope = {}


    def _update_or_create_functional_test(self, session: "Session") -> None:
        """Update existing functional test entry or create new one."""
        flow_test_entry = session.query(FMSFunctionalTests).filter_by(
            fms_id=self.selected_fms_id, 
            test_id=self.test_id
        ).first()
        
        # Determine if status should be updated
        flow_check = session.query(FMSFunctionalTests).filter_by(
            fms_id=self.selected_fms_id
        ).all()
        status_update = FMSProgressStatus.TESTING if not flow_check else None
        
        # Parse test date
        date = self._parse_test_date()
        
        if flow_test_entry:
            self._update_existing_functional_test(flow_test_entry, date, status_update)
        else:
            self._create_new_functional_test(session, date, status_update)
        
        session.commit()


    def _parse_test_date(self) -> datetime.date:
        """Parse test date from test_id string."""
        try:
            return datetime.strptime(self.test_id, "%Y_%m_%d_%H-%M-%S").date()
        except Exception as e:
            print(f"Error parsing date: {str(e)}")
            return datetime.now().date()


    def _get_test_type_map(self) -> dict:
        """Get mapping of test type strings to enum values."""
        return {
            'high_closed_loop': FunctionalTestType.HIGH_CLOSED_LOOP,
            'high_open_loop': FunctionalTestType.HIGH_OPEN_LOOP,
            'low_closed_loop': FunctionalTestType.LOW_CLOSED_LOOP,
            'low_open_loop': FunctionalTestType.LOW_OPEN_LOOP,
            'low_slope': FunctionalTestType.LOW_SLOPE,
            'high_slope': FunctionalTestType.HIGH_SLOPE,
        }


    def _update_existing_functional_test(self, flow_test_entry: FMSFunctionalTests, 
                                        date: datetime.date, status_update: FMSProgressStatus | None) -> None:
        """Update an existing functional test entry with current data."""
        type_map = self._get_test_type_map()
        
        flow_test_entry.test_type = type_map[self.test_type]
        flow_test_entry.inlet_pressure = self.inlet_pressure
        flow_test_entry.outlet_pressure = self.outlet_pressure
        flow_test_entry.temp_type = self.temperature_type
        flow_test_entry.trp_temp = self.temperature
        flow_test_entry.date = date
        flow_test_entry.gas_type = self.gas_type if self.gas_type else 'Xe'
        flow_test_entry.slope12 = self.flow_power_slope.get('slope12', None)
        flow_test_entry.slope24 = self.flow_power_slope.get('slope24', None)
        flow_test_entry.intercept12 = self.flow_power_slope.get('intercept12', None)
        flow_test_entry.intercept24 = self.flow_power_slope.get('intercept24', None)
        flow_test_entry.response_times = self.response_times
        flow_test_entry.response_regions = self.response_regions
        flow_test_entry.slope_correction = self.slope_correction
        
        # Update FMS main status if applicable
        if status_update:
            self._update_fms_main_status(flow_test_entry.fms_main, status_update)


    def _create_new_functional_test(self, session: "Session", date: datetime.date, 
                                    status_update: FMSProgressStatus | None) -> None:
        """Create a new functional test entry."""
        type_map = self._get_test_type_map()
        
        flow_test_entry = FMSFunctionalTests(
            fms_id=self.selected_fms_id,
            test_id=self.test_id,
            test_type=type_map[self.test_type],
            inlet_pressure=self.inlet_pressure,
            outlet_pressure=self.outlet_pressure,
            temp_type=self.temperature_type,
            trp_temp=self.temperature,
            gas_type=self.gas_type if self.gas_type else 'Xe',
            date=date,
            response_times=self.response_times,
            response_regions=self.response_regions,
            slope_correction=self.slope_correction,
            **self.flow_power_slope
        )
        
        session.add(flow_test_entry)
        session.flush()
        
        # Update FMS main status if applicable
        if status_update:
            self._update_fms_main_status(flow_test_entry.fms_main, status_update)


    def _update_fms_main_status(self, fms_main: FMSMain | None, 
                                status_update: FMSProgressStatus) -> None:
        """Update FMS main status if not in terminal state."""
        if not fms_main:
            return
        
        # Don't update if in terminal states
        terminal_states = {
            FMSProgressStatus.SHIPMENT,
            FMSProgressStatus.DELIVERED,
            FMSProgressStatus.SCRAPPED
        }
        
        if fms_main.status not in terminal_states:
            fms_main.status = status_update


    def _update_functional_results(self, session: "Session") -> None:
        """Update detailed functional test results in database."""
        # Check if results already exist
        characteristics = session.query(FMSFunctionalResults).filter_by(
            test_id=self.test_id
        ).all()
        
        if characteristics:
            print(f"This {self.test_type} test with test ID {self.test_id} has already been registered in the database")
            return
        
        # Insert new results
        self._insert_functional_results(session)
        session.commit()


    def _insert_functional_results(self, session: "Session") -> None:
        """Insert functional test results row by row into database."""
        for row in self.functional_test_results:
            logtime = row.get('logtime', 0)
            
            for param, value in row.items():
                if param == 'logtime':
                    continue

                if self._is_nan_value(value):
                    continue
                
                flow_entry = FMSFunctionalResults(
                    test_id=self.test_id,
                    logtime=logtime,
                    parameter_name=param,
                    parameter_value=value,
                    parameter_unit=self.units[param]
                )
                session.add(flow_entry)


    def _is_nan_value(self, value) -> bool:
        """Check if value is NaN (float NaN or string 'nan')."""
        if isinstance(value, float) and np.isnan(value):
            return True
        if str(value).lower() == "nan":
            return True
        return False

    def check_test_status(self) -> None:
        """
        Checks the status of the FMS in the testing sequence.
        If all flow tests are completed and FR tests are done, updates the status to READY_FOR_TVAC.
        """
        session = None
        try:
            try:
                session = self.Session()
            except:
                session = self.Session
            flow_tests = session.query(FMSFunctionalTests).filter_by(fms_id=self.selected_fms_id).all()
            fr_tests = session.query(FMSFRTests).filter_by(fms_id=self.selected_fms_id).all()
            tvac_tests = session.query(FMSTvac).filter_by(fms_id=self.selected_fms_id).all()
            if flow_tests:
                if all(test_type in [test.test_type for test in flow_tests] for test_type in\
                        [FunctionalTestType.HIGH_CLOSED_LOOP, FunctionalTestType.LOW_CLOSED_LOOP, FunctionalTestType.LOW_SLOPE, FunctionalTestType.HIGH_SLOPE]) and fr_tests and not tvac_tests:
                    fms_main: FMSMain = flow_tests[0].fms_main
                    if fms_main:
                        fms_main.status = FMSProgressStatus.READY_FOR_TVAC if not\
                              (fms_main.status == FMSProgressStatus.SHIPMENT or fms_main.status == FMSProgressStatus.DELIVERED or fms_main.status == FMSProgressStatus.SCRAPPED) else fms_main.status
                    else:
                        fms_main = session.query(FMSMain).filter_by(fms_id=self.selected_fms_id).first()
                        if fms_main:
                            fms_main.status = FMSProgressStatus.READY_FOR_TVAC if not\
                                  (fms_main.status == FMSProgressStatus.SHIPMENT or fms_main.status == FMSProgressStatus.DELIVERED or fms_main.status == FMSProgressStatus.SCRAPPED) else fms_main.status
                    print(f"FMS {self.selected_fms_id} flow tests completed.")

                    session.commit()
            # self.fms.print_table(FMSMain, limit=3)
        except Exception as e:
            print(f"Error checking test status: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()
                    
    def update_fr_characteristics_results(self, flow_test_file: str = "") -> None:
        """
        Updates the FR characterization test results in the database.
        
        Processes FR characteristics flow test data and updates the corresponding database entries.
        If no file is provided, it uses the attributes from the listening event.
        
        Args:
            flow_test_file (str, optional): Path to the FR characteristics test file to process. 
                If empty, uses the current file attributes. Defaults to "".
        
        Raises:
            ValueError: If file parsing errors occur.
            Exception: If database update fails.
        """
        session = None
        if not hasattr(self, "functional_test_results") or not self.functional_test_results:
            if flow_test_file:
                self.flow_test_file = flow_test_file
                self.test_type = "fr_characteristics"
                self.extract_flow_data()
            else:
                print("Either provide the flow_test_file or use the 'listen_to_functional_tests' function to update the fr characteristics test results.")
                return
        try:
            session = self._get_session()
            
            if self.functional_test_results and self.selected_fms_id:
                # Delete existing entry if present
                if not self._check_existing_fr_test(session):
                    return
                
                # Ensure FMS entry exists
                self._ensure_fms_main_entry_exists(session)
                
                # Create and add new FR test entry
                self._create_and_add_fr_test(session)
                
                session.commit()
                self.check_test_status()
                self.fms.print_table(FMSFRTests)
                
        except Exception as e:
            print(f"Error updating FR characteristics results: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

    def _check_existing_fr_test(self, session: "Session") -> bool:
        """Check if the current FR test already exists."""
        fr_check = session.query(FMSFRTests).filter_by(
            fms_id=self.selected_fms_id, 
            test_id=self.test_id
        ).first()
        
        if fr_check:
            print(f"This {self.test_type} test with test ID {self.test_id} has already been registered in the database")
            return False
        return True

    def _create_and_add_fr_test(self, session: "Session") -> None:
        """Create and add new FR test entry to session."""
        # Build update dictionary from functional test results
        update_dict = self._build_fr_update_dict()
        
        # Parse test date
        date = self._parse_test_date()
        
        # Create FR test entry
        fr_entry = FMSFRTests(
            **update_dict,
            gas_type=self.gas_type if self.gas_type else 'Xe',
            fms_id=self.selected_fms_id,
            inlet_pressure=self.inlet_pressure,
            outlet_pressure=self.outlet_pressure,
            test_id=self.test_id,
            trp_temp=self.temperature,
            date=date
        )
        
        session.add(fr_entry)


    def _build_fr_update_dict(self) -> dict:
        """Build dictionary of FR test columns from functional test results."""
        fr_columns = FMSFRTests.__table__.columns.keys()
        
        update_dict = {
            key: [value[key] for value in self.functional_test_results]
            for key in fr_columns
            if key in self.functional_test_results[0]
            and key != FMSFlowTestParameters.INLET_PRESSURE.value
        }
        
        return update_dict

    def update_tvac_cycle_results(self, csv_files: list[str] = None) -> None:
        """
        Updates the TVAC cycle test results in the database using the FMS data class instance.
        This method checks if there are existing functional test results. If not, it attempts to 
        extract TVAC data from the provided CSV files. If no CSV files are provided, it prompts 
        the user to either supply the files or use the 'listen_to_functional_tests' function 
        to update the results.

        Parameters:
            csv_files (list[str], optional): A list of file paths to the CSV files containing 
            TVAC cycle test data. If not provided, the method will attempt to retrieve data 
            from existing functional test results.
        Raises:
            Exception: If an error occurs during the update process, the error message will be 
            printed, and the session will be rolled back if it was initiated.
        """
        session = None
        if not hasattr(self, "functional_test_results") or not bool(self.functional_test_results):
            if csv_files:
                self.csv_files = csv_files
                self.test_type = "tvac_cycle"
                self.extract_tvac_from_csv()
            else:
                print("Either provide the tvac log files in the function or use the 'listen_to_functional_tests' function to update the tvac cycle test results.")
                return
        try:
            session = self._get_session()
            if self.functional_test_results and self.selected_fms_id:
                self._handle_tvac_entries(session)
            # self.fms.print_table(FMSTvac, limit=10)
            # self.fms.print_table(FMSMain, limit=10)

        except Exception as e:
            print(f"Error updating Tvac results: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

    def _handle_tvac_entries(self, session: "Session"):
        if not self._check_existing_tvac_entries(session):
            return
        tvac_entry = self._create_tvac_entry(session)
        self._update_fms_status(session, tvac_entry)
        session.commit()

    def _check_existing_tvac_entries(self, session: "Session"):
        tvac_check = session.query(FMSTvac).filter_by(
            fms_id=self.selected_fms_id, test_id=self.test_id
        ).all()
        if tvac_check:
            print(f"This {self.test_type} test with test ID {self.test_id} has already been registered in the database")
            return False
        return True

    def _create_tvac_entry(self, session: "Session"):
        tvac_columns = FMSTvac.__table__.columns.keys()
        update_dict = {
            key: [value[key] for value in self.functional_test_results]
            for key in tvac_columns if key in self.functional_test_results[0]
        }
        try:
            date = datetime.strptime(self.test_id, "%Y_%m_%d_%H-%M-%S").date()
        except Exception as e:
            print(f"Error parsing date: {str(e)}")
            date = datetime.now().date()

        tvac_entry = FMSTvac(**update_dict, fms_id=self.selected_fms_id,
                            test_id=self.test_id, date=date, remark=self.remark)
        session.add(tvac_entry)
        return tvac_entry

    def _update_fms_status(self, session: "Session"):
        fms_main = session.query(FMSMain).filter_by(fms_id=self.selected_fms_id).first()
        if fms_main and fms_main.status not in [
            FMSProgressStatus.SHIPMENT,
            FMSProgressStatus.DELIVERED,
            FMSProgressStatus.SCRAPPED
        ]:
            fms_main.status = FMSProgressStatus.TVAC_COMPLETED

    def allocate_components(self, session: "Session", fms_entry: FMSMain, component_dict: dict) -> None:
        """
        Allocates components to the specified FMS entry in the database.
        This method retrieves the necessary component IDs from the provided 
        component dictionary and calculates the air conditioning ratios. It 
        then allocates the high-pressure inlet valve (HPIV), television (TV), 
        and manifold to the FMS entry. In case of an error during the allocation 
        process, the session is rolled back to maintain database integrity.

        Parameters:
            session (Session): The database session used for the allocation.
            fms_entry (FMSMain): The FMS entry to which components are being allocated.
            component_dict (dict): A dictionary containing component IDs and other 
                                   relevant data for allocation.
        Raises:
            Exception: If an error occurs during the allocation process, it will 
                       print the error message and traceback, and rollback the session.
        """
        try:
            fms_id = component_dict.get('fms_id')
            calculated_ac_ratio, specified_ac_ratio = self._calculate_ac_ratios(session, component_dict)

            self._allocate_hpiv(session, component_dict.get('hpiv_id'), fms_id)
            self._allocate_tv(session, component_dict.get('tv_id'), fms_id)

            manifold_id = component_dict.get('manifold_id', None)
            self._allocate_manifold(
                session, fms_entry, component_dict, fms_id,
                calculated_ac_ratio, specified_ac_ratio, manifold_id
            )

        except Exception as e:
            print(f"Error allocating components: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

    def _calculate_ac_ratios(self, session: "Session", component_dict: dict):
        anode_fr_id = component_dict.get('anode_fr_id')
        cathode_fr_id = component_dict.get('cathode_fr_id')
        calculated_ac_ratio = self.calculate_ac_ratio(session, anode_fr_id, cathode_fr_id)
        specified_ac_ratio = round(calculated_ac_ratio) if calculated_ac_ratio else None
        return calculated_ac_ratio, specified_ac_ratio


    def _allocate_hpiv(self, session: "Session", hpiv_id: str = "", fms_id: str = ""):
        hpiv = session.query(HPIVCertification).filter_by(hpiv_id=hpiv_id).first()
        if hpiv and hpiv.allocated != fms_id:
            hpiv.allocated = fms_id


    def _allocate_tv(self, session: "Session", tv_id: str = "", fms_id: str = ""):
        tv = session.query(TVStatus).filter_by(tv_id=tv_id).first()
        if tv and tv_id != str(15):
            tv.allocated = fms_id

    def _allocate_manifold(self, session: "Session", fms_entry: FMSMain, manifold: ManifoldStatus, component_dict: dict[str, Any], 
                           fms_id: str = "", calculated_ac_ratio: float = None, specified_ac_ratio: float = None, manifold_id: str = ""):
        """
        Allocate a manifold to an FMS entry and update its associated components.
        This method handles the allocation of a manifold to a specific FMS (Fuel Management System) entry.
        It supports allocation by manifold ID or through lookup chain matching on LPT, anode, and cathode
        components. Updates manifold allocation status and AC ratio values as needed.
        Args:
            session (Session): The database session for querying and updating records.
            fms_entry (FMSMain): The FMS main entry associated with this allocation.
            manifold (ManifoldStatus): The manifold status object to allocate (may be overridden).
            component_dict (dict[str, Any]): Dictionary containing component IDs:
            fms_id (str, optional): The FMS identifier for allocation. Defaults to "".
            calculated_ac_ratio (float, optional): The calculated AC ratio value. Defaults to None.
            specified_ac_ratio (float, optional): The specified AC ratio value. Defaults to None.
            manifold_id (str, optional): Specific manifold ID to allocate. If provided, direct allocation
                is performed. Defaults to "".
        Behavior:
            - If manifold_id is provided: allocates that specific manifold and returns early.
            - If no manifold_id: searches for existing allocation or performs lookup chain matching
                on LPT, anode, and cathode relationships to find and allocate an appropriate manifold.
            - Updates manifold AC ratio values and manifold entries when a match is found.
        """
        lpt_id = component_dict.get('lpt_id')
        anode_fr_id = component_dict.get('anode_fr_id')
        cathode_fr_id = component_dict.get('cathode_fr_id')

        if manifold_id:
            manifold = session.query(ManifoldStatus).filter_by(set_id=manifold_id).first()
            if manifold and manifold.allocated != fms_id:
                manifold.allocated = fms_id
            return

        manifold = session.query(ManifoldStatus).filter_by(allocated=fms_id).first()
        if manifold:
            self._update_manifold_entries(session, fms_entry, manifold, fms_id, lpt_id, anode_fr_id, cathode_fr_id, calculated_ac_ratio, specified_ac_ratio)
        else:
            lookup_chain = [
                (ManifoldStatus.lpt, ManifoldStatus.lpt.any(lpt_id=lpt_id)),
                (ManifoldStatus.anode, ManifoldStatus.anode.any(
                    or_(AnodeFR.allocated.contains(fms_id), AnodeFR.fr_id == anode_fr_id)
                )),
                (ManifoldStatus.cathode, ManifoldStatus.cathode.any(
                    or_(CathodeFR.allocated.contains(fms_id), CathodeFR.fr_id == cathode_fr_id)
                )),
            ]
            for rel, condition in lookup_chain:
                manifold = session.query(ManifoldStatus).join(rel).filter(condition).first()
                if manifold:
                    if manifold.allocated != fms_id:
                        manifold.allocated = fms_id
                        manifold.ac_ratio = calculated_ac_ratio
                        manifold.ac_ratio_specified = specified_ac_ratio
                    self._update_manifold_entries(session, fms_entry, manifold, fms_id, lpt_id, anode_fr_id, cathode_fr_id, calculated_ac_ratio, specified_ac_ratio)
                    break


    def _update_manifold_entries(self, session: "Session", fms_entry: FMSMain, manifold: ManifoldStatus,
                                fms_id: str = "", lpt_id: str = "", anode_fr_id: str = "", cathode_fr_id: str = "", calculated_ac_ratio: float = None, specified_ac_ratio: float = None):
        """
        Update FMS entry and manifold-related component associations.
        This method synchronizes the FMS entry with manifold status and manages the relationship
        between anode, cathode, and LPT components with the manifold. It updates component
        set IDs when they differ from the manifold's set ID and sets AC ratio values accordingly.

        Args:
            session (Session): Database session for querying component data.
            fms_entry (FMSMain): The FMS main entry to be updated.
            manifold (ManifoldStatus): The manifold status containing component references.
            fms_id (str, optional): The FMS identifier. Defaults to "".
            lpt_id (str, optional): The LPT (Low-Pressure Turbine) identifier. Defaults to "".
            anode_fr_id (str, optional): The anode flow regulator identifier. Defaults to "".
            cathode_fr_id (str, optional): The cathode flow regulator identifier. Defaults to "".
            calculated_ac_ratio (float, optional): Calculated anode-cathode ratio value. Defaults to None.
            specified_ac_ratio (float, optional): Specified anode-cathode ratio value. Defaults to None.
        Returns:
            None
        Side Effects:
            - Updates fms_entry.manifold_id, anode_fr_id, and cathode_fr_id
            - Modifies anode, cathode, and LPT component set_id values in the database
            - Updates manifold AC ratio values when components are reassigned
        """
        # Update FMS entry from manifold
        fms_entry.manifold_id = manifold.set_id

        # Anode
        anode_check = manifold.anode
        if anode_check:
            anode_id = anode_check[0].fr_id
            if anode_id != anode_fr_id:
                fms_entry.anode_fr_id = anode_id
        else:
            anode = session.query(AnodeFR).filter(AnodeFR.allocated.contains(fms_id)).first()
            if anode and anode.set_id != manifold.set_id:
                anode.set_id = manifold.set_id
                manifold.ac_ratio = calculated_ac_ratio
                manifold.ac_ratio_specified = specified_ac_ratio

        # Cathode
        cathode_check = manifold.cathode
        if cathode_check:
            cathode_id = cathode_check[0].fr_id
            if cathode_id != cathode_fr_id:
                fms_entry.cathode_fr_id = cathode_id
        else:
            cathode = session.query(CathodeFR).filter(CathodeFR.allocated.contains(fms_id)).first()
            if cathode and cathode.set_id != manifold.set_id:
                cathode.set_id = manifold.set_id
                manifold.ac_ratio = calculated_ac_ratio
                manifold.ac_ratio_specified = specified_ac_ratio

        # LPT
        lpt_check = manifold.lpt
        if lpt_check:
            lpt_id_check = lpt_check[0].lpt_id
            if lpt_id_check != lpt_id:
                fms_entry.lpt_id = lpt_id_check
        else:
            lpt = session.query(LPTCalibration).filter_by(lpt_id=lpt_id).first()
            if lpt and lpt.set_id != manifold.set_id:
                lpt.set_id = manifold.set_id

    def convert_FR_id(
        self, 
        session: "Session", 
        type: str, 
        fr_id: str, 
        available_anodes: list[str] = [], 
        available_cathodes: list[str] = [], 
        fms_id: str = None
    ) -> str:
        """
        Converts an ambiguous FR ID to the correct full FR ID from the database.
        Args:
            session (Session): SQLAlchemy session for database operations.
            type (str): Type of FR ('anode' or 'cathode').
            fr_id (str): Ambiguous FR ID to convert.
            available_anodes (list[str], optional): List of available anode FR IDs. Defaults to [].
            available_cathodes (list[str], optional): List of available cathode FR IDs. Defaults to [].
            fms_id (str, optional): FMS ID to prioritize certain FRs. Defaults to None.
        Returns:
            str: Converted full FR ID or the original FR ID if not found.
        """
        self.converted_ids = []
        start_fms = fms_id.split("-")[0] if fms_id else None
        fr_id = str(fr_id).zfill(3)

        try:
            if type == "anode":
                return self._convert_anode_fr(session, fr_id, available_anodes, start_fms)
            elif type == "cathode":
                return self._convert_cathode_fr(session, fr_id, available_cathodes, start_fms)
            return fr_id
        except Exception as e:
            print(f"Error converting FR ID: {str(e)}")
            traceback.print_exc()
            return None


    def _convert_anode_fr(self, session, fr_id: str, available_anodes: list[str], start_fms: str) -> str:
        # FMS "24" priority
        if start_fms == "24" and available_anodes:
            fr = session.query(AnodeFR).filter(
                ~AnodeFR.fr_id.in_(self.converted_ids),
                AnodeFR.fr_id.in_(available_anodes),
                AnodeFR.fr_id.startswith("C24"),
                AnodeFR.fr_id.endswith(fr_id),
                AnodeFR.flow_rates != None
            ).first()
            if fr:
                self.converted_ids.append(fr.fr_id)
                return fr.fr_id

        # Regular AnodeFR search
        fr = self._search_anode_fr(session, fr_id, available_anodes)
        if fr:
            return fr

        # FRCertification fallback
        fr = self._search_anode_cert(session, fr_id, available_anodes)
        if fr:
            return fr

        return fr_id

    def _convert_cathode_fr(self, session, fr_id: str, available_cathodes: list[str], start_fms: str) -> str:
        # FMS "24" priority
        if start_fms == "24" and available_cathodes:
            fr = session.query(CathodeFR).filter(
                ~CathodeFR.fr_id.in_(self.converted_ids),
                CathodeFR.fr_id.in_(available_cathodes),
                CathodeFR.fr_id.startswith("C24"),
                CathodeFR.fr_id.endswith(fr_id),
                CathodeFR.flow_rates != None
            ).first()
            if fr:
                self.converted_ids.append(fr.fr_id)
                return fr.fr_id

        # Regular CathodeFR search
        fr = self._search_cathode_fr(session, fr_id, available_cathodes)
        if fr:
            return fr

        # FRCertification fallback
        fr = self._search_cathode_cert(session, fr_id, available_cathodes)
        if fr:
            return fr

        return fr_id


    def _search_anode_fr(self, session, fr_id: str, available_anodes: list[str]) -> str | None:
        filters = [~AnodeFR.fr_id.in_(self.converted_ids), AnodeFR.fr_id.endswith(fr_id), AnodeFR.flow_rates != None]
        if available_anodes:
            filters.append(AnodeFR.fr_id.in_(available_anodes))
        fr = session.query(AnodeFR).filter(*filters).first()
        if fr:
            self.converted_ids.append(fr.fr_id)
            return fr.fr_id
        return None


    def _search_anode_cert(self, session, fr_id: str, available_anodes: list[str]) -> str | None:
        filters_cert = [~FRCertification.anode_fr_id.in_(self.converted_ids), FRCertification.anode_fr_id.endswith(fr_id)]
        if available_anodes:
            filters_cert.append(FRCertification.anode_fr_id.in_(available_anodes))
        fr = session.query(FRCertification).filter(*filters_cert).first()
        if fr:
            self.converted_ids.append(fr.anode_fr_id)
            return fr.anode_fr_id
        return None


    def _search_cathode_fr(self, session, fr_id: str, available_cathodes: list[str]) -> str | None:
        filters = [~CathodeFR.fr_id.in_(self.converted_ids), CathodeFR.fr_id.endswith(fr_id), CathodeFR.flow_rates != None]
        if available_cathodes:
            filters.append(CathodeFR.fr_id.in_(available_cathodes))
        fr = session.query(CathodeFR).filter(*filters).first()
        if fr:
            self.converted_ids.append(fr.fr_id)
            return fr.fr_id
        return None


    def _search_cathode_cert(self, session, fr_id: str, available_cathodes: list[str]) -> str | None:
        filters_cert = [~FRCertification.cathode_fr_id.in_(self.converted_ids), FRCertification.cathode_fr_id.endswith(fr_id)]
        if available_cathodes:
            filters_cert.append(FRCertification.cathode_fr_id.in_(available_cathodes))
        fr = session.query(FRCertification).filter(*filters_cert).first()
        if fr:
            self.converted_ids.append(fr.cathode_fr_id)
            return fr.cathode_fr_id
        return None

    def calculate_ac_ratio(self, session: "Session", anode_id: str, cathode_id: str) -> float | None:
        """
        Calculates the Anode to Cathode flow rate ratio for given FR IDs.
        Args:
            session (Session): SQLAlchemy session for database operations.
            anode_id (str): Anode FR ID.
            cathode_id (str): Cathode FR ID.
        Returns:
            float | None: Calculated Anode to Cathode flow rate ratio or None if calculation fails.
        """
        try:
            anode = session.query(AnodeFR).filter_by(fr_id=anode_id).first()
            cathode = session.query(CathodeFR).filter_by(fr_id=cathode_id).first()

            anode_flows = anode.flow_rates if anode else None
            cathode_flows = cathode.flow_rates if cathode else None
            if anode_flows and cathode_flows:
                
                ratio = round(np.mean(np.array(anode_flows) / np.array(cathode_flows)), 2)
                return ratio

        except Exception as e:
            print(f"Error calculating A/C ratio: {str(e)}")
            traceback.print_exc()
            return None

    def add_fms_assembly_data(
        self, 
        report_pdf_file: str = "", 
        assembly_data: dict[str, str] = {}, 
        update_test_results: bool = False
    ) -> None:
        """
        Adds FMS assembly data to the database from test reports or manual assembly input.

        This method processes FMS assembly information and creates/updates FMS main entries in the database.
        Assembly data can be obtained automatically from PDF test reports or provided manually via the 
        assembly_data parameter. If neither source is available, uses attributes from listening events.

        Args:
            report_pdf_file (str, optional): Path to the FMS test report PDF containing assembly data.
                If provided, automatically extracts component serials and test results. Defaults to "".
            assembly_data (dict[str, str], optional): Manual assembly data dictionary containing FMS 
                component information (fms_id, hpiv_id, tv_id, lpt_id, anode_fr_id, cathode_fr_id, etc.).
                Defaults to empty dict.
            update_test_results (bool, optional): If True, automatically updates FMS main test results 
                after extracting from the PDF report. Only used when report_pdf_file is provided. 
                Defaults to False.

        Raises:
            Exception: If database operations fail, the exception is caught, printed, and the session 
                is rolled back to maintain database integrity.

        Side Effects:
            - Creates or updates FMS main entry in the database
            - Allocates components (HPIV, TV, LPT, manifold, anode FR, cathode FR) to the FMS entry
            - Updates component availability status in the database
            - Commits changes to the database upon successful completion

        Note:
            Requires at least one data source: report_pdf_file, assembly_data, or pre-populated 
            component_serials attribute from a listening event.
        """
        session: "Session" | None = None
        try:
            self._prepare_component_serials(report_pdf_file, assembly_data, update_test_results)
            if not self.component_serials and not assembly_data:
                return

            session = self.Session()
            doc_ref: str | None = os.path.basename(self.pdf_file) if self.pdf_file else None
            max_id: int = session.query(func.max(FMSMain.id)).scalar() or 0

            available_anodes, available_cathodes = self._get_available_fr(session)
            if self.component_serials and not assembly_data:
                fms_entry: FMSMain = self._build_fms_entry_from_serials(session, max_id, available_anodes, available_cathodes, doc_ref)
            elif assembly_data:
                fms_entry: FMSMain = self._build_fms_entry_from_assembly(session, max_id)
            
            session.commit()
            self.fms.print_table(FMSMain)

        except Exception as e:
            print(f"Error adding fms assembly data: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()


    def _prepare_component_serials(
        self, 
        report_pdf_file: str, 
        assembly_data: dict[str, str], 
        update_test_results: bool
    ) -> None:
        if not hasattr(self, "component_serials") or not self.component_serials:
            if report_pdf_file and not assembly_data:
                self.pdf_file = report_pdf_file
                self.extract_FMS_test_results()
                if update_test_results:
                    self.update_fms_main_test_results()
            elif not report_pdf_file:
                print(
                    "Either provide the test report pdf file that contains the assembly data or use the "
                    "'listen_for_fms_acceptance_reports' function to obtain the acceptance test results."
                )
                return
        self.component_serials = getattr(self, "component_serials", {})


    def _get_available_fr(
        self, 
        session: "Session"
    ) -> tuple[list[AnodeFR], list[CathodeFR]]:
        available_anodes: list[AnodeFR] = session.query(AnodeFR).filter(AnodeFR.set_id == None).all()
        available_cathodes: list[CathodeFR] = session.query(CathodeFR).filter(CathodeFR.set_id == None).all()
        return available_anodes, available_cathodes


    def _build_fms_entry_from_serials(
        self, 
        session: "Session", 
        max_id: int, 
        available_anodes: list[AnodeFR], 
        available_cathodes: list[CathodeFR], 
        doc_ref: str | None
    ) -> FMSMain:
        anode_ids: list[str] = [a.fr_id for a in available_anodes] if available_anodes else []
        cathode_ids: list[str] = [c.fr_id for c in available_cathodes] if available_cathodes else []

        anode_id: str = self.convert_FR_id(
            session, 'anode', self.component_serials.get('anode_fr_id', ''), 
            available_anodes=anode_ids, fms_id=self.component_serials.get('fms_id', '')
        )
        cathode_id: str = self.convert_FR_id(
            session, 'cathode', self.component_serials.get('cathode_fr_id', ''), 
            available_cathodes=cathode_ids, fms_id=self.component_serials.get('fms_id', '')
        )

        self.component_serials['anode_fr_id'] = anode_id
        self.component_serials['cathode_fr_id'] = cathode_id
        self.component_serials.setdefault('drawing', '20025.10.AF-R8')
        self.component_serials.setdefault('model', 'FM')
        self.component_serials.setdefault('gas_type', 'Xe')

        fms_entry: FMSMain = FMSMain(**self.component_serials, test_doc_ref=doc_ref, id=max_id + 1)
        self.allocate_components(session, fms_entry, self.component_serials)
        session.merge(fms_entry)
        return fms_entry


    def _build_fms_entry_from_assembly(
        self, 
        session: "Session", 
        max_id: int
    ) -> FMSMain:
        fms_entry: FMSMain = FMSMain(
            **self.assembly_data, 
            status=FMSProgressStatus.ASSEMBLY_COMPLETED, 
            id=max_id + 1
        )
        self.allocate_components(session, fms_entry, self.assembly_data)
        session.merge(fms_entry)
        return fms_entry
    
    def get_limit_status(self, parameter_name: str, value: float, unit: str, fms_data: FMSData = None) -> LimitStatus | None:
        """
        Determines the limit status of a parameter value based on predefined limits.
        Args:
            parameter_name (str): Name of the parameter to check.
            value (float): Value of the parameter.
            unit (str): Unit of the parameter value.
            fms_data (FMS_data, optional): FMS data class instance containing limits. Defaults to None.
        Returns:
            LimitStatus | None: Limit status (TRUE, FALSE, ON_LIMIT) or None if no limits are defined.
        """
        limits = fms_data.fms_limits.get(parameter_name, {}) if fms_data else self.fms_listener.fms_data.fms_limits.get(parameter_name, {})
        limit_min = limits.get('min')
        limit_max = limits.get('max')
        if unit == 'GOhm':
            value = value * 1e9  

        if limit_min is None and limit_max is None:
            return None
        if limit_min is not None and value < limit_min:
            return LimitStatus.FALSE
        if limit_max is not None and value > limit_max:
            return LimitStatus.FALSE

        if limit_min is not None and value == limit_min:
            return LimitStatus.ON_LIMIT
        if limit_max is not None and value == limit_max:
            return LimitStatus.ON_LIMIT

        return LimitStatus.TRUE

    def update_fms_main_test_results(self) -> None:
        """
        Updates the FMS main test results in the database.
        """
        automated_entry = False
        test_results: dict[str, dict] = self.fms_main_test_results
        self.component_serials = self.component_serials
        automated_entry = True
        session = None
        try:
            try:
                session = self.Session()
            except:
                session = self.Session
            if not test_results:
                print("No FMS test results to update.")
                return  

            fms_id = self.component_serials.get('fms_id', None)
            if not fms_id:
                print("FMS ID not found in component serials.")
                return
            
            for param, values in test_results.items():
                characteristics = session.query(FMSTestResults).filter_by(
                    fms_id=fms_id, parameter_name = param).all()
                if characteristics:
                    for char in characteristics:
                        session.delete(char)
                    session.commit()

                if param in [FMSMainParameters.POWER_BUDGET_COLD.value, 
                             FMSMainParameters.POWER_BUDGET_HOT.value, 
                             FMSMainParameters.POWER_BUDGET_ROOM.value]:
                    value = values
                    unit = 'W'
                    lower = False
                    equal = True
                    larger = False
                    within_limits = None
                else:
                    value = values.get('value')
                    unit = values.get('unit', None)
                    within_limits = self.get_limit_status(param, value, unit)
                    lower = values.get('lower', False)
                    larger = values.get('larger', False)
                    equal = values.get('equal', True)

                if (isinstance(value, float) and np.isnan(value)) or str(param).lower() == "nan":
                    continue

                characteristic = FMSTestResults(
                    fms_id=fms_id,
                    parameter_name=param,
                    parameter_value=value if isinstance(value, (int, float)) else None,
                    parameter_json=value if isinstance(value, (dict, list)) else None,
                    parameter_unit=unit,
                    within_limits=within_limits,
                    lower=lower,
                    larger=larger,
                    equal=equal,
                    automated_entry=automated_entry
                )
                session.add(characteristic)
            session.commit()
            # self.fms.print_table(FMSTestResults)
        except Exception as e:
            print(f"Error updating fms main test results: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

    def update_limit_database(self) -> None:
        """
        Updates the limit database with the latest FMS limits.
        """
        session: "Session" = self.Session()
        fms_limits = self.fms_limits

        processed_fms_ids = [i.fms_id for i in session.query(FMSMain).all()]
        for fms_id in processed_fms_ids:
            existing = session.query(FMSLimits).filter_by(fms_id = fms_id).first()
            if existing:
                continue
            limits_entry = FMSLimits(
                fms_id=fms_id,
                limits=fms_limits
            )

            session.add(limits_entry)
        session.commit()
        self.fms.print_table(FMSLimits)


if __name__ == "__main__":
    # Example usage
    listener = FMSListener(path="FMS_data")