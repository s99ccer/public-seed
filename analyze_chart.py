import cv2
import numpy as np
from PIL import Image

img_path = r"C:\Users\user\Desktop\image.png"

pil_img = Image.open(img_path)
print(f"크기: {pil_img.width} x {pil_img.height}")
print(f"모드: {pil_img.mode}")
print(f"포맷: {pil_img.format}")

img = cv2.imread(img_path)
h, w = img.shape[:2]
print(f"OpenCV: {w}x{h}")

# 색상 분석 (좌우 반으로 나누어 추세 파악)
left = img[:, :w//2]
right = img[:, w//2:]

left_avg = cv2.mean(left)
right_avg = cv2.mean(right)

print(f"\n좌측 평균 색상 (BGR): ({left_avg[0]:.0f}, {left_avg[1]:.0f}, {left_avg[2]:.0f})")
print(f"우측 평균 색상 (BGR): ({right_avg[0]:.0f}, {right_avg[1]:.0f}, {right_avg[2]:.0f})")

# 녹색(양봉) / 적색(음봉) 비율
hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

# 녹색 범위 (양봉)
green_mask = cv2.inRange(hsv, np.array([40, 40, 40]), np.array([80, 255, 255]))
# 적색 범위 (음봉) - HSV에서 빨강은 0과 180 근처
red_mask1 = cv2.inRange(hsv, np.array([0, 40, 40]), np.array([10, 255, 255]))
red_mask2 = cv2.inRange(hsv, np.array([160, 40, 40]), np.array([180, 255, 255]))
red_mask = cv2.bitwise_or(red_mask1, red_mask2)

green_pixels = cv2.countNonZero(green_mask)
red_pixels = cv2.countNonZero(red_mask)
total = green_pixels + red_pixels

if total > 0:
    print(f"\n양봉(녹색) 비율: {green_pixels/total*100:.1f}%")
    print(f"음봉(적색) 비율: {red_pixels/total*100:.1f}%")

# Canny 에지 검출
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(gray, 50, 150)

# 허프 변환으로 선 검출
lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100, minLineLength=50, maxLineGap=10)

if lines is not None:
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2-y1, x2-x1))
        angles.append(angle)
    
    angles = np.array(angles)
    print(f"\n감지된 선분: {len(angles)}개")
    print(f"선 기울기 범위: {angles.min():.1f}° ~ {angles.max():.1f}°")
    print(f"평균 기울기: {angles.mean():.1f}°")
    
    # 수평에 가까운 선 (추세선 후보)
    horizontal = angles[(angles > -30) & (angles < 30)]
    if len(horizontal) > 0:
        print(f"수평/추세선 후보: {len(horizontal)}개 (평균 기울기: {horizontal.mean():.1f}°)")
else:
    print("\n감지된 선분 없음")

# 상단/하단 영역 밝기로 채널 추정
top = img[:h//4]
bottom = img[3*h//4:]
print(f"\n상단 25% 평균 밝기: {cv2.mean(cv2.cvtColor(top, cv2.COLOR_BGR2GRAY))[0]:.1f}")
print(f"하단 25% 평균 밝기: {cv2.mean(cv2.cvtColor(bottom, cv2.COLOR_BGR2GRAY))[0]:.1f}")

# 흰색/파란색 선 감지 (차트의 추세선)
white_mask = cv2.inRange(img, np.array([200, 200, 200]), np.array([255, 255, 255]))
blue_mask = cv2.inRange(img, np.array([150, 100, 0]), np.array([255, 200, 50]))
white_lines = cv2.countNonZero(white_mask)
blue_lines = cv2.countNonZero(blue_mask)
print(f"\n흰색 픽셀 (추세선/레이블): {white_lines}")
print(f"파란색 픽셀 (추세선): {blue_lines}")

# 텍스트 영역 감지 (흰색 배경에 검은 텍스트)
inverted = cv2.bitwise_not(gray)
text_areas = cv2.countNonZero(cv2.inRange(inverted, np.array([200]), np.array([255])))
print(f"텍스트/레이블 영역 비율: {text_areas/(h*w)*100:.1f}%")

print("\n=== 요약 ===")
print(f"이미지는 {pil_img.width}x{pil_img.height} 차트 스크린샷입니다.")
if green_pixels > red_pixels:
    print("양봉(녹색)이 음봉(적색)보다 많아 상승 추세 또는 횡보 중.")
else:
    print("음봉(적색)이 양봉(녹색)보다 많아 하락 추세 가능성.")
print(f"추세선/수평선 {len(angles) if lines is not None else 0}개 감지됨.")
