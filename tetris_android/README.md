# Tetris Android App

모바일 최적화된 테트리스 게임 (WebView 기반)

## 빌드 방법 (Android Studio)

1. Android Studio에서 `tetris_android/` 폴더 열기
2. Gradle Sync 실행
3. Run 버튼으로 APK 빌드 및 실행

## APK 직접 생성 (커맨드라인)

```bash
# Android SDK가 설치된 환경에서:
./gradlew assembleRelease
# 또는
gradlew.bat assembleRelease
```

## 게임 조작

- **터치/스와이프**: 좌/우 이동, 위 스와이프 = 회전, 아래 스와이프 = 하드 드롭
- **버튼**: 화면 우측의 버튼으로도 조작 가능
- **탭**: 보드를 탭하면 회전
- **키보드 (디버깅)**: 방향키, Space(하드 드롭), R(재시작)

## 특징

- 7가지 테트로미노 (I, O, T, S, Z, J, L)
- 라인 제거 점수 (100점/라인)
- 다음 블록 미리보기
- 게임 오버 및 재시작
- 전체화면 모드, 세로 방향 고정
