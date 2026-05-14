"""Resume parser for PDF and DOCX files."""
from pathlib import Path

def parse_resume(file_path: str) -> str:
    """Extract text from a .pdf or .docx resume."""
    path = Path(file_path)
    ext = path.suffix.lower()
    
    if ext == ".pdf":
        from PyPDF2 import PdfReader
        reader = PdfReader(file_path)
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    elif ext in (".docx", ".doc"):
        from docx import Document
        doc = Document(file_path)
        text = "\n".join(p.text for p in doc.paragraphs)
    else:
        raise ValueError(f"Unsupported file format: {ext}. Use .pdf or .docx")
    
    return text.strip()
