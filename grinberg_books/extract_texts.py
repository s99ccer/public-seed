import fitz, os, glob, json, re
from pathlib import Path

outdir = r"C:\test\grinberg_texts"
os.makedirs(outdir, exist_ok=True)

results = {}
files = sorted(glob.glob(r"C:\test\grinberg_books\*.pdf"))
for fpath in files:
    bname = os.path.basename(fpath)
    name = bname.replace(".pdf", "")
    try:
        doc = fitz.open(fpath)
        pages = doc.page_count
        total_chars = 0
        has_text = False
        text_parts = []
        for i in range(pages):
            text = doc[i].get_text()
            text_parts.append(text)
            total_chars += len(text)
            if len(text.strip()) > 50:
                has_text = True
        doc.close()
        
        full_text = "\n".join(text_parts)
        txt_path = os.path.join(outdir, name + ".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        
        results[name] = {
            "pages": pages,
            "chars": total_chars,
            "has_text": has_text,
            "size_kb": os.path.getsize(fpath) // 1024
        }
        status = "TEXT" if has_text else "SCAN"
        print(f"[{status}] {name}: {pages}p, {total_chars}c, {results[name]['size_kb']}KB")
    except Exception as e:
        results[name] = {"error": str(e)}
        print(f"[ERR] {name}: {e}")

summary_path = os.path.join(outdir, "_summary.json")
with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

text_count = sum(1 for v in results.values() if v.get("has_text"))
scan_count = sum(1 for v in results.values() if not v.get("has_text") and "error" not in v)
err_count = sum(1 for v in results.values() if "error" in v)
print(f"\n=== Summary: {len(results)} files, {text_count} extractable text, {scan_count} scanned images, {err_count} errors ===")
