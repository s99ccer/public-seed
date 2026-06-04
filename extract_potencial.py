import fitz, os, re

# Extract clean text from El Potencial Transferido
doc = fitz.open(r"C:\test\grinberg_books\El_Potencial_Transferido.pdf")
pages = doc.page_count
all_text = []
for i in range(pages):
    text = doc[i].get_text()
    # Keep only reasonable characters
    clean = re.sub(r'[^\x20-\x7E\n\r\t\u00C0-\u024F\u00D1\u00F1\u00BF\u00A1\u00BF]', ' ', text)
    all_text.append(clean)

full = "\n".join(all_text)
doc.close()

outpath = r"C:\test\grinberg_texts\El_Potencial_Transferido.txt"
with open(outpath, "w", encoding="utf-8") as f:
    f.write(full)

print(f"Pages: {pages}, Chars: {len(full)}, File: {outpath}")

# Read key metadata
# Look for keywords
keywords = ["sintergia", "syntergy", "potencial", "transferido", "experimento", "comunicaci", "telepat", "campo", "neuronal", "cuant"]
for kw in keywords:
    count = len(re.findall(kw, full, re.IGNORECASE))
    if count > 0:
        print(f"  '{kw}': {count} occurrences")
