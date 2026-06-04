import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import pyupbit
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands

class BacktestWorker(QThread):
    """백테스팅 실행을 위한 별도 스레드"""
    finished = pyqtSignal(object)
    progress = pyqtSignal(str)
    
    def __init__(self, ticker, interval, start_date, end_date, indicators):
        super().__init__()
        self.ticker = ticker
        self.interval = interval
        self.start_date = start_date
        self.end_date = end_date
        self.indicators = indicators
        
    def run(self):
        try:
            # interval 매핑 (pyupbit 형식으로 변환)
            interval_map = {
                '4시간': 'minute240',
                '1일': 'day',
                '주봉': 'week'
            }
            upbit_interval = interval_map.get(self.interval, 'day')
            
            self.progress.emit("데이터 다운로드 중...")
            
            # OHLCV 데이터 가져오기
            df = pyupbit.get_ohlcv(self.ticker, interval=upbit_interval, 
                                   to=self.end_date, count=200)
            
            if df is None or len(df) == 0:
                self.progress.emit("데이터를 불러올 수 없습니다.")
                self.finished.emit(None)
                return
            
            # 날짜 범위로 필터링
            df.index = pd.to_datetime(df.index)
            df = df[(df.index >= pd.to_datetime(self.start_date)) & 
                    (df.index <= pd.to_datetime(self.end_date))]
            
            if len(df) == 0:
                self.progress.emit("선택한 날짜 범위에 데이터가 없습니다.")
                self.finished.emit(None)
                return
            
            # 보조지표 계산
            self.progress.emit("보조지표 계산 중...")
            df = self.calculate_indicators(df)
            
            # 백테스팅 실행
            self.progress.emit("백테스팅 실행 중...")
            results = self.run_backtest(df)
            results['df'] = df
            results['ticker'] = self.ticker
            results['interval'] = self.interval
            
            self.finished.emit(results)
            
        except Exception as e:
            self.progress.emit(f"오류 발생: {str(e)}")
            self.finished.emit(None)
    
    def calculate_indicators(self, df):
        """보조지표 계산"""
        
        # RSI (기본값 14일)
        if self.indicators.get('rsi', False):
            rsi = RSIIndicator(close=df['close'], window=14)
            df['RSI'] = rsi.rsi()
        
        # 볼린저 밴드 (기본값 20, 2)
        if self.indicators.get('bollinger', False):
            bb = BollingerBands(close=df['close'], window=20, window_dev=2)
            df['BB_upper'] = bb.bollinger_hband()
            df['BB_middle'] = bb.bollinger_mavg()
            df['BB_lower'] = bb.bollinger_lband()
        
        # Envelope (기본값 10%, 이동평균 20)
        if self.indicators.get('envelope', False):
            df['MA20'] = df['close'].rolling(window=20).mean()
            envelope_pct = self.indicators.get('envelope_pct', 10) / 100
            df['ENV_upper'] = df['MA20'] * (1 + envelope_pct)
            df['ENV_lower'] = df['MA20'] * (1 - envelope_pct)
        
        return df
    
    def run_backtest(self, df):
        """백테스팅 실행 (간단한 전략 예시)"""
        
        initial_balance = 1000000  # 초기 자금 100만원
        balance = initial_balance
        position = 0  # 보유 수량
        trades = []
        
        for i in range(1, len(df)):
            current_price = df['close'].iloc[i]
            prev_price = df['close'].iloc[i-1]
            
            buy_signal = False
            sell_signal = False
            
            # RSI 신호 (30 이하면 과매도로 매수, 70 이상이면 과매수로 매도)
            if self.indicators.get('rsi', False) and 'RSI' in df.columns:
                rsi_value = df['RSI'].iloc[i]
                if not pd.isna(rsi_value):
                    if rsi_value < 30:
                        buy_signal = True
                    elif rsi_value > 70:
                        sell_signal = True
            
            # 볼린저 밴드 신호 (하단 터치 시 매수, 상단 터치 시 매도)
            if self.indicators.get('bollinger', False) and all(col in df.columns for col in ['BB_lower', 'BB_upper']):
                bb_lower = df['BB_lower'].iloc[i]
                bb_upper = df['BB_upper'].iloc[i]
                if not pd.isna(bb_lower) and current_price <= bb_lower:
                    buy_signal = True
                if not pd.isna(bb_upper) and current_price >= bb_upper:
                    sell_signal = True
            
            # Envelope 신호 (하단 터치 시 매수, 상단 터치 시 매도)
            if self.indicators.get('envelope', False) and all(col in df.columns for col in ['ENV_lower', 'ENV_upper']):
                env_lower = df['ENV_lower'].iloc[i]
                env_upper = df['ENV_upper'].iloc[i]
                if not pd.isna(env_lower) and current_price <= env_lower:
                    buy_signal = True
                if not pd.isna(env_upper) and current_price >= env_upper:
                    sell_signal = True
            
            # 매수 실행
            if buy_signal and position == 0:
                position = balance / current_price
                balance = 0
                trades.append({
                    'date': df.index[i],
                    'type': 'BUY',
                    'price': current_price,
                    'quantity': position
                })
            
            # 매도 실행
            elif sell_signal and position > 0:
                balance = position * current_price
                position = 0
                trades.append({
                    'date': df.index[i],
                    'type': 'SELL',
                    'price': current_price,
                    'quantity': position
                })
        
        # 최종 결과 계산
        final_value = balance + (position * df['close'].iloc[-1] if position > 0 else 0)
        total_return = (final_value - initial_balance) / initial_balance * 100
        
        return {
            'initial_balance': initial_balance,
            'final_value': final_value,
            'total_return': total_return,
            'trades': trades,
            'num_trades': len(trades)
        }


