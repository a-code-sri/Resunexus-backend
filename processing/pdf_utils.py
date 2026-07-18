import io

import fitz
import pdfplumber
import PyPDF2


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """
    Extracts all text from a PDF.

    Parameters
    ----------
    pdf_bytes : bytes
        Raw PDF bytes.

    Returns
    -------
    str
        Extracted text.

    Raises
    ------
    RuntimeError
        If no supported PDF parser can extract text.
    """

    # ==========================================================
    # First Attempt : PyMuPDF (Most Reliable)
    # ==========================================================

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


    # ==========================================================
    # Second Attempt : pdfplumber
    # ==========================================================

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


    # ==========================================================
    # Third Attempt : PyPDF2
    # ==========================================================

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
                # Skip only the corrupted page
                continue

        result = "\n".join(pages).strip()

        if result:
            return result

    except Exception:
        pass


    # ==========================================================
    # Nothing worked
    # ==========================================================

    raise RuntimeError(
        "Unable to extract text from the uploaded PDF. "
        "The document may be scanned, encrypted, corrupted, "
        "or use unsupported font encodings."
    )