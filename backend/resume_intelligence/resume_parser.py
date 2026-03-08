import re
from pypdf import PdfReader


def clean_text(text):

    # Fix cases like "K E V I N"
    text = re.sub(r'(?<=\b[A-Z])\s(?=[A-Z]\b)', '', text)

    # Remove spaces between letters
    text = re.sub(r'(?<=\w)\s(?=\w)', '', text)

    # Normalize spacing
    text = " ".join(text.split())

    return text


def extract_text(file_path):

    reader = PdfReader(file_path)

    text = ""

    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text += page_text + "\n"

    text = clean_text(text)

    return text


def extract_links(file_path):
    """Extract all hyperlinks from PDF annotations."""
    reader = PdfReader(file_path)
    links = []

    for page in reader.pages:
        if "/Annots" in page:
            annotations = page["/Annots"]
            for annot in annotations:
                obj = annot.get_object()
                if obj.get("/Subtype") == "/Link":
                    uri = obj.get("/A", {}).get("/URI")
                    if uri:
                        links.append(str(uri))

    return links