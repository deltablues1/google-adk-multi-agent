"""
Quick script to read KPD Excel and extract IT-related codes for sample catalog
"""
import sys
from pathlib import Path
try:
    import pandas as pd
    import openpyxl
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Installing openpyxl...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "openpyxl", "-q"])
    import pandas as pd
    import openpyxl

# Resolve paths relative to project root (this script lives in scripts/)
PROJECT_ROOT = Path(__file__).parent.parent
EXCEL_PATH = PROJECT_ROOT / 'data' / 'kpd_2025' / 'KPD_2025_struktura.xlsx'

# Read Excel
df = pd.read_excel(EXCEL_PATH)

print("=" * 80)
print("KPD 2025 STRUKTURA - Column Names:")
print("=" * 80)
print(df.columns.tolist())
print()

print("=" * 80)
print("First 30 rows:")
print("=" * 80)
print(df.head(30).to_string())
print()

# Try to find IT-related codes (section 62, 63, 70, 73, 74)
print("=" * 80)
print("IT-RELATED CODES (Section 62 - Computer programming):")
print("=" * 80)
it_codes = df[df.iloc[:, 0].astype(str).str.contains('62', na=False)]
print(it_codes.to_string())
