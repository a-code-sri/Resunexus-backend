import io

import fitz
import pdfplumber
import PyPDF2

from docx import Document


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extract text from a PDF using multiple fallback libraries.

    Returns
    -------
    str
        Extracted text.

    Raises
    ------
    RuntimeError
        If no parser can successfully extract text.
    """


    try:

        document = fitz.open(
            stream=pdf_bytes,
            filetype="pdf"
        )

        pages = []

        for page in document:

            text = page.get_text()

            if text:
                pages.append(text)

        document.close()

        result = "\n".join(pages).strip()

        if result:
            return result

    except Exception:
        pass



    try:

        pages = []

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:

            for page in pdf.pages:

                text = page.extract_text()

                if text:
                    pages.append(text)

        result = "\n".join(pages).strip()

        if result:
            return result

    except Exception:
        pass


    try:

        reader = PyPDF2.PdfReader(
            io.BytesIO(pdf_bytes)
        )

        pages = []

        for page in reader.pages:

            try:

                text = page.extract_text()

                if text:
                    pages.append(text)

            except Exception:
                continue

        result = "\n".join(pages).strip()

        if result:
            return result

    except Exception:
        pass


    raise RuntimeError(
        "Unable to extract text from the uploaded PDF. "
        "The document may be scanned, encrypted, corrupted, "
        "or use unsupported font encodings."
    )


def extract_text_from_docx(docx_bytes: bytes) -> str:
    """
    Extract text from a DOCX document.
    """

    try:

        document = Document(
            io.BytesIO(docx_bytes)
        )

        paragraphs = []

        for para in document.paragraphs:

            text = para.text.strip()

            if text:
                paragraphs.append(text)

        # Extract text from tables too
        for table in document.tables:

            for row in table.rows:

                cells = [
                    cell.text.strip()
                    for cell in row.cells
                    if cell.text.strip()
                ]

                if cells:
                    paragraphs.append(" ".join(cells))

        result = "\n".join(paragraphs).strip()

        if result:
            return result

    except Exception:
        pass

    raise RuntimeError(
        "Unable to extract text from the uploaded DOCX."
    )


def extract_text_from_document(
    filename: str,
    file_bytes: bytes
) -> str:
    """
    Automatically dispatch extraction based on file extension.
    Keeps the rest of the project independent of document type.
    """

    filename = filename.lower()

    if filename.endswith(".pdf"):

        return extract_text_from_pdf(file_bytes)

    if filename.endswith(".docx"):

        return extract_text_from_docx(file_bytes)

    raise RuntimeError(
        "Unsupported document type."
    )