import os
import traceback
import pytesseract
import cv2

import numpy as np
import re
import fitz  # PyMuPDF
from PIL import Image

from .general_utils import FRParts, load_from_json, save_to_json


class OCRReader:
    """
    Base class for OCR reading and processing scanned PDF documents.
    Uses PyMuPDF for PDF handling, OpenCV for image processing,
    and Tesseract for OCR. Includes methods for auto-rotation,
    skew correction, and text extraction. The methods are tailored to specific 
    document formats, belonging to the different companies that provide the parts for the FMS.
    Slight changes in the document layout may require adjustments in the class. Moving to 
    a more robust solution like using Textract is suggested.

    Attributes
    ----------
    pdf_file : str
        Path to the PDF file to be processed.
    pdf_document : fitz.Document
        The opened PDF document.
    total_lines : str
        Accumulated OCR'd text from the document.
    certification : str
        Certification number extracted from the document filename.
    debug : bool
        Flag to enable debug image displays.
    
    Methods
    -------
    read_scanned_page(idx: int) -> tuple[str, bool]
        Reads and OCRs a scanned page from the PDF.
    auto_rotate(img: np.ndarray) -> np.ndarray
        Automatically rotates an image to correct orientation and skew.
    preprocess_image_for_ocr(pil_image: Image.Image) -> np.ndarray
        Preprocesses a PIL image for OCR.
    main_delivery_slip_reader(part_type: str) -> None
        Main function to read delivery slips and store OCR results.
    packing_list_reader(part_type: str) -> None
        Main function to read packing lists and store OCR results.
    read_scanned_page_veldlaser() -> tuple[str | None, str | None]
        Reads and OCRs Veldlaser scanned pages from the PDF.
    extract_drawing(text: str) -> str | None
        Extracts drawing number from OCR'd text.
    read_scanned_page_coremans() -> int
        Reads and OCRs Coremans scanned pages from the PDF to extract number of items.
    remove_lines(img: np.ndarray) -> np.ndarray
        Removes horizontal and vertical lines from the image.
    preprocess_image_for_ocr_veldlaser(pil_img: Image.Image) -> Image.Image
        Preprocesses PIL image for OCR specific to Veldlaser documents.
    show_debug_image(title: str, pil_img: Image.Image) -> None
        Shows PIL image with OpenCV, converting binary images correctly.
    detect_skew_angle_via_hough(img: np.ndarray) -> float
        Detects skew angle using Hough Transform.
    detect_angle_with_tesseract(img: Image.Image) -> int
        Detects image orientation using Tesseract's OSD.
    fallback_angle_with_min_area_rect(img: np.ndarray) -> float
        Fallback method to detect skew angle using minimum area rectangle.
    rotate_image(img: np.ndarray, angle: float) -> np.ndarray
        Rotates image by a given angle.
    """
    def __init__(self, pdf_file: str, debug: bool = False, tesseract_cmd: str = r"C:\Users\TANTENS\Tools\tesseract.exe"):
        self.pdf_file = pdf_file
        self.pdf_document = fitz.open(pdf_file)
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        self.total_lines = ''
        self.certification = ''
        self.debug = debug

    def detect_skew_angle_via_hough(self, img: np.ndarray) -> float:
        """
        Detect skew angle using Hough Transform.
        Parameters:
            img (np.ndarray): Input image in BGR format.
        Returns:
            float: Detected skew angle in degrees.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray = cv2.bitwise_not(gray)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

        edges = cv2.Canny(thresh, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180.0, 200)

        if lines is None:
            return 0

        angles = []
        for rho, theta in lines[:, 0]:
            angle = (theta * 180 / np.pi) - 90
            if -45 < angle < 45:  # filter out near-verticals
                angles.append(angle)

        if len(angles) == 0:
            return 0

        median_angle = np.median(angles)
        return median_angle

    def detect_angle_with_tesseract(self, img: Image.Image) -> int:
        """
        Detect image orientation using Tesseract's OSD.
        Parameters:
            img (PIL.Image.Image): Input image.
        Returns:
            int: Detected rotation angle in degrees.
        """
        try:
            osd = pytesseract.image_to_osd(img)
            angle = int(re.search(r'(?<=Rotate: )\d+', osd).group(0))
            return angle
        except Exception as e:
            print(f"OSD detection failed: {e}")
            return None

    def fallback_angle_with_min_area_rect(self, img: np.ndarray) -> float:
        """
        Fallback method to detect skew angle using minimum area rectangle.
        Parameters:
            img (np.ndarray): Input image in BGR format.
        Returns:
            float: Detected skew angle in degrees.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        binary = 255 - binary  # Invert: text is white

        contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        text_regions = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area > 100:
                rect = cv2.minAreaRect(cnt)
                box = cv2.boxPoints(rect)
                box = np.intp(box)
                text_regions.append(box)

        if not text_regions:
            return 0

        all_points = np.vstack(text_regions)
        angle = cv2.minAreaRect(all_points)[-1]

        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        return angle

    def rotate_image(self, img: np.ndarray, angle: float) -> np.ndarray:
        """
        Rotate image by a given angle.
        Parameters:
            img (np.ndarray): Input image in BGR format.
            angle (float): Angle in degrees to rotate.
        Returns:
            np.ndarray: Rotated image.
        """
        (h, w) = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        new_w = int((h * sin) + (w * cos))
        new_h = int((h * cos) + (w * sin))
        M[0, 2] += (new_w / 2) - center[0]
        M[1, 2] += (new_h / 2) - center[1]
        return cv2.warpAffine(img, M, (new_w, new_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    def auto_rotate(self, img: np.ndarray) -> np.ndarray:
        """
        Automatically rotate image to correct orientation and skew.
        Parameters:
            img (np.ndarray): Input image in BGR format.
        Returns:
            np.ndarray: Corrected image.
        """
        angle = self.detect_angle_with_tesseract(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
        if angle is not None and angle != 0:
            angle = -angle if angle != 270 else -90
        else:
            angle = self.fallback_angle_with_min_area_rect(img)

        # After coarse rotation, check for skew
        if angle != 0:
            img = self.rotate_image(img, angle)

        skew_angle = self.detect_skew_angle_via_hough(img)
        if abs(skew_angle) > 0.5:  # Ignore small variations
            img = self.rotate_image(img, skew_angle)

        return img

    def preprocess_image_for_ocr(self, pil_image: Image.Image) -> np.ndarray:
        """
        Preprocess PIL image for OCR.
        Parameters:
            pil_image (PIL.Image.Image): Input PIL image.
        Returns:
            np.ndarray: Preprocessed image in grayscale.
        """
        img = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (3, 3), 0)
        thresh = cv2.adaptiveThreshold(
            blur, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31, 2
        )
        return gray

    def read_scanned_page(self, idx: int) -> tuple[str, bool]:
        """
        Read and OCR a scanned page from the PDF.
        Parameters:
            idx (int): Page index.
        Returns:
            tuple[str, bool]: OCR'd text and whether it's a delivery slip.
        """
        page: fitz.Page = self.pdf_document[idx]
        zoom = 2
        config = '--psm 6 --oem 3'
        mat = fitz.Matrix(zoom, zoom)
        pix: fitz.Pixmap = page.get_pixmap(matrix=mat, alpha=False)
        pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        img_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        img_bgr = self.auto_rotate(img_bgr)
        x, y = 550, 100
        w, h = 500, 100  
        cropped = img_bgr[y:y+h, x:x+w]

        self.show_debug_image("Cropped", cropped)

        processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))
        text = pytesseract.image_to_string(processed, lang='eng', config=config)
        text = text.strip()
        # print(f'page number: {idx+1}')
        lines = ''
        if text == 'Delivery slip':
            delivery_slip = True
            # Scan vertically along the page with the set width and height
            page_height, page_width = img_bgr.shape[:2]
            # Estimate line height in pixels using PDF layout
            line_height_pt = 12  # typical line height in points
            pt_to_px_ratio = page_height / page.rect.height
            h = int(pt_to_px_ratio * line_height_pt)*2

            x, w = 0, page_width
            step = h//2
            for y in range(380, page_height - h + 1, step):
                cropped = img_bgr[y:y+h, x:x+w]
                processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))
                text = pytesseract.image_to_string(processed, lang='eng', config=config)
                if not text:
                    text = ''
                lines += text + '\n'
                # print(text)
                # Optionally, process or check the text here as needed
                # x, y = 50, 640
                # w, h = 800, 40
                # cropped = img_bgr[y:y+h, x:x+w]
                # processed = preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))
                # text = pytesseract.image_to_string(processed, lang='eng', config=config)
                self.show_debug_image("Cropped", processed)

        else:
            delivery_slip = False
        # print(lines)
        return lines, delivery_slip

    def read_scanned_page_keller(self, idx: int) -> tuple[str, bool]:
        """
        Read and OCR a scanned page from the PDF for Keller documents.
        Parameters:
            idx (int): Page index.
        Returns:
            tuple[str, bool]: OCR'd text and whether it's a packing list.
        """
        page: fitz.Page = self.pdf_document[idx]
        config = '--psm 6 --oem 3'
        zoom = 2
        mat = fitz.Matrix(zoom, zoom)
        pix: fitz.Pixmap = page.get_pixmap(matrix=mat, alpha=False)
        pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        
        img_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        img_bgr = self.auto_rotate(img_bgr)
        x, y = 50, 500
        w, h = 200, 100  
        cropped = img_bgr[y:y+h, x:x+w]
        # print(f'page number: {idx+1}')

        self.show_debug_image("Cropped", cropped)

        processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))
        text = pytesseract.image_to_string(processed, lang='eng', config=config)
        text = text.strip()
        lines = ''
        if 'packing list' in text.lower():
            packing_list = True
            # Scan vertically along the page with the set width and height
            page_height, page_width = img_bgr.shape[:2]
            # Estimate line height in pixels using PDF layout
            line_height_pt = 12  # typical line height in points
            pt_to_px_ratio = page_height / page.rect.height
            h = int(pt_to_px_ratio * line_height_pt)*2

            x, w = 0, page_width
            step = h//2
            for y in range(770, page_height - h + 1, step):
                cropped = img_bgr[y:y+h, x:x+w]
                processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))
                text = pytesseract.image_to_string(processed, lang='eng', config=config)
                lines += text + '\n'
                # print(lines)
                self.show_debug_image("Cropped", processed)
        else:
            packing_list = False

        # print(lines)
        return lines, packing_list

    def remove_lines(self, img: np.ndarray) -> np.ndarray:
        """
        Remove horizontal and vertical lines from the image.
        Parameters:
            img (np.ndarray): Input image in BGR format.
        Returns:
            np.ndarray: Image with lines removed.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        horizontal_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, horizontal_kernel, iterations=1)

        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        vertical_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, vertical_kernel, iterations=1)

        mask = cv2.bitwise_or(horizontal_lines, vertical_lines)
        cleaned = cv2.inpaint(img, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

        return cleaned

    def preprocess_image_for_ocr_veldlaser(self, pil_img: Image.Image) -> Image.Image:
        """
        Preprocess PIL image for OCR specific to Veldlaser documents.
        Parameters:
            pil_img (PIL.Image.Image): Input PIL image.
        Returns:
            PIL.Image.Image: Preprocessed binary image.
        """
        img = pil_img.convert("L")  # grayscale
        img = img.point(lambda x: 0 if x < 180 else 255, '1')  # binarize
        return img

    def show_debug_image(self, title: str, pil_img: Image.Image) -> None:
        """
        Show PIL image with OpenCV, converting binary images correctly.
        """
        if not self.debug:
            return
        img_np = np.array(pil_img)
        if img_np.dtype == bool:
            img_np = img_np.astype(np.uint8) * 255
        cv2.imshow(title, img_np)
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def extract_drawing(self, text: str) -> str | None:
        """
        Extract drawing number in parentheses after a line containing 'FLOW RESTRICTOR'.
        
        Parameters:
            text (str): The OCR'd text containing multiple lines.
            
        Returns:
            str or None: The drawing number if found, else None.
        """
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if FRParts.RESTRICTOR.value.lower() in line.lower(): 
                for next_line in lines[i+1:]:
                    next_line = next_line.strip()
                    if not next_line:  
                        continue
                    match = re.search(r'\(([^)]+)\)', next_line)
                    if match:
                        return match.group(1).upper() 
                return None
        return None

    def read_scanned_page_veldlaser(self) -> tuple[str | None, str | None]:
        """
        Read and OCR Veldlaser scanned pages from the PDF.
        Returns:
            tuple[str | None, str | None]: OCR'd text and drawing number if found.
        """
        match = re.search(r'C\d{2}-\d{4}', os.path.basename(self.pdf_file))
        self.certification = match.group(0) if match else None
        all_certifications = load_from_json("restrictor_ocr_certifications")
        total_lines = None
        drawing = None
        if all_certifications and os.path.basename(self.pdf_file) in all_certifications:
            total_lines = all_certifications.get(os.path.basename(self.pdf_file), '')
        if total_lines:
            drawing = all_certifications.get(os.path.basename(self.pdf_file) + " drawing", "")
        if total_lines:
            return total_lines, drawing
        
        config = '--psm 11 --oem 3'

        veldlaser = False
        batch_complete = False
        lines = ''
        for idx, page in enumerate(self.pdf_document[1:]):
            zoom = 4
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            img_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            img_bgr = self.auto_rotate(img_bgr)
            # print(f'page number: {idx + 1}')
            if not veldlaser:
                x, y = 125, 300
                w, h = 800, 200  
                cropped = img_bgr[y:y+h, x:x+w]


                processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))
                text = pytesseract.image_to_string(processed, lang='eng', config=config).strip()
                text = re.sub(r'veldiaser', 'veldlaser', text, flags=re.IGNORECASE)
                self.show_debug_image("Cropped", processed)
                if 'veldlaser' in text.lower():
                    veldlaser = True
                    if not drawing:
                        x, y = 1150, 700
                        w, h = 750, 200
                        cropped = img_bgr[y:y+h, x:x+w]
                        self.show_debug_image("Cropped", cropped)

                        # no_lines = remove_lines(cropped)
                        processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))

                        text = pytesseract.image_to_string(processed, lang='eng', config=config)
                        # print(text)
                        lines += text + '\n'
                        drawing = self.extract_drawing(text)
                        if drawing:
                            drawing = drawing.upper().replace("X", "4")
                            # print(drawing)

                    x, y = 125, 2050
                    w, h = 750, 100  
                    cropped = img_bgr[y:y+h, x:x+w]
                    self.show_debug_image("Cropped", cropped)

                    # no_lines = remove_lines(cropped)
                    processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))

                    text = pytesseract.image_to_string(processed, lang='eng', config=config)
                    lines += text + '\n'
                    # print(text)

            elif veldlaser and not batch_complete:
                page_height, page_width = img_bgr.shape[:2]
                line_height_pt = 12  
                pt_to_px_ratio = page_height / page.rect.height
                h = int(pt_to_px_ratio * line_height_pt)*3
                x, w = 125, 750
                step = h//2

                for y in range(120, page_height - h + 1, step):
                    cropped = img_bgr[y:y+h, x:x+w]
                    # no_lines = remove_lines(cropped)
                    processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))
                    text = pytesseract.image_to_string(processed, lang='eng', config=config)
                    lines += text + '\n'

                    self.show_debug_image("Cropped", processed)
                    # print(text)
                    if 'batch quality passed' in text.lower() and drawing:
                        batch_complete = True
                        certification_text = load_from_json("restrictor_ocr_certifications")
                        if not certification_text:
                            certification_text = {}
                        certification_text[os.path.basename(self.pdf_file)] = lines
                        certification_text[os.path.basename(self.pdf_file) + " drawing"] = drawing
                        save_to_json(certification_text, "restrictor_ocr_certifications")
                        return lines, drawing

        return None, None

    def read_scanned_page_coremans(self) -> int:
        """
        Read and OCR Coremans scanned pages from the PDF to extract number of items.
        Returns:
            int: Number of items extracted from the document.
        """
        config = '--psm 6 --oem 3'
        conformance = False
        lines = ''
        for idx, page in enumerate(self.pdf_document[3:]):
            zoom = 4
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            pil_image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            img_bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
            img_bgr = self.auto_rotate(img_bgr)
            # print(f'page number: {idx + 1}')
            if not conformance:
                x, y = 750, 500
                w, h = 850, 250  
                cropped = img_bgr[y:y+h, x:x+w]
                self.show_debug_image("Cropped", cropped)

                processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))
                text = pytesseract.image_to_string(processed, lang='eng', config=config).strip()
                text = re.sub(r'veldiaser', 'veldlaser', text, flags=re.IGNORECASE)
                self.show_debug_image("Cropped", processed)
                if 'certificate of conformance' in text.lower():
                    conformance = True
                    x, y = 1300, 1100
                    w, h = 1000, 300 
                    cropped = img_bgr[y:y+h, x:x+w]
                    self.show_debug_image("Cropped", cropped)

                    # no_lines = remove_lines(cropped)
                    processed = self.preprocess_image_for_ocr(Image.fromarray(cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)))

                    text = pytesseract.image_to_string(processed, lang='eng', config=config)
                    item_match = re.search(r'number of items\s*[:=]?\s*(\d+)', text, re.IGNORECASE)
                    if item_match:
                        number_of_items = int(item_match.group(1))

                        return number_of_items
                    else:
                        return 1
                    
    def main_delivery_slip_reader(self, part_type: str) -> None:
        """
        Main function to read delivery slips and store OCR results.
        Parameters:
            part_type (str): Type of part.
        """
        match = re.search(r'C\d{2}-\d{4}', os.path.basename(self.pdf_file))
        self.certification = match.group(0) if match else None
        delivery_slips = 0
        no_slip_streak = 0

        all_certifications = load_from_json(f"{part_type.lower()}_ocr_certifications")
        if all_certifications and os.path.basename(self.pdf_file) in all_certifications:
            self.total_lines = all_certifications.get(os.path.basename(self.pdf_file), '')
        else:
            for page_number in range(len(self.pdf_document)):
                print(page_number)
                if page_number < 10:
                    lines, delivery_slip = self.read_scanned_page(page_number)

                    if delivery_slip:
                        self.total_lines += lines
                        delivery_slips += 1
                        no_slip_streak = 0
                    else:
                        if delivery_slips > 0:
                            no_slip_streak += 1
                            if no_slip_streak >= 3:
                                break

            certification_text = load_from_json(f"{part_type.lower()}_ocr_certifications")
            if not certification_text:
                certification_text = {}

            certification_text[os.path.basename(self.pdf_file)] = self.total_lines
            save_to_json(certification_text, f"{part_type.lower()}_ocr_certifications")

    def packing_list_reader(self, part_type: str) -> None:
        """
        Main function to read packing lists and store OCR results.
        Parameters:
            part_type (str): Type of part.
        """
        match = re.search(r'C\d{2}-\d{4}', os.path.basename(self.pdf_file))
        self.certification = match.group(0) if match else None
        packing_lists = 0
        no_list_streak = 0

        all_certifications = load_from_json(f"{part_type.lower()}_ocr_certifications")
        if all_certifications and os.path.basename(self.pdf_file) in all_certifications:
            self.total_lines = all_certifications.get(os.path.basename(self.pdf_file), '')
        else:
            for page_number in range(len(self.pdf_document)):
                print(page_number)
                if page_number < 10:
                    lines, packing_list = self.read_scanned_page_keller(page_number)
                    if packing_list:
                        self.total_lines += lines
                        packing_lists += 1
                        no_list_streak = 0
                    else:
                        if packing_lists > 0:
                            no_list_streak += 1
                            if no_list_streak >= 3:
                                break

            certification_text = load_from_json(f"{part_type.lower()}_ocr_certifications")
            if not certification_text:
                certification_text = {}

            certification_text[os.path.basename(self.pdf_file)] = self.total_lines
            save_to_json(certification_text, f"{part_type.lower()}_ocr_certifications")


