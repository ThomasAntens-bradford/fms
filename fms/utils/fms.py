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
from typing import TYPE_CHECKING
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

    def __init__(self, path="FMS_data", fms_data: "FMSData" = None):
        """
        Initialize the HPIV data listener.

        Args:
            path (str, optional): Directory path to monitor. Defaults to "FMS_data".
        """
        self.path = path
        self.observer = Observer()
        self.observer.schedule(self, path, recursive=False)
        self.observer.start()
        self.processed = False
        self.csv_files = []
        self._csv_timer = None
        self.test_type = None
        self.fms_data = fms_data


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
                self.fms_data.extract_FMS_test_results()
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
    
    def extract_tvac_from_csv(self) -> None:
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
        # print(self.tvac_df.head())

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
        
        # Clean and prepare data
        df = self._clean_and_prepare_data(df)
        
        # Trim data to valid test region
        df = self._trim_to_valid_test_region(df)
        
        # Store functional test results
        self.functional_test_results = df.to_dict(orient='records')
        
        # Extract test conditions
        self._extract_test_conditions(df)
        
        # Store dataframe and process by test type
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
        listen_to_fms_main_results(): 
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

    def listen_to_fms_main_results(self, data_folder: str = 'FMS_data') -> None:
        """
        Starts FMSListener class to listen for new FMS main test result files in the specified data folder.
        Upon detecting a new file, it processes the data and updates the database accordingly.
        """

        data_folder = os.path.join(os.getcwd(), data_folder)
        try:
            self.fms_listener = FMSListener(data_folder)
            print(f"Started monitoring FMS data in: {data_folder}")
            while True:
                try:
                    time.sleep(1)  # Keep the script running to monitor for new files
                    
                    # Check if listener has processed new data
                    if hasattr(self.fms_listener, 'processed') and self.fms_listener.processed:

                        if hasattr(self.fms_listener, 'fms_data') and self.fms_listener.fms_data:
                            self.fms_test_results = self.fms_listener.fms_data.fms_main_test_results
                            self.component_serials = self.fms_listener.fms_data.component_serials

                            self.add_fms_assembly_data()
                            self.update_fms_main_test_results()
                            self.fms_listener.processed = False  # Reset processed flag

                except Exception as e:
                    print(f"Error in fms listener loop: {str(e)}")
                    print("Listener will continue monitoring...")
                    traceback.print_exc()
                    
        except KeyboardInterrupt:
            print("Stopping fms test results listener...")
            if hasattr(self, 'fms_listener') and self.fms_listener:
                self.fms_listener.observer.stop()
                self.fms_listener.observer.join()
        except Exception as e:
            print(f"Fatal error in fms test results listener: {str(e)}")
            traceback.print_exc()
            # Try to restart the listener after a brief delay
            time.sleep(5)
            print("Attempting to restart fms test results listener...")
            self.listen_to_fms_main_results(data_folder=data_folder)

    def listen_to_functional_tests(self, data_folder: str = 'FMS_data') -> None:
        """
        Starts FMSListener class to listen for new functional test files in the specified data folder.
        Upon detecting a new file, it processes the data and updates the database accordingly.
        """
        data_folder = os.path.join(os.getcwd(), data_folder)
        print(data_folder)
        try:
            self.functional_tests_listener = FMSListener(data_folder)
            print(f"Started monitoring functional tests data in: {data_folder}\n Drop the xls file in the FMS Data folder on the desktop.")
            while True:
                try:
                    time.sleep(1)  # Keep the script running to monitor for new files

                    # Check if listener has processed new data
                    if hasattr(self.functional_tests_listener, 'processed') and self.functional_tests_listener.processed:
                        
                        if hasattr(self.functional_tests_listener, 'fms_data') and self.functional_tests_listener.fms_data:
                            try:
                                session = self.Session()
                            except:
                                session = self.Session
                            self.functional_tests_listener.fms_data.show_test_input_field(session = session, fms_sql = self)
                            self.functional_tests_listener.processed = False  
                            break

                except Exception as e:
                    print(f"Error in functional tests listener loop: {str(e)}")
                    print("Listener will continue monitoring...")
                    traceback.print_exc()

        except KeyboardInterrupt:
            print("Stopping functional tests listener...")
            if hasattr(self, 'functional_tests_listener') and self.functional_tests_listener:
                self.functional_tests_listener.observer.stop()
                self.functional_tests_listener.observer.join()
        except Exception as e:
            print(f"Fatal error in functional tests listener: {str(e)}")
            traceback.print_exc()
            # Try to restart the listener after a brief delay
            time.sleep(5)
            print("Attempting to restart functional tests listener...")
            self.listen_to_functional_tests(data_folder=data_folder)

    def update_flow_test_results(self, fms_data: FMSData = None) -> None:
        """
        Updates flow test results in the database with the FMS data class instance.
        This can be done automatically from the test reports or directly using input from the FMSTesting
        class procedure. If fms_data is not provided, it uses the attributes obtained in the listening event.
        Args:
            fms_data (FMS_data): FMS data class instance containing flow test results.
        """
        session = None
        if fms_data:
            self.inlet_pressure = fms_data.inlet_pressure
            self.outlet_pressure = fms_data.outlet_pressure
            self.temp_type = fms_data.temperature_type
            self.temperature = fms_data.temperature
            self.units = fms_data.units
            self.test_type = fms_data.test_type
            self.test_id = fms_data.test_id
            self.flow_power_slope = fms_data.flow_power_slope
            self.response_times = fms_data.response_times
            self.response_regions = fms_data.response_regions
            self.slope_correction = fms_data.slope_correction
            self.remark = 'Automated entry'
            self.functional_test_results = fms_data.functional_test_results
        try:
            try:
                session = self.Session()
            except:
                session = self.Session
            type_map = {
                'high_closed_loop': FunctionalTestType.HIGH_CLOSED_LOOP,
                'high_open_loop': FunctionalTestType.HIGH_OPEN_LOOP,
                'low_closed_loop': FunctionalTestType.LOW_CLOSED_LOOP,
                'low_open_loop': FunctionalTestType.LOW_OPEN_LOOP,
                'low_slope': FunctionalTestType.LOW_SLOPE,
                'high_slope': FunctionalTestType.HIGH_SLOPE,
            }

            fms_entry = session.query(FMSMain).filter_by(fms_id=self.selected_fms_id).first()
            if not fms_entry:
                tv_check = session.query(TVStatus).filter_by(allocated = self.selected_fms_id).first()
                max_id = session.query(func.max(FMSMain.id)).scalar() or 0
                new_fms = FMSMain(
                    fms_id=self.selected_fms_id,
                    model='FM',
                    status=FMSProgressStatus.TESTING,
                    drawing='20025.10.AF-R8',
                    gas_type=self.gas_type if self.gas_type else 'Xe',
                    id = max_id + 1
                )
                if tv_check:
                    new_fms.tv_id = tv_check.tv_id
                session.add(new_fms)

            if self.flow_power_slope:
                del self.flow_power_slope['tv_power_12']
                del self.flow_power_slope['tv_power_24']
                del self.flow_power_slope['total_flows_12']
                del self.flow_power_slope['total_flows_24']
            else:
                self.flow_power_slope = {}
            

            if self.functional_test_results and self.selected_fms_id:
                flow_test_entry = session.query(FMSFunctionalTests).filter_by(fms_id = self.selected_fms_id, test_id = self.test_id).first()
                flow_check = session.query(FMSFunctionalTests).filter_by(fms_id = self.selected_fms_id).all()
                if not flow_check:
                    status_update = FMSProgressStatus.TESTING
                else:
                    status_update = None
                try:
                    date = datetime.strptime(self.test_id, "%Y_%m_%d_%H-%M-%S").date()
                except Exception as e:
                    print(f"Error parsing date: {str(e)}")
                    date = datetime.now().date()
                if flow_test_entry:
                    flow_test_entry.test_type = type_map[self.test_type]
                    flow_test_entry.inlet_pressure = self.inlet_pressure
                    flow_test_entry.outlet_pressure = self.outlet_pressure
                    flow_test_entry.temp_type = self.temp_type
                    flow_test_entry.trp_temp = self.temperature
                    flow_test_entry.remark = self.remark
                    flow_test_entry.date = date
                    flow_test_entry.gas_type = self.gas_type if self.gas_type else 'Xe'
                    flow_test_entry.slope12 = self.flow_power_slope.get('slope12', None)
                    flow_test_entry.slope24 = self.flow_power_slope.get('slope24', None)
                    flow_test_entry.intercept12 = self.flow_power_slope.get('intercept12', None)
                    flow_test_entry.intercept24 = self.flow_power_slope.get('intercept24', None)
                    flow_test_entry.response_times = self.response_times
                    flow_test_entry.response_regions = self.response_regions
                    flow_test_entry.slope_correction = self.slope_correction
                    fms_main: FMSMain = flow_test_entry.fms_main
                    if status_update and fms_main:
                        fms_main.status = status_update if not (fms_main.status == FMSProgressStatus.SHIPMENT or\
                                                                 fms_main.status == FMSProgressStatus.DELIVERED or fms_main.status == FMSProgressStatus.SCRAPPED) else fms_main.status
                else:
                    flow_test_entry = FMSFunctionalTests(
                        fms_id=self.selected_fms_id,
                        test_id=self.test_id,
                        test_type=type_map[self.test_type],
                        inlet_pressure=self.inlet_pressure,
                        outlet_pressure=self.outlet_pressure,
                        temp_type=self.temp_type,
                        trp_temp=self.temperature,
                        gas_type=self.gas_type if self.gas_type else 'Xe',
                        remark=self.remark,
                        date=date,
                        response_times=self.response_times,
                        response_regions=self.response_regions,
                        slope_correction=self.slope_correction,
                        **self.flow_power_slope
                    )
                    session.add(flow_test_entry)
                    session.flush()
                    if status_update:
                        fms_main = flow_test_entry.fms_main
                        if fms_main:
                            fms_main.status = status_update if not (fms_main.status == FMSProgressStatus.SHIPMENT or\
                                                                     fms_main.status == FMSProgressStatus.DELIVERED or fms_main.status == FMSProgressStatus.SCRAPPED) else fms_main.status
                session.commit()
                # Update test results
                characteristics = session.query(FMSFunctionalResults).filter_by(test_id=self.test_id).all()
                if not characteristics:
                    for row in self.functional_test_results:
                        logtime = row.get('logtime', 0)
                        for param, value in row.items():
                            if param == 'logtime':
                                continue
                            if (isinstance(value, float) and np.isnan(value)) or str(value).lower() == "nan":
                                continue
                            flow_entry = FMSFunctionalResults(
                                test_id=self.test_id,
                                logtime=logtime,
                                parameter_name=param,
                                parameter_value=value,
                                parameter_unit=self.units[param]
                            )
                            session.add(flow_entry)
                    session.commit()
                    self.check_test_status()
                else:
                    print("This test has already been registered in the database")
                    return
            # self.fms.print_table(FMSFunctionalTests)
        except Exception as e:
            print(f"Error adding fms test data: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

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
                
    def update_fr_characteristics_results(self, fms_data: FMSData = None) -> None:
        """
        Updates the test results from the FR characterization in the database.
        This can be done automatically from the test reports or directly using input from the FMSTesting
        class procedure. If fms_data is not provided, it uses the attributes obtained in the
        listening event.
        Args:
            fms_data (FMS_data): FMS data class instance containing FR characterization test results.
        """
        session = None
        if fms_data:
            self.inlet_pressure = fms_data.inlet_pressure
            self.outlet_pressure = fms_data.outlet_pressure
            self.temp_type = fms_data.temperature_type
            self.temperature = fms_data.temperature
            self.units = fms_data.units
            self.test_type = fms_data.test_type
            self.test_id = fms_data.test_id
            self.gas_type = fms_data.gas_type
            self.remark = 'Automated entry'
            self.functional_test_results = fms_data.functional_test_results
        try:
            try:
                session = self.Session()
            except:
                session = self.Session
            if self.functional_test_results and self.selected_fms_id:
                fr_check = session.query(FMSFRTests).filter_by(fms_id=self.selected_fms_id, test_id=self.test_id).first()
                # if fr_check:
                #     print("This test has already been registered in the database")
                #     return
                if fr_check:
                    session.delete(fr_check)

                fms_entry = session.query(FMSMain).filter_by(fms_id=self.selected_fms_id).first()
                if not fms_entry:
                    tv_check = session.query(TVStatus).filter_by(allocated = self.selected_fms_id).first()
                    max_id = session.query(func.max(FMSMain.id)).scalar() or 0
                    new_fms = FMSMain(
                        fms_id=self.selected_fms_id,
                        model='FM',
                        status=FMSProgressStatus.TESTING,
                        drawing='20025.10.AF-R8',
                        gas_type=self.gas_type if self.gas_type else 'Xe',
                        id = max_id + 1
                    )
                    if tv_check:
                        new_fms.tv_id = tv_check.tv_id
                    session.add(new_fms)                
                fr_columns = FMSFRTests.__table__.columns.keys()
                update_dict = {key: [value[key] for value in self.functional_test_results] for key in fr_columns if key in self.functional_test_results[0] \
                               and not key == FMSFlowTestParameters.INLET_PRESSURE.value}
                try:
                    date = datetime.strptime(self.test_id, "%Y_%m_%d_%H-%M-%S").date()
                except Exception as e:
                    print(f"Error parsing date: {str(e)}")
                    date = datetime.now().date()

                fr_entry = FMSFRTests(**update_dict, gas_type = self.gas_type if self.gas_type else 'Xe', fms_id=self.selected_fms_id,\
                                        inlet_pressure=self.inlet_pressure,
                                        outlet_pressure=self.outlet_pressure, test_id=self.test_id, trp_temp = self.temperature,
                                        date=date, remark=self.remark)
                session.add(fr_entry)

                session.commit()
                self.check_test_status()
                self.fms.print_table(FMSFRTests)
        except Exception as e:
            print(f"Error updating FR characteristics results: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

    def update_tvac_cycle_results(self, fms_data: FMSData = None) -> None:
        """
        Updates TVAC cycle test results in the database with the FMS data class instance.
        This can be done automatically from the test reports or directly using input from the FMSTesting
        class procedure. If fms_data is not provided, it uses the attributes obtained in the
        listening event.
        Args:
            fms_data (FMS_data): FMS data class instance containing TVAC cycle test results.
        """
        session = None
        try:
            try:
                session = self.Session()
            except Exception as e:
                session = self.Session
            if fms_data:
                self.test_id = fms_data.test_id
                self.remark = 'Automated entry'
                self.functional_test_results = fms_data.functional_test_results
            if self.functional_test_results and self.selected_fms_id:
                tvac_check = session.query(FMSTvac).filter_by(fms_id=self.selected_fms_id, test_id=self.test_id).all()
                if tvac_check:
                    # print("This test has already been registered in the database")
                    for entry in tvac_check:
                        session.delete(entry)
                    # return
                fms_entry = session.query(FMSMain).filter_by(fms_id=self.selected_fms_id).first()
                if not fms_entry:
                    tv_check = session.query(TVStatus).filter_by(allocated = self.selected_fms_id).first()
                    max_id = session.query(func.max(FMSMain.id)).scalar() or 0
                    new_fms = FMSMain(
                        fms_id=self.selected_fms_id,
                        model='FM',
                        status=FMSProgressStatus.TESTING,
                        drawing='20025.10.AF-R8',
                        gas_type=self.gas_type if self.gas_type else 'Xe',
                        id = max_id + 1
                    )
                    if tv_check:
                        new_fms.tv_id = tv_check.tv_id
                    session.add(new_fms)
                total = len(self.functional_test_results)
                tvac_columns = FMSTvac.__table__.columns.keys()
                update_dict = {key: [value[key] for value in self.functional_test_results] for key in tvac_columns if key in self.functional_test_results[0]}

                try:
                    date = datetime.strptime(self.test_id, "%Y_%m_%d_%H-%M-%S").date()
                except Exception as e:
                    print(f"Error parsing date: {str(e)}")
                    date = datetime.now().date()

                tvac_entry = FMSTvac(**update_dict, fms_id=self.selected_fms_id, test_id=self.test_id,
                                    date=date, remark=self.remark)
                session.add(tvac_entry)

                fms_main = tvac_entry.fms_main
                if fms_main:
                    fms_main.status = FMSProgressStatus.TVAC_COMPLETED if not (fms_main.status == FMSProgressStatus.SHIPMENT or\
                                                                                fms_main.status == FMSProgressStatus.DELIVERED or fms_main.status == FMSProgressStatus.SCRAPPED) else fms_main.status
                else:
                    fms_main = session.query(FMSMain).filter_by(fms_id=self.selected_fms_id).first()
                    if fms_main:
                        fms_main.status = FMSProgressStatus.TVAC_COMPLETED if not (fms_main.status == FMSProgressStatus.SHIPMENT or\
                                                                                    fms_main.status == FMSProgressStatus.DELIVERED or fms_main.status == FMSProgressStatus.SCRAPPED) else fms_main.status
                session.commit()
            
            self.fms.print_table(FMSTvac, limit=10)
            self.fms.print_table(FMSMain, limit=10)

        except Exception as e:
            print(f"Error updating Tvac results: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

    def allocate_components(self, session: "Session", fms_entry: FMSMain, component_dict: dict) -> None:
        """
        Allocates components to the FMS entry in the database, using the current FMS ID.
        Args:
            session (Session): SQLAlchemy session for database operations.
            fms_entry (FMSMain): FMSMain entry to allocate components and their databases to.
            component_dict (dict): Dictionary containing component serial numbers.
        """
        try:
            hpiv_id = component_dict.get('hpiv_id')
            tv_id = component_dict.get('tv_id')
            lpt_id = component_dict.get('lpt_id')
            anode_fr_id = component_dict.get('anode_fr_id')
            cathode_fr_id = component_dict.get('cathode_fr_id')
            fms_id = component_dict.get('fms_id')
            manifold_id = component_dict.get('manifold_id', None)
            calculated_ac_ratio = self.calculate_ac_ratio(session, anode_fr_id, cathode_fr_id)
            if calculated_ac_ratio:
                specified_ac_ratio = round(calculated_ac_ratio)
            else:
                specified_ac_ratio = None

            hpiv = session.query(HPIVCertification).filter_by(hpiv_id=hpiv_id).first()
            if hpiv:
                if hpiv.allocated != fms_id:
                    hpiv.allocated = fms_id
            
            tv = session.query(TVStatus).filter_by(tv_id=tv_id).first()
            if tv and not tv_id == str(15):
                if not tv.allocated:
                    tv.allocated = fms_id
                elif tv.allocated != fms_id:
                    tv.allocated = fms_id
                print(tv_id)

            manifold = None
            lookup_chain = [
                (ManifoldStatus.lpt, ManifoldStatus.lpt.any(lpt_id=lpt_id)),
                (ManifoldStatus.anode, ManifoldStatus.anode.any(
                    or_(
                        AnodeFR.allocated.contains(fms_id),
                        AnodeFR.fr_id == anode_fr_id
                    )
                )),
                (ManifoldStatus.cathode, ManifoldStatus.cathode.any(
                    or_(
                        CathodeFR.allocated.contains(fms_id),
                        CathodeFR.fr_id == cathode_fr_id
                    )
                )),
            ]

            if not manifold_id:
                manifold = session.query(ManifoldStatus).filter_by(allocated=fms_id).first()
                if manifold:
                    fms_entry.manifold_id = manifold.set_id
                    anode_check: list[AnodeFR] = manifold.anode
                    if anode_check:
                        anode_check = anode_check[0]
                        anode_id = anode_check.fr_id
                        if anode_id != anode_fr_id:
                            fms_entry.anode_fr_id = anode_id
                    else:
                        anode = session.query(AnodeFR).filter(AnodeFR.allocated.contains(fms_id)).first()
                        if anode and anode.set_id != manifold.set_id:
                            anode.set_id = manifold.set_id
                            manifold.ac_ratio = calculated_ac_ratio
                            manifold.ac_ratio_specified = specified_ac_ratio
                    cathode_check: list[CathodeFR] = manifold.cathode
                    if cathode_check:
                        cathode_check = cathode_check[0]
                        cathode_id = cathode_check.fr_id
                        if cathode_id != cathode_fr_id:
                            fms_entry.cathode_fr_id = cathode_id
                    else:
                        cathode = session.query(CathodeFR).filter(CathodeFR.allocated.contains(fms_id)).first()
                        if cathode and cathode.set_id != manifold.set_id:
                            cathode.set_id = manifold.set_id
                            manifold.ac_ratio = calculated_ac_ratio
                            manifold.ac_ratio_specified = specified_ac_ratio
                    lpt_check: list[LPTCalibration] = manifold.lpt
                    if lpt_check:
                        lpt_check = lpt_check[0]
                        lpt_id_check = lpt_check.lpt_id
                        if lpt_id_check != lpt_id:
                            fms_entry.lpt_id = lpt_id_check
                    else:
                        lpt = session.query(LPTCalibration).filter_by(lpt_id=lpt_id).first()
                        if lpt and lpt.set_id != manifold.set_id:
                            lpt.set_id = manifold.set_id
                else:
                    for rel, condition in lookup_chain:
                        manifold = session.query(ManifoldStatus).join(rel).filter(condition).first()
                        # print(f"set_id found: {manifold.set_id}")
                        if manifold:
                            if manifold.allocated != fms_id:
                                manifold.allocated = fms_id
                                manifold.ac_ratio = calculated_ac_ratio
                                manifold.ac_ratio_specified = specified_ac_ratio
                            fms_entry.manifold_id = manifold.set_id
                            anode_check = manifold.anode
                            if anode_check:
                                anode_check = anode_check[0]
                                anode_id = anode_check.fr_id
                                if anode_id != anode_fr_id:
                                    fms_entry.anode_fr_id = anode_id
                            else:
                                anode = session.query(AnodeFR).filter(AnodeFR.allocated.contains(fms_id)).first()
                                if anode and anode.set_id != manifold.set_id:
                                    anode.set_id = manifold.set_id
                                    manifold.ac_ratio = calculated_ac_ratio
                                    manifold.ac_ratio_specified = specified_ac_ratio
                            cathode_check = manifold.cathode
                            if cathode_check:
                                cathode_check = cathode_check[0]
                                cathode_id = cathode_check.fr_id
                                if cathode_id != cathode_fr_id:
                                    fms_entry.cathode_fr_id = cathode_id
                            else:
                                cathode = session.query(CathodeFR).filter(CathodeFR.allocated.contains(fms_id)).first()
                                if cathode and cathode.set_id != manifold.set_id:
                                    cathode.set_id = manifold.set_id
                                    manifold.ac_ratio = calculated_ac_ratio
                                    manifold.ac_ratio_specified = specified_ac_ratio
                            lpt_check = manifold.lpt
                            if lpt_check:
                                lpt_check = lpt_check[0]
                                lpt_id_check = lpt_check.lpt_id
                                if lpt_id_check != lpt_id:
                                    fms_entry.lpt_id = lpt_id_check
                            else:
                                lpt = session.query(LPTCalibration).filter_by(lpt_id=lpt_id).first()
                                if lpt and lpt.set_id != manifold.set_id:
                                    lpt.set_id = manifold.set_id
                            break
            else:
                manifold = session.query(ManifoldStatus).filter_by(set_id=manifold_id).first()
                if manifold and manifold.allocated != fms_id:
                    manifold.allocated = fms_id

        except Exception as e:
            print(f"Error allocating components: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

    def convert_FR_id(self, session: "Session", type: str, fr_id: str, available_anodes: list[str] = [], available_cathodes: list[str] = [], fms_id: str = None) -> str:
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
            if type == 'anode':
                # First, try matching with FMS "24" priority
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

                # Regular search without FMS priority
                filters = [~AnodeFR.fr_id.in_(self.converted_ids),
                        AnodeFR.fr_id.endswith(fr_id),
                        AnodeFR.flow_rates != None]
                if available_anodes:
                    filters.append(AnodeFR.fr_id.in_(available_anodes))
                fr = session.query(AnodeFR).filter(*filters).first()
                if fr:
                    self.converted_ids.append(fr.fr_id)
                    return fr.fr_id

                # FRCertification fallback
                filters_cert = [~FRCertification.anode_fr_id.in_(self.converted_ids),
                                FRCertification.anode_fr_id.endswith(fr_id)]
                if available_anodes:
                    filters_cert.append(FRCertification.anode_fr_id.in_(available_anodes))
                fr = session.query(FRCertification).filter(*filters_cert).first()
                if fr:
                    self.converted_ids.append(fr.anode_fr_id)
                    return fr.anode_fr_id

            elif type == 'cathode':
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

                filters = [~CathodeFR.fr_id.in_(self.converted_ids),
                        CathodeFR.fr_id.endswith(fr_id),
                        CathodeFR.flow_rates != None]
                if available_cathodes:
                    filters.append(CathodeFR.fr_id.in_(available_cathodes))
                fr = session.query(CathodeFR).filter(*filters).first()
                if fr:
                    self.converted_ids.append(fr.fr_id)
                    return fr.fr_id

                # FRCertification fallback
                filters_cert = [~FRCertification.cathode_fr_id.in_(self.converted_ids),
                                FRCertification.cathode_fr_id.endswith(fr_id)]
                if available_cathodes:
                    filters_cert.append(FRCertification.cathode_fr_id.in_(available_cathodes))
                fr = session.query(FRCertification).filter(*filters_cert).first()
                if fr:
                    self.converted_ids.append(fr.cathode_fr_id)
                    return fr.cathode_fr_id

            return fr_id

        except Exception as e:
            print(f"Error converting FR ID: {str(e)}")
            traceback.print_exc()
            return None
        
    def fms_assembly_input_field(self) -> None:
        """
        Creates an input form for FMS assembly with:
        - FMS ID (ComboBox)
        - Manifold Set ID (ComboBox)
        - HPIV ID (ComboBox)
        - TV ID (ComboBox)
        - Gas Type (Dropdown)
        - Drawing Ref (Text)
        - Model Type (ToggleButtons)
        All fields in a neat grid layout, with error handling for drawing.
        """
        label_width = '160px'
        field_width = '300px'

        def field(description):
            return dict(
                description=description,
                layout=widgets.Layout(width=field_width),
                style={'description_width': label_width}
            )

        # --- Preload options for ComboBoxes ---
        try:
            session: "Session" = self.Session()
            manifold_ids = [str(m.set_id) for m in session.query(ManifoldStatus).filter(ManifoldStatus.set_id != None, ManifoldStatus.allocated == None).all()]
            hpiv_ids = [h.hpiv_id for h in session.query(HPIVCertification).filter(HPIVCertification.hpiv_id != None, HPIVCertification.allocated == None).all()]
            tv_ids = [str(t.tv_id) for t in session.query(TVStatus).filter(TVStatus.tv_id != None, TVStatus.allocated == None).all()]
            last_fms = session.query(FMSMain).order_by(FMSMain.id.desc()).first()
            if last_fms and last_fms.fms_id:
                last_part = int(last_fms.fms_id.split("-")[-1])
                first_part = "-".join(last_fms.fms_id.split("-")[:-1])
                new_fms_id = f"{str(first_part)}-{str(last_part + 1).zfill(3)}"
            else:
                new_fms_id = "25-001"
        except Exception:
            traceback.print_exc()
            manifold_ids = []
            hpiv_ids = []
            tv_ids = []
            new_fms_id = "25-001"

        title = widgets.HTML("<h3>FMS Assembly Form</h3>")
        # --- Widgets ---
        fms_widget = widgets.Combobox(
            **field("FMS ID:"),
            value=new_fms_id
        )
        manifold_widget = widgets.Combobox(
            **field("Manifold Set ID:"),
            options=manifold_ids,
            placeholder="Select or Type ..."
        )
        hpiv_widget = widgets.Combobox(
            **field("HPIV ID:"),
            options=hpiv_ids,
            placeholder="Select or Type ..."
        )
        tv_widget = widgets.Combobox(
            **field("TV ID:"),
            options=tv_ids,
            placeholder="Select or Type ..."
        )

        gas_type_widget = widgets.Dropdown(
            options=['Xe', 'Kr'],
            value='Xe',
            description='Gas type:',
            style={'description_width': label_width},
            layout=widgets.Layout(width=field_width, height='50px')
        )

        drawing_widget = widgets.Text(
            **field("Drawing Ref:"),
            value='20025.10.AF-R8',
            placeholder="Enter drawing reference"
        )
        model_widget = widgets.ToggleButtons(
            description='Model Type:',
            options=['FM', 'EM', 'QM', 'EQM'],
            style={'description_width': label_width},
            layout=widgets.Layout(width='220px'),
            value='FM'
        )

        submit_button = widgets.Button(
            description="Submit",
            button_style="success",
            layout=widgets.Layout(width='120px')
        )
        output = widgets.Output()

        confirmed_once = {'clicked': False}
        submitted = {'done': False}
        DRAFT_NAME = 'fms_assembly_draft'

        try:
            draft = load_from_json(DRAFT_NAME)  
            if draft:
                fms_widget.value = draft.get('fms_id', new_fms_id)
                manifold_widget.value = draft.get('manifold_id', '')
                hpiv_widget.value = draft.get('hpiv_id', '')
                tv_widget.value = draft.get('tv_id', '')
                drawing_widget.value = draft.get('drawing', '20025.10.AF-R8')
                model_widget.value = draft.get('model', 'FM')
                gas_type_widget.value = draft.get('gas_type', 'Xe')
        except Exception:
            pass

        def save_fms_form_data(change: "widgets.Widget" = None) -> None:
            form = {
                'fms_id': fms_widget.value,
                'manifold_id': manifold_widget.value,
                'hpiv_id': hpiv_widget.value,
                'tv_id': tv_widget.value,
                'drawing': drawing_widget.value,
                'model': model_widget.value,
                'gas_type': gas_type_widget.value
            }
            save_to_json(form, DRAFT_NAME)
            submitted['done'] = False
            confirmed_once['clicked'] = False

        for w in [fms_widget, manifold_widget, hpiv_widget, tv_widget, drawing_widget, model_widget]:
            w.observe(save_fms_form_data, names='value')

        # --- Submit handler ---
        def on_submit_clicked(b):
            with output:
                output.clear_output()
                if submitted['done']:
                    print("Already Submitted")
                    return

                # Validate required fields
                required = [
                    (fms_widget, "FMS ID"),
                    (manifold_widget, "Manifold Set ID"),
                    (hpiv_widget, "HPIV ID"),
                    (tv_widget, "TV ID"),
                    (drawing_widget, "Drawing Ref"),
                    (model_widget, "Model Type"),
                ]
                for widget, label in required:
                    if not widget.value:
                        print(f"Please enter/select a {label}.")
                        return

                if not confirmed_once['clicked']:
                    confirmed_once['clicked'] = True
                    print("Click submit again to confirm.")
                    return

                # Validate formats
                hpiv_pattern = r"^VS197-(\d{3})$"
                fms_pattern = r"^\d{2}-\d{3}$"
                drawing_pattern = r"^\d{5}\.\d{2}\.\w{2}-R\d$"
                try:
                    fms_id = fms_widget.value.strip()
                    manifold_set_id = manifold_widget.value
                    hpiv_id = hpiv_widget.value.strip()
                    tv_id = tv_widget.value.strip()
                    drawing = drawing_widget.value.strip()
                    model = model_widget.value
                    gas_type = gas_type_widget.value
                except Exception:
                    print("Invalid input. Please check all fields.")
                    return

                if not re.match(hpiv_pattern, hpiv_id):
                    print("Invalid HPIV ID format. Use 'VS197-XXX'.")
                    return
                if not re.match(fms_pattern, fms_id):
                    print("Invalid FMS ID format. Use 'XX-XXX' (2 digits)-(3 digits).")
                    return
                if not drawing:
                    print("Drawing reference cannot be empty.")
                    return
                if not re.match(drawing_pattern, drawing):
                    print("Invalid drawing reference format. Use 'XXXXX.XX.AA-AX'.")
                    return

                # Lookup FR and LPT IDs
                try:
                    manifold = session.query(ManifoldStatus).filter_by(set_id=manifold_set_id).first()
                    anode_fr_id = manifold.anode.fr_id if manifold and manifold.anode else None
                    cathode_fr_id = manifold.cathode.fr_id if manifold and manifold.cathode else None
                    lpt_id = manifold.lpt.fr_id if manifold and manifold.lpt else None
                except Exception:
                    anode_fr_id = cathode_fr_id = lpt_id = None

                fms_check = session.query(FMSMain).filter_by(fms_id = fms_id).first()
                if fms_check:
                    print("This FMS has already been assembled.")
                    return

                # Check allocation for each component (manifold, tv, hpiv) in a loop
                component_fields = [
                    ('manifold_id', manifold_set_id, 'Manifold Set'),
                    ('tv_id', tv_id, 'TV'),
                    ('hpiv_id', hpiv_id, 'HPIV'),
                ]
                for field, value, label in component_fields:
                    if not value:
                        continue
                    check_fms = session.query(FMSMain).filter_by(**{field: value}).first()
                    if check_fms:
                        print(f"This {label} has already been allocated to FMS with ID: {check_fms.fms_id}")
                        return

                self.assembly_data = {
                    'fms_id': fms_id,
                    'manifold_id': int(manifold_set_id),
                    'hpiv_id': hpiv_id,
                    'tv_id': int(tv_id),
                    'anode_fr_id': anode_fr_id,
                    'cathode_fr_id': cathode_fr_id,
                    'lpt_id': lpt_id,
                    'drawing': drawing,
                    'model': model,
                    'gas_type': gas_type
                }
                self.add_fms_assembly_data()
                confirmed_once['clicked'] = False
                submitted['done'] = True

                delete_json_file(DRAFT_NAME)

        submit_button.on_click(on_submit_clicked)

        # --- Display form in a grid ---
        grid = widgets.GridBox(
            [
                fms_widget, manifold_widget,
                hpiv_widget, tv_widget,
                drawing_widget, model_widget,
                gas_type_widget
            ],
            layout=widgets.Layout(
                grid_template_columns="repeat(2, 320px)",
                grid_gap="12px 24px",
                border='1px solid #ccc',
                padding='18px',
                width='fit-content',
                background_color="#f9f9f9"
            )
        )
        display(widgets.VBox([title, grid]))
        display(submit_button, output)

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

    def add_fms_assembly_data(self, fms_data: FMSData = None) -> None:
        """
        Adds FMS assembly data to the database with the FMS data class instance.
        This can be done automatically from the test reports or directly using input from the FMS assembly
        class procedure. If fms_data is not provided, it uses the attributes obtained in the listening event.
        Args:
            fms_data (FMS_data): FMS data class instance containing assembly data.
        """
        session = None
        if fms_data:
            self.component_serials = fms_data.component_serials
            doc_ref = os.path.basename(fms_data.pdf_file) if fms_data.pdf_file else None
        try:
            session: "Session" = self.Session()
            max_id = session.query(func.max(FMSMain.id)).scalar() or 0
            available_anodes = session.query(AnodeFR).filter(AnodeFR.set_id == None).all()
            available_cathodes = session.query(CathodeFR).filter(CathodeFR.set_id == None).all()
            if available_anodes and available_cathodes:
                anode_ids = [a.fr_id for a in available_anodes]
                cathode_ids = [c.fr_id for c in available_cathodes]
            if self.component_serials and not self.assembly_data:
                anode_id = self.convert_FR_id(session, 'anode', self.component_serials.get('anode_fr_id', ''), available_anodes=anode_ids, fms_id = self.component_serials.get('fms_id', ''))
                cathode_id = self.convert_FR_id(session, 'cathode', self.component_serials.get('cathode_fr_id', ''), available_cathodes=cathode_ids, fms_id = self.component_serials.get('fms_id', ''))
                if not self.component_serials.get('drawing', None):
                    self.component_serials['drawing'] = '20025.10.AF-R8'
                self.component_serials['anode_fr_id'] = anode_id
                self.component_serials['cathode_fr_id'] = cathode_id
                if not self.component_serials.get('model', None):
                    self.component_serials['model'] = 'FM'
                if not self.component_serials.get('gas_type', None):
                    self.component_serials['gas_type'] = 'Xe'
                fms_entry = FMSMain(**self.component_serials, test_doc_ref = doc_ref, id = max_id + 1)
                self.allocate_components(session, fms_entry, self.component_serials)
                session.merge(fms_entry)

            elif self.assembly_data:
                fms_entry = FMSMain(**self.assembly_data, status = FMSProgressStatus.ASSEMBLY_COMPLETED, id = max_id + 1)
                self.allocate_components(session, fms_entry, self.assembly_data)
                session.merge(fms_entry)

            session.commit()
            self.fms.print_table(FMSMain)
        except Exception as e:
            print(f"Error adding fms assembly data: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()

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

    def update_fms_main_test_results(self, fms_data: FMSData = None) -> None:
        """
        Updates the FMS main test results in the database with the FMS data class instance.
        Args:
            fms_data (FMSData): FMS data class instance containing main test results.
        """
        automated_entry = False
        if fms_data:
            self.fms_test_results = fms_data.fms_main_test_results
            self.component_serials = fms_data.component_serials
            automated_entry = True
        session = None
        try:
            try:
                session = self.Session()
            except:
                session = self.Session
            if not hasattr(self, 'fms_test_results') or not self.fms_test_results:
                print("No FMS test results to update.")
                return  

            fms_id = self.component_serials.get('fms_id', None)
            if not fms_id:
                print("FMS ID not found in component serials.")
                return
            
            for param, values in self.fms_test_results.items():
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
                    within_limits = self.get_limit_status(param, value, unit, fms_data)
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
            self.fms.print_table(FMSTestResults)
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
        fms_data = FMSData()
        fms_limits = fms_data.fms_limits

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