import os
import json
import argparse
import logging
import re
from datetime import datetime

import pdfplumber
from pdf2image import convert_from_path
import pytesseract

# ------------- Helpers ------------- #

def extract_text_with_pdfplumber(pdf_path):
    """Try to extract text using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
    except Exception as e:
        logging.error(f"pdfplumber failed on {pdf_path}: {e}")
    return text.strip()


def extract_text_with_ocr(pdf_path):
    """Fallback: OCR each page of the PDF."""
    text = ""
    try:
        images = convert_from_path(pdf_path)
        for i, img in enumerate(images):
            page_text = pytesseract.image_to_string(img, lang="eng")
            text += page_text + "\n"
    except Exception as e:
        logging.error(f"OCR failed for {pdf_path}: {e}")
    return text.strip()


def extract_text_from_pdf(pdf_path):
    """Extract text: try pdfplumber, fallback to OCR if needed."""
    text = extract_text_with_pdfplumber(pdf_path)
    if not text:
        logging.info(f"No text extracted from {pdf_path}, using OCR...")
        text = extract_text_with_ocr(pdf_path)
    return text


def slugify_filename(filename):
    """Convert filename into URL/ID-friendly slug."""
    base = os.path.splitext(filename)[0]
    slug = re.sub(r"[^\w\s-]", "", base).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug


# ------------- Main ------------- #

def main():
    parser = argparse.ArgumentParser(description="Extract PDFs into JSON/JSONL with schema.org format")
    parser.add_argument("--pdf-dir", type=str, default="/tmp/pdfs", help="Directory containing PDFs")
    parser.add_argument("--output-dir", type=str, help="Directory to store processed files (default: pdf-dir/processed)")
    parser.add_argument("--output-format", choices=["json", "jsonl", "both"], default="jsonl", help="Output format")
    parser.add_argument("--include-full-text", action="store_true", help="Include full extracted text in articleBody")
    parser.add_argument("--base-url", type=str, default="https://example.com/pdf/", help="Base URL for @id and url fields")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    pdf_dir = args.pdf_dir
    if not os.path.exists(pdf_dir):
        logging.error(f"PDF directory not found: {pdf_dir}")
        return

    processed_dir = args.output_dir or os.path.join(pdf_dir, "processed")
    os.makedirs(processed_dir, exist_ok=True)

    logging.info(f"PDF source directory: {pdf_dir}")
    logging.info(f"Processed output directory: {processed_dir}")
    logging.info(f"Output format: {args.output_format}")
    logging.info(f"Include full text: {args.include_full_text}")

    count = 0
    for filename in os.listdir(pdf_dir):
        if filename.lower().endswith(".pdf"):
            pdf_path = os.path.join(pdf_dir, filename)
            logging.info(f"Processing {filename}...")

            text = extract_text_from_pdf(pdf_path)
            slug = slugify_filename(filename)
            doc_url = os.path.join(args.base_url.rstrip("/"), slug)

            doc_info = {
                "@context": "https://schema.org",
                "@type": "CreativeWork",
                "@id": doc_url,
                "name": filename,
                "url": doc_url,
                "description": text[:500] + ("..." if len(text) > 500 else ""),
                "filePath": pdf_path,
                "dateCreated": datetime.fromtimestamp(os.path.getctime(pdf_path)).isoformat()
            }

            if args.include_full_text:
                doc_info["articleBody"] = text

            # JSON output
            if args.output_format in ["json", "both"]:
                out_json_filename = filename.replace(".pdf", ".json")
                outpath = os.path.join(processed_dir, out_json_filename)
                with open(outpath, "w", encoding="utf-8") as f:
                    json.dump(doc_info, f, ensure_ascii=False, indent=2)

            # JSONL output (<url>\t<json>)
            if args.output_format in ["jsonl", "both"]:
                out_jsonl_filename = filename.replace(".pdf", ".jsonl")
                outpath = os.path.join(processed_dir, out_jsonl_filename)
                with open(outpath, "w", encoding="utf-8") as f:
                    f.write(f"{doc_url}\t{json.dumps(doc_info, ensure_ascii=False)}\n")

            count += 1

    logging.info(f"Finished processing. Total PDFs processed: {count}")


if __name__ == "__main__":
    main()
