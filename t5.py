import requests
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import time
from typing import List, Dict, Tuple, Optional
from scipy import stats

class UpbitParallelChannelAnalyzer:
    """업비트 비트코인 Parallel Channel 자동 분석기"""
    
    def __init__(self, market: str = "KRW-BTC"):
        self.base_url = "https://api.upbit.com"
        self.market = market
        self.df = None
        
    def fetch_daily_candles(self, count: int = 200, to_time: str = None) -> List[Dict]:
        """일봉 데이터 조회"""
        url = f"{self.base_url}/v1/candles/days"
        params = {"market": self.market, "count": count}
        if to_time:
            params["to"] = to_time
            
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return response.json()
        raise Exception(f"API 오류: {response.status_code}")
    
    def fetch_all_daily_candles(self, target_count: int = 365) -> pd.DataFrame:
        """전체 일봉 데이터 수집"""
        all_candles = []
        last_time = None
        remaining = target_count
        
        print(f"📊 {self.market} 일봉 데이터 수집 중...")
        
        while remaining > 0:
            fetch_count = min(200, remaining)
            candles = self.fetch_daily_candles(fetch_count, last_time)
            
            if not candles:
                break
                
            all_candles.extend(candles)
            print(f"  → {len(candles)}개 수집 (총 {len(all_candles)}/{target_count})")
            
            last_time = candles[-1]["candle_date_time_utc"]
            remaining -= len(candles)
            time.sleep(0.3)
        
        df = pd.DataFrame(all_candles)
        df = df[["candle_date_time_kst", "opening_price", "high_price", 
                 "low_price", "trade_price", "candle_acc_trade_volume"]]
        df.columns = ["datetime", "open", "high", "low", "close", "volume"]
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime").reset_index(drop=True)
        
        print(f"✅ 완료! 총 {len(df)}개 데이터")
        self.df = df
        return df
    
    def find_peaks_and_troughs(self, lookback: int = 5) -> Tuple[List[int], List[int]]:
        """
        국지적 고점(Peak)과 저점(Trough) 찾기
        
        Args:
            lookback: 피크/트로프 판단을 위한 좌우 비교 범위
        """
        highs = self.df['high'].values
        lows = self.df['low'].values
        n = len(highs)
        
        peaks = []  # 고점 인덱스
        troughs = []  # 저점 인덱스
        
        for i in range(lookback, n - lookback):
            # 고점 찾기: 현재 고점이 양옆 lookback 범위 내 최대값인지 확인
            if highs[i] == max(highs[i-lookback:i+lookback+1]):
                peaks.append(i)
            
            # 저점 찾기: 현재 저점이 양옆 lookback 범위 내 최소값인지 확인
            if lows[i] == min(lows[i-lookback:i+lookback+1]):
                troughs.append(i)
        
        return peaks, troughs
    
    def fit_channel_lines(self, peaks: List[int], troughs: List[int], 
                          days: int = 180) -> Dict:
        """
        상단선(저항)과 하단선(지지) 회귀선 피팅
        
        Returns:
            상단선, 하단선 정보가 담긴 딕셔너리
        """
        if len(self.df) == 0:
            return None
            
        # 최근 days일 데이터만 사용
        start_idx = max(0, len(self.df) - days)
        plot_df = self.df.iloc[start_idx:].reset_index(drop=True)
        plot_indices = np.arange(len(plot_df))
        plot_dates = plot_df['datetime']
        
        # 인덱스 조정 (plot_df 기준)
        adjusted_peaks = [p - start_idx for p in peaks if p >= start_idx]
        adjusted_troughs = [t - start_idx for t in troughs if t >= start_idx]
        
        # 상단선 (고점들로 회귀분석)
        if len(adjusted_peaks) >= 2:
            peak_x = np.array(adjusted_peaks)
            peak_y = plot_df.iloc[adjusted_peaks]['high'].values
            peak_slope, peak_intercept, _, _, _ = stats.linregress(peak_x, peak_y)
            upper_line = peak_slope * plot_indices + peak_intercept
        else:
            upper_line = None
            peak_slope = None
            
        # 하단선 (저점들로 회귀분석)
        if len(adjusted_troughs) >= 2:
            trough_x = np.array(adjusted_troughs)
            trough_y = plot_df.iloc[adjusted_troughs]['low'].values
            trough_slope, trough_intercept, _, _, _ = stats.linregress(trough_x, trough_y)
            lower_line = trough_slope * plot_indices + trough_intercept
        else:
            lower_line = None
            trough_slope = None
            
        return {
            'plot_df': plot_df,
            'plot_indices': plot_indices,
            'plot_dates': plot_dates,
            'peaks': adjusted_peaks,
            'troughs': adjusted_troughs,
            'upper_line': upper_line,
            'lower_line': lower_line,
            'peak_slope': peak_slope,
            'trough_slope': trough_slope
        }
    
    def calculate_channel_width(self, upper_line: np.ndarray, 
                                lower_line: np.ndarray) -> float:
        """채널 폭 계산"""
        if upper_line is not None and lower_line is not None:
            return np.mean(upper_line - lower_line)
        return 0
    
    def plot_parallel_channel(self, days: int = 180, lookback: int = 5):
        """
        Parallel Channel 차트 그리기
        """
        if self.df is None:
            print("❌ 데이터가 없습니다. 먼저 fetch_all_daily_candles()를 실행하세요.")
            return
        
        # 1. 피크/트로프 찾기
        peaks, troughs = self.find_peaks_and_troughs(lookback=lookback)
        
        # 2. 채널 라인 피팅
        channel_data = self.fit_channel_lines(peaks, troughs, days)
        if channel_data is None:
            print("❌ 채널 생성 실패")
            return
        
        plot_df = channel_data['plot_df']
        plot_indices = channel_data['plot_indices']
        plot_dates = channel_data['plot_dates']
        upper_line = channel_data['upper_line']
        lower_line = channel_data['lower_line']
        
        # 3. 차트 그리기
        fig, ax = plt.subplots(figsize=(16, 10))
        
        # 캔들차트 (바 형태)
        for i, (idx, row) in enumerate(plot_df.iterrows()):
            color = 'red' if row['close'] >= row['open'] else 'blue'
            # 몸통
            ax.plot([i, i], [row['open'], row['close']], 
                   color=color, linewidth=10, alpha=0.7)
            # 심지
            ax.plot([i, i], [row['low'], row['high']], 
                   color=color, linewidth=1.5, alpha=0.5)
        
        # 고점 표시
        if channel_data['peaks']:
            peak_y = plot_df.iloc[channel_data['peaks']]['high'].values
            ax.scatter(channel_data['peaks'], peak_y, 
                      color='red', s=80, zorder=5, label='고점 (Peak)', marker='^')
            
        # 저점 표시
        if channel_data['troughs']:
            trough_y = plot_df.iloc[channel_data['troughs']]['low'].values
            ax.scatter(channel_data['troughs'], trough_y, 
                      color='green', s=80, zorder=5, label='저점 (Trough)', marker='v')
        
        # 상단 채널선 (저항선)
        if upper_line is not None:
            ax.plot(plot_indices, upper_line, 'r--', linewidth=2, 
                   label=f'상단 저항선 (기울기: {channel_data["peak_slope"]:.2f})')
            
        # 하단 채널선 (지지선)
        if lower_line is not None:
            ax.plot(plot_indices, lower_line, 'g--', linewidth=2,
                   label=f'하단 지지선 (기울기: {channel_data["trough_slope"]:.2f})')
        
        # 채널 영역 채우기 (두 선이 모두 있을 때)
        if upper_line is not None and lower_line is not None:
            ax.fill_between(plot_indices, lower_line, upper_line, 
                           alpha=0.15, color='yellow', label='Parallel Channel')
            channel_width = self.calculate_channel_width(upper_line, lower_line)
            ax.text(0.02, 0.95, f'채널 폭: {channel_width:,.0f}원', 
                   transform=ax.transAxes, fontsize=11,
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))
        
        # 차트 꾸미기
        ax.set_title(f'비트코인 {self.market} Parallel Channel (평행 채널)\n최근 {days}일, 피크/트로프 Lookback={lookback}', 
                    fontsize=14, fontweight='bold')
        ax.set_xlabel('날짜 (최신순)', fontsize=12)
        ax.set_ylabel('가격 (KRW)', fontsize=12)
        ax.legend(loc='upper left')
        ax.grid(True, alpha=0.3)
        
        # X축 레이블 (일부만 표시)
        step = max(1, len(plot_dates) // 15)
        xtick_positions = range(0, len(plot_dates), step)
        xtick_labels = [plot_dates[i].strftime('%m/%d') for i in xtick_positions]
        ax.set_xticks(xtick_positions)
        ax.set_xticklabels(xtick_labels, rotation=45, fontsize=9)
        
        # 현재가 표시
        current_price = plot_df['close'].iloc[-1]
        ax.axhline(y=current_price, color='purple', linestyle='-', 
                  linewidth=1.5, alpha=0.7, label=f'현재가: {current_price:,.0f}원')
        
        plt.tight_layout()
        plt.show()
        
        # 분석 결과 출력
        self.print_channel_analysis(channel_data, current_price)
    
    def print_channel_analysis(self, channel_data: Dict, current_price: float):
        """채널 분석 결과 출력"""
        print("\n" + "="*60)
        print("📐 Parallel Channel 분석 결과")
        print("="*60)
        
        if channel_data['peak_slope'] is not None:
            print(f"📈 상단 저항선 기울기: {channel_data['peak_slope']:.2f}원/일")
        if channel_data['trough_slope'] is not None:
            print(f"📉 하단 지지선 기울기: {channel_data['trough_slope']:.2f}원/일")
            
        if channel_data['peak_slope'] is not None and channel_data['trough_slope'] is not None:
            slope_diff = abs(channel_data['peak_slope'] - channel_data['trough_slope'])
            if slope_diff < 100:
                print(f"✅ 두 선의 기울기 차이: {slope_diff:.2f} → 평행도 우수")
            else:
                print(f"⚠️ 두 선의 기울기 차이: {slope_diff:.2f} → 평행도 낮음 (채널 깨짐 가능성)")
        
        # 현재가 채널 내 위치 확인
        if channel_data['upper_line'] is not None and channel_data['lower_line'] is not None:
            last_idx = len(channel_data['plot_df']) - 1
            current_upper = channel_data['upper_line'][last_idx]
            current_lower = channel_data['lower_line'][last_idx]
            
            print(f"\n💰 현재 채널 내 위치:")
            print(f"   상단 저항: {current_upper:,.0f}원")
            print(f"   하단 지지: {current_lower:,.0f}원")
            print(f"   현재 가격: {current_price:,.0f}원")
            
            if current_price > current_upper:
                print("   🔴 상단 저항선 상향 돌파 → 강세 신호")
            elif current_price < current_lower:
                print("   🟢 하단 지지선 하향 이탈 → 약세 신호")
            else:
                channel_pos = (current_price - current_lower) / (current_upper - current_lower) * 100
                print(f"   채널 내 위치: {channel_pos:.1f}% (0%=지지선, 100%=저항선)")
                if channel_pos > 80:
                    print("   ⚠️ 저항선 근접 → 조정 가능성")
                elif channel_pos < 20:
                    print("   ⚠️ 지지선 근접 → 반등 가능성")


# 실행 예제
if __name__ == "__main__":
    # 1. 분석기 인스턴스 생성
    analyzer = UpbitParallelChannelAnalyzer(market="KRW-BTC")
    
    # 2. 1년치 일봉 데이터 수집
    analyzer.fetch_all_daily_candles(target_count=365)
    
    # 3. Parallel Channel 차트 그리기
    # lookback: 피크/트로프 판단 범위 (값이 클수록 더 큰 파동만 감지)
    analyzer.plot_parallel_channel(days=180, lookback=5)