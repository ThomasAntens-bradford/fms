from __future__ import annotations
from typing import TYPE_CHECKING, Any
if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from ..fms_data_structure import FMSDataStructure
# Standard library imports
import json
import os
import re
import time
import traceback

# Path adjustments for script execution
if __name__ == "__main__":
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Third-party imports
import chardet
import matplotlib.pyplot as plt
import numpy as np
import openpyxl
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Local application imports
from ..db import (
    AnodeFR,
    CathodeFR,
    FRCertification,
    LPTCalibration,
    LPTCoefficients,
    ManifoldStatus,
)
from .manifold_query import ManifoldQuery
from .general_utils import (
    FRStatus,
    LimitStatus,
    LPTCoefficientParameters,
    ManifoldProgressStatus,
)
from .ocr_reader import OCRReader
from .textract import TextractReader

class LPTListener(FileSystemEventHandler):
    """
    File system event handler for monitoring HPIV data packages.
    
    This class extends FileSystemEventHandler to monitor a specified directory
    for new PDF files containing HPIV test data. When a new PDF is detected,
    it automatically processes the file to extract test results.
    
    Attributes
    ----------
        path (str): 
            Directory path to monitor for new PDF files.
        observer (Observer): 
            Watchdog observer instance for file monitoring.
        processed (bool): 
            Flag indicating if new data has been processed.
        lpt_data (LPT_data): 
            Instance of LPT_data to which the data is fed.
        processed_dirs (set): 
            Set of directories already processed.
        manifold (bool): 
            Flag indicating if the processed data is for a manifold.
    """


    def __init__(self, path: str = 'LPT_data'):
        self.path = path
        self.observer = Observer()
        self.observer.schedule(self, path, recursive=True)
        self.observer.start()
        self.processed = False
        self.data = None
        self.processed_dirs = set()
        self.manifold = False

    def on_created(self, event) -> None:
        """
        Event handler for file creation events.
        Parameters
        ----------
        event (FileSystemEvent): 
            The file system event that triggered this handler.
        """
        try:
            if os.path.basename(event.src_path).startswith('.') or event.src_path.endswith('.tmp'):
                return

            if self.path.endswith('LPT_data'):
                if event.is_directory:
                    if event.src_path in self.processed_dirs:
                        return
                    print(f"Directory detected: {event.src_path}")
                    time.sleep(0.5)  # Allow time for files to settle

                    json_files = [
                        os.path.join(event.src_path, f)
                        for f in os.listdir(event.src_path)
                        if f.endswith('.json')
                    ]

                    if json_files:
                        self.lpt_data = ManifoldData(json_files=json_files)
                        self.lpt_data.extract_coefficients_from_json()
                        self.processed = True
                        self.processed_dirs.add(event.src_path)
                    return

                # Single file created
                if event.src_path.endswith('.json'):
                    parent_dir = os.path.dirname(event.src_path)
                    if parent_dir in self.processed_dirs:
                        return
                    self.data = ManifoldData(json_files=[event.src_path])
                    self.data.extract_coefficients_from_json()
                    self.processed = True
            
            elif self.path.endswith('certifications'):
                
                if not event.src_path.endswith('.pdf'):
                    return
                print(f"New certification file detected: {event.src_path}")
                self.pdf_file = event.src_path

                pdf_basename = os.path.basename(self.pdf_file).lower()
                if 'keller' in pdf_basename:
                    self.data = ManifoldData(pdf_file=self.pdf_file)
                    self.data.get_ocr_certification()
                    self.processed = True
                elif 'sk' in pdf_basename or 'sk technology' in pdf_basename or 'veld laser' in pdf_basename or 'veldlaser' in pdf_basename:
                    self.data = ManifoldData(pdf_file=self.pdf_file)
                    self.data.get_manifold_ocr_certification()
                    self.manifold = True
                    self.processed = True
                elif 'coremans' in pdf_basename:
                    self.data = ManifoldData(pdf_file=self.pdf_file, coremans=True)
                    self.manifold = True
                    self.data.get_manifold_ocr_certification()
                    self.processed = True

        except Exception as e:
            print(f"Error processing: {e}")
            traceback.print_exc()
            self.observer.stop()
            self.observer.start()

