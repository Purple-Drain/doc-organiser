#!/usr/bin/env python3
import os, re, json, csv, shutil, subprocess, hashlib
from pathlib import Path
from dateutil import parser as dtp
import pdfplumber
from PyPDF2 import PdfReader, PdfWriter
from PIL import Image
import pytesseract

# ---------- SETTINGS ----------
WORK = Path("/Users/aaron/TempScanWork/leftovers")
OUT = WORK / "_Organised"
ORIG_BACKUP = OUT / "_Originals"

OUT.mkdir(parents=True, exist_ok=True)
ORIG_BACKUP.mkdir(parents=True, exist_ok=True)

FOLDERS = {
    "bank":    OUT / "1 - Financial & Banking",
    "gov":     OUT / "2 - Government & Services",
    "retail":  OUT / "3 - Retail & Purchases",
    "manuals": OUT / "4 - Instructions & Manuals",
    "medical": OUT / "5 - Health & Medical",
    "other":   OUT / "9 - Other",
}
for p in FOLDERS.values():
    p.mkdir(parents=True, exist_ok=True)

# ---------- LOAD CONFIG ----------
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
        (re.compile(r"\b(bankwest|coles\s*credit\s*cards?|nab(?!\w)|westpac|comm(?:onwealth)?\s*bank|commbank|virgin\s*money)\b", re.I), "bank"),
        (re.compile(r"\b(australian\s*government|services\s*australia|department\s*of\s*social\s*services|nsw\s*government|council|centrelink)\b", re.I), "gov"),
        (re.compile(r"\b(petbarn|chemist\s*warehouse|decjuba|jb\s*hi[- ]?fi|ikea|country\s*road|adidas|bunnings|apex\s*petroleum|tax\s*invoice|receipt)\b", re.I), "retail"),
        (re.compile(r"\b(instruction|user\s*manual|guide|warranty|folding\s*board)\b", re.I), "manuals"),
        (re.compile(r"\b(pathology|ultrasound|referral|invoice.*(?:dental|dentist|clinic|pharmacy)|mometasone|insulin|doctor|\bdr\b|medical)\b", re.I), "medical"),
    ]
    NAMES_RX = [
        (re.compile(r"\bAaron\s+De\s+Vries\b", re.I), "Aaron De Vries"),
        (re.compile(r"\bSylvia\s+Lam\b", re.I), "Sylvia Lam"),
    ]

DATE_PAT = re.compile(
    r"("
    r"(?:\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})|"
    r"(?:\d{4}[-/]\d{1,2}[-/]\d{1,2})|"
    r"(?:\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})"
    r")"
)

