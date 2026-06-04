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
from matplotlib.figure import Figure
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
import warnings
warnings.filterwarnings('ignore')

class BacktestWorker(QThread):
    """백테스팅 실행을 위한 별도 스레드"""
    finished = pyqtSignal(object)
    progress = pyqtSignal(str)
    data_fetched = pyqtSignal(object)
    
    def __init__(self, ticker, interval, start_date, end_date, indicators, initial_balance=1000000):
        super().__init__()
        self.ticker = ticker
        self.interval = interval
        self.start_date = start_date
        self.end_date = end_date
        self.indicators = indicators
        self.initial_balance = initial_balance
        
    def run(self):
        try:
            # interval 매핑 (pyupbit 형식으로 변환)
            interval_map = {
                '4시간': 'minute240',
                '1일': 'day',
                '주봉': 'week'
            }
            upbit_interval = interval_map.get(self.interval, 'day')
            
            self.progress.emit(f"{self.ticker} 데이터 다운로드 중...")
            
            # 더 많은 데이터를 가져오기 위해 count 증가
            # 2020년부터 현재까지 약 4년치 데이터
            if upbit_interval == 'minute240':
                count = 9000  # 4시간봉: 9000개 = 약 1500일
            elif upbit_interval == 'day':
                count = 1500  # 일봉: 1500개 = 약 4년
            else:  # week
                count = 250   # 주봉: 250개 = 약 5년
                
            df = pyupbit.get_ohlcv(self.ticker, interval=upbit_interval, count=count)
            
            if df is None or len(df) == 0:
                self.progress.emit(f"{self.ticker} 데이터를 불러올 수 없습니다.")
                self.finished.emit(None)
                return
            
            # 날짜 범위로 필터링 (2020년부터)
            df.index = pd.to_datetime(df.index)
            start_dt = pd.to_datetime(self.start_date)
            end_dt = pd.to_datetime(self.end_date)
            df = df[(df.index >= start_dt) & (df.index <= end_dt)]
            
            if len(df) == 0:
                self.progress.emit(f"{self.ticker} 선택한 날짜 범위에 데이터가 없습니다.")
                self.finished.emit(None)
                return
            
            self.data_fetched.emit(df)
            
            # 보조지표 계산
            self.progress.emit(f"{self.ticker} 보조지표 계산 중...")
            df = self.calculate_indicators(df)
            
            # 백테스팅 실행
            self.progress.emit(f"{self.ticker} 백테스팅 실행 중...")
            results = self.run_backtest(df)
            results['df'] = df
            results['ticker'] = self.ticker
            results['interval'] = self.interval
            results['initial_balance'] = self.initial_balance
            
            self.finished.emit(results)
            
        except Exception as e:
            self.progress.emit(f"오류 발생: {str(e)}")
            self.finished.emit(None)
    
    def calculate_indicators(self, df):
        """보조지표 계산"""
        
        # RSI (기본값 14)
        if self.indicators.get('rsi', False):
            rsi = RSIIndicator(close=df['close'], window=14)
            df['RSI'] = rsi.rsi()
        
        # 볼린저 밴드 (기본값 20, 2)
        if self.indicators.get('bollinger', False):
            bb = BollingerBands(close=df['close'], window=20, window_dev=2)
            df['BB_upper'] = bb.bollinger_hband()
            df['BB_middle'] = bb.bollinger_mavg()
            df['BB_lower'] = bb.bollinger_lband()
        
        # Envelope (기본값 5%, 이동평균 20)
        if self.indicators.get('envelope', False):
            df['MA20'] = df['close'].rolling(window=20).mean()
            envelope_pct = self.indicators.get('envelope_pct', 5) / 100
            df['ENV_upper'] = df['MA20'] * (1 + envelope_pct)
            df['ENV_lower'] = df['MA20'] * (1 - envelope_pct)
        
        return df
    
    def run_backtest(self, df):
        """백테스팅 실행 (조합 전략)"""
        
        balance = self.initial_balance
        position = 0  # 보유 수량
        trades = []
        in_position = False
        entry_price = 0
        
        # 슬리피지 및 수수료 설정 (0.05%)
        fee_rate = 0.0005
        
        for i in range(20, len(df)):  # 지표 계산을 위해 20번째부터 시작
            current_price = df['close'].iloc[i]
            
            buy_signals = []
            sell_signals = []
            
            # RSI 신호 (30 이하면 과매도로 매수, 70 이상이면 과매수로 매도)
            if self.indicators.get('rsi', False) and 'RSI' in df.columns:
                rsi_value = df['RSI'].iloc[i]
                if not pd.isna(rsi_value):
                    if rsi_value < 30:
                        buy_signals.append('RSI')
                    elif rsi_value > 70:
                        sell_signals.append('RSI')
            
            # 볼린저 밴드 신호
            if self.indicators.get('bollinger', False) and all(col in df.columns for col in ['BB_lower', 'BB_upper']):
                bb_lower = df['BB_lower'].iloc[i]
                bb_upper = df['BB_upper'].iloc[i]
                if not pd.isna(bb_lower) and current_price <= bb_lower:
                    buy_signals.append('BB')
                if not pd.isna(bb_upper) and current_price >= bb_upper:
                    sell_signals.append('BB')
            
            # Envelope 신호
            if self.indicators.get('envelope', False) and all(col in df.columns for col in ['ENV_lower', 'ENV_upper']):
                env_lower = df['ENV_lower'].iloc[i]
                env_upper = df['ENV_upper'].iloc[i]
                if not pd.isna(env_lower) and current_price <= env_lower:
                    buy_signals.append('ENV')
                if not pd.isna(env_upper) and current_price >= env_upper:
                    sell_signals.append('ENV')
            
            # 매수 조건 (2개 이상의 지표가 동시에 매수 신호)
            buy_condition = len(buy_signals) >= 2
            
            # 매도 조건 (1개 이상의 지표가 매도 신호)
            sell_condition = len(sell_signals) >= 1
            
            # 매수 실행
            if buy_condition and not in_position:
                # 수수료 적용
                amount_to_invest = balance * (1 - fee_rate)
                position = amount_to_invest / current_price
                balance = 0
                in_position = True
                entry_price = current_price
                trades.append({
                    'date': df.index[i],
                    'type': 'BUY',
                    'price': current_price,
                    'quantity': position,
                    'signals': buy_signals.copy()
                })
            
            # 매도 실행
            elif sell_condition and in_position:
                # 수수료 적용
                balance = position * current_price * (1 - fee_rate)
                position = 0
                in_position = False
                trades.append({
                    'date': df.index[i],
                    'type': 'SELL',
                    'price': current_price,
                    'quantity': 0,
                    'signals': sell_signals.copy(),
                    'profit_pct': (current_price - entry_price) / entry_price * 100
                })
        
        # 마지막 포지션 정리
        if in_position:
            final_price = df['close'].iloc[-1]
            balance = position * final_price * (1 - fee_rate)
        
        # 결과 계산
        final_value = balance
        total_return = (final_value - self.initial_balance) / self.initial_balance * 100
        
        # 추가 통계
        winning_trades = [t for t in trades if t.get('profit_pct', 0) > 0]
        losing_trades = [t for t in trades if t.get('profit_pct', 0) < 0]
        
        return {
            'final_value': final_value,
            'total_return': total_return,
            'trades': trades,
            'num_trades': len(trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': len(winning_trades) / len(trades) * 100 if trades else 0,
            'max_drawdown': self.calculate_max_drawdown(df, trades)
        }
    
    def calculate_max_drawdown(self, df, trades):
        """최대 낙폭 계산"""
        try:
            # 간단한 포트폴리오 가치 계산
            portfolio_values = []
            balance = self.initial_balance
            position = 0
            
            for i in range(len(df)):
                current_price = df['close'].iloc[i]
                # 해당 날짜의 거래 찾기
                trade = next((t for t in trades if t['date'] == df.index[i]), None)
                if trade:
                    if trade['type'] == 'BUY':
                        position = balance / trade['price']
                        balance = 0
                    elif trade['type'] == 'SELL':
                        balance = position * trade['price']
                        position = 0
                
                current_value = balance + (position * current_price if position > 0 else 0)
                portfolio_values.append(current_value)
            
            if portfolio_values:
                peak = portfolio_values[0]
                max_dd = 0
                for value in portfolio_values:
                    if value > peak:
                        peak = value
                    dd = (peak - value) / peak * 100
                    if dd > max_dd:
                        max_dd = dd
                return max_dd
        except:
            pass
        return 0


class BacktestWindow(QMainWindow):
    """메인 프로그램 창"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("업비트 백테스팅 프로그램 v2.0")
        self.setGeometry(100, 100, 1400, 900)
        
        self.worker = None
        self.results = None
        self.current_data = None
        self.init_ui()
        self.load_tickers()
    
    def init_ui(self):
        """UI 초기화"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        # 왼쪽: 설정 패널
        left_panel = QWidget()
        left_panel.setMaximumWidth(400)
        left_panel.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        left_layout = QVBoxLayout(left_panel)
        
        # 코인 선택 그룹
        coin_group = QGroupBox("코인 선택")
        coin_layout = QVBoxLayout()
        
        self.coin_list = QListWidget()
        self.coin_list.setSelectionMode(QListWidget.MultiSelection)
        self.coin_list.setMaximumHeight(150)
        coin_layout.addWidget(QLabel("복수 선택 가능 (Ctrl+클릭):"))
        coin_layout.addWidget(self.coin_list)
        
        # 빠른 선택 버튼
        btn_layout = QHBoxLayout()
        select_all_btn = QPushButton("전체 선택")
        select_all_btn.clicked.connect(self.select_all_coins)
        clear_all_btn = QPushButton("전체 해제")
        clear_all_btn.clicked.connect(self.clear_all_coins)
        btn_layout.addWidget(select_all_btn)
        btn_layout.addWidget(clear_all_btn)
        coin_layout.addLayout(btn_layout)
        
        coin_group.setLayout(coin_layout)
        left_layout.addWidget(coin_group)
        
        # 날짜 선택
        date_group = QGroupBox("기간 설정")
        date_layout = QGridLayout()
        
        date_layout.addWidget(QLabel("시작 날짜:"), 0, 0)
        self.start_date = QDateEdit()
        self.start_date.setDate(QDate(2020, 1, 1))
        self.start_date.setCalendarPopup(True)
        self.start_date.setMinimumDate(QDate(2018, 1, 1))
        self.start_date.setMaximumDate(QDate.currentDate())
        date_layout.addWidget(self.start_date, 0, 1)
        
        date_layout.addWidget(QLabel("종료 날짜:"), 1, 0)
        self.end_date = QDateEdit()
        self.end_date.setDate(QDate.currentDate())
        self.end_date.setCalendarPopup(True)
        self.end_date.setMaximumDate(QDate.currentDate())
        date_layout.addWidget(self.end_date, 1, 1)
        
        # 빠른 기간 선택
        date_layout.addWidget(QLabel("빠른 선택:"), 2, 0)
        quick_btn_layout = QHBoxLayout()
        btn_1y = QPushButton("1년")
        btn_2y = QPushButton("2년")
        btn_3y = QPushButton("3년")
        btn_all = QPushButton("2020년~현재")
        btn_1y.clicked.connect(lambda: self.set_quick_date(365))
        btn_2y.clicked.connect(lambda: self.set_quick_date(730))
        btn_3y.clicked.connect(lambda: self.set_quick_date(1095))
        btn_all.clicked.connect(self.set_full_date)
        quick_btn_layout.addWidget(btn_1y)
        quick_btn_layout.addWidget(btn_2y)
        quick_btn_layout.addWidget(btn_3y)
        quick_btn_layout.addWidget(btn_all)
        date_layout.addLayout(quick_btn_layout, 2, 1)
        
        date_group.setLayout(date_layout)
        left_layout.addWidget(date_group)
        
        # 캔들 타임프레임 선택
        candle_group = QGroupBox("캔들 타임프레임")
        candle_layout = QVBoxLayout()
        self.candle_combo = QComboBox()
        self.candle_combo.addItems(["4시간", "1일", "주봉"])
        candle_layout.addWidget(self.candle_combo)
        candle_group.setLayout(candle_layout)
        left_layout.addWidget(candle_group)
        
        # 보조지표 선택
        indicator_group = QGroupBox("보조지표 설정")
        indicator_layout = QVBoxLayout()
        
        self.rsi_check = QCheckBox("RSI (과매수 70 / 과매도 30)")
        self.bb_check = QCheckBox("볼린저 밴드 (20일, 2시그마)")
        self.env_check = QCheckBox("Envelope (이동평균 ± %)")
        
        indicator_layout.addWidget(self.rsi_check)
        indicator_layout.addWidget(self.bb_check)
        indicator_layout.addWidget(self.env_check)
        
        # Envelope 퍼센트 설정
        env_pct_layout = QHBoxLayout()
        env_pct_layout.addWidget(QLabel("Envelope 비율:"))
        self.env_spin = QDoubleSpinBox()
        self.env_spin.setRange(1, 20)
        self.env_spin.setValue(5)
        self.env_spin.setSuffix("%")
        self.env_spin.setSingleStep(0.5)
        env_pct_layout.addWidget(self.env_spin)
        indicator_layout.addLayout(env_pct_layout)
        
        indicator_group.setLayout(indicator_layout)
        left_layout.addWidget(indicator_group)
        
        # 초기 자금 설정
        money_group = QGroupBox("초기 자금 설정")
        money_layout = QHBoxLayout()
        money_layout.addWidget(QLabel("초기 투자금:"))
        self.initial_balance = QSpinBox()
        self.initial_balance.setRange(100000, 100000000)
        self.initial_balance.setValue(1000000)
        self.initial_balance.setSingleStep(100000)
        self.initial_balance.setSuffix(" 원")
        money_layout.addWidget(self.initial_balance)
        money_group.setLayout(money_layout)
        left_layout.addWidget(money_group)
        
        left_layout.addStretch()
        
        # 실행 버튼
        self.run_btn = QPushButton("백테스팅 실행")
        self.run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2ecc71;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #27ae60;
            }
            QPushButton:disabled {
                background-color: #95a5a6;
            }
        """)
        self.run_btn.clicked.connect(self.run_backtest)
        left_layout.addWidget(self.run_btn)
        
        # 진행 상태 표시
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        left_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("준비됨")
        self.status_label.setStyleSheet("color: #7f8c8d; padding: 5px;")
        left_layout.addWidget(self.status_label)
        
        # 오른쪽: 결과 패널 (탭 위젯)
        right_panel = QTabWidget()
        right_panel.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ccc;
                border-radius: 5px;
            }
            QTabBar::tab {
                padding: 8px 16px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #2ecc71;
                color: white;
            }
        """)
        
        # 차트 탭
        self.chart_tab = QWidget()
        chart_layout = QVBoxLayout(self.chart_tab)
        self.figure = Figure(figsize=(12, 8), dpi=100)
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        right_panel.addTab(self.chart_tab, "📈 차트")
        
        # 결과 요약 탭
        self.summary_tab = QWidget()
        summary_layout = QVBoxLayout(self.summary_tab)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setStyleSheet("font-family: monospace; font-size: 11px;")
        summary_layout.addWidget(self.summary_text)
        right_panel.addTab(self.summary_tab, "📊 결과 요약")
        
        # 거래 내역 탭
        self.trades_tab = QWidget()
        trades_layout = QVBoxLayout(self.trades_tab)
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(6)
        self.trades_table.setHorizontalHeaderLabels(["날짜", "타입", "가격", "수량", "신호", "수익률(%)"])
        self.trades_table.horizontalHeader().setStretchLastSection(True)
        trades_layout.addWidget(self.trades_table)
        right_panel.addTab(self.trades_tab, "📝 거래 내역")
        
        # 비교 탭
        self.compare_tab = QWidget()
        compare_layout = QVBoxLayout(self.compare_tab)
        self.compare_text = QTextEdit()
        self.compare_text.setReadOnly(True)
        compare_layout.addWidget(self.compare_text)
        right_panel.addTab(self.compare_tab, "🔄 코인별 비교")
        
        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 3)
    
    def load_tickers(self):
        """업비트 코인 목록 로드"""
        self.coin_list.addItem("KRW-BTC (비트코인)")
        self.coin_list.addItem("KRW-ETH (이더리움)")
        self.coin_list.addItem("KRW-XRP (리플)")
        self.coin_list.addItem("KRW-DOGE (도지코인)")
        self.coin_list.addItem("KRW-SOL (솔라나)")
        self.coin_list.addItem("KRW-XLM (스텔라)")
        self.coin_list.addItem("KRW-ADA (에이다)")
        
        # 실제 업비트 API로 코인 목록 가져오기 시도
        try:
            tickers = pyupbit.get_tickers(fiat="KRW")
            if tickers:
                self.coin_list.clear()
                for ticker in tickers:
                    name_map = {
                        "KRW-BTC": "비트코인", "KRW-ETH": "이더리움", "KRW-XRP": "리플",
                        "KRW-DOGE": "도지코인", "KRW-SOL": "솔라나", "KRW-XLM": "스텔라",
                        "KRW-ADA": "에이다"
                    }
                    if ticker in name_map:
                        self.coin_list.addItem(f"{ticker} ({name_map[ticker]})")
                    elif "KRW-" in ticker:
                        self.coin_list.addItem(ticker)
        except:
            pass
    
    def select_all_coins(self):
        """모든 코인 선택"""
        for i in range(self.coin_list.count()):
            self.coin_list.item(i).setSelected(True)
    
    def clear_all_coins(self):
        """모든 코인 선택 해제"""
        for i in range(self.coin_list.count()):
            self.coin_list.item(i).setSelected(False)
    
    def set_quick_date(self, days):
        """빠른 날짜 설정"""
        end = QDate.currentDate()
        start = end.addDays(-days)
        self.start_date.setDate(start)
        self.end_date.setDate(end)
    
    def set_full_date(self):
        """전체 기간 설정 (2020년~현재)"""
        self.start_date.setDate(QDate(2020, 1, 1))
        self.end_date.setDate(QDate.currentDate())
    
    def run_backtest(self):
        """백테스팅 실행"""
        selected_items = self.coin_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "경고", "최소 1개 이상의 코인을 선택해주세요.")
            return
        
        selected_coins = [item.text().split(" ")[0] for item in selected_items]
        
        interval = self.candle_combo.currentText()
        start_date = self.start_date.date().toString("yyyy-MM-dd")
        end_date = self.end_date.date().toString("yyyy-MM-dd")
        
        indicators = {
            'rsi': self.rsi_check.isChecked(),
            'bollinger': self.bb_check.isChecked(),
            'envelope': self.env_check.isChecked(),
            'envelope_pct': self.env_spin.value()
        }
        
        if not any([indicators['rsi'], indicators['bollinger'], indicators['envelope']]):
            QMessageBox.warning(self, "경고", "최소 1개 이상의 보조지표를 선택해주세요.")
            return
        
        initial_balance = self.initial_balance.value()
        
        # 실행 버튼 비활성화
        self.run_btn.setEnabled(False)
        self.run_btn.setText("실행 중...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(selected_coins))
        self.progress_bar.setValue(0)
        
        # 모든 결과를 저장할 리스트
        self.all_results = []
        self.current_coin_index = 0
        self.selected_coins = selected_coins
        self.backtest_params = {
            'interval': interval,
            'start_date': start_date,
            'end_date': end_date,
            'indicators': indicators,
            'initial_balance': initial_balance
        }
        
        # 첫 번째 코인 백테스팅 시작
        self.run_next_backtest()
    
    def run_next_backtest(self):
        """다음 코인 백테스팅 실행"""
        if self.current_coin_index >= len(self.selected_coins):
            self.on_all_backtests_finished()
            return
        
        ticker = self.selected_coins[self.current_coin_index]
        self.status_label.setText(f"처리 중: {ticker} ({self.current_coin_index + 1}/{len(self.selected_coins)})")
        
        self.worker = BacktestWorker(
            ticker,
            self.backtest_params['interval'],
            self.backtest_params['start_date'],
            self.backtest_params['end_date'],
            self.backtest_params['indicators'],
            self.backtest_params['initial_balance']
        )
        self.worker.progress.connect(self.update_status)
        self.worker.finished.connect(self.on_backtest_finished)
        self.worker.start()
    
    def update_status(self, message):
        """상태 업데이트"""
        self.status_label.setText(message)
    
    def on_backtest_finished(self, results):
        """개별 백테스팅 완료 처리"""
        if results is not None:
            self.all_results.append(results)
        
        self.progress_bar.setValue(self.current_coin_index + 1)
        self.current_coin_index += 1
        
        # 다음 코인 실행
        self.run_next_backtest()
    
    def on_all_backtests_finished(self):
        """모든 백테스팅 완료 처리"""
        self.run_btn.setEnabled(True)
        self.run_btn.setText("백테스팅 실행")
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"완료! {len(self.all_results)}개 코인 백테스팅 완료")
        
        if not self.all_results:
            self.status_label.setText("백테스팅 결과가 없습니다.")
            return
        
        # 마지막 결과를 차트에 표시
        self.results = self.all_results[-1]
        self.display_results(self.results)
        self.display_chart(self.results)
        self.display_trades(self.results)
        self.display_comparison()
        
        QMessageBox.information(self, "완료", f"{len(self.all_results)}개 코인의 백테스팅이 완료되었습니다.")
    
    def display_results(self, results):
        """결과 요약 표시"""
        summary = f"""
╔══════════════════════════════════════════════════════════════════╗
║                    백테스팅 결과 요약                              ║
╠══════════════════════════════════════════════════════════════════╣
║  코인: {results['ticker']:<50}║
║  타임프레임: {results['interval']:<47}║
╠══════════════════════════════════════════════════════════════════╣
║  초기 자금: {results['initial_balance']:>15,.0f} 원                              ║
║  최종 자금: {results['final_value']:>15,.0f} 원                              ║
║  총 수익률: {results['total_return']:>14,.2f} %                              ║
╠══════════════════════════════════════════════════════════════════╣
║  총 거래 횟수: {results['num_trades']:<43}║
║  승리 거래: {results['winning_trades']:<43}║
║  패배 거래: {results['losing_trades']:<43}║
║  승률: {results['win_rate']:<44.1f} %║
║  최대 낙폭: {results['max_drawdown']:<44.1f} %║
╚══════════════════════════════════════════════════════════════════╝
        """
        self.summary_text.setText(summary)
    
    def display_chart(self, results):
        """차트 표시"""
        df = results['df']
        
        self.figure.clear()
        
        # 메인 차트 (가격)
        ax1 = self.figure.add_subplot(211)
        ax1.plot(df.index, df['close'], label='종가', color='black', linewidth=1.5, alpha=0.8)
        
        # 볼린저 밴드
        if 'BB_upper' in df.columns:
            ax1.plot(df.index, df['BB_upper'], label='BB 상단', color='red', linestyle='--', alpha=0.7, linewidth=1)
            ax1.plot(df.index, df['BB_middle'], label='BB 중간', color='blue', linestyle='--', alpha=0.7, linewidth=1)
            ax1.plot(df.index, df['BB_lower'], label='BB 하단', color='red', linestyle='--', alpha=0.7, linewidth=1)
            ax1.fill_between(df.index, df['BB_upper'], df['BB_lower'], alpha=0.1, color='gray')
        
        # Envelope
        if 'ENV_upper' in df.columns:
            ax1.plot(df.index, df['ENV_upper'], label='ENV 상단', color='green', linestyle=':', alpha=0.7, linewidth=1)
            ax1.plot(df.index, df['ENV_lower'], label='ENV 하단', color='green', linestyle=':', alpha=0.7, linewidth=1)
        
        # 매수/매도 포인트 표시
        if results['trades']:
            buy_dates = [t['date'] for t in results['trades'] if t['type'] == 'BUY']
            buy_prices = [df.loc[t['date'], 'close'] for t in results['trades'] if t['type'] == 'BUY' and t['date'] in df.index]
            sell_dates = [t['date'] for t in results['trades'] if t['type'] == 'SELL']
            sell_prices = [df.loc[t['date'], 'close'] for t in results['trades'] if t['type'] == 'SELL' and t['date'] in df.index]
            
            ax1.scatter(buy_dates, buy_prices, color='green', marker='^', s=100, label='매수', zorder=5)
            ax1.scatter(sell_dates, sell_prices, color='red', marker='v', s=100, label='매도', zorder=5)
        
        ax1.set_title(f"{results['ticker']} - {results['interval']} 차트", fontsize=12, fontweight='bold')
        ax1.set_ylabel('가격 (KRW)')
        ax1.legend(loc='upper left', fontsize=9)
        ax1.grid(True, alpha=0.3)
        
        # RSI 차트
        if 'RSI' in df.columns:
            ax2 = self.figure.add_subplot(212)
            ax2.plot(df.index, df['RSI'], label='RSI', color='purple', linewidth=1.5)
            ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5, label='과매수 (70)')
            ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5, label='과매도 (30)')
            ax2.fill_between(df.index, 70, 100, alpha=0.1, color='red')
            ax2.fill_between(df.index, 0, 30, alpha=0.1, color='green')
            ax2.set_ylim(0, 100)
            ax2.set_title('RSI (상대강도지수)', fontsize=10, fontweight='bold')
            ax2.set_xlabel('날짜')
            ax2.set_ylabel('RSI 값')
            ax2.legend(loc='upper left', fontsize=9)
            ax2.grid(True, alpha=0.3)
        
        self.figure.tight_layout()
        self.canvas.draw()
    
    def display_trades(self, results):
        """거래 내역 표시"""
        trades = results['trades']
        self.trades_table.setRowCount(len(trades))
        
        for i, trade in enumerate(trades):
            date_str = trade['date'].strftime("%Y-%m-%d %H:%M")
            self.trades_table.setItem(i, 0, QTableWidgetItem(date_str))
            self.trades_table.setItem(i, 1, QTableWidgetItem(trade['type']))
            self.trades_table.setItem(i, 2, QTableWidgetItem(f"{trade['price']:,.0f}"))
            
            if trade['type'] == 'BUY':
                self.trades_table.setItem(i, 3, QTableWidgetItem(f"{trade['quantity']:.6f}"))
            else:
                self.trades_table.setItem(i, 3, QTableWidgetItem("-"))
            
            signals = ', '.join(trade.get('signals', []))
            self.trades_table.setItem(i, 4, QTableWidgetItem(signals))
            
            profit = trade.get('profit_pct', 0)
            profit_item = QTableWidgetItem(f"{profit:+.2f}%" if profit else "-")
            if profit > 0:
                profit_item.setForeground(QColor(46, 204, 113))
            elif profit < 0:
                profit_item.setForeground(QColor(231, 76, 60))
            self.trades_table.setItem(i, 5, profit_item)
        
        self.trades_table.resizeColumnsToContents()
    
    def display_comparison(self):
        """코인별 비교 결과 표시"""
        if not self.all_results:
            return
        
        comparison = "╔════════════════════════════════════════════════════════════════════════════════╗\n"
        comparison += "║                           코인별 성과 비교                                      ║\n"
        comparison += "╠════════════════════════════════════════════════════════════════════════════════╣\n"
        comparison += f"║ {'코인':<15} {'최종자금':>15} {'수익률':>12} {'거래수':>8} {'승률':>8} {'최대낙폭':>10} ║\n"
        comparison += "╠════════════════════════════════════════════════════════════════════════════════╣\n"
        
        # 수익률 기준