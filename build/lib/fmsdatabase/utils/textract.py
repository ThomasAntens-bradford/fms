import boto3
import time
from collections import defaultdict
import os
import fitz
import io
from datetime import datetime

from .general_utils import load_from_json, save_to_json

class TextractReader:
    """
    Handles uploading PDF files to S3, processing them with Textract, 
    and extracting text and table data. Supports automatic handling of 
    multi-page PDFs, free-tier page limits, and resuming existing Textract jobs.

    Parameters
    ----------
    pdf_file : str
        Local path to the PDF file.
    bucket_folder : str
        S3 folder where files will be uploaded.
    bucket_name : str, optional
        Name of the S3 bucket. Defaults to 'textractresultsfms'.
    company : str, optional
        Company identifier used for special handling rules.
    max_pages_free : int, optional
        Maximum pages allowed per month before triggering free-tier warnings.
    save_json : callable, optional
        Callable used for saving JSON state.
    load_json : callable, optional
        Callable used for loading JSON state.

    Attributes
    ----------
    client : boto3.client
        Boto3 Textract client.
    s3_client : boto3.client
        Boto3 S3 client.
    max_pages_free : int
        Maximum pages allowed per month before triggering free-tier warnings.
    pages_processed_data : dict
        Tracks pages processed per month.
    current_month : str
        Current month in 'YYYY-MM' format.
    pages_processed_this_month : dict
        Pages processed in the current month.
    processed_text : dict
        Cache of processed text per S3 key.
    bucket_name : str
        Name of the S3 bucket.
    pdf_file : str
        Local path to the PDF file.
    bucket_folder : str
        S3 folder where files will be uploaded.
    company : str
        Company identifier used for special handling rules.
    cut_required : bool
        Indicates if the PDF needs to be truncated before upload.
    already_processed : bool
        Indicates if the PDF has already been processed.
    page_limit : int
        Company-specific page limit for processing.
    general_page_limit : int
        General page limit for processing.
    page_count : int
        Total number of pages in the PDF.
    start_page : int
        Starting page number for processing.
    s3_key : str
        S3 object key for the uploaded PDF.
    """
    def __init__(self, pdf_file: str, bucket_folder: str, bucket_name: str = 'textractresultsfms', company: str = None, max_pages_free: int = 1000):
        self.client = boto3.client("textract")
        self.s3_client = boto3.client("s3")
        self.max_pages_free = max_pages_free
        self.pages_processed_data = load_from_json("pages_processed") or {}
        self.current_month = datetime.now().strftime("%Y-%m")

        if self.current_month not in self.pages_processed_data:
            self.pages_processed_data[self.current_month] = {"pages": 0}

        self.pages_processed_this_month = self.pages_processed_data[self.current_month]

        self.processed_text = load_from_json("certifications_text")
        if not self.processed_text:
            self.processed_text = {}
        self.bucket_name = bucket_name
        self.pdf_file = pdf_file
        self.bucket_folder = bucket_folder
        self.company = company
        self.cut_required = False
        self.already_processed = False
        self.page_limit = 30
        self.general_page_limit = 20
        self.page_count = 0
        self.start_page = 1
        self.s3_key = f"{self.bucket_folder.strip('/').replace('\\', '/')}/{os.path.basename(self.pdf_file)}"

    def get_page_count(self, pdf_path: str = None) -> int:
        """
        Return the number of pages in a PDF.

        Parameters
        ----------
        pdf_path : str, optional
            Path to the PDF file. Defaults to the instance PDF.

        Returns
        -------
        int
            Number of pages in the PDF.
        """
        path = pdf_path or self.pdf_file
        doc = fitz.open(path)
        page_count = doc.page_count
        doc.close()
        return page_count

    def generate_cut_pdf(self, start_page: int = None, end_page: int = None, general_page_limit: bool = True) -> io.BytesIO:
        """
        Generate a truncated PDF from a page range.

        Limits page extraction according to general or company-specific rules
        and returns an in-memory BytesIO object of the resulting PDF.

        Parameters
        ----------
        start_page : int, optional
            Starting page number, 1-based.
        end_page : int, optional
            Ending page number, inclusive.
        general_page_limit : bool, optional
            Whether to apply the general page limit rules.

        Returns
        -------
        BytesIO
            In-memory PDF bytes.
        """
        total_pages = self.get_page_count()
        if start_page is None: start_page = self.start_page
        if end_page is None: end_page = self.general_page_limit if general_page_limit else total_pages

        if general_page_limit: 
            if end_page - start_page + 1 > self.general_page_limit:
                end_page = start_page + self.general_page_limit - 1
        else: 
            if end_page - start_page + 1 > self.page_limit:
                end_page = start_page + self.page_limit - 1

        doc = fitz.open(self.pdf_file)  
        new_doc = fitz.open()
        
        for page_num in range(start_page - 1, min(end_page, total_pages)):
            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
        
        pdf_bytes = io.BytesIO()
        new_doc.save(pdf_bytes)
        pdf_bytes.seek(0)

        new_doc.close()
        doc.close()

        return pdf_bytes

    def upload_file_to_s3(self, start_page: int = None, end_page: int = None) -> None:
        """
        Upload the PDF file or its truncated version to S3.

        Applies page-limit rules and avoids reuploading if already processed.

        Parameters
        ----------
        start_page : int, optional
            Start page for cutting the PDF.
        end_page : int, optional
            End page for cutting the PDF.

        Returns
        -------
        None
        """
        self.page_count = self.get_page_count()

        if self.company in ['sk technology', 'sk', 'sktechnology']:
            self.cut_required = (start_page is not None or end_page is not None or self.page_count > self.page_limit)
            general_page_limit = False
        else:
            self.cut_required = True
            general_page_limit = True

        if self.s3_key in self.processed_text:
            self.already_processed = True
            return

        if self.cut_required:
            pdf_bytes = self.generate_cut_pdf(start_page, end_page, general_page_limit=general_page_limit)
            self.s3_client.upload_fileobj(pdf_bytes, self.bucket_name, self.s3_key)
        else:
            self.s3_client.upload_file(self.pdf_file, self.bucket_name, self.s3_key)

    def start_job(self):
        """
        Start a Textract text-detection job.

        Returns
        -------
        str
            Textract Job ID.
        """
        response = self.client.start_document_text_detection(
            DocumentLocation={"S3Object": {"Bucket": self.bucket_name, "Name": self.s3_key}}
        )
        job_id = response["JobId"]
        print(f"Started job {job_id}")
        return job_id

    def is_job_complete(self, job_id: str) -> str:
        """
        Check the status of a Textract job.

        Parameters
        ----------
        job_id : str
            Job ID to check.

        Returns
        -------
        str
            Job status string.
        """
        response = self.client.get_document_text_detection(JobId=job_id)
        status = response["JobStatus"]
        return status

    def get_job_results(self, job_id: str) -> list[dict]:
        """
        Retrieve all Textract blocks for a completed job.

        Parameters
        ----------
        job_id : str
            Job ID to retrieve results for.

        Returns
        -------
        list[dict]
            Textract block objects.
        """
        blocks = []
        next_token = None

        while True:
            if next_token:
                response = self.client.get_document_text_detection(
                    JobId=job_id, NextToken=next_token
                )
            else:
                response = self.client.get_document_text_detection(JobId=job_id)

            blocks.extend(response["Blocks"])

            if "NextToken" in response:
                next_token = response["NextToken"]
            else:
                break

        page_count = sum(1 for b in blocks if b["BlockType"] == "PAGE")
        self.pages_processed_data[self.current_month]['pages'] += page_count
        save_to_json(self.pages_processed_data, "pages_processed")
        return blocks

    def process_pdf(self):
        """
        Process the uploaded PDF through Textract.

        Handles job creation, job resumption, polling,
        free-tier page checks, and final block retrieval.

        Returns
        -------
        list[dict]
            Textract block results.

        Raises
        ------
        RuntimeError
            If free-tier limits are exceeded or the job fails.
        """
        if self.already_processed:
            print(f"Skipping processing for {self.s3_key} as it has already been processed.")
            return

        if self.pages_processed_this_month['pages'] + self.page_count >= self.max_pages_free:
            raise RuntimeError("Free tier limit reached! Aborting to avoid charges.")

        job_ids = load_from_json("textract_job_ids") or {}
        job_id = job_ids.get(self.s3_key)

        if not job_id:
            job_id = self.start_job()
            job_ids[self.s3_key] = job_id
            save_to_json(job_ids, "textract_job_ids")
        else:
            print(f"Resuming existing Textract job {job_id}")

        retries = 0
        while True:
            try:
                status = self.is_job_complete(job_id)
                if status in ["SUCCEEDED", "FAILED"]:
                    break
                time.sleep(5)
                retries = 0
            except Exception as e:
                retries += 1
                if retries > 10:
                    raise RuntimeError(f"Too many connection failures: {e}")
                print(f"Connection lost or error: {e}. Retrying in 10 seconds...")
                time.sleep(10)

        if job_id in job_ids:
            del job_ids[self.s3_key]
            save_to_json(job_ids, "textract_job_ids")

        if status == "SUCCEEDED":
            return self.get_job_results(job_id)
        else:
            raise RuntimeError(f"Textract job {job_id} failed.")

    def extract_lines(self, blocks: list[dict]) -> list[str]:
        """
        Extract line-level text from Textract blocks.

        Parameters
        ----------
        blocks : list[dict]
            Textract block objects.

        Returns
        -------
        list[str]
            List of extracted text lines.
        """
        if self.already_processed:
            return self.processed_text.get(self.s3_key, [])
        
        lines = [
            block["Text"].lower()
            for block in blocks
            if block["BlockType"] == "LINE"
        ]
        self.processed_text[self.s3_key] = lines
        save_to_json(self.processed_text, "certifications_text")
        return lines
    
    def get_text(self, start_page: int = None, end_page: int = None) -> list[str]:
        """
        Obtain extracted text from the PDF through Textract.

        Handles S3 upload, job processing, and line extraction.

        Parameters
        ----------
        start_page : int, optional
            Start page for cutting the PDF before processing.
        end_page : int, optional
            End page for cutting.

        Returns
        -------
        list[str]
            Extracted text lines.
        """
        self.upload_file_to_s3(start_page=start_page, end_page=end_page)
        blocks = self.process_pdf()
        return self.extract_lines(blocks)

    def extract_tables(self, blocks: list[dict]) -> list[list[list[str]]]:
        """
        Extract tables from Textract block output.

        Parameters
        ----------
        blocks : list[dict]
            Textract block objects.

        Returns
        -------
        list[list[list[str]]]
            A list of tables, where each table is a list of rows,
            and each row is a list of cell text values.
        """
        block_map = {block["Id"]: block for block in blocks}

        tables = []
        for block in blocks:
            if block["BlockType"] == "TABLE":
                table = []

                cell_ids = []
                for rel in block.get("Relationships", []):
                    if rel["Type"] == "CHILD":
                        cell_ids.extend(rel["Ids"])

                cells = [block_map[cell_id] for cell_id in cell_ids if block_map[cell_id]["BlockType"] == "CELL"]
                table_cells = defaultdict(dict)
                max_row = 0
                max_col = 0

                for cell in cells:
                    row = cell["RowIndex"]
                    col = cell["ColumnIndex"]
                    max_row = max(max_row, row)
                    max_col = max(max_col, col)

                    text = ""
                    for rel in cell.get("Relationships", []):
                        if rel["Type"] == "CHILD":
                            words = [block_map[word_id]["Text"] for word_id in rel["Ids"] if block_map[word_id]["BlockType"] in ("WORD", "LINE")]
                            text = " ".join(words)
                    table_cells[row][col] = text

                for r in range(1, max_row + 1):
                    row = []
                    for c in range(1, max_col + 1):
                        row.append(table_cells.get(r, {}).get(c, ""))
                    table.append(row)

                tables.append(table)

        return tables


if __name__ == "__main__":
    local_pdf_path = "test_certificates/C25-0110 SK Technology 513225.pdf"
    bucket_name = "textractresultsfms"
    reader = TextractReader(pdf_file = local_pdf_path, bucket_folder = "Thermal Valve")

    # Upload the local PDF first
    reader.upload_file_to_s3()

    # Then process it with Textract
    blocks = reader.process_pdf()

    lines = reader.extract_lines(blocks)
    print("Lines:")
    for line in lines:
        print(line)

