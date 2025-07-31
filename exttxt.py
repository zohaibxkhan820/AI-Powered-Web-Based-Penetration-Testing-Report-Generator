import sys
import os
from PyPDF2 import PdfReader

# Check if filename is provided
if len(sys.argv) < 2:
    print("❌ Usage: python3 extract_pdf_text.py <yourfile.pdf>")
    sys.exit(1)

pdf_path = sys.argv[1]  # Get PDF filename from terminal
output_path = os.path.join("outputs", "extxt.txt")

# Read and extract PDF text
try:
    reader = PdfReader(pdf_path)
    full_text = ""

    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n\n"

    # Save extracted text to output file
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)

    print(f"✅ Text extracted and saved to '{output_path}'")

except FileNotFoundError:
    print(f"❌ File '{pdf_path}' not found.")
except Exception as e:
    print(f"❌ Error: {e}")