class ManifoldData:
    """
    Class for handling LPT Coefficients and Calibration, and Manifold data extraction and processing.
    Attributes
    ----------
    json_files (list):
        List of JSON file paths containing LPT coefficient data.
    pdf_file (str):
        Path to the PDF file for OCR extraction of certifications.
    coremans (bool):
        Flag indicating if the data is from Coremans.
    company (str):
        Company name for specific processing logic.

    Methods
    -------
    extract_coefficients_from_json():
        Extracts LPT coefficients from provided JSON files.
    calculate_pressure(R, U, c):
        Calculates pressure based on resistance, signal, and coefficients.
    calculate_temperature(R, U, c):
        Calculates temperature based on resistance, signal, and coefficients.
    convert_coefficients(lpt_id, file_path, max_signal, Rb, base_signal, signal_step, R_min, R_max, R_step):
        Converts extracted coefficients into calibration data.
    extract_serials():
        Extracts LPT serial numbers from OCR text. ***REMARK: USES OCRReader CLASS, NOT TEXTRACT!***
    get_ocr_certification():
        Extracts LPT certifications using OCR from the PDF file. ***REMARK: USES OCRReader CLASS, NOT TEXTRACT!***
    get_lpt_certification(total_lines):
        Extracts LPT certifications from provided text lines.
    extract_ocr_parts():
        Extracts manifold parts information from OCR text. ***REMARK: USES OCRReader CLASS, NOT TEXTRACT!***
    get_manifold_ocr_certification():
        Extracts manifold certifications using OCR from the PDF file. ***REMARK: USES OCRReader CLASS, NOT TEXTRACT!***
    get_manifold_certification(total_lines):
        Extracts manifold certifications from provided text lines.
    get_assembly_certification(total_lines):
        Extracts assembly certifications from provided text lines.
    plot_pressure(lpt_id):
        Plots pressure calibration data for a given LPT ID.
    plot_temperature(lpt_id):
        Plots temperature calibration data for a given LPT ID.
    """

    def __init__(self, json_files: list[str] = None, pdf_file: str = None, coremans: bool = False, company: str = None):
        self.lpt_id = None
        self.lpt_coefficients = {}
        self.json_files = json_files
        self.pdf_file = pdf_file
        self.temp_cells = [i.value for i in LPTCoefficientParameters if 't' in i.value.lower() and not i.value.startswith('lpt_id')]
        self.pressure_cells = [i.value for i in LPTCoefficientParameters if 'p' in i.value.lower() and not i.value.startswith('lpt_id')]
        self.lpt_calibration = {}
        self.coremans = coremans
        self.extracted_lpt_serials = []
        self.extracted_manifold_parts = {}
        self.default_manifold_drawing = '20025.10.08-R4'
        self.company = company
        self.total_lines = ""
        self.drawing_reference = None
        self.total_amount = 1

    def extract_coefficients_from_json(self) -> None:
        """
        Extracts LPT coefficients from the provided JSON files and converts them into calibration data.
        """
        for file_path in self.json_files:
            with open(file_path, 'rb') as f:
                raw_data = f.read()
                encoding = chardet.detect(raw_data)['encoding']
                if encoding is None:
                    print(f"Could not detect encoding for {file_path}. Using utf-8 as fallback.")
                    encoding = 'utf-8'

            with open(file_path, 'r', encoding=encoding) as file:
                data = json.load(file)
                
                header = data['header']
                lpt_id = header['serialNumber']
                date = header['creationDate']
                
                mathematical_models = data['compensationMethods']['mathematicalModels'].items()
                used_model = [f for f in mathematical_models][0][0]
                calibration_data = data['compensationMethods']['mathematicalModels'][used_model]['parts']
                pressure_coefficients = [
                item for sublist in calibration_data['pressure']['coefficients'] for item in sublist
                ]
                temperature_coefficients = [
                item for sublist in calibration_data['temperature']['coefficients'] for item in sublist
                ]
                self.lpt_coefficients[lpt_id] = {
                'pressure_coefficients': pressure_coefficients,
                'temperature_coefficients': temperature_coefficients
                }
            
                self.convert_coefficients(lpt_id=lpt_id, file_path=file_path)

    def calculate_pressure(self,R: float, U: float, c: list[float]) -> float:
        """
        Calculate pressure from resistance R, signal U, and 16 pressure coefficients c.

        Args:
            R (float): Base resistance.
            U (float): Signal.
            c (list[float]): Flattened list of 16 pressure coefficients.

        Returns:
            float: Calculated pressure.
        """
        return (
            c[0] + R*c[1] + R**2*c[2] + R**3*c[3] +
            U*(c[4] + R*c[5] + R**2*c[6] + R**3*c[7]) +
            U**2*(c[8] + R*c[9] + R**2*c[10] + R**3*c[11]) +
            U**3*(c[12] + R*c[13] + R**2*c[14] + R**3*c[15])
        )
    
    def calculate_temperature(self, R: float, U: float, c: list[float]) -> float:
        """
        Calculate temperature from resistance R, signal U, and 16 temperature coefficients c.

        Args:
            R (float): Base resistance.
            U (float): Signal.
            c (list[float]): Flattened list of 16 temperature coefficients.

        Returns:
            float: Calculated temperature.
        """
        return (
            c[0] + U*c[1] + U**2*c[2] + U**3*c[3] +
            R*(c[4] + U*c[5] + U**2*c[6] + U**3*c[7]) +
            R**2*(c[8] + U*c[9] + U**2*c[10] + U**3*c[11]) +
            R**3*(c[12] + U*c[13] + U**2*c[14] + U**3*c[15]) 
        )
    
    
    def convert_coefficients(self, lpt_id, file_path, max_signal: float = 170, Rb: float = 3450, 
                             base_signal: float = 0, signal_step: float = 0.05, R_min: float = 3100, R_max: float = 4000, R_step: float = 50) -> None:
        """
        Convert LPT coefficients into calibration data for pressure and temperature.
        Args:
            lpt_id (str): LPT serial number.
            file_path (str): Path to the JSON file.
            max_signal (float): Maximum signal value for pressure calibration.
            Rb (float): Base resistance for pressure calibration.
            base_signal (float): Base signal for temperature calibration.
            signal_step (float): Step size for signal values.
            R_min (float): Minimum resistance for temperature calibration.
            R_max (float): Maximum resistance for temperature calibration.
            R_step (float): Step size for resistance values.
        """
        self.lpt_calibration[lpt_id] = {}
        signal = np.arange(0, max_signal + signal_step, signal_step)
        base_resistance_p = [Rb for _ in range(len(signal))]
        c_pressure = self.lpt_coefficients[lpt_id]['pressure_coefficients']
        calculated_pressures = [float(self.calculate_pressure(R, U, c_pressure)) for R, U in zip(base_resistance_p, signal)]
        self.lpt_calibration[lpt_id]['pressure'] = calculated_pressures
        self.lpt_calibration[lpt_id]['base_resistance'] = Rb
        self.lpt_calibration[lpt_id]['signal'] = signal.tolist()

        c_temp = self.lpt_coefficients[lpt_id]['temperature_coefficients']
        resistance = np.arange(R_min, R_max + R_step, R_step)
        base_signal_t = [base_signal for _ in range(len(resistance))]
        calculated_temperatures = [float(self.calculate_temperature(R, U, c_temp)) for R, U in zip(resistance, base_signal_t)]
        self.lpt_calibration[lpt_id]['temperature'] = calculated_temperatures
        self.lpt_calibration[lpt_id]['base_signal'] = base_signal
        self.lpt_calibration[lpt_id]['resistance'] = resistance.tolist()
        self.lpt_calibration[lpt_id]['file_reference'] = os.path.basename(file_path)

    def extract_serials(self) -> list[str]:
        """
        Extracts LPT serial numbers from OCR text.
        Returns:
            list[str]: Sorted list of unique LPT serial numbers.
        """
        # Find all serials matching a letter followed by six digits
        raw_serials = re.findall(r'\b[A-Z]\d{6}\b', self.total_lines)
        if not raw_serials:
            return []

        # Remove duplicates and sort by numeric part
        result = sorted(
            set(raw_serials),
            key=lambda s: int(s[1:])
        )

        return result

    def get_ocr_certification(self) -> None:
        """
        Extracts LPT certifications using OCR from the PDF file.
        """
        ocr_reader = OCRReader(pdf_file=self.pdf_file)
        ocr_reader.packing_list_reader(part_type='lpt')
        self.total_lines = ocr_reader.total_lines
        self.certification = ocr_reader.certification
        if self.total_lines:
            print(self.total_lines)
            self.extracted_lpt_serials = self.extract_serials()

    def get_lpt_certification(self, total_lines: list[str]) -> None:
        """
        Extracts LPT certification and serial numbers from provided text lines.

        Args:
            total_lines (list[str]): Lines of text to extract information from.
        """
        match = re.search(r'C\d{2}-\d{4}', os.path.basename(self.pdf_file))
        self.certification = match.group(0) if match else None
        self.total_lines = total_lines

        serial_index = None
        for idx, cell in enumerate(self.total_lines):
            if isinstance(cell, str) and 'serial number' in cell.lower() and 'filled in' not in cell.lower() and 'during inspection' not in cell.lower():
                serial_index = idx
                break

        if serial_index is None:
            print("Could not find 'serial number' in total_lines.")
            return

        count = 1
        found_first = False
        while True:
            if serial_index + count >= len(self.total_lines):
                break
            item = str(self.total_lines[serial_index + count]).strip()

            # Match serial number: letter + ≥5 digits OR ≥5 digits
            if re.match(r'^([A-Za-z]\d{5,}|\d{5,})$', item):
                self.extracted_lpt_serials.append(item.upper())
                found_first = True
            else:
                if found_first:
                    break

            count += 1

    def extract_ocr_parts(self) -> dict:
        """
        Extracts manifold parts information from OCR text.
        Returns:
            dict: Extracted parts information including amounts, drawings, and certifications.
        """
        text = self.total_lines
        text_lower = text.lower()
        manifold_found = False
        assembly_found = False
        certification_raw = None
        manifold_cert_raw = None
        parts = {
            'manifold': '20025.10.08-R4',
            'lpt assembly': '20025.10.AB-R4-51'
        }

        result = {}
        lines = text.splitlines()

        for part_name, default_drawing in parts.items():
            drawing_found = default_drawing

            if part_name == 'manifold':
                for line in lines:
                    if part_name in line.lower():
                        manifold_found = True
                        match = re.search(r'([0-9]{5}\.[0-9]{2}\.[0-9]{2,3}-[A-Z0-9]+)', line)
                        if match:
                            drawing_found = match.group(1)
                        cert_match = re.search(r'[\s_\-—]*([Cc]?\d{2}-\d{4})', line, re.IGNORECASE)
                        if cert_match:
                            cert_raw = cert_match.group(1).upper()
                            if not cert_raw.startswith('C'):
                                manifold_cert_raw = 'C' + cert_raw
                            else:
                                manifold_cert_raw = cert_raw
                        
                        break

                manifold_cert = manifold_cert_raw or self.certification
                # Find total amount
                total_match = re.search(r'totaal aantal\s*[:=]*\s*(\d{1,3}(?:[.,]\d{3})*|\d+)', text_lower)
                if total_match:
                    try:
                        total_str = total_match.group(1).replace('.', '').replace(',', '.')
                        amount_found = int(round(float(total_str)))
                    except:
                        amount_found = None
                else:
                    amount_found = None

                if amount_found is not None and manifold_found and not self.coremans:
                    result[part_name] = {
                        'amount': amount_found,
                        'drawing': drawing_found,
                        'certification': manifold_cert
                    }
                elif self.coremans and manifold_found and not amount_found:
                    ocr_reader = OCRReader(pdf_file=self.pdf_file)
                    amount = ocr_reader.read_scanned_page_coremans()
                    if amount is not None:
                        result[part_name] = {
                            'amount': amount,
                            'drawing': drawing_found,
                            'certification': manifold_cert
                        }

            elif part_name == 'lpt assembly':
                ratio_default = 13
                lpt_assemblies = {}

                for line in lines:
                    if part_name in line.lower():
                        current_drawing = drawing_found
                        assembly_found = True
                        drawing_match = re.search(r'([0-9]{5}\.[0-9]{2}\.[0-9]{2,3}-[A-Z0-9]+)', line)
                        if drawing_match:
                            current_drawing = drawing_match.group(1)

                        ratio_match = re.search(r'lpt assembly\s*\(ratio\s*(\d+)\)', line.lower())
                        ratio = int(ratio_match.group(1)) if ratio_match else ratio_default


                        serial_match = re.search(r'((?:C)?\d{2}-\d{4})\s+SN#?(\d{2,})', line, re.IGNORECASE)
                        if serial_match:
                            certification_raw = serial_match.group(1).upper()
                            sn = serial_match.group(2)  

                            if certification_raw:
                                # Add leading 'C' if missing
                                if not certification_raw.startswith('C'):
                                    certification_raw = 'C' + certification_raw

                                # Save certification once
                                certification = certification_raw
                            else:
                                certification = self.certification

                            lpt_assemblies[sn] = {
                                'drawing': current_drawing,
                                'ratio': ratio,
                                'certification': certification
                            }

                if lpt_assemblies:
                    result[part_name] = lpt_assemblies
        return result

    def get_manifold_ocr_certification(self) -> None:
        """
        Extracts manifold certifications using OCR from the PDF file.
        """
        ocr_reader = OCRReader(pdf_file=self.pdf_file)
        ocr_reader.main_delivery_slip_reader(part_type='manifold')
        self.total_lines = ocr_reader.total_lines
        self.certification = ocr_reader.certification
        if self.total_lines:
            self.extracted_manifold_parts = self.extract_ocr_parts()

    def get_manifold_certification(self, total_lines: list[str]) -> None:
        """
        Extracts manifold certifications from provided text lines.
        Args:
            total_lines (list[str]): Lines of text to extract information from.
        """
        match = re.search(r'C\d{2}-\d{4}', os.path.basename(self.pdf_file))
        self.certification = match.group(0) if match else None
        self.extracted_manifold_parts = {}
        self.total_lines = total_lines

        if self.company != 'coremans':
            try:
                # Find index of element that contains 'totaal aantal'
                totaal_index = next(
                    idx for idx, val in enumerate(self.total_lines)
                    if re.search(r'totaal\s*aantal', val, re.IGNORECASE)
                )
                print(totaal_index)

                # Look ahead to find the next item with digits
                for next_val in self.total_lines[totaal_index+1 : totaal_index+5]:
                    if re.search(r'\d', next_val):  # contains a digit
                        self.total_amount = int(float(next_val.strip().replace(',', '.')))
                        break
                
            except (IndexError, ValueError, StopIteration):
                try:
                    quantity_pattern = r"quantity(?: supplied)?:\s*(\d+)"
                    quantity_line = next((i for i in self.total_lines if re.search(quantity_pattern, i, re.IGNORECASE)), None)
                    if quantity_line:
                        match = re.search(quantity_pattern, quantity_line, re.IGNORECASE)
                        if match:
                            self.total_amount = int(match.group(1))
                except (IndexError, ValueError):
                    quantity_index = self.total_lines.index('quantity supplied:')
                    self.total_amount = int(self.total_lines[quantity_index + 1].strip().replace(',', '').replace('.', ''))
        else:
            try:
                # Find index of element that contains 'totaal aantal'
                totaal_index = next(
                    idx for idx, val in enumerate(self.total_lines)
                    if re.search(r'totaal\s*aantal', val, re.IGNORECASE)
                )
                print(totaal_index)

                # Look ahead to find the next item with digits
                for next_val in self.total_lines[totaal_index+1 : totaal_index+5]:
                    if re.search(r'\d', next_val):  # contains a digit
                        self.total_amount = int(float(next_val.strip().replace(',', '.')))
                        break
                
            except (IndexError, ValueError, StopIteration):
                quantity_pattern = r"quantity(?: supplied)?:"

                # Find the index of the line containing 'quantity:'
                quantity_idx = next((i for i, line in enumerate(self.total_lines)
                                    if re.search(quantity_pattern, line, re.IGNORECASE)), None)

                if quantity_idx is not None:
                    # Look at this line and the next few lines for a number
                    for offset in range(0, 3):  # check this line + 2 lines after
                        if quantity_idx + offset >= len(self.total_lines):
                            break
                        line = self.total_lines[quantity_idx + offset].strip()
                        number_match = re.match(r"^\d+$", line)  # integer only
                        if number_match:
                            self.total_amount = int(number_match.group(0))
                            break

        for line in self.total_lines:
            drawing_match = re.search(r'([0-9]{5}\.[0-9]{2}\.[a-zA-Z0-9]{2,3}-R[0-9]+)(?:\s+\w+)?', line, re.IGNORECASE)
            if drawing_match:
                if not self.drawing_reference:
                    self.drawing_reference = drawing_match.group(1).strip().upper()

        self.extracted_manifold_parts['manifold'] = {
            'amount': self.total_amount,
            'drawing': self.drawing_reference if self.drawing_reference else self.default_manifold_drawing,
            'certification': self.certification
        }

        print(self.manifold_parts)


    def get_assembly_certification(self, total_lines: list[str]) -> None:
        """
        Extracts assembly certifications from provided text lines.

        Args:
            total_lines (list[str]): Lines of text to extract information from.
        """
        match = re.search(r'C\d{2}-\d{4}', os.path.basename(self.pdf_file))
        self.certification = match.group(0) if match else None
        self.total_lines = total_lines
        ratio_default = 13
        serials = []
        ratios = []
        self.drawing_reference = None
        self.extracted_manifold_parts = {'lpt assembly': {}}
        for line in self.total_lines:
            serial_match = re.search(r'\b(C\d{2}-\d{4})\b.*\bSN#?(\d+)\b', line, re.IGNORECASE)
            ratio_match = re.search(r'lpt assembly\s*\(ratio\s*(\d+)\)', line.lower())
            drawing_match = re.search(r'([0-9]{5}\.[0-9]{2}\.[a-z0-9]{2,3}-[Rr][0-9]+(?:-[0-9]+)?)', line)
            if drawing_match:
                if self.drawing_reference:
                    continue
                self.drawing_reference = drawing_match.group(1).upper()
            ratio = int(ratio_match.group(1)) if ratio_match else None
            if ratio: ratios.append(ratio)
            if serial_match:
                lpt_certification = serial_match.group(1).upper()
                serial_number = serial_match.group(2)
                if lpt_certification == self.certification:
                    serials.append(serial_number)
                    

        self.extracted_manifold_parts['lpt assembly'] = {serial: {
            'certification': self.certification,
            'ratio': ratio if ratio else ratio_default,
            'drawing': self.drawing_reference if self.drawing_reference else '20025.10.AB-R4-51'
        } for serial, ratio in zip(serials, ratios)}

        print(self.extracted_manifold_parts)


    def plot_pressure(self, lpt_id: str) -> None:
        """
        Plots pressure calibration data for a given LPT ID.
        Args:
            lpt_id (str): LPT serial number.
        """
        if lpt_id not in self.lpt_calibration:
            print(f"No calibration data for LPT ID: {lpt_id}")
            return
        
        data = self.lpt_calibration[lpt_id]
        plt.plot(data['signal'], data['pressure'], label='Pressure Calibration')
        plt.xlabel('Signal [mV]]')
        plt.ylabel('Pressure [bar]')
        plt.title(f'LPT Pressure Calibration for {lpt_id}')
        plt.legend()
        plt.grid()
        plt.show()

    def plot_temperature(self, lpt_id: str) -> None:
        """
        Plots temperature calibration data for a given LPT ID.
        Args:
            lpt_id (str): LPT serial number.
        """
        if lpt_id not in self.lpt_calibration:
            print(f"No calibration data for LPT ID: {lpt_id}")
            return
        
        data = self.lpt_calibration[lpt_id]
        plt.plot(data['resistance'], data['temperature'], label='Temperature Calibration')
        plt.xlabel('Resistance [Ohm]')
        plt.ylabel('Temperature [degC]')
        plt.title(f'LPT Temperature Calibration for {lpt_id}')
        plt.legend()
        plt.grid()
        plt.show()

