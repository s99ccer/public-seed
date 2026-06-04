with open(r"C:\test\grinberg_summaries_korean.md", "r", encoding="utf-8") as f:
    content = f.read()

with open(r"C:\test\grinberg_summaries_korean_clean.md", "w", encoding="utf-8") as f:
    f.write(content)

# Count books
import re
books = re.findall(r"^## \d", content, re.MULTILINE)
print(f"Total books summarized: {len(books)}")
print(f"Total chars: {len(content)}")

# Print all section headers
for line in content.split("\n"):
    if line.startswith("## "):
        print(f"  Section: {line[:80]}")
