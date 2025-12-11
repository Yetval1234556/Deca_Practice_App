
import sys
import json
from pathlib import Path

# Add current directory to path so we can import app
sys.path.append(str(Path.cwd()))

from app import _parse_pdf_source

def test_parsing(pdf_path):
    print(f"Parsing {pdf_path}...")
    try:
        with open(pdf_path, "rb") as f:
            # We use the file object directly as _parse_pdf_source supports it
            result = _parse_pdf_source(f, name_hint=pdf_path.name)
        
        print(f"Parsed {len(result.get('questions', []))} questions.")
        
        # Print first 5 questions to inspect
        for q in result.get("questions", [])[:5]:
            print(f"\nQuestion {q['number']}:")
            print(f"Prompt: {q['question']}")
            print("Options:")
            for i, opt in enumerate(q['options']):
                print(f"  {chr(65+i)}. {opt}")
            print(f"Correct: {q.get('correct_letter')}")
            
    except Exception as e:
        print(f"Error parsing {pdf_path}: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_file = Path("tests/2017.pdf")
    if test_file.exists():
        test_parsing(test_file)
    else:
        # Try another one if 2017 doesn't exist
        pdfs = list(Path("tests").glob("*.pdf"))
        if pdfs:
            test_parsing(pdfs[0])
        else:
            print("No PDFs found in tests/ directory.")