class ManifoldLogicSQL:
    """
    Class for managing LPT calibration data and status updates in the database.
    Attributes
    ----------
    Session (sessionmaker):
        SQLAlchemy session factory for database interactions.
    fms (FMSDataStructure):
        Parent FMS data structure for accessing related data, or top-level functions.
    lpt_coefficient_data (str):
        Directory path for LPT coefficient data.
    lpt_certifications (str):
        Directory path for LPT certifications.
    signal_threshold (float):
        Specified signal at which the LPT should read 0.2 [bar].
    signal_tolerance (float):
        Allowed tolerance for the signal threshold.
    pressure_threshold (float):
        Specified pressure at which the LPT signal is checked.
    assembly_file (str):
        Path to the Excel template for manifold assembly status.

    Methods
    -------
    listen_to_lpt_calibration():
        Listens for new LPT calibration data and updates the database.
    get_lpt_status(signal, pressures):
        Determines the LPT status based on signal and pressure data.
    update_lpt_calibration(lpt_data):
        Updates the LPT calibration data in the database.
    query_lpt_status(lpt_id):
        Queries the LPT status from the database for a given LPT ID.
    convert_FR_id(session, type, fr_id, fms_id):
        Converts an ambiguous FR ID to the correct format based on type and availability.
    extract_assembly_from_excel():
        Extracts manifold assembly data from the Excel template.
    update_related_parts(session, set_id, anode_fr, anode_filter, anode_outlet,
                cathode_fr, cathode_filter, cathode_outlet, lpt_id):
        Updates related parts to the manifold in the database based on assembly data.   
    get_allocated_manifolds():
        Retrieves a list of allocated manifolds from the database.
    add_manifold_assembly_data(assembly_file):
        Adds manifold assembly data from the specified Excel file.
    update_lpt_certification():
        Updates LPT certification data in the database.
    update_manifold_certification():
        Updates manifold certification data in the database.
    manifold_query():
        Instantiates a ManifoldQuery object for querying manifold data.
    """

    def __init__(self, session: "Session", fms: "FMSDataStructure", signal_threshold: float = 7.5, signal_tolerance: float = 0.05, 
                 pressure_threshold: float = 0.2):
        
        self.Session = session
        self.fms = fms
        self.signal_threshold = signal_threshold
        self.signal_tolerance = signal_tolerance
        self.pressure_threshold = pressure_threshold
        self.manifold_assembly_data = []
        self.temp_cells = [i.value for i in LPTCoefficientParameters if 't' in i.value.lower() and not i.value.startswith('lpt_id')]
        self.pressure_cells = [i.value for i in LPTCoefficientParameters if 'p' in i.value.lower() and not i.value.startswith('lpt_id')]

    def listen_to_lpt_calibration(self, lpt_calibration: str = "") -> None:
        """
        Listens for new LPT calibration data and updates the database accordingly.
        """
        if not lpt_calibration:
            print("No LPT calibration directory specified. Exiting listener.")
            return
        
        data_folder = os.path.join(os.getcwd(), lpt_calibration)
        
        try:
            self.lpt_listener = LPTListener(path=data_folder)
            print(f"Started monitoring LPT calibration data in: {data_folder}")
            while True:
                try:
                    time.sleep(1)  # Keep the script running to monitor for new files
                    
                    # Check if listener has processed new data
                    if self.lpt_listener.processed:
                        if hasattr(self.lpt_listener, 'lpt_data') and self.lpt_listener.lpt_data:
                            self.lpt_coefficients = self.lpt_listener.lpt_data.lpt_coefficients
                            self.lpt_calibration = self.lpt_listener.lpt_data.lpt_calibration
                            self.temp_cells = self.lpt_listener.lpt_data.temp_cells
                            self.pressure_cells = self.lpt_listener.lpt_data.pressure_cells
                            self.update_lpt_calibration()
                            self.lpt_listener.processed = False
                except Exception as e:
                    print(f"Error in LPT listener loop: {str(e)}")
                    print("Listener will continue monitoring...")
                    traceback.print_exc()
                    
        except KeyboardInterrupt:
            print("Stopping LPT test results listener...")
            if hasattr(self, 'lpt_listener') and self.lpt_listener:
                self.lpt_listener.observer.stop()
                self.lpt_listener.observer.join()
        except Exception as e:
            print(f"Fatal error in LPT calibration listener: {str(e)}")
            traceback.print_exc()
            # Try to restart the listener after a brief delay
            time.sleep(5)
            print("Attempting to restart LPT calibration listener...")
            self.listen_to_lpt_calibration(lpt_calibration=lpt_calibration)

    def get_lpt_status(self, signal: np.ndarray, pressures: np.ndarray) -> dict:
        """
        Determines the LPT status based on signal and pressure data.
        Args:
            signal (np.ndarray): Array of signal values.
            pressures (np.ndarray): Array of pressure values.
        Returns:
            dict: Dictionary containing 'status' and adjusted 'signal'.
        """
        if not signal or not pressures or len(signal) != len(pressures):
            raise ValueError("Signal and pressure arrays must be non-empty and of equal length.")

        pressures = np.asarray(pressures)
        signal = np.asarray(signal)

        check_idx = np.argmin(np.abs(pressures - self.pressure_threshold))
        check_signal = signal[check_idx]
        adjusted_signal = check_signal + self.signal_tolerance
        status_dict = {
            'status': None,
            'signal': adjusted_signal
        }

        if adjusted_signal < self.signal_threshold:
            status_dict['status'] = LimitStatus.TRUE
        elif np.isclose(adjusted_signal, self.signal_threshold, atol=1e-3):
            status_dict['status'] = LimitStatus.ON_LIMIT
        else:
            status_dict['status'] = LimitStatus.FALSE

        return status_dict

    def update_lpt_calibration(self, data: ManifoldData = None) -> None:
        """
        Update the LPT calibration data in the database.
        """
        session: "Session" = self.Session()
        self.lpt_coefficients: dict = data.lpt_coefficients
        self.lpt_calibration: dict = data.lpt_calibration
        try:
            for lpt_id, coefficients in self.lpt_coefficients.items():
                # Check if LPTCalibration already exists
                pressure_coefficients = coefficients['pressure_coefficients']
                temperature_coefficients = coefficients['temperature_coefficients']
                existing_coefficients = session.query(LPTCoefficients).filter_by(lpt_id=lpt_id).all()
                if existing_coefficients:
                    for entry in existing_coefficients:
                        session.delete(entry)
                    session.commit()
                for idx,cp in enumerate(pressure_coefficients):
                    if (isinstance(cp, float) and np.isnan(cp)) or str(cp).lower() == "nan":
                        continue
                    coefficient_entry = LPTCoefficients(
                        lpt_id=lpt_id,
                        parameter_name=self.pressure_cells[idx],
                        parameter_value = cp,
                    )
                    session.merge(coefficient_entry)

                for idx,ct in enumerate(temperature_coefficients):
                    if (isinstance(ct, float) and np.isnan(ct)) or str(ct).lower() == "nan":
                        continue
                    coefficient_entry = LPTCoefficients(
                        lpt_id=lpt_id,
                        parameter_name=self.temp_cells[idx],
                        parameter_value = ct,
                    )
                    session.merge(coefficient_entry)

                
            for lpt_id, calibration_data in self.lpt_calibration.items():
                lpt_calibration_entry = LPTCalibration(
                    lpt_id=lpt_id,
                    base_resistance=calibration_data['base_resistance'],
                    base_signal = calibration_data['base_signal'],
                    signal=calibration_data['signal'],
                    resistance=calibration_data['resistance'],
                    p_calculated=calibration_data['pressure'],
                    temp_calculated=calibration_data['temperature'],
                    file_reference=calibration_data.get('file_reference', None),
                    within_limits = self.get_lpt_status(calibration_data['signal'], calibration_data['pressure'])['status']
                )
                session.merge(lpt_calibration_entry)

            session.commit()
            # self.fms.print_table(LPTCoefficients)
            # self.fms.print_table(LPTCalibration)
        except Exception as e:
            session.rollback()
            print(f"Error updating LPT calibration data: {str(e)}")
            traceback.print_exc()
        finally:
            session.close()

    def convert_FR_id(self, session: "Session", type: str, fr_id: str, fms_id: str = None) -> str:
        """
        Converts an ambiguous FR ID to the correct format based on type and availability.
        Args:
            session (Session): SQLAlchemy session for database queries.
            type (str): Type of FR ('anode' or 'cathode').
            fr_id (str): Ambiguous FR ID to convert.
            fms_id (str, optional): FMS ID for prioritization. Defaults to None.
        Returns:
            str: Converted FR ID or original if not found.
        """
        self.converted_ids = []
        start_fms = fms_id.split("-")[0] if fms_id else None
        fr_id = str(fr_id).zfill(3)

        try:
            if type == 'anode':
                # First, try matching with FMS "24" priority
                if start_fms == "24":
                    fr = session.query(AnodeFR).filter(
                        ~AnodeFR.fr_id.in_(self.converted_ids),
                        ~AnodeFR.fr_id.in_(self.anode_ids),
                        AnodeFR.fr_id.startswith("C24"),
                        AnodeFR.fr_id.endswith(fr_id),
                        AnodeFR.flow_rates != None
                    ).first()
                    if fr:
                        self.converted_ids.append(fr.fr_id)
                        return fr.fr_id

                # Regular search without FMS priority
                filters = [~AnodeFR.fr_id.in_(self.converted_ids),
                           ~AnodeFR.fr_id.in_(self.anode_ids),
                        AnodeFR.fr_id.endswith(fr_id),
                        AnodeFR.flow_rates != None]

                fr = session.query(AnodeFR).filter(*filters).first()
                if fr:
                    self.converted_ids.append(fr.fr_id)
                    return fr.fr_id

                # FRCertification fallback
                filters_cert = [~FRCertification.anode_fr_id.in_(self.converted_ids),
                                ~FRCertification.anode_fr_id.in_(self.anode_ids),
                                FRCertification.anode_fr_id.endswith(fr_id)]
                
                fr = session.query(FRCertification).filter(*filters_cert).first()
                if fr:
                    self.converted_ids.append(fr.anode_fr_id)
                    return fr.anode_fr_id

            elif type == 'cathode':
                if start_fms == "24":
                    fr = session.query(CathodeFR).filter(
                        ~CathodeFR.fr_id.in_(self.converted_ids),
                        ~CathodeFR.fr_id.in_(self.cathode_ids),
                        CathodeFR.fr_id.startswith("C24"),
                        CathodeFR.fr_id.endswith(fr_id),
                        CathodeFR.flow_rates != None
                    ).first()
                    if fr:
                        self.converted_ids.append(fr.fr_id)
                        return fr.fr_id

                filters = [~CathodeFR.fr_id.in_(self.converted_ids),
                            ~CathodeFR.fr_id.in_(self.cathode_ids),
                        CathodeFR.fr_id.endswith(fr_id),
                        CathodeFR.flow_rates != None]
                fr = session.query(CathodeFR).filter(*filters).first()
                if fr:
                    self.converted_ids.append(fr.fr_id)
                    return fr.fr_id

                # FRCertification fallback
                filters_cert = [~FRCertification.cathode_fr_id.in_(self.converted_ids),
                                ~FRCertification.cathode_fr_id.in_(self.cathode_ids),
                                FRCertification.cathode_fr_id.endswith(fr_id)]
                fr = session.query(FRCertification).filter(*filters_cert).first()
                if fr:
                    self.converted_ids.append(fr.cathode_fr_id)
                    return fr.cathode_fr_id

            return fr_id

        except Exception as e:
            print(f"Error converting FR ID: {str(e)}")
            traceback.print_exc()
            return None
        
    def extract_assembly_from_excel(self) -> None:
        """
        Extracts manifold assembly data from the Excel template.
        """
        wb = openpyxl.open(self.assembly_file, data_only=True)
        wb.active = wb['20025.10.AB']
        self.anode_ids = []
        self.cathode_ids = []
        sheet = wb.active

        for row in sheet.iter_rows(min_row=3, max_col = 25, values_only=True):
            if all(cell is None for cell in row[2:]):
                break
            set_id = row[0]
            drawing = '20025.10.AB' + '-' + row[1]
            allocated = row[14]
            allocated = allocated[:6] if allocated else None
            assembly_certification = row[15]
            manifold_certification = row[16]
            anode_fr = row[17]
            if anode_fr:
                parts = str(anode_fr).split('-')
                if len(parts) == 3:
                    parts[2] = parts[2].zfill(3)
                    anode_fr = '-'.join(parts)
            anode_filter = row[18]
            anode_outlet = row[19]
            cathode_fr = row[20]
            if cathode_fr:
                parts = str(cathode_fr).split('-')
                if len(parts) == 3:
                    parts[2] = parts[2].zfill(3)
                    cathode_fr = '-'.join(parts)

            cathode_filter = row[21]
            cathode_outlet = row[22]
            lpt_id = row[23]
            lpt_id = lpt_id[-7:] if lpt_id else None

            pattern = r"^C\d{2}-\d{4}-\d{3}$"

            # Perform the match
            if anode_fr:
                if not re.match(pattern, str(anode_fr)):
                    anode_fr = self.convert_FR_id(self.Session(), 'anode', anode_fr, allocated)
                else:
                    self.anode_ids.append(anode_fr)

            if cathode_fr:
                if not re.match(pattern, str(cathode_fr)):
                    cathode_fr = self.convert_FR_id(self.Session(), 'cathode', cathode_fr, allocated)
                else:
                    self.cathode_ids.append(cathode_fr)

            row = {
                'set_id': set_id,
                'drawing': drawing,
                'allocated': allocated,
                'assembly_certification': assembly_certification,
                'manifold_certification': manifold_certification,
                'anode_fr': anode_fr,
                'anode_filter': anode_filter,
                'anode_outlet': anode_outlet,
                'cathode_fr': cathode_fr,
                'cathode_filter': cathode_filter,
                'cathode_outlet': cathode_outlet,
                'lpt_id': lpt_id
            }
            self.manifold_assembly_data.append(row)

    def update_related_parts(self, session: "Session", set_id: str, anode_fr: str, anode_filter: str, anode_outlet: str, \
                             cathode_fr: str, cathode_filter: str, cathode_outlet: str, lpt_id: str) -> None:
        """
        Updates related parts to the manifold in the database based on assembly data.
        Args:
            session (Session): SQLAlchemy session for database operations.
            set_id (str): Set ID of the manifold.
            anode_fr (str): Anode FR ID.
            anode_filter (str): Anode filter certification.
            anode_outlet (str): Anode outlet certification.
            cathode_fr (str): Cathode FR ID.
            cathode_filter (str): Cathode filter certification.
            cathode_outlet (str): Cathode outlet certification.
            lpt_id (str): LPT serial number.
        """
        if anode_fr:
            anode = session.query(AnodeFR).filter_by(fr_id=anode_fr).first()
            set_check = session.query(AnodeFR).filter_by(set_id=set_id).first()
            if anode and not set_check:
                print('anode found')
                anode.set_id = set_id
                anode_filter_entry = session.query(FRCertification).filter_by(certification=anode_filter, part_name='ejay filter', anode_fr_id=None).first()
                anode_outlet_entry = session.query(FRCertification).filter_by(certification=anode_outlet, part_name='restrictor outlet', anode_fr_id=None).first()
                if anode_filter_entry:
                    anode_filter_entry.anode_fr_id = anode.fr_id
                if anode_outlet_entry:
                    anode_outlet_entry.anode_fr_id = anode.fr_id

        if cathode_fr:
            cathode = session.query(CathodeFR).filter_by(fr_id=cathode_fr).first()
            set_check = session.query(CathodeFR).filter_by(set_id=set_id).first()
            if cathode and not set_check:
                print('cathode found')
                cathode.set_id = set_id
                cathode_filter_entry = session.query(FRCertification).filter_by(certification=cathode_filter, part_name='ejay filter', cathode_fr_id=None).first()
                cathode_outlet_entry = session.query(FRCertification).filter_by(certification=cathode_outlet, part_name='restrictor outlet', cathode_fr_id=None).first()
                if cathode_filter_entry:
                    cathode_filter_entry.cathode_fr_id = cathode.fr_id
                if cathode_outlet_entry:
                    cathode_outlet_entry.cathode_fr_id = cathode.fr_id

        if lpt_id:
            lpt_calibration = session.query(LPTCalibration).filter_by(set_id=None, lpt_id=lpt_id).first()
            if lpt_calibration:
                lpt_calibration.set_id = set_id

    def get_allocated_manifolds(self) -> dict:
        """
        Retrieves a list of allocated manifolds from the database.
        Returns:
            dict: Dictionary of allocated manifolds with allocated ID as key.
        """
        try:
            session: "Session" = self.Session()
            allocated_manifolds = session.query(ManifoldStatus).filter(ManifoldStatus.allocated != None).all()
            allocated_dict = {manifold.allocated: manifold for manifold in allocated_manifolds}
            return allocated_dict
        except Exception as e:
            print(f"Error retrieving allocated manifolds: {str(e)}")
            traceback.print_exc()
            return {}

    def add_manifold_assembly_data(self, assembly_file: str = None) -> None:
        """
        Adds manifold assembly data from the specified Excel file.
        Args:
            assembly_file (str, optional): Path to the Excel template. Defaults to None.
        """
        current_session_allocated = {}
        session = None
        if assembly_file:
            self.assembly_file = assembly_file
        try:
            session: "Session" = self.Session()
            self.extract_assembly_from_excel()
            with_cert = [row for row in self.manifold_assembly_data if row.get('manifold_certification')]
            without_cert = [row for row in self.manifold_assembly_data if not row.get('manifold_certification')]
            ordered_rows = with_cert + without_cert
            allocated_dict: dict[str, ManifoldStatus] = self.get_allocated_manifolds()
            print(current_session_allocated, allocated_dict)
            for row in ordered_rows:
                set_id = row['set_id']
                drawing = row['drawing']
                allocated = row['allocated']
                if allocated and (allocated in allocated_dict or allocated in current_session_allocated):
                    print(f"Clearing previous allocation for manifold: {allocated}")
                    faulty_manifold = allocated_dict.get(allocated) or current_session_allocated.get(allocated)
                    faulty_manifold.allocated = None
                    allocated_dict.pop(allocated, None)
                    current_session_allocated.pop(allocated, None)
                    session.merge(faulty_manifold)
                    session.commit()
                
                assembly_certification = row['assembly_certification']
                manifold_certification = row['manifold_certification']
                anode_fr = row['anode_fr']
                anode_filter = row['anode_filter']
                anode_outlet = row['anode_outlet']
                cathode_fr = row['cathode_fr']
                cathode_filter = row['cathode_filter']
                cathode_outlet = row['cathode_outlet']
                lpt_id = row['lpt_id']
                existing_entry = session.query(ManifoldStatus).filter_by(set_id=set_id).first()

                if cathode_fr and anode_fr:
                    anode_record = session.query(AnodeFR).filter_by(fr_id=anode_fr).first()
                    cathode_record = session.query(CathodeFR).filter_by(fr_id=cathode_fr).first()
                    anode_flows = np.array(anode_record.flow_rates) if anode_record and anode_record.flow_rates is not None else np.array([])
                    cathode_flows = np.array(cathode_record.flow_rates) if cathode_record and cathode_record.flow_rates is not None else np.array([])
                    if anode_flows.size > 0 and cathode_flows.size > 0:
                        ratio = np.average(anode_flows / cathode_flows)
                    else:
                        ratio = 13
                else:
                    ratio = 13

                if existing_entry:
                    existing_entry.assembly_drawing = drawing
                    existing_entry.allocated = allocated if allocated else existing_entry.allocated
                    existing_entry.assembly_certification = assembly_certification if assembly_certification else existing_entry.assembly_certification
                    existing_entry.certification = manifold_certification if manifold_certification else existing_entry.certification
                    existing_entry.drawing = drawing
                    existing_entry.ac_ratio = ratio
                    existing_entry.ac_ratio_specified = round(ratio)
                    existing_entry.status = ManifoldProgressStatus.ASSEMBLY_COMPLETED
                    current_session_allocated[allocated] = existing_entry
                else:
                    available_entry = session.query(ManifoldStatus).filter_by(set_id=None, allocated=None, status=ManifoldProgressStatus.AVAILABLE, certification=manifold_certification).first() if manifold_certification \
                        else session.query(ManifoldStatus).filter_by(set_id=None, allocated=None, status=ManifoldProgressStatus.AVAILABLE).first()
                    if available_entry:
                        available_entry.set_id = set_id
                        available_entry.allocated = allocated if allocated else available_entry.allocated
                        available_entry.assembly_certification = assembly_certification if assembly_certification else available_entry.assembly_certification
                        available_entry.assembly_drawing = drawing if drawing else available_entry.assembly_drawing
                        available_entry.ac_ratio = ratio if ratio else 13
                        available_entry.ac_ratio_specified = 13
                        available_entry.status = ManifoldProgressStatus.ASSEMBLY_COMPLETED if not assembly_certification else ManifoldProgressStatus.WELDING_COMPLETED
                        current_session_allocated[allocated] = available_entry
                    else:
                        new_entry = ManifoldStatus(
                            set_id=set_id,
                            assembly_drawing=drawing,
                            allocated=allocated,
                            assembly_certification=assembly_certification,
                            certification=manifold_certification,
                            status=ManifoldProgressStatus.ASSEMBLY_COMPLETED if not assembly_certification else ManifoldProgressStatus.WELDING_COMPLETED,
                            ac_ratio=ratio if ratio else 13,
                            ac_ratio_specified=13
                        )
                        session.add(new_entry)
                        current_session_allocated[allocated] = new_entry

                self.update_related_parts(
                        session,
                        set_id,
                        anode_fr,
                        anode_filter,
                        anode_outlet,
                        cathode_fr,
                        cathode_filter,
                        cathode_outlet,
                        lpt_id
                    )
                    
            session.commit()
            # self.fms.print_table(ManifoldStatus)
            # self.fms.print_table(AnodeFR)
            # self.fms.print_table(CathodeFR)
            
        except Exception as e:
            print(f"Error updating manifold assembly data: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()
        finally:
            if session:
                session.close()

    def update_lpt_certification(self, data: ManifoldData = None) -> None:
        """
        Update the LPT certification data in the database.
        """
        self.data = data
        self.certification_data = self.data.extracted_lpt_serials
        self.certification = self.data.certification
        try:
            session: "Session" = self.Session()
            existing_entries = session.query(LPTCalibration).all()
            for serial in self.certification_data:
                existing_entry = next((entry for entry in existing_entries if entry.lpt_id == serial), None)
                if not existing_entry:
                    lpt_calibration_entry = LPTCalibration(
                        lpt_id=serial,
                        set_id=None, 
                        certification=self.certification,  
                        base_resistance=None,
                        base_signal=None,
                        signal=None,
                        resistance=None,
                        p_calculated=None,
                        temp_calculated=None,
                        file_reference=None
                    )
                    session.add(lpt_calibration_entry)

                else:
                    existing_entry.certification = self.certification
                    session.merge(existing_entry)
                
            session.commit()
            
            self.fms.print_table(LPTCalibration)

        except Exception as e:
            print(f"Error updating lpt certification: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()
        finally:
            if session:
                session.close()            
            
    def update_manifold_certification(self, data: ManifoldData = None) -> None:
        """
        Update the manifold certification data in the database.
        """
        session: "Session" = self.Session()
        self.manifold_parts: dict = data.extracted_manifold_parts
        try:
            for part_name, parts in self.manifold_parts.items():
                if part_name == 'manifold':
                    drawing = parts['drawing']
                    certification = parts.get('certification')
                    amount = parts['amount'] if 'amount' in parts else 1
                    existing_entries = session.query(ManifoldStatus).filter_by(certification = certification).all()
                    if existing_entries:
                        print("This certification already exists in the database, skipping addition.")
                        continue
                    for _ in range(amount):
                        manifold_entry = ManifoldStatus(
                            drawing=drawing,
                            certification=certification,
                            status=ManifoldProgressStatus.AVAILABLE
                        )
                        session.add(manifold_entry)
                elif part_name == 'lpt assembly':
                    parts: dict[str, dict[str, Any]]
                    for sn, details in parts.items():
                        existing_entry = session.query(ManifoldStatus).filter_by(set_id=sn).first()
                        if existing_entry:
                            existing_entry.assembly_certification = details.get('certification')
                            existing_entry.assembly_drawing = details.get('drawing', None)
                            existing_entry.ac_ratio_specified = details.get('ratio', None)
                            existing_entry.status = ManifoldProgressStatus.WELDING_COMPLETED
                        else:
                            manifold_entry = ManifoldStatus(
                                set_id=sn,
                                assembly_certification=details.get('certification'),
                                assembly_drawing=details.get('drawing', None),
                                status=ManifoldProgressStatus.WELDING_COMPLETED,
                                ac_ratio_specified=details.get('ratio', None)
                            )
                            session.add(manifold_entry)
            session.commit()
            self.fms.print_table(ManifoldStatus)
        except Exception as e:
            print(f"Error updating manifold certification: {str(e)}")
            if session:
                session.rollback()
            traceback.print_exc()
        finally:
            if session:
                session.close()

    def manifold_query(self) -> None:
        """
        Instantiates a ManifoldQuery object for querying manifold data.
        """
        query = ManifoldQuery(session=self.Session(), fms_entry=None, manifold_status=ManifoldStatus,
                 lpt_calibration=LPTCalibration, lpt_coefficients=LPTCoefficients,
                 anode_fr=AnodeFR, cathode_fr=CathodeFR, coefficient_enum=LPTCoefficientParameters,
                 fr_certification=FRCertification, fr_status=FRStatus, limit_status=LimitStatus)
        
        query.manifold_query_field()

if __name__ == "__main__":
    manifold_file = "certifications/C25-0036 Coremans 513359.pdf"
    # assembly_file = "certifications/C25-0487 Veldlaser 513898.pdf"
    # lpt_data = LPT_data(pdf_file = assembly_file)
    # lpt_data.get_manifold_ocr_certification()

    # print(lpt_data.extracted_manifold_parts)
    # file = "certifications/C24-0112 Keller 512467.pdf"
    # Example usage
    data = ManifoldData(pdf_file = manifold_file, coremans=True)
    company = "Keller"
    # reader = TextractReader(pdf_file=file, bucket_folder="Certifications", company=company, load_json=load_from_json, save_json=save_to_json)
    # total_lines = reader.get_text()
    # lpt_data.get_lpt_certification(total_lines)
    data.get_manifold_ocr_certification()
    print(data.extracted_manifold_parts)
    print(data.extracted_lpt_serials)