class BacktestWindow(QMainWindow):
    """메인 프로그램 창"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("업비트 백테스팅 프로그램")
        self.setGeometry(100, 100, 1200, 800)
        
        self.worker = None
        self.results = None
        self.init_ui()
        self.load_tickers()
    
    def init_ui(self):
        """UI 초기화"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # 왼쪽: 설정 패널
        left_panel = QWidget()
        left_panel.setMaximumWidth(350)
        left_layout = QVBoxLayout(left_panel)
        
        # 코인 선택
        left_layout.addWidget(QLabel("코인 선택:"))
        self.coin_combo = QComboBox()
        self.coin_combo.setEditable(True)
        left_layout.addWidget(self.coin_combo)
        
        # 날짜 선택
        left_layout.addWidget(QLabel("시작 날짜:"))
        self.start_date = QDateEdit()
        self.start_date.setDate(QDate.currentDate().addDays(-30))
        self.start_date.setCalendarPopup(True)
        left_layout.addWidget(self.start_date)
        
        left_layout.addWidget(QLabel("종료 날짜:"))
        self.end_date = QDateEdit()
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        left_layout.addWidget(self.end_date)
        
        # 캔들 타임프레임 선택
        left_layout.addWidget(QLabel("캔들 타임프레임:"))
        self.candle_combo = QComboBox()
        self.candle_combo.addItems(["4시간", "1일", "주봉"])
        left_layout.addWidget(self.candle_combo)
        
        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        left_layout.addWidget(line)
        
        # 보조지표 선택
        left_layout.addWidget(QLabel("보조지표 설정:"))
        
        self.rsi_check = QCheckBox("RSI")
        left_layout.addWidget(self.rsi_check)
        
        self.bb_check = QCheckBox("볼린저 밴드")
        left_layout.addWidget(self.bb_check)
        
        self.env_check = QCheckBox("Envelope")
        left_layout.addWidget(self.env_check)
        
        # Envelope 퍼센트 설정
        env_layout = QHBoxLayout()
        env_layout.addWidget(QLabel("Envelope %:"))
        self.env_spin = QDoubleSpinBox()
        self.env_spin.setRange(1, 30)
        self.env_spin.setValue(10)
        self.env_spin.setSuffix("%")
        env_layout.addWidget(self.env_spin)
        left_layout.addLayout(env_layout)
        
        left_layout.addStretch()
        
        # 실행 버튼
        self.run_btn = QPushButton("백테스팅 실행")
        self.run_btn.setStyleSheet("background-color: #2ecc71; color: white; font-size: 14px; padding: 8px;")
        self.run_btn.clicked.connect(self.run_backtest)
        left_layout.addWidget(self.run_btn)
        
        # 진행 상태 표시
        self.status_label = QLabel("준비됨")
        left_layout.addWidget(self.status_label)
        
        # 오른쪽: 결과 패널 (탭 위젯)
        right_panel = QTabWidget()
        
        # 차트 탭
        self.chart_tab = QWidget()
        chart_layout = QVBoxLayout(self.chart_tab)
        self.figure = plt.Figure(figsize=(10, 6), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        right_panel.addTab(self.chart_tab, "차트")
        
        # 결과 요약 탭
        self.summary_tab = QWidget()
        summary_layout = QVBoxLayout(self.summary_tab)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        summary_layout.addWidget(self.summary_text)
        right_panel.addTab(self.summary_tab, "결과 요약")
        
        # 거래 내역 탭
        self.trades_tab = QWidget()
        trades_layout = QVBoxLayout(self.trades_tab)
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(4)
        self.trades_table.setHorizontalHeaderLabels(["날짜", "타입", "가격", "수량"])
        trades_layout.addWidget(self.trades_table)
        right_panel.addTab(self.trades_tab, "거래 내역")
        
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 3)
    
    def load_tickers(self):
        """업비트 코인 목록 로드"""
        try:
            tickers = pyupbit.get_tickers(fiat="KRW")
            for ticker in tickers:
                self.coin_combo.addItem(ticker)
        except Exception as e:
            self.coin_combo.addItem("KRW-BTC")
            self.coin_combo.addItem("KRW-ETH")
            self.coin_combo.addItem("KRW-XRP")
            self.status_label.setText(f"코인 목록 로드 실패: {str(e)}")
    
    def run_backtest(self):
        """백테스팅 실행"""
        ticker = self.coin_combo.currentText()
        interval = self.candle_combo.currentText()
        start_date = self.start_date.date().toString("yyyy-MM-dd")
        end_date = self.end_date.date().toString("yyyy-MM-dd")
        
        indicators = {
            'rsi': self.rsi_check.isChecked(),
            'bollinger': self.bb_check.isChecked(),
            'envelope': self.env_check.isChecked(),
            'envelope_pct': self.env_spin.value()
        }
        
        # 실행 버튼 비활성화
        self.run_btn.setEnabled(False)
        self.run_btn.setText("실행 중...")
        self.status_label.setText("백테스팅 시작...")
        
        # 워커 스레드 시작
        self.worker = BacktestWorker(ticker, interval, start_date, end_date, indicators)
        self.worker.progress.connect(self.update_status)
        self.worker.finished.connect(self.on_backtest_finished)
        self.worker.start()
    
    def update_status(self, message):
        """상태 업데이트"""
        self.status_label.setText(message)
    
    def on_backtest_finished(self, results):
        """백테스팅 완료 처리"""
        self.run_btn.setEnabled(True)
        self.run_btn.setText("백테스팅 실행")
        
        if results is None:
            self.status_label.setText("백테스팅 실패")
            return
        
        self.results = results
        self.status_label.setText("백테스팅 완료")
        
        # 결과 표시
        self.display_results(results)
        self.display_chart(results)
        self.display_trades(results)
    
    def display_results(self, results):
        """결과 요약 표시"""
        summary = f"""
        ===== 백테스팅 결과 요약 =====
        
        코인: {results['ticker']}
        타임프레임: {results['interval']}
        
        초기 자금: {results['initial_balance']:,.0f} 원
        최종 자금: {results['final_value']:,.0f} 원
        총 수익률: {results['total_return']:+.2f}%
        
        총 거래 횟수: {results['num_trades']}
        
        ============================
        """
        self.summary_text.setText(summary)
    
    def display_chart(self, results):
        """차트 표시"""
        df = results['df']
        
        self.figure.clear()
        
        # 메인 차트 (가격)
        ax1 = self.figure.add_subplot(211)
        ax1.plot(df.index, df['close'], label='Close Price', color='black', linewidth=1)
        
        # 볼린저 밴드
        if 'BB_upper' in df.columns:
            ax1.plot(df.index, df['BB_upper'], label='BB Upper', color='red', linestyle='--', alpha=0.7)
            ax1.plot(df.index, df['BB_middle'], label='BB Middle', color='blue', linestyle='--', alpha=0.7)
            ax1.plot(df.index, df['BB_lower'], label='BB Lower', color='red', linestyle='--', alpha=0.7)
            ax1.fill_between(df.index, df['BB_upper'], df['BB_lower'], alpha=0.1, color='gray')
        
        # Envelope
        if 'ENV_upper' in df.columns:
            ax1.plot(df.index, df['ENV_upper'], label='ENV Upper', color='green', linestyle=':', alpha=0.7)
            ax1.plot(df.index, df['ENV_lower'], label='ENV Lower', color='green', linestyle=':', alpha=0.7)
        
        # 매수/매도 포인트 표시
        if results['trades']:
            buy_dates = [t['date'] for t in results['trades'] if t['type'] == 'BUY']
            buy_prices = [df.loc[t['date'], 'close'] if t['date'] in df.index else None for t in results['trades'] if t['type'] == 'BUY']
            sell_dates = [t['date'] for t in results['trades'] if t['type'] == 'SELL']
            sell_prices = [df.loc[t['date'], 'close'] if t['date'] in df.index else None for t in results['trades'] if t['type'] == 'SELL']
            
            buy_prices = [p for p in buy_prices if p is not None]
            sell_prices = [p for p in sell_prices if p is not None]
            
            ax1.scatter(buy_dates[:len(buy_prices)], buy_prices, color='green', marker='^', s=100, label='Buy')
            ax1.scatter(sell_dates[:len(sell_prices)], sell_prices, color='red', marker='v', s=100, label='Sell')
        
        ax1.set_title(f"{results['ticker']} - {results['interval']} 차트")
        ax1.legend(loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # RSI 차트
        if 'RSI' in df.columns:
            ax2 = self.figure.add_subplot(212)
            ax2.plot(df.index, df['RSI'], label='RSI', color='purple', linewidth=1)
            ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='과매수 (70)')
            ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='과매도 (30)')
            ax2.set_ylim(0, 100)
            ax2.set_title('RSI')
            ax2.legend(loc='upper left')
            ax2.grid(True, alpha=0.3)
        
        self.figure.tight_layout()
        self.canvas.draw()
    
    def display_trades(self, results):
        """거래 내역 표시"""
        trades = results['trades']
        self.trades_table.setRowCount(len(trades))
        
        for i, trade in enumerate(trades):
            date_str = trade['date'].strftime("%Y-%m-%d %H:%M") if hasattr(trade['date'], 'strftime') else str(trade['date'])
            self.trades_table.setItem(i, 0, QTableWidgetItem(date_str))
            self.trades_table.setItem(i, 1, QTableWidgetItem(trade['type']))
            self.trades_table.setItem(i, 2, QTableWidgetItem(f"{trade['price']:,.0f}"))
            self.trades_table.setItem(i, 3, QTableWidgetItem(f"{trade['quantity']:.8f}"))
        
        self.trades_table.resizeColumnsToContents()


def main():
    app = QApplication(sys.argv)
    window = BacktestWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()