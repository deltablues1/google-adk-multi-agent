"""
Build complete KPD 2025 catalog JSON from Excel file.
This will be used by search_kpd_code for real RAG search.
"""
import pandas as pd
import json
from pathlib import Path

# Resolve paths relative to project root (this script lives in scripts/)
PROJECT_ROOT = Path(__file__).parent.parent
EXCEL_PATH = PROJECT_ROOT / 'data' / 'kpd_2025' / 'KPD_2025_struktura.xlsx'

print("Building KPD 2025 catalog from Excel...")

# Read Excel
df = pd.read_excel(EXCEL_PATH)
print(f"Loaded {len(df)} rows from Excel")

# Build catalog dictionary
catalog = {}
count = 0

for idx, row in df.iterrows():
    code = str(row.iloc[0]).strip()
    name = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""

    # Skip header row and rows without proper code
    if code == '�ifra' or code == 'Šifra' or not name or name == 'Naziv':
        continue

    # Only include leaf nodes (codes with descriptions)
    if name and not name.startswith('Unnamed'):
        # Determine parent code
        if '.' in code:
            parent = code.rsplit('.', 1)[0]
        else:
            parent = code[0] if len(code) > 1 else ""

        catalog[code] = {
            "name_hr": name,
            "parent": parent,
            "vat_rate": "25",  # Default VAT rate (will need manual adjustment for special rates)
            "code": code
        }
        count += 1

print(f"Built catalog with {count} KPD codes")

# Save to data folder
data_dir = PROJECT_ROOT / 'data' / 'kpd_2025'
data_dir.mkdir(parents=True, exist_ok=True)

output_file = data_dir / 'kpd_catalog.json'
with open(output_file, 'w', encoding='utf-8') as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)

print(f"Saved catalog to: {output_file}")
print(f"Total codes: {len(catalog)}")

# Show sample of IT codes (section 62)
print("\n" + "=" * 80)
print("SAMPLE: Section 62 (IT services) codes:")
print("=" * 80)
it_codes = {k: v for k, v in catalog.items() if k.startswith('62')}
for code, data in list(it_codes.items())[:20]:
    print(f"{code}: {data['name_hr']}")

print(f"\n✓ Catalog successfully built with {len(catalog)} codes!")
