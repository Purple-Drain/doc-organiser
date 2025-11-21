#!/usr/bin/env python3
"""
Document Organiser v3.1 - Enhanced Filename Detail
Improved metadata extraction, smart categorisation, OID backup system
"""
import os, re, json, csv, shutil, subprocess, hashlib
from pathlib import Path
from dateutil import parser as dtp
import pdfplumber
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
import pytesseract

# ========== SETTINGS ==========
WORK = Path("/Users/aaron/Library/CloudStorage/GoogleDrive-azzad10@gmail.com/My Drive/Brother Scans")
OUT = WORK / "_Organised"
ORIG_BACKUP = OUT / "_Originals"

OUT.mkdir(parents=True, exist_ok=True)
ORIG_BACKUP.mkdir(parents=True, exist_ok=True)

FOLDERS = {
    "bank": OUT / "1 - Financial & Banking",
    "gov": OUT / "2 - Government & Services",
    "retail": OUT / "3 - Retail & Purchases",
    "manuals": OUT / "4 - Instructions & Manuals",
    "medical": OUT / "5 - Health & Medical",
    "utilities": OUT / "6 - Utilities & Services",
    "other": OUT / "9 - Other",
}
for p in FOLDERS.values():
    p.mkdir(parents=True, exist_ok=True)

# ========== LOAD CONFIG ==========
config_path = WORK / "rules.json"
ISSUER_RULES = []
NAMES_RX = []

if config_path.exists():
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    for pattern, bucket in config.get("issuer_rules", []):
        ISSUER_RULES.append((re.compile(pattern, re.I), bucket))
    for pattern, name in config.get("party_names", []):
        NAMES_RX.append((re.compile(pattern, re.I), name))
else:
    ISSUER_RULES = [
        (re.compile(r"\b(bankwest|coles\s*credit|nab|westpac|comm(?:onwealth)?\s*bank|commbank|virgin\s*money)\b", re.I), "bank"),
        (re.compile(r"\b(services\s*australia|centrelink|department|council|nsw\s*government)\b", re.I), "gov"),
        (re.compile(r"\b(petbarn|chemist\s*warehouse|bunnings|jb\s*hi-?fi|ikea|receipt|tax\s*invoice)\b", re.I), "retail"),
        (re.compile(r"\b(instruction|user\s*manual|guide|warranty)\b", re.I), "manuals"),
        (re.compile(r"\b(pathology|ultrasound|referral|dental|clinic|pharmacy|medical)\b", re.I), "medical"),
    ]
    NAMES_RX = [
        (re.compile(r"\bAaron\b", re.I), "Aaron"),
        (re.compile(r"\bSylvia\b", re.I), "Sylvia"),
    ]

DATE_PAT = re.compile(
    r"("
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4})|"
    r"(?:\d{4}[/-]\d{1,2}[/-]\d{1,2})|"
    r"(?:\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})|"
    r"(?:(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})"
    r")",
    re.IGNORECASE,
)

