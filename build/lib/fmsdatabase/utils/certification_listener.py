# Standard library
import os
import re
import threading
import traceback
from typing import TYPE_CHECKING
import queue

# Third-party imports
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Local application imports
from .general_utils import TVParts, FRParts
from .textract import TextractReader
from ..utils.tv import TVData
from ..utils.fr import FRData
from ..utils.hpiv import HPIVData
from ..utils.lpt_manifold import ManifoldData

# Type-checking imports
if TYPE_CHECKING:
    from ..fms_data_structure import FMSDataStructure


class CertificationListener(FileSystemEventHandler):
    """
    Monitors a directory for newly created certification PDF files and processes
    them asynchronously. A worker thread handles queued files sequentially to
    ensure ordered, non-overlapping processing.

    Parameters
    ----------
    fms : FMSDataStructure, optional
        Data structure providing SQL interface access for certification updates.
    path : str, optional
        Directory to watch for new certification PDFs.
    load_json : callable, optional
        Function used to load cached JSON data such as previously processed parts.
    save_json : callable, optional
        Function used to persist JSON data for state tracking.

    Attributes
    ----------
    observer : Observer
        Watches the filesystem for new PDF files.
    file_queue : queue.Queue
        Holds incoming PDF files awaiting processing.
    worker_thread : threading.Thread
        Consumes items from the queue and processes them.
    certification : str or None
        Currently processed certification identifier.
    companies : list[str]
        Known companies used for matching file origins.
    part_certification_map : dict
        Maps part categories to lists of keywords used for detection.
    object_map : dict
        Maps part categories to their data-handling objects.
    sql_map : dict
        Maps part categories to SQL update functions.
    function_map : dict
        Maps part categories to functions that extract certification details.
    """

    def __init__(self, fms: "FMSDataStructure" = None, path: str="certifications", load_json: callable = None, save_json: callable = None):
        self.path = os.path.join(os.getcwd(), path)
        self.observer = Observer()
        self.observer.schedule(self, self.path)
        self.observer.start()

        self.load_from_json = load_json
        self.save_to_json = save_json
        self.certification = None
        self.found_parts = self.load_from_json("previous_parts")
        self.previous_part = self.load_from_json("processed_part")
        # Queue to store files awaiting processing
        self.file_queue = queue.Queue()
        # Worker thread
        self.worker_thread = threading.Thread(target=self.process_queue, daemon=True)
        self.worker_thread.start()

        self.fms = fms
        self.companies = [
            'sk technology', 'sk', 'veldlaser', 'ceratec', 'pretec', 'veld laser',
            'branl', 'ejay filtration', 'space solutions', 'ss', 'spacesolutions',
            'keller', 'coremans'
        ]
        self.company = None
        self.tv_data = TVData()
        self.fr_data = FRData()
        self.hpiv_data = HPIVData()
        self.manifold_data = ManifoldData()
        self.part_certification_map = {
            "TV": [i.value for i in TVParts],
            "lpt_assembly": ['lpt assembly', 'lptassembly'],
            "LPT": ['keller'],
            "Manifold": ['manifold'],
            "FR": [i.value for i in FRParts],
            "HPIV": ['hpiv', 'space solutions'],
        }

        self.object_map = {
            "TV": self.tv_data,
            "lpt_assembly": self.manifold_data,
            "LPT": self.manifold_data,
            "Manifold": self.manifold_data,
            "FR": self.fr_data,
            "HPIV": self.hpiv_data,
        }

        self.sql_map = {
            "TV": self.fms.tv_sql.update_tv_certification,
            "lpt_assembly": self.fms.lpt_sql.update_manifold_certification,
            "LPT": self.fms.lpt_sql.update_lpt_certification,
            "Manifold": self.fms.lpt_sql.update_manifold_certification,
            "FR": self.fms.fr_sql.update_fr_certification,
            "HPIV": self.fms.hpiv_sql.update_hpiv_certifications,
        }

        self.function_map = {
            "TV": self.tv_data.get_certification,
            "lpt_assembly": self.manifold_data.get_assembly_certification,
            "LPT": self.manifold_data.get_lpt_certification,
            "Manifold": self.manifold_data.get_manifold_certification,
            "FR": self.fr_data.get_certification,
            "HPIV": self.hpiv_data.get_certification,
        }

        print(f"Started monitoring certification files in {self.path}")

    def detect_part(self, total_lines: list[str], part_certification_map: dict) -> str | None:
        """
        Identifies which part should be processed for the current certification.

        This scans the extracted PDF text, detects parts belonging to the active
        certification, and filters out parts that appear to belong to other
        certifications. Returns the first valid match in reading order.

        Parameters
        ----------
        total_lines : list[str]
            Lines of text extracted from the PDF.
        part_certification_map : dict
            Mapping of part names to lists of identifying keywords.

        Returns
        -------
        str or None
            The detected part name, or ``None`` if no valid match is found.
        """
        # Detect all parts in this PDF
        all_parts = self.detect_all_parts(total_lines, part_certification_map)

        # Build a list of lines associated with other certifications
        other_cert_lines = []
        for idx, line in enumerate(total_lines):
            cert_match = re.search(r'\b(C\d{2}-\d{4})\b', line, re.IGNORECASE)
            if cert_match:
                certification = cert_match.group(1).upper()
                if self.certification and certification != self.certification:
                    # Add a larger range of lines around this certification
                    start = max(0, idx - 8)
                    end = min(len(total_lines), idx + 8)
                    other_cert_lines.extend(total_lines[start:end])

        # Now look for parts from the current certification
        for idx, line in enumerate(total_lines):
            for part in all_parts:
                for keyword in part_certification_map[part]:
                    pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                    if re.search(pattern, line.lower()):
                        # Skip if this part occurs in lines from other certifications
                        if not any(re.search(pattern, check_line.lower()) for check_line in other_cert_lines):
                            print(part)
                            return part

        return None
    
    def detect_all_parts(self, total_lines: list[str], part_certification_map: dict) -> list[str]:
        """
        Returns a list of all parts found in total_lines, in order of appearance.
        """
        found_parts = []

        for line in total_lines:
            for part, keywords in part_certification_map.items():
                for keyword in keywords:
                    pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                    if re.search(pattern, line):
                        if part not in found_parts:
                            found_parts.append(part)
        return found_parts

    def on_created(self, event):
        """When a new file is created, add it to the queue."""
        if event.is_directory or not event.src_path.endswith('.pdf'):
            return
        print(f"New certification file detected: {event.src_path}")
        self.file_queue.put(event.src_path)  # Add to queue

    def process_queue(self):
        """Worker thread that processes one file at a time."""
        while True:
            pdf_file = self.file_queue.get()  # Wait until a file is available
            try:
                match = re.search(r'C\d{2}-\d{4}', os.path.basename(pdf_file))
                self.certification = match.group(0) if match else None
                self.process_file(pdf_file)
            except Exception as e:
                print(f"Error processing {pdf_file}: {e}")
                traceback.print_exc()
            finally:
                self.file_queue.task_done()

    def process_file(self, pdf_file: str) -> None:
        """
        Processes a single certification PDF file.

        Extracts text using the Textract reader, determines which part of the
        certification the file represents, parses the relevant information,
        and applies database updates through the mapped SQL handlers.

        Parameters
        ----------
        pdf_file : str
            Path to the PDF file being processed.

        Returns
        -------
        None
        """
        if any(company in pdf_file.lower() for company in self.companies):
            self.company = next(company for company in self.companies if company in pdf_file.lower())
            try:
                reader = TextractReader(pdf_file=pdf_file, bucket_folder="Certifications", company=self.company, load_json=self.load_from_json, save_json=self.save_to_json)
                total_lines = reader.get_text()
                # print(total_lines)
            except Exception as e:
                print(f"Error processing PDF file {pdf_file}: {e}")
                traceback.print_exc()
                return

            try:
                process_part = self.detect_part(total_lines, self.part_certification_map)

                if not process_part:
                    print(f"No matching part found for {pdf_file}")
                    return

                self.previous_part = process_part
                print(f"Detected part: {process_part}")
                obj: TVData | FRData | HPIVData | ManifoldData = self.object_map[process_part]
                obj.pdf_file = pdf_file
                if hasattr(obj, 'company'):
                    obj.company = self.company

                # Process certification lines and update DB
                self.function_map[process_part](total_lines)
                self.sql_map[process_part](obj)

                # Reset any attributes if needed
                if hasattr(obj, 'total_amount'):
                    obj.total_amount = None

                if hasattr(obj, 'company'):
                    obj.company = None

                if hasattr(obj, 'drawing_reference'):
                    obj.drawing_reference = None

            except Exception as e:
                print(f"Error in part detection or function mapping: {e}")
                traceback.print_exc()
