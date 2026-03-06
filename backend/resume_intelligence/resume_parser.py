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