# ========== HELPER FUNCTIONS ==========
def safe_name(s: str) -> str:
    """Sanitize filename strings"""
    s = re.sub(r"[^\w\s\-\&\(\)]", "", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s or "Document"

def pick_date(text: str):
    """Extract first valid date from text"""
    m = DATE_PAT.search(text)
    if m:
        try:
            return dtp.parse(m.group(1), dayfirst=True).date().isoformat()
        except Exception:
            return None
    return None

def detect_parties(text: str):
    """Detect party names (Aaron, Sylvia, or both)"""
    found = [who for rx, who in NAMES_RX if rx.search(text)]
    if len(found) == 2:
        return "Aaron & Sylvia"
    return " & ".join(found) if found else None

def extract_title_from_filename(filepath: Path) -> str:
    """Extract meaningful title from filename"""
    stem = filepath.stem
    # Remove timestamp patterns
    stem = re.sub(r'[-_]\d{14,}[-_]\d{3}$', '', stem)
    stem = re.sub(r'[-_]Scan\d{4}-\d{2}-\d{2}[-_]\d{6}$', '', stem, flags=re.I)
    stem = re.sub(r'\s*\[OID-[A-F0-9]+\]', '', stem)
    stem = re.sub(r'[-_]+', ' ', stem).strip()

    # Check if generic
    generic_patterns = [r'^\d{8,14}$', r'^scan\d+', r'^img_?\d+', r'^\d{4}-\d{2}-\d{2}']
    for pattern in generic_patterns:
        if re.match(pattern, stem, re.I):
            return None

    if len(stem) > 15:
        return safe_name(stem)
    return None

def extract_title_from_text(text: str, max_lines: int = 10) -> str:
    """Extract meaningful title from document text"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    candidates = [line for line in lines[:max_lines] if 10 < len(line) < 100]
    if candidates:
        return safe_name(candidates[0])
    return "Document"

def detect_bucket_and_title(text: str, file_path: Path = None):
    """Detect category bucket and extract title"""
    lowered = text.lower()
    bucket = "other"

    for rx, b in ISSUER_RULES:
        if rx.search(lowered):
            bucket = b
            break

    # Extract title from filename first, then text
    title = None
    if file_path:
        title = extract_title_from_filename(file_path)
    if not title:
        title = extract_title_from_text(text)

    parties = detect_parties(text)
    if parties and parties not in title:
        title += f" – {parties}"

    return bucket, title, pick_date(text)

def ocr_pdf_if_needed(pdf_path: Path) -> Path:
    """OCR PDF if it contains no searchable text"""
    try:
        with pdfplumber.open(pdf_path) as doc:
            head_text = "".join([(doc.pages[i].extract_text() or "") for i in range(min(2, len(doc.pages)))])
            if head_text.strip():
                return pdf_path
    except Exception:
        pass

    ocred = pdf_path.with_suffix(".ocr.pdf")
    try:
        subprocess.run(
            ["ocrmypdf", "--skip-text", "--fast-web-view", "1", "--optimize", "0", str(pdf_path), str(ocred)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if ocred.exists():
            return ocred
    except Exception:
        pass
    return pdf_path

def backup_with_oid(file_path: Path):
    """Create backup with unique OID identifier"""
    oid = "OID-" + hashlib.sha256(file_path.read_bytes()).hexdigest()[:10].upper()
    backup = ORIG_BACKUP / f"{file_path.stem} [{oid}]{file_path.suffix}"
    if not backup.exists():
        shutil.copy2(str(file_path), str(backup))
    return backup, oid

def split_by_full_logic(pdf_path: Path):
    """Split PDF by topic, sender, and date changes"""
    segments = []
    with pdfplumber.open(pdf_path) as doc:
        cur_start = 0
        cur_bucket = cur_title = cur_date = None

        for i, page in enumerate(doc.pages):
            txt = page.extract_text() or ""
            b, title, d = detect_bucket_and_title(txt, pdf_path if i == 0 else None)

            changed = (cur_bucket is None) or (b != cur_bucket or title != cur_title or d != cur_date)

            if changed:
                if cur_bucket is not None:
                    segments.append((cur_start, i - 1, cur_bucket, cur_title, cur_date))
                cur_start, cur_bucket, cur_title, cur_date = i, b, title, d

        segments.append((cur_start, len(doc.pages)-1, cur_bucket, cur_title, cur_date))

    return segments

def export_segment(src: Path, seg, dest_base: Path, oid: str):
    """Export PDF segment with detailed filename"""
    s, e, bucket, title, date_s = seg
    reader = PdfReader(str(src))
    w = PdfWriter()

    for i in range(s, e+1):
        w.add_page(reader.pages[i])

    date_part = date_s or "undated"
    subj = safe_name(title or "Document")
    seg_len = e - s + 1

    name = f"{date_part} – {subj} [OID-{oid}] – p{str(1).zfill(2)}-p{str(seg_len).zfill(2)}.pdf"

    dest_dir = FOLDERS.get(bucket, FOLDERS["other"])
    out_path = dest_dir / name

    with open(out_path, "wb") as f:
        w.write(f)

    return bucket, out_path, (s+1, e+1), (1, seg_len), date_part, subj

# ========== MAIN PROCESSING ==========
print(f"\n{'='*60}")
print("DOCUMENT ORGANISER v3.1")
print(f"{'='*60}")
print(f"Working directory: {WORK}")
print(f"Output directory: {OUT}\n")

index = {"processed": [], "images": [], "errors": []}
stats = {"pdfs": 0, "images": 0, "segments": 0, "errors": 0}

allowed_exts = {'.pdf', '.jpg', '.jpeg', '.png'}
files = sorted([f for f in WORK.glob("*") 
                if f.suffix.lower() in allowed_exts 
                and not f.name.startswith("_") 
                and not f.name.startswith(".")])

total_files = len(files)
print(f"Found {total_files} files to process\n")

for idx, file in enumerate(files, 1):
    print(f"[{idx}/{total_files}] {file.name}")

    try:
        backup_path, oid = backup_with_oid(file)

        if file.suffix.lower() == ".pdf":
            searchable = ocr_pdf_if_needed(file)
            segments = split_by_full_logic(searchable)

            for seg in segments:
                bucket, outp, orig_pages, new_pages, date_part, subj = export_segment(searchable, seg, OUT, oid)
                index["processed"].append({
                    "src": file.name,
                    "backup": str(backup_path.relative_to(OUT)),
                    "oid": oid,
                    "saved_as": str(outp.relative_to(OUT)),
                    "bucket": bucket,
                    "date": date_part,
                    "title": subj,
                    "orig_pages": f"p{orig_pages[0]}-p{orig_pages[1]}",
                    "new_pages": f"p{new_pages[0]}-p{new_pages[1]}"
                })
                print(f"  → {date_part} – {subj} → {bucket}")
                stats["segments"] += 1

            if searchable != file and searchable.exists():
                searchable.unlink()

            stats["pdfs"] += 1

        else:
            img = Image.open(file)
            text = pytesseract.image_to_string(img)
            bucket, title, date_s = detect_bucket_and_title(text, file)

            dest_dir = FOLDERS.get(bucket, FOLDERS["other"])
            date_part = date_s or "undated"
            subj = safe_name(title or "Image Scan")
            newname = f"{date_part} – {subj} [OID-{oid}]{file.suffix}"
            out_path = dest_dir / newname

            shutil.copy2(file, out_path)

            index["images"].append({
                "src": file.name,
                "backup": str(backup_path.relative_to(OUT)),
                "oid": oid,
                "saved_as": str(out_path.relative_to(OUT)),
                "bucket": bucket,
                "date": date_part,
                "title": subj
            })
            print(f"  → {date_part} – {subj} → {bucket}")
            stats["images"] += 1

    except Exception as e:
        print(f"  ✗ ERROR: {str(e)}")
        index["errors"].append({"file": file.name, "error": str(e)})
        stats["errors"] += 1

# Save index files
with open(OUT / "_index.json", "w", encoding="utf-8") as f:
    json.dump(index, f, indent=2, ensure_ascii=False)

with open(OUT / "_index.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Source", "Backup", "OID", "Output", "Bucket", "Date", "Title", "Orig Pages", "New Pages"])

    for r in index.get("processed", []):
        w.writerow([r["src"], r["backup"], r["oid"], r["saved_as"], r["bucket"], 
                   r.get("date",""), r.get("title",""), r.get("orig_pages",""), r.get("new_pages","")])

    for r in index.get("images", []):
        w.writerow([r["src"], r["backup"], r["oid"], r["saved_as"], r["bucket"], 
                   r.get("date",""), r.get("title",""), "", ""])

print("\n" + "="*60)
print("PROCESSING COMPLETE")
print("="*60)
print(f"PDFs processed: {stats['pdfs']}")
print(f"Segments created: {stats['segments']}")
print(f"Images processed: {stats['images']}")
print(f"Errors: {stats['errors']}")
print(f"\nOutput: {OUT}")
print(f"Backups: {ORIG_BACKUP}")
print(f"Indexes: _index.json, _index.csv")
print("="*60 + "\n")
