import re, os

files = {
    "7FE01vXzbeM": "제18강_예수와_붓다",
    "56BsH5NG5YA": "제19강_윤회와_죽음",
    "pOwX4cJasg0": "제20강_최후의_문",
    "Qb0CehlLAHo": "제21강_명상의_목적은",
    "YzstkwBcR0U": "제22강_아무런_일도",
    "sJmNbmaBkM0": "제23강_집착과_집중_관찰",
    "1XDPO7UcyXQ": "제24강_의식은_경향적이다",
    "SyvaYNzfdU8": "제25강_집착을_내려놓으려면",
    "8nlevxqYpp0": "제26강_바르게_기도하는_법",
    "ykccY_eK7_o": "제27강_붓다의_인식론",
    "JW5ICGmlH3s": "제28강_기후변화와_의식의_시대",
    "AX7-kDPD7-k": "제29강_일상에서_깨어있으려면",
    "Rdh5PmG7s8w": "제30강_스님의_일기",
    "t1NgF1qcWNE": "제31강_천사_임사체험_사후",
    "_0L6-QaQhws": "제32강_신비한_능력"
}

for vid, title in files.items():
    vtt_path = f"{vid}.ko.vtt"
    if not os.path.exists(vtt_path):
        print(f"{title}: NO SUBS FILE")
        continue
    
    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    lines = content.split("\n")
    clean_lines = []
    for line in lines:
        if line.startswith("WEBVTT") or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        if "-->" in line:
            continue
        if line.strip() == "":
            continue
        line = re.sub(r'<00:\d+:\d+\.\d+><c>', '', line)
        line = re.sub(r'</c>', '', line)
        line = re.sub(r' align:start position:0%', '', line)
        line = line.strip()
        if line:
            clean_lines.append(line)
    
    full_text = "\n".join(clean_lines)
    output_path = f"clean_{vid}_{title}.txt"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)
    print(f"{title}: {len(clean_lines)} lines, {len(full_text)} chars -> {output_path}")

print("\n=== ALL DONE ===")
