import sys
import requests
from bs4 import BeautifulSoup
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit, QPushButton, QTextBrowser, QHBoxLayout, QLabel, QTabWidget, QFrame, QGraphicsOpacityEffect
from PyQt6.QtCore import Qt, QPropertyAnimation, QTimer, QUrl, QPoint
from PyQt6.QtGui import QPainter, QPolygon
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtQuick import QQuickWindow
from urllib.parse import urljoin, urlparse
import psutil, GPUtil, time

class JustBrowse(QWidget):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("JustBrowse")
        self.resize(515, 620)
        self.opacity_sys = 0.3
        self.setWindowOpacity(self.opacity_sys)
        # 建立動畫物件，綁定到視窗的 opacity 屬性
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(300)  # 動畫時間 (毫秒)
        
        self.status_expanded = False 
        
        self.color_text_sys = "rgba(170,170,170,0.5)"
        self.color_text_app = "rgba(127,127,127,1.0)"
        self.color_bg_sys = "rgba(127,127,127,0.05)"
        
        
        self.last_net = psutil.net_io_counters()
        self.last_time = time.time()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        if self.status_expanded:
            self.timer.start(2000)  # 每 2 秒更新一次
        
        # 取得螢幕大小
        screen = app.primaryScreen()
        rect = screen.availableGeometry()
        
        # 計算右下角座標
        x = rect.width() - self.width() - 50
        y = rect.height() - self.height() - 50
        
        # 移動視窗到右下角
        self.move(x, y)

        self.history = []   # 儲存瀏覽歷史
        self.current_index = -1
        self.always_on_top = True

        layout = QVBoxLayout()
        
        # 在 top_layout 裡加一個透明的拖曳區
        title_label = QLabel(" ⛶")
        title_label.setFixedHeight(20)  # 高度跟關閉按鈕一致
        title_label.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 3px;")  # 幾乎透明
        
        # 讓 title_label 可以拖曳視窗
        def mousePressEvent(event):
            if event.button() == Qt.MouseButton.LeftButton:
                title_label.drag_pos = event.globalPosition().toPoint() - title_label.window().frameGeometry().topLeft()
                event.accept()

        def mouseMoveEvent(event):
            if event.buttons() == Qt.MouseButton.LeftButton:
                title_label.window().move(event.globalPosition().toPoint() - title_label.drag_pos)
                event.accept()
        
        def mouseDoubleClickEvent(event):
            main_window = title_label.window()
            if main_window.isMaximized():
                main_window.showNormal()
            else:
                main_window.showMaximized()

        title_label.mouseDoubleClickEvent = mouseDoubleClickEvent
        title_label.mousePressEvent = mousePressEvent
        title_label.mouseMoveEvent = mouseMoveEvent
        
        # 最小化按鈕
        minimize_btn = QPushButton("-")
        minimize_btn.setFixedSize(20, 20)
        minimize_btn.setStyleSheet(f"background: rgba(0,0,255,0.05); color: {self.color_text_sys}; border: none; border-radius: 7px;")
        minimize_btn.clicked.connect(self.showMinimized)

        # 置頂開關
        self.toggle_btn = QPushButton("⌅")
        self.toggle_btn.setFixedSize(20, 20)
        self.toggle_btn.setStyleSheet(f"background: rgba(0,255,0,0.05); color: {self.color_text_sys}; border: none; border-radius: 7px;")
        self.toggle_btn.clicked.connect(self.toggle_on_top)
        
        # 關閉按鈕
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet(f"background: rgba(255,0,0,0.05); color: {self.color_text_sys}; border-radius: 7px;")
        close_btn.clicked.connect(self.close)

        # 標題列排版
        top_layout = QHBoxLayout()
        top_layout.addWidget(title_label)
        top_layout.addWidget(minimize_btn)
        top_layout.addWidget(self.toggle_btn)
        top_layout.addWidget(close_btn)
        layout.addLayout(top_layout)

        # 按鈕列
        button_layout = QHBoxLayout()
        self.back_button = QPushButton("←")
        self.back_button.setFixedSize(20, 20)
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 7px;")
        button_layout.addWidget(self.back_button)

        self.forward_button = QPushButton("→")
        self.forward_button.setFixedSize(20, 20)
        self.forward_button.clicked.connect(self.go_forward)
        self.forward_button.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 7px;")
        button_layout.addWidget(self.forward_button)
        
        # URL輸入框
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("輸入網址，例如 https://example.com")
        self.url_input.setText("https://github.com/allapse/JustBrowse")
        self.url_input.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 3px; padding: 1px;")
        button_layout.addWidget(self.url_input)
        
        self.fetch_button = QPushButton("↵")
        self.fetch_button.setFixedSize(20, 20)
        self.fetch_button.clicked.connect(self.fetch_page)
        self.fetch_button.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 7px;")
        button_layout.addWidget(self.fetch_button)

        layout.addLayout(button_layout)
        
        # 建立 Tab 面板
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.setStyleSheet(f"""
            QTabBar::tab {{background: rgba(200,200,0,0.05); color: {self.color_text_sys}; border-radius: 7px; padding: 3px; min-width: 100px}}
            QTabBar::tab:selected {{background: {self.color_bg_sys}; border-radius: 1px;}}
            QTabWidget::pane {{background: transparent; border-radius: 1px;}}
        """)
        
        # 第一個分頁：QTextBrowser
        self.text_browser = QTextBrowser()
        self.text_browser.setFrameShape(QFrame.Shape.NoFrame)
        # QTextBrowser 背景透明
        self.text_browser.setStyleSheet(f"background: {self.color_bg_sys};")
        self.text_browser.anchorClicked.connect(self.handle_link_click)
        self.tabs.addTab(self.text_browser, "Text")
        
        # 第二個分頁：QWebEngineView
        self.web_view = QWebEngineView()
        self.web_view.setUrl(QUrl("https://allapse.github.io/allgivz/givez.html"))
        self.web_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        self.tabs.addTab(self.web_view, "Web")
        
        # 狀態列 Label
        self.status_text = "⛗"
        self.status_label = QLabel(self.status_text)
        self.status_label.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_app}; border-radius: 3px; padding: 1px;")
        self.status_label.mouseDoubleClickEvent = self.toggle_status_label
        layout.addWidget(self.status_label)
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setLayout(layout)
        
    def fetch_page(self, url=None, add_to_history=True):
        if not url:
            url = self.url_input.text()
        try:
            # 判斷目前 Tab
            current_tab = self.tabs.currentIndex()
            
            if current_tab == 0:  # Text tab
                headers = {"User-Agent": "JustBrowse/1.0 (https://github.com/allapse/JustBrowse)"}
                response = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, "lxml")
                color = "rgba(0,127,0,0.8)"

                content = f'<h2 style="color:{color};">{soup.title.string if soup.title else "無標題"}</h2>'
                for p in soup.find_all("p"):
                    if len(p.get_text()) > 0:
                        color = "rgba(0,127,0,0.8)" if color==self.color_text_app else self.color_text_app
                        content += f'<p style="color:{color};">{p.get_text()}</p>'
                for a in soup.find_all("a", href=True):
                    link = a["href"]
                    text = a.get_text() or link
                    per = 10 + round(15/(2 + round(len(text) / 7)))
                    #color = "rgba(0,0,255,0.5)" if per > 14 else "rgba(127,127,127,0.9)"
                    color = "rgba(255,0,0,0.5)" if color==self.color_text_app else self.color_text_app
                    content += f'<span style="white-space: pre;"><a href="{link}" style="color:{color}; font-size:{per}px;">{text}</a>       </span>'
                
                self.text_browser.setHtml(content)

            elif current_tab == 1:  # Web tab
                self.web_view.setUrl(QUrl(url))

            # 更新歷史紀錄
            if add_to_history:
                if self.current_index < len(self.history) - 1:
                    self.history = self.history[:self.current_index+1]
                self.history.append(url)
                self.current_index += 1

        except Exception as e:
            self.text_browser.setPlainText(f"抓取失敗: {e}")

    def handle_link_click(self, url):
        new_url = url.toString()
        
        # 從目前輸入框的 URL 判斷 base
        current_url = self.url_input.text()
        parsed = urlparse(current_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # 拼接完整 URL
        full_url = urljoin(base_url, new_url)
        
        self.url_input.setText(full_url)
        self.fetch_page(full_url)

    def go_back(self):
        if self.current_index > 0:
            self.current_index -= 1
            prev_url = self.history[self.current_index]
            self.url_input.setText(prev_url)

            # 判斷目前 Tab
            if self.tabs.currentIndex() == 0:
                self.fetch_page(prev_url, add_to_history=False)
            else:
                self.web_view.setUrl(QUrl(prev_url))

    def go_forward(self):
        if self.current_index < len(self.history) - 1:
            self.current_index += 1
            next_url = self.history[self.current_index]
            self.url_input.setText(next_url)

            # 判斷目前 Tab
            if self.tabs.currentIndex() == 0:
                self.fetch_page(next_url, add_to_history=False)
            else:
                self.web_view.setUrl(QUrl(next_url))

            
    def toggle_on_top(self):
        if self.always_on_top:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint)  # 關掉置頂
            self.always_on_top = False
            self.toggle_btn.setText("⌆")
        else:
            self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)  # 開啟置頂
            self.always_on_top = True
            self.toggle_btn.setText("⌅")
        self.show()  # 重新顯示以套用旗標
        
    def enterEvent(self, event):
        # 滑鼠移入 → 漸變到
        self.anim.stop()
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(0.9)
        self.anim.start()
        event.accept()

    def leaveEvent(self, event):
        # 滑鼠移出 → 漸變
        self.anim.stop()
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(self.opacity_sys)
        self.anim.start()
        event.accept()
        
    def update_status(self):
        # CPU 使用率
        cpu = psutil.cpu_percent(interval=0)

        # RAM 使用率
        mem = psutil.virtual_memory().percent

        # GPU 使用率
        gpus = GPUtil.getGPUs()
        gpu_info = ""
        if gpus:
            gpu = gpus[0]
            gpu_info = f"[GPU]: {gpu.load*100:.1f}%  |  {gpu.temperature}°C  |  {gpu.memoryUsed/1024:.1f}/{gpu.memoryTotal/1024:.1f}GB"

        # 網路瞬間速度
        now_net = psutil.net_io_counters()
        now_time = time.time()
        interval = now_time - self.last_time

        recv_speed = (now_net.bytes_recv - self.last_net.bytes_recv) / 1024 / 1024 / interval  # MB/s
        sent_speed = (now_net.bytes_sent - self.last_net.bytes_sent) / 1024 / 1024 / interval  # MB/s

        net_info = f"[NET]: ↓{recv_speed:.2f} MB/s ↑{sent_speed:.2f} MB/s"

        # 更新狀態
        self.status_label.setText(f" [CPU]: {cpu}%  |  [RAM]: {mem}%\r\n {gpu_info}\r\n {net_info}")

        # 更新基準值
        self.last_net = now_net
        self.last_time = now_time
        
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()
            self.start_size = self.size()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            diff = event.globalPosition().toPoint() - self.drag_pos
            new_width = max(200, self.start_size.width() + diff.x())
            new_height = max(200, self.start_size.height() + diff.y())
            self.resize(new_width, new_height)
            
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(Qt.GlobalColor.lightGray)
        size = 7
        points = [
            QPoint(self.width()- 2 * size, self.height()- 2 * size),
            QPoint(self.width()- 3 * size, self.height()- 2 * size),
            QPoint(self.width()- 2 * size, self.height()- 3 * size)
        ]
        painter.drawPolygon(QPolygon(points))
        
    def toggle_status_label(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.status_expanded:
                # 收闔：顯示固定文字，停止更新
                self.status_label.setText(self.status_text)
                self.timer.stop()
                self.status_expanded = False
            else:
                # 展開：恢復更新
                self.last_net = psutil.net_io_counters()
                self.last_time = time.time()
                self.timer.start(2000)
                self.update_status()
                self.status_expanded = True      

app = QApplication(sys.argv)
window = JustBrowse()
window.fetch_page()
window.show()
sys.exit(app.exec())
