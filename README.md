# Document Organiser v3.1

Automatically organises scanned PDFs and images with intelligent categorisation, enhanced metadata extraction, and OID backup system.

## Features

- **Smart PDF Splitting** - Detects topic/sender/date changes and splits multi-document scans
- **OCR Text Extraction** - Automatically OCRs image-based PDFs using `ocrmypdf`
- **Intelligent Categorisation** - Auto-sorts into: Financial, Government, Retail, Medical, Manuals, Other
- **Enhanced Filenames** - Generates descriptive names with dates, subjects, party names, and page ranges
- **OID Backup System** - SHA-256 based Original IDs link organised files to source backups
- **Comprehensive Indexing** - Generates JSON and CSV indexes for searchability

## Installation

### Dependencies

```bash
# Python packages
pip3 install pdfplumber PyPDF2 python-dateutil pillow pytesseract

# System tools (macOS)
brew install ocrmypdf tesseract ghostscript
```

## Configuration

Edit `rules.json` to customise issuer patterns and party name detection:

```json
{
  "issuer_rules": [
    ["\\b(bankwest|commbank)\\b", "bank"],
    ["\\b(chemist warehouse)\\b", "retail"]
  ],
  "party_names": [
    ["\\bAaron\\b", "Aaron"],
    ["\\bSylvia\\b", "Sylvia"]
  ]
}
```

## Usage

1. Update the `WORK` path in `organise_scans.py`
2. Run the script:

```bash
python3 organise_scans.py
```

## Output Structure

```
_Organised/
├── _Originals/              # Backup copies with OIDs
├── 1 - Financial & Banking/
├── 2 - Government & Services/
├── 3 - Retail & Purchases/
├── 4 - Instructions & Manuals/
├── 5 - Health & Medical/
├── 6 - Utilities & Services/
├── 9 - Other/
├── _index.json             # Detailed JSON index
└── _index.csv              # Simplified CSV index
```

## Filename Format

Organised files use this format:
```
YYYY-MM-DD – Subject Title – Party [OID-XXXXXXXXXX] – p01-p03.pdf
```

Example:
```
2025-11-04 – Chemist Warehouse Tax Invoice – Aaron [OID-A1B2C3D4E5] – p01-p01.pdf
```

## Version History

- **v3.1** - Enhanced filename detail, improved title extraction, better date parsing
- **v3.0** - OID backup system, comprehensive indexing
- **v2.0** - PDF splitting, OCR integration
- **v1.0** - Initial release

## License

MIT