def safe_name(s: str) -> str:
    s = re.sub(r"[^\w\s\-\&\(\)]", "", s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s or "Document"

def pick_date(text: str):
    m = DATE_PAT.search(text)
    if not m:
        return None
    try:
        return dtp.parse(m.group(1), dayfirst=True).date().isoformat()
    except Exception:
        return None

def detect_parties(text: str):
    found = []
    for rx, who in NAMES_RX:
        if rx.search(text):
            found.append(who)
    if len(found) == 2:
        return "Aaron & Sylvia"
    return " & ".join(found) if found else None

def extract_title_from_text(text: str, max_lines=5) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    candidates = [l for l in lines[:max_lines] if len(l) > 10]
    if candidates:
        return safe_name(candidates[0])
    return "Document"

def detect_bucket_and_title(text: str):
    lowered = text.lower()
    bucket = "other"
    for rx, b in ISSUER_RULES:
        if rx.search(lowered):
            bucket = b
            break
    title = extract_title_from_text(text)
    parties = detect_parties(text)
    if parties:
        title += f" – {parties}"
    return bucket, title, pick_date(text)

def ocr_pdf_if_needed(pdf_path: Path) -> Path:
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
            ["ocrmypdf", "--skip-text", "--fast-web-view", "1", "--optimize", "0",
             str(pdf_path), str(ocred)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if ocred.exists():
            return ocred
    except Exception:
        pass
    return pdf_path

def backup_with_oid(file_path: Path) -> tuple[Path, str]:
    oid = "OID-" + hashlib.sha256(file_path.read_bytes()).hexdigest()[:10].upper()
    backup = ORIG_BACKUP / f"{file_path.stem} [{oid}]{file_path.suffix}"
    if not backup.exists():
        shutil.copy2(str(file_path), str(backup))
    return backup, oid

def split_by_full_logic(pdf_path: Path):
    segments = []
    with pdfplumber.open(pdf_path) as doc:
        cur_start = 0
        cur_bucket = cur_title = cur_date = None
        for i, page in enumerate(doc.pages):
            txt = page.extract_text() or ""
            b, title, d = detect_bucket_and_title(txt)
            changed = (cur_bucket is None) or (b != cur_bucket or title != cur_title or d != cur_date)
            if changed:
                if cur_bucket is not None:
                    segments.append((cur_start, i-1, cur_bucket, cur_title, cur_date))
                cur_start, cur_bucket, cur_title, cur_date = i, b, title, d
        segments.append((cur_start, len(doc.pages)-1, cur_bucket, cur_title, cur_date))
    return segments

def export_segment(src: Path, seg, dest_base: Path, oid: str):
    s, e, bucket, title, date_s = seg
    reader = PdfReader(str(src))
    w = PdfWriter()
    for i in range(s, e+1):
        w.add_page(reader.pages[i])
    date_part = date_s or "undated"
    subj = safe_name(title or "Document")
    seg_len = e - s + 1
    name = f"{date_part} – {subj} [{oid}] – p{str(1).zfill(2)}-p{str(seg_len).zfill(2)}.pdf"
    dest_dir = FOLDERS.get(bucket, FOLDERS["other"])
    out_path = dest_dir / name
    with open(out_path, "wb") as f:
        w.write(f)
    return bucket, out_path, (s+1, e+1), (1, seg_len), date_part, subj

# ---------- MAIN ----------
index = {"processed": [], "images": [], "errors": []}
link_records = []
allowed_exts = {'.pdf', '.jpg', '.jpeg', '.png'}

for file in sorted(WORK.glob("*")):
    if file.name.startswith(("_", ".")): 
        continue
    if file.suffix.lower() not in allowed_exts: 
        continue

    try:
        backup_path, oid = backup_with_oid(file)

        if file.suffix.lower() == ".pdf":
            searchable = ocr_pdf_if_needed(file)
            segments = split_by_full_logic(searchable)
            seg_files = []
            for i, seg in enumerate(segments, 1):
                bucket, outp, gpages, lpages, dpart, subj = export_segment(searchable, seg, OUT, oid)
                index["processed"].append({
                    "src": file.name, "segment": i, "saved_as": str(outp.relative_to(OUT)), "bucket": bucket
                })
                seg_files.append({
                    "file": outp.name, "path": str(outp),
                    "global_pages": list(gpages), "local_pages": list(lpages),
                    "date": dpart, "title": subj, "bucket": bucket
                })
            link_records.append({
                "source": file.name, "backup": backup_path.name, "oid": oid, "segments": seg_files
            })
            if searchable != file and searchable.exists():
                try: searchable.unlink()
                except: pass

        else:
            img = Image.open(file)
            text = pytesseract.image_to_string(img)
            bucket, title, date_s = detect_bucket_and_title(text)
            date_part = date_s or "undated"
            subj = safe_name(title or "Document")
            name = f"{date_part} – {subj} [{oid}] – {file.name}"
            dest_dir = FOLDERS.get(bucket, FOLDERS["other"])
            out_path = dest_dir / name
            shutil.copy2(file, out_path)
            index["images"].append({"src": file.name, "saved_as": str(out_path.relative_to(OUT)), "bucket": bucket})
            link_records.append({
                "source": file.name, "backup": backup_path.name, "oid": oid,
                "segments": [{"file": out_path.name, "path": str(out_path), "global_pages": None, "local_pages": None,
                              "date": date_part, "title": subj, "bucket": bucket}]
            })

    except Exception as e:
        index["errors"].append({"file": file.name, "error": str(e)})

(OUT / "_index.json").write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")
with open(OUT / "_index.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["Source","Segment","Output","Bucket"])
    for r in index["processed"]: w.writerow([r["src"], r["segment"], r["saved_as"], r.get("bucket","")])
    for r in index["images"]:    w.writerow([r["src"], "", r["saved_as"], r.get("bucket","")])
(OUT / "_index_links.json").write_text(json.dumps(link_records, indent=2, ensure_ascii=False), encoding="utf-8")

print("✅ Done. Output in:", OUT)
print("   • Originals backed up in:", ORIG_BACKUP)
print("   • Link index:", OUT / "_index_links.json")
