"""Sample EDI X12 test data files."""
import os

SAMPLE_DIR = os.path.dirname(os.path.abspath(__file__))

def get_sample_path(filename: str) -> str:
    return os.path.join(SAMPLE_DIR, filename)

def read_sample(filename: str) -> str:
    with open(get_sample_path(filename), "r", encoding="utf-8") as f:
        return f.read()
