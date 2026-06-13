#!/usr/bin/env python3
"""텍스트 파일을 자연스러운 목소리로 읽어주는 프로그램"""

import sys, os, asyncio, tempfile
import edge_tts

VOICE = "ko-KR-HyunsuMultilingualNeural"  # Hyunsu (현수, 남성 다국어) / InJoon (남성) / SunHi (여성)
SPEED = "+0%"  # "-10%" 느리게, "+10%" 빠르게

async def speak(text, voice=VOICE, rate=SPEED, save_path=None):
    tts = edge_tts.Communicate(text, voice, rate=rate)
    if save_path:
        await tts.save(save_path)
        print(f"저장 완료: {save_path}")
    else:
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        await tts.save(tmp.name)
        os.startfile(tmp.name)
        await asyncio.sleep(2)
        try:
            os.unlink(tmp.name)
        except:
            pass

def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("사용법:")
        print("  python read_aloud.py <파일경로> [시작줄] [끝줄]")
        print("  python read_aloud.py <파일경로> --save 출력.mp3")
        print("  python read_aloud.py <파일경로> [시작줄] [끝줄] --save 출력.mp3")
        print("예시:")
        print("  python read_aloud.py README.md            # 전체 듣기")
        print("  python read_aloud.py README.md 10 30      # 10~30줄 듣기")
        print('  python read_aloud.py README.md --save "C:\\Users\\user\\Desktop\\test.mp3"')
        return

    filepath = sys.argv[1]
    save_path = None
    start, end = 0, None

    args = sys.argv[2:]
    if "--save" in args:
        idx = args.index("--save")
        save_path = args[idx + 1] if idx + 1 < len(args) else None
        args = args[:idx]

    if len(args) >= 2:
        start = int(args[0]) - 1
        end = int(args[1])
    elif len(args) == 1:
        start = int(args[0]) - 1

    if not os.path.exists(filepath):
        print(f"파일 없음: {filepath}")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if end is None:
        end = len(lines)
    text = ''.join(lines[start:end])

    if not text.strip():
        print("읽을 내용이 없습니다.")
        return

    print(f"읽는 중... ({len(text)}글자, {end-start}줄)")
    asyncio.run(speak(text, save_path=save_path))
    print("완료!")

if __name__ == "__main__":
    main()
