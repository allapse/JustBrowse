import sys
import yaml
import argparse
import platform
from PyQt6.QtWidgets import QApplication, QWidget, QSplashScreen
from PyQt6.QtCore import Qt, QTimer, QUrl, QPoint, QPointF
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtGui import QPainter, QPolygon, QPixmap, QColor, QWindow, QBrush

parser = argparse.ArgumentParser(description="JustBrowse with config")
parser.add_argument("--config", "-c", default="config.yaml", help="指定配置檔路徑")
args = parser.parse_args()

# 讀取配置檔
with open(args.config, "r", encoding="utf-8") as f:
    CONFIG = yaml.safe_load(f)
    
windows = []
focus_window = None

class JustBrowse(QWidget):
    def __init__(self):
        super().__init__()
        
        import psutil, GPUtil, time
        from PyQt6.QtWidgets import QVBoxLayout, QLineEdit, QPushButton, QTextBrowser, QHBoxLayout, QLabel, QSizePolicy, QTabWidget, QFrame, QProgressBar, QListWidget, QGraphicsOpacityEffect, QToolButton
        from PyQt6.QtCore import QPropertyAnimation
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        from PyQt6.QtQuick import QQuickWindow
        
        self.psutil = psutil
        self.GPUtil = GPUtil
        self.time = time
        
        # 取得螢幕大小
        screen = app.primaryScreen()
        self.ageo = screen.availableGeometry()
        
        self.setWindowTitle(CONFIG["window"]["title"])
        # 使用配置檔的視窗尺寸
        self.resize(CONFIG["window"]["width"], CONFIG["window"]["height"])
        self.opacity_bg = CONFIG["window"]["opacity_bg"]
        self.opacity_fade = CONFIG["window"]["opacity_fade"]
        self.opacity_focus = CONFIG["window"]["opacity_focus"]
        self.setWindowOpacity(self.opacity_fade)
        # 建立動畫物件，綁定到視窗的 opacity 屬性
        self.anim = QPropertyAnimation(self, b"windowOpacity")
        self.anim.setDuration(CONFIG["default"]["animation_duration"] )  # 動畫時間 (毫秒)
        
        self.status_expanded = CONFIG["default"]["status_expanded"] 
        self.force_rst = CONFIG["default"]["force_rst"] 
        self.dock_parent_cmd = CONFIG["default"]["dock_parent_cmd"] 
        self.always_on_top = CONFIG["default"]["always_on_top"] 
        self.bg_lock = CONFIG["default"]["bg_lock"] 
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # 允許接收焦點
        
        # 使用配置檔的顏色
        self.color_text_sys = f'rgba({CONFIG["colors"]["text_sys"]})'
        self.color_text_app = f'rgba({CONFIG["colors"]["text_app"]})'
        self.color_bg_sys   = f'rgba({CONFIG["colors"]["bg_sys"]},{self.opacity_bg})'
        self.shadow_offset = (0, 0)
        self.shadow_alpha = 0
        
        self.last_net = psutil.net_io_counters()
        self.last_disk = psutil.disk_io_counters()
        self.last_time = time.time()
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_status)
        
        self.history = []   # 儲存瀏覽歷史
        self.history_index = -1
        
        layout = QVBoxLayout()
        
        self.button_size = max(20, min(CONFIG["window"]["button_size"], 40));
        
        # 在 top_layout 裡加一個透明的拖曳區
        self.title_label = QLabel("  ⛶")
        self.title_label.setFixedHeight(self.button_size)  # 高度跟關閉按鈕一致
        self.title_label.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 3px;")  # 幾乎透明
        
        # 讓 title_label 可以拖曳視窗
        def mousePressEvent(event):
            if event.button() == Qt.MouseButton.LeftButton:
                # 記錄滑鼠初始位置
                self.drag_pos = event.globalPosition().toPoint()
                event.accept()

        def mouseMoveEvent(event):
            if event.buttons() == Qt.MouseButton.LeftButton:
                # 計算位移差
                current_pos = event.globalPosition().toPoint()
                delta = current_pos - self.drag_pos
                self.drag_pos = current_pos  # 更新基準點

                if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                    # Ctrl + 拖曳 → 移動所有視窗 (保持相對位置)
                    for w in windows:
                        w.move(w.pos() + delta)
                else:
                    # 單獨移動當前視窗
                    self.window().move(self.window().pos() + delta)

                event.accept()
                
        def mouseDoubleClickEvent(event):
            self.dock_space()

        self.title_label.mouseDoubleClickEvent = mouseDoubleClickEvent
        self.title_label.mousePressEvent = mousePressEvent
        self.title_label.mouseMoveEvent = mouseMoveEvent
        
        # 背景鎖定按鈕
        self.bg_lock_btn = QPushButton("◒" if self.bg_lock else "◓")
        self.bg_lock_btn.setFixedSize(self.button_size, self.button_size)
        self.bg_lock_btn.setStyleSheet(f"background: rgba(255,255,0,{self.opacity_bg}); color: {self.color_text_sys}; border: none; border-radius: 7px;")
        
        def on_bg_lock_clicked():
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                for w in windows:
                    w.toggle_bg_lock()
            else:
                self.toggle_bg_lock()
                
        self.bg_lock_btn.clicked.connect(on_bg_lock_clicked)
        
        # 最小化按鈕
        minimize_btn = QPushButton("-")
        minimize_btn.setFixedSize(self.button_size, self.button_size)
        minimize_btn.setStyleSheet(f"background: rgba(0,0,255,{self.opacity_bg}); color: {self.color_text_sys}; border: none; border-radius: 7px;")
        
        def on_minimize_clicked():
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                # Ctrl + 點 minimize → 最小化所有視窗
                for w in windows:
                    w.showMinimized()
            else:
                # 單純 minimize → 只最小化自己
                focus_window.showMinimized()
                
        minimize_btn.clicked.connect(on_minimize_clicked)

        # 置頂開關
        self.toggle_btn = QPushButton("⌅" if self.always_on_top else "⌆")
        self.toggle_btn.setFixedSize(self.button_size, self.button_size)
        self.toggle_btn.setStyleSheet(f"background: rgba(0,255,0,{self.opacity_bg}); color: {self.color_text_sys}; border: none; border-radius: 7px;")
        
        def on_toggle_clicked():
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                for w in windows:
                    w.toggle_on_top()
            else:
                focus_window.toggle_on_top()
                
        self.toggle_btn.clicked.connect(on_toggle_clicked)
        
        # 關閉按鈕
        close_btn = QPushButton("×")
        close_btn.setFixedSize(self.button_size, self.button_size)
        close_btn.setStyleSheet(f"background: rgba(255,0,0,{self.opacity_bg}); color: {self.color_text_sys}; border-radius: 7px;")
        
        def on_close_clicked():
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                for w in list(windows):
                    w.close()
            else:
                focus_window.close()
        
        close_btn.clicked.connect(on_close_clicked)

        # 標題列排版
        top_layout = QHBoxLayout()
        top_layout.addWidget(self.title_label)
        top_layout.addWidget(self.bg_lock_btn)
        top_layout.addWidget(minimize_btn)
        top_layout.addWidget(self.toggle_btn)
        top_layout.addWidget(close_btn)
        layout.addLayout(top_layout)

        # 按鈕列
        button_layout = QHBoxLayout()
        self.back_button = QPushButton("←")
        self.back_button.setFixedSize(self.button_size, self.button_size)
        self.back_button.clicked.connect(self.go_back)
        self.back_button.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 7px;")
        button_layout.addWidget(self.back_button)

        self.forward_button = QPushButton("→")
        self.forward_button.setFixedSize(self.button_size, self.button_size)
        self.forward_button.clicked.connect(self.go_forward)
        self.forward_button.setStyleSheet(f"""
            QPushButton {{background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 7px;}}
            QPushButton:disabled {{background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: {round(self.button_size / 2)}px;}}
        """)
        button_layout.addWidget(self.forward_button)
        
        # URL輸入框
        self.url_input = QLineEdit()
        self.url_input.setFixedHeight(self.button_size)
        self.url_input.setPlaceholderText("   ↵")
        self.url_input.setText(CONFIG["default"]["url_text"])
        self.url_input.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 3px; padding: 1px;")
        button_layout.addWidget(self.url_input)
        
        self.reload_button = QPushButton("↺")
        self.reload_button.setFixedSize(self.button_size, self.button_size)
        self.reload_button.clicked.connect(self.on_reload_button_clicked)
        self.reload_button.setStyleSheet(f"""
            QPushButton {{background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 7px;}}
            QPushButton:disabled {{background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: {round(self.button_size / 2)}px;}}
        """)
        button_layout.addWidget(self.reload_button)
        
        self.url_input.returnPressed.connect(self.fetch_page)

        layout.addLayout(button_layout)
        
        def set_sys_opacity(widget, value=0.5):
            effect = QGraphicsOpacityEffect()
            effect.setOpacity(value)
            widget.setGraphicsEffect(effect)
        
        # 建立 Tab 面板
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        self.tabs.setStyleSheet(f"""
            QTabBar::tab {{background: rgba(220,220,0,{self.opacity_bg}); color: {self.color_text_sys}; border-radius: 7px; margin-right: 7px; min-width: 100px; min-height: {10 + 0.5 * self.button_size}px;}}
            QTabBar::tab:selected {{background: {self.color_bg_sys}; color: {self.color_text_sys}; border-radius: 1px;}}
            QTabWidget::pane {{background: transparent; border-radius: 1px;}}
            QTabBar::scroller {{background: {self.color_bg_sys}; border: none;}}
            QTabBar QToolButton {{border: none; padding: 4px;}}
        """)
        tabbar = self.tabs.tabBar()
        buttons = tabbar.findChildren(QToolButton)

        for btn in buttons:
            set_sys_opacity(btn)
        
        # 第一個分頁：QTextBrowser
        self.text_browser = QTextBrowser()
        self.text_browser.setOpenLinks(False)
        self.text_browser.setFrameShape(QFrame.Shape.NoFrame)
        # QTextBrowser 背景透明
        self.text_browser.setStyleSheet(f"""
            QTextBrowser {{
                background: {self.color_bg_sys};
                border: none;
            }}
        """)
        self.text_browser.anchorClicked.connect(self.handle_link_click)
        self.tabs.addTab(self.text_browser, "Text")
        self.tabs.tabBar().setTabData(self.tabs.indexOf(self.text_browser), {"type": "Text", "title": "Text"})
        set_sys_opacity(self.text_browser.verticalScrollBar())
        set_sys_opacity(self.text_browser.horizontalScrollBar())
        
        # 第二個分頁：QWebEngineView
        self.web_view = MyWebView()
        self.web_view.setUrl(QUrl(CONFIG["default"]["url_web"]))
        self.web_view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        self.web_view.settings().setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        self.tabs.addTab(self.web_view, "Web")
        self.tabs.tabBar().setTabData(self.tabs.indexOf(self.web_view), {"type": "Web", "title": "Web"})
        self.web_view.loadFinished.connect(self.sync_url_input)
        
        # Html請求分頁: QWebEnginePage
        self.requestPage = QWebEnginePage()
        self.requestPage.loadFinished.connect(self.on_load_finished)
        
        if platform.system() == "Windows":
            import windows_dock
            self.windows_dock = windows_dock
        
            # 建立清單分頁
            self.app_list = QListWidget()
            # QTextBrowser 背景透明
            self.app_list.setStyleSheet(f"""
                QListWidget {{
                    background: {self.color_bg_sys};
                    color: {self.color_text_app};
                    border: none;
                }}
            """)
            self.tabs.addTab(self.app_list, "App")
            self.tabs.tabBar().setTabData(self.tabs.indexOf(self.app_list), {"type": "App", "title": "App"})
            set_sys_opacity(self.app_list.verticalScrollBar())
            set_sys_opacity(self.app_list.horizontalScrollBar())

            def on_app_item_changed(current, previous):
                if current:
                    data = current.data(Qt.ItemDataRole.UserRole)
                    if data:
                        current_tab = self.tabs.tabBar().tabData(self.tabs.currentIndex()).get("type")
                        if current_tab == "App":
                            self.url_input.setText(f"hwnd: {data['hwnd']}, pid: {data['pid']}")
            
            self.app_list.currentItemChanged.connect(on_app_item_changed)
            
            def on_item_double_clicked(item):
                hwnd = int(item.data(Qt.ItemDataRole.UserRole)["hwnd"])
                index = self.windows_dock.dock_window(self.tabs, hwnd, self.app_list)
                self.tabs.setCurrentIndex(index)
                
            self.app_list.itemDoubleClicked.connect(on_item_double_clicked)
            
            self.windows_dock.reload_app_list(self.app_list)
            if self.dock_parent_cmd:
                self.windows_dock.dock_parent_cmd(self, self.tabs, self.app_list)
                
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        # 狀態列 Label
        status_layout = QHBoxLayout()
        self.status_text = "⛗"
        self.status_label = QLabel(self.status_text)
        self.status_label.setMinimumHeight(self.button_size)
        self.status_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.status_label.setStyleSheet(f"background: {self.color_bg_sys}; color: {self.color_text_app}; border-radius: 3px; padding: 1px; font-family: 'Courier New';")
        
        def status_mouseDoubleClickEvent(event):
            self.toggle_status_label()
            
        self.status_label.mouseDoubleClickEvent = status_mouseDoubleClickEvent
        status_layout.addWidget(self.status_label)
        
        # CPU / RAM / GPU 垂直進度條
        self.cpu_bar = QProgressBar()
        self.cpu_bar.setOrientation(Qt.Orientation.Vertical)
        self.cpu_bar.setRange(0, 100)
        self.cpu_bar.setFixedWidth(self.button_size)
        self.cpu_bar.setFormat("🅲")
        self.cpu_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 2px;
                background: rgba(0,0,255,{self.opacity_bg});
                text-align: center;
                color: {self.color_text_app};
            }}
            QProgressBar::chunk {{
                background-color: {self.color_text_sys};
                border-radius: 2px;
            }}
        """)
        self.cpu_bar.hide()
        status_layout.addWidget(self.cpu_bar)

        self.ram_bar = QProgressBar()
        self.ram_bar.setOrientation(Qt.Orientation.Vertical)
        self.ram_bar.setRange(0, 100)
        self.ram_bar.setFixedWidth(self.button_size)
        self.ram_bar.setFormat("🅼")
        self.ram_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 2px;
                background: rgba(0,255,0,{self.opacity_bg});
                text-align: center;
                color: {self.color_text_app};
            }}
            QProgressBar::chunk {{
                background-color: {self.color_text_sys};
                border-radius: 2px;
            }}
        """)
        self.ram_bar.hide()
        status_layout.addWidget(self.ram_bar)

        self.gpu_bar = QProgressBar()
        self.gpu_bar.setOrientation(Qt.Orientation.Vertical)
        self.gpu_bar.setRange(0, 100)
        self.gpu_bar.setFixedWidth(self.button_size)
        self.gpu_bar.setFormat("🅶")
        self.gpu_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                border-radius: 2px;
                background: rgba(255,0,0,{self.opacity_bg});
                text-align: center;
                color: {self.color_text_app};
            }}
            QProgressBar::chunk {{
                background-color: {self.color_text_sys};
                border-radius: 2px;
            }}
        """)
        self.gpu_bar.hide()
        status_layout.addWidget(self.gpu_bar)
        layout.addLayout(status_layout)
        
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setLayout(layout)
        
        if self.status_expanded:
            self.status_expanded = False
            self.toggle_status_label()
            
        QTimer.singleShot(0, self.reposition_window)
       
    def reposition_window(self):
        # 計算右下角座標
        x = self.ageo.width() - self.width() - 50
        y = self.ageo.height() - self.height() - 50
        
        # 移動視窗到右下角
        self.move(x, y)
        
    def on_load_finished(self, ok):
        if ok:
            # 非同步呼叫，HTML 準備好後會傳給 handle_html
            self.requestPage.toHtml(self.handle_html)
            #self.requestPage.runJavaScript("document.body.innerHTML", self.handle_html)

    def on_reload_button_clicked(self):
        current_tab = self.tabs.tabBar().tabData(self.tabs.currentIndex()).get("type")

        match current_tab:
            case "Text":
                self.fetch_page(self.history[self.history_index][0], add_to_history=False)
            case "Web":
                self.web_view.reload()
            case "App":
                self.windows_dock.reload_app_list(self.app_list)
        
    def fetch_page(self, url=None, add_to_history=True):
        if not url:
            url = self.url_input.text()
        
        if not url:
            return
            
        try:
            import requests, socket
            
            # 判斷目前 Tab
            tab_index = self.tabs.currentIndex()
            current_tab = self.tabs.tabBar().tabData(tab_index)
            match current_tab.get("type"):
                case "Text":
                    current_tab['title'] = url
                    self.tabs.tabBar().setTabData(tab_index, current_tab)
                    self.setWindowTitle(url)
                    
                    
                    # 更新歷史紀錄
                    if add_to_history:
                        scroll_pos = self.text_browser.verticalScrollBar().value()
                            
                        if self.history_index < len(self.history) - 1:
                            self.history = self.history[:self.history_index+1]
                        self.history.append((url, scroll_pos))
                        self.history_index += 1
                    
                    headers = {
                        "User-Agent": "JustBrowse/1.0 (+https://github.com/allapse/JustBrowse)",
                        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        "Accept-Language": "zh-TW,en;q=0.7"
                    }
                    
                    response = requests.get(url, headers=headers, timeout=10, stream=True)
                    status_code = response.status_code
                    content = response.text
                    
                    if  status_code == 200:
                        if self.force_rst:
                            #嘗試重連並直接中斷
                            response = requests.get(url, headers=headers, timeout=10, stream=True)
                            response.raw._fp.fp.raw._sock.shutdown(socket.SHUT_RDWR)
                            status_code = "RST"
                        
                        self.handle_html(content)
                    else:
                        self.requestPage.load(QUrl(url))
                    
                    if status_code != 200:
                        status_code = f" [{status_code}]"
                    else:
                        status_code = ""
                        
                    self.tabs.setTabText(0, f"Text{status_code}")
                    
                    if not add_to_history:
                        if self.history_index < len(self.history) - 1:
                            prev_scroll = self.history[self.history_index + 1][1]
                            # 還原捲動位置
                            self.text_browser.verticalScrollBar().setValue(prev_scroll)
                
                case "Web":
                    self.web_view.setUrl(QUrl(url))
           
        except Exception as e:
            self.text_browser.setPlainText(f"抓取失敗: {e}")
    
    def handle_html(self, html):
        from bs4 import BeautifulSoup
        
        soup = BeautifulSoup(html, "lxml")
        color = "rgba(0,127,0,0.8)"
        per_base = 15
        max_len = 17

        content = f'<h2 style="color:{color};">{soup.title.string if soup.title else "無標題"}</h2>'
        
        # 預設要跳過的標籤
        skip_tags = {"script", "style", "nav", "footer"}

        # 顏色交替控制
        text_colors = ["rgba(0,127,0,0.8)", self.color_text_app]
        link_colors = ["rgba(255,0,0,0.5)", self.color_text_app]
        text_index, link_index= 0, 0
        
        # 連結重複檢查
        link = ""
        last_link = ""
        last_text = ""
        
        for text in soup.strings:
            parent = text.parent.name if text.parent else None
            parent = "a" if text.find_parent("a") else parent

            # 1. 跳過指定標籤
            if parent in skip_tags:
                continue

            clean_text = text.strip()
            if parent == "a":
                link = text.find_parent("a").get("href", "")
                if link == last_link:
                    continue
                    
                clean_text = " ".join(text.find_parent("a").stripped_strings)
            
            if not clean_text:
                continue
                
            if clean_text == last_text:
                continue
            
            last_text = clean_text
                
            # 字體大小依文字長度調整（字越少越大）
            per = f'{per_base + round(15 / (1.5 + round(len(clean_text) / 6)))}px'

            # 2. 判斷是否超連結
            if parent == "a":
                # 顏色交替
                color = link_colors[link_index % 2]
                link_index += 1

                # 3. 判斷長度 → span 或 p
                if len(clean_text) < max_len:
                    content += f'<span style="white-space: pre;"><a href="{link}" style="color:{color}; font-size:{per};">{clean_text}</a>   </span>'
                else:
                    content += f'<p><a href="{link}" style="color:{color}; font-size:{per};">{clean_text}</a></p>'
                    
                last_link = link
                continue

            # 一般文字處理
            color = text_colors[link_index % 2]
            link_index += 1

            if len(clean_text) < max_len:
                content += f'<span style="white-space: pre; color:{color}; font-size:{per};">{clean_text}   </span>'
            else:
                content += f'<p style="color:{color}; font-size:{per};">{clean_text}</p>'
                
        if not content.strip():
            # 保證至少有東西顯示
            content = "<p style='color:red;'>沒有可顯示的內容</p>"

        self.text_browser.setHtml(content)
    
    def on_tab_changed(self, index):
        btn_enable = True
        current_tab = self.tabs.tabBar().tabData(self.tabs.currentIndex())
        
        if not current_tab:
            return
            
        match current_tab.get("type"):
            case "Text":
                # 假設你有存當前 URL
                if self.history_index >= 0:
                    self.url_input.setText(self.history[self.history_index][0])
            case "Web":
                self.sync_url_input()
            case "App":
                item = self.app_list.currentItem()
                if item:
                    data = item.data(Qt.ItemDataRole.UserRole)
                    self.url_input.setText(f"hwnd: {data['hwnd']}, pid: {data['pid']}")
                else:
                    self.url_input.setText("")
            case "Dock":
                self.url_input.setText(f"hwnd: {current_tab['hwnd']}, pid: {current_tab['pid']}")
                btn_enable = False
                    
        self.forward_button.setEnabled(btn_enable)
        self.reload_button.setEnabled(btn_enable)
        self.setWindowTitle(current_tab['title'])
            
    def sync_url_input(self):
        tab_index = self.tabs.currentIndex()
        current_tab = self.tabs.tabBar().tabData(tab_index)
       
        if current_tab.get("type") == "Web":
            url = self.web_view.url().toString()
            current_tab['title'] = url
            self.tabs.tabBar().setTabData(tab_index, current_tab)
            self.url_input.setText(url)
            self.setWindowTitle(url)
            
    def handle_link_click(self, url):
        from urllib.parse import urljoin, urlparse
        new_url = url.toString()
        
        # 從目前輸入框的 URL 判斷 base
        current_url = self.url_input.text()
        parsed = urlparse(current_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # 拼接完整 URL
        full_url = urljoin(base_url, new_url)
        
        # 判斷是否按下 Ctrl
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # new 出一個新的瀏覽器視窗
            new_browser = JustBrowse()
            if new_browser.status_expanded:
                new_browser.toggle_status_label()
            new_browser.url_input.setText(full_url)
            new_browser.fetch_page(full_url)
            QTimer.singleShot(200, lambda: new_browser.dock_space())
            new_browser.show()
            windows.append(new_browser)  # 保留參考
        else:
            # 在原本視窗跳轉
            self.url_input.setText(full_url)
            self.fetch_page(full_url)

    def go_back(self):
        tab_index = self.tabs.currentIndex()
        current_tab = self.tabs.tabBar().tabData(tab_index).get("type")

        match current_tab:
            case "Text":
                if self.history_index > 0:
                    self.history_index -= 1
                    prev_url = self.history[self.history_index][0]
                    self.url_input.setText(prev_url)
                    self.fetch_page(prev_url, add_to_history=False)
            case "Web":
                self.web_view.back()
            case "App":
                row = self.app_list.currentRow()
                if row > 0:
                    self.app_list.setCurrentRow(row - 1)
            case "Dock":
                widget = self.tabs.widget(tab_index)
                self.tabs.removeTab(tab_index)
                widget.deleteLater()
                QTimer.singleShot(1000, lambda: self.windows_dock.reload_app_list(self.app_list))
            
    def go_forward(self):
        current_tab = self.tabs.tabBar().tabData(self.tabs.currentIndex()).get("type")
        
        match current_tab:
            case "Text":
                if self.history_index < len(self.history) - 1:
                    self.history_index += 1
                    next_url = self.history[self.history_index][0]
                    self.url_input.setText(next_url)
                    self.fetch_page(next_url, add_to_history=False)
            case "Web":
                self.web_view.forward()
            case "App":
                row = self.app_list.currentRow()
                if row < self.app_list.count() - 1:
                    self.app_list.setCurrentRow(row + 1)

    def toggle_bg_lock(self):
        self.bg_lock = not self.bg_lock
        
        if self.bg_lock:
            self.bg_lock_btn.setText("◓")
        else:
            self.bg_lock_btn.setText("◒")

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
        self.anim.stop()
        self.anim.setStartValue(self.windowOpacity())
        self.anim.setEndValue(self.opacity_focus)
        self.anim.start()
        global focus_window
        focus_window = self
        self.raise_()
        self.apply_dynamic_shadow(self)
        event.accept()

    def leaveEvent(self, event):
        from PyQt6.QtGui import QCursor
        
        cursor_pos = self.mapFromGlobal(QCursor.pos())
        if not self.rect().contains(cursor_pos):
            self.anim.stop()
            self.anim.setStartValue(self.windowOpacity())
            self.anim.setEndValue(self.opacity_fade)
            self.anim.start()
        event.accept()

    def update_status(self):
        # CPU 使用率
        cpu = self.psutil.cpu_percent(interval=0)
        self.cpu_bar.setValue(int(cpu))

        # RAM 使用率
        mem = self.psutil.virtual_memory().percent
        self.ram_bar.setValue(int(mem))

        # GPU 使用率
        gpus = self.GPUtil.getGPUs()
        gpu_info = ""
        if gpus:
            gpu = gpus[0]
            gpu_load = gpu.load * 100
            gpu_info = f"GPU‐ {gpu_load:5.1f}% |{gpu.temperature:5.1f}°C | {gpu.memoryUsed/1024:.1f}/{gpu.memoryTotal/1024:.1f} GB"
        
        self.gpu_bar.setValue(int(gpu_load))

        # 網路瞬間速度
        now_net = self.psutil.net_io_counters()
        now_time = self.time.time()
        interval = now_time - self.last_time

        recv_speed = (now_net.bytes_recv - self.last_net.bytes_recv) / 1024 / 1024 / interval  # MB/s
        sent_speed = (now_net.bytes_sent - self.last_net.bytes_sent) / 1024 / 1024 / interval  # MB/s
        
        net_info = f"NET‐ ↓{recv_speed:4.1f} / ↑{sent_speed:4.1f} MB/s"
        
        # disk瞬間速度
        now_disk = self.psutil.disk_io_counters()

        recv_speed = (now_disk.read_bytes - self.last_disk.read_bytes) / 1024 / 1024 / interval  # MB/s
        sent_speed = (now_disk.write_bytes  - self.last_disk.write_bytes ) / 1024 / 1024 / interval  # MB/s

        disk_info = f"DSK‐ r{recv_speed:4.1f} / w{sent_speed:4.1f} MB/s"

        # 更新狀態
        self.status_label.setText(f"CPU‐ {cpu:5.1f}% |{mem:5.1f}%  ‐MEM | VRAM⌍\r\n{gpu_info}\r\n{net_info}\r\n{disk_info}")

        # 更新基準值
        self.last_net = now_net
        self.last_disk = now_disk
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

    def toggle_status_label(self):
        if self.status_expanded:
            # 收闔：顯示固定文字，停止更新
            self.status_label.setText(self.status_text)
            self.timer.stop()
            self.status_expanded = False
            self.cpu_bar.hide()
            self.ram_bar.hide()
            self.gpu_bar.hide()
        else:
            # 展開：恢復更新
            self.last_net = self.psutil.net_io_counters()
            self.last_disk = self.psutil.disk_io_counters()
            self.last_time = self.time.time()
            self.timer.start(CONFIG["default"]["status_rate"])
            self.update_status()
            self.cpu_bar.setMaximumHeight(self.status_label.sizeHint().height())
            self.ram_bar.setMaximumHeight(self.status_label.sizeHint().height())
            self.gpu_bar.setMaximumHeight(self.status_label.sizeHint().height())
            self.status_expanded = True 
            self.cpu_bar.show()
            self.ram_bar.show()
            self.gpu_bar.show()
            
    def makeRadialGradient(self, center, radius, alpha):
        from PyQt6.QtGui import QRadialGradient, QPen
        
        g = QRadialGradient(center, radius, center)
        g.setColorAt(0.6, QColor(255, 255, 0, alpha))
        g.setColorAt(0.5, QColor(159, 159, 255, round(alpha ** 2)))
        g.setColorAt(0.3, QColor(255, 255, 0, alpha))
        g.setColorAt(0.0, QColor(255, 255, 255, alpha))
        
        return QPen(g, 1)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
        painter.setPen(Qt.PenStyle.NoPen)

        # 畫背景 polygon
        size = 7
        points = [
            QPoint(self.width()-size, self.height()-size),
            QPoint(self.width()-2*size, self.height()-size),
            QPoint(self.width()-size, self.height()-2*size)
        ]
        painter.setBrush(Qt.GlobalColor.lightGray)
        painter.drawPolygon(QPolygon(points))

        size_base = 10
        
        my_rect = self.geometry()
        overlap = False
        if not self.bg_lock:
            for w in windows:
                if w is not self and my_rect.intersects(w.geometry()):
                    overlap = True
                    break

        if self.bg_lock or overlap:
            rect3 = self.rect().adjusted(size_base, size_base, -size_base, -size_base)
            painter.setBrush(QColor(255, 255, 255, 255))
            painter.drawRoundedRect(rect3, 3, 3)
            self.update()
            return
            
        offset_x, offset_y = self.shadow_offset
        int_x, int_y = int(offset_x), int(offset_y)
        screen_center = self.ageo.center()

        # rect1
        rect1 = self.rect().adjusted(
            max(size_base+int_x, size_base),
            max(size_base+int_x, size_base),
            min(-(size_base+int_y), -size_base),
            min(-(size_base+int_y), -size_base)
        )
        rect1.translate(int_x, int_y)
        painter.setBrush(QColor(159, 255, 159, self.shadow_alpha))
        painter.drawRoundedRect(rect1, 7, 7)
        
        # rect2
        rect2 = self.rect().adjusted(
            max(size_base-int_x, size_base),
            max(size_base-int_x, size_base),
            min(-(size_base-int_y), -size_base),
            min(-(size_base-int_y), -size_base)
        )
        rect2.translate(-int_x, -int_y)
        painter.setBrush(QColor(255, 159, 159, self.shadow_alpha))
        painter.drawRoundedRect(rect2, 7, 7)

        pen1 = self.makeRadialGradient(QPointF(rect1.center()), max(rect1.width(), rect1.height()), self.shadow_alpha)
        pen1.setStyle(Qt.PenStyle.CustomDashLine)
        pen1.setDashPattern([7 + abs(offset_x), 7 + abs(offset_y)])
        painter.setPen(pen1)

        y_left = y_right = 0
        while y_left < rect1.height()/1.2 and y_right < rect1.height()/1.2:
            painter.drawLine(rect1.left(), rect1.center().y()+int(y_left),
                             rect1.right(), rect1.center().y()+int(y_right))
            painter.drawLine(rect1.left(), rect1.center().y()-int(y_left),
                             rect1.right(), rect1.center().y()-int(y_right))
            if self.pos().x() + self.width()/2 < screen_center.x():
                y_left += self.button_size + abs(offset_x)
                y_right += self.button_size
            else:
                y_left += self.button_size
                y_right += self.button_size + abs(offset_x)

        pen2 = self.makeRadialGradient(QPointF(rect2.center()), max(rect2.width(), rect2.height()), self.shadow_alpha)
        pen2.setStyle(Qt.PenStyle.CustomDashLine)
        pen2.setDashPattern([7 + abs(offset_y), 7 + abs(offset_x)])
        painter.setPen(pen2)

        y_left = y_right = 0
        while y_left < rect2.width()/1.2 and y_right < rect2.width()/1.2:
            painter.drawLine(rect2.center().x()+int(y_left), rect2.top(),
                             rect2.center().x()+int(y_right), rect2.bottom())
            painter.drawLine(rect2.center().x()-int(y_left), rect2.top(),
                             rect2.center().x()-int(y_right), rect2.bottom())
            if self.pos().y() + self.height()/2 < screen_center.y():
                y_left += self.button_size + abs(offset_y)
                y_right += self.button_size
            else:
                y_left += self.button_size
                y_right += self.button_size + abs(offset_y)

    def apply_dynamic_shadow(self, focus_win):
        fx, fy = focus_win.pos().x() + focus_win.width()/2, focus_win.pos().y() + focus_win.height()/2

        for w in windows:
            wx, wy = w.pos().x() + w.width() / 2, w.pos().y() + w.height() / 2
            dx, dy = fx - wx, fy - wy

            if w is focus_win:
                dx, dy = w.ageo.center().x() - wx, w.ageo.center().y() -wy
                
            dist = (dx**2 + dy**2)**0.5
            alpha_min, alpha_max = 7, 13
            alpha = alpha_min + (alpha_max - alpha_min) * (dist / (min(w.ageo.width(),  w.ageo.height())))
            alpha = max(alpha_min, min(alpha_max, alpha))

            w.shadow_offset = (dx*0.02, dy*0.03)
            w.shadow_alpha = int(alpha)
            w.update()   # 觸發重繪
        
    def moveEvent(self, event):
        if focus_window is self:
            self.apply_dynamic_shadow(self)
        super().moveEvent(event)
        
    def dock_space(self, tolerance=40):
        import cv2
        import numpy as np

        self = self.title_label.window()
        self.setWindowOpacity(0.0)

        # Step 1: 截圖
        screen = QApplication.primaryScreen()
        pixmap = screen.grabWindow(0)
        image = pixmap.toImage()
        ptr = image.bits()
        ptr.setsize(image.sizeInBytes())
        arr = np.array(ptr, dtype=np.uint8).reshape(image.height(), image.width(), 4)

        # Step 3: 自動偵測 dominant color
        small = cv2.resize(arr[:,:,:3], (50,50))  # 縮小加快速度
        pixels = small.reshape(-1,3)
        colors, counts = np.unique(pixels, axis=0, return_counts=True)
        dominant_color = colors[np.argmax(counts)]

        # Step 4: 顏色距離 + 容忍度
        diff = np.linalg.norm(arr[:,:,:3] - dominant_color, axis=2)
        mask = np.where(diff < tolerance, 255, 0).astype(np.uint8)
        mat = (mask // 255).astype(np.uint8)

        # Step 5: 最大矩形演算法
        def max_rectangle_in_binary(mat):
            rows, cols = mat.shape
            height = [0] * cols
            best = (0,0,0,0)
            max_area = 0

            for i in range(rows):
                for j in range(cols):
                    if mat[i,j] == 1:
                        height[j] += 1
                    else:
                        height[j] = 0

                stack = []
                for j in range(cols+1):
                    h = height[j] if j < cols else 0
                    while stack and h < height[stack[-1]]:
                        top = stack.pop()
                        w = j if not stack else j - stack[-1] - 1
                        area = height[top] * w
                        if area > max_area:
                            max_area = area
                            best = (stack[-1]+1 if stack else 0, i-height[top]+1, w, height[top])
                    stack.append(j)

            return best

        bx, by, bw, bh = max_rectangle_in_binary(mat)

        # Step 7: 調整視窗
        self.setGeometry(bx, by, bw, bh)
        QTimer.singleShot(200, lambda: self.setWindowOpacity(self.opacity_focus))
        
    def closeEvent(self, event):
        # 從 windows 移除自己
        if self in windows:
            windows.remove(self)

        # 清掉自己底下的 tabs
        while self.tabs.count() > 0:
            self.tabs.removeTab(0)

        # 確保正常關閉
        super().closeEvent(event)
        
class MyWebView(QWebEngineView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPage(MyPage(self))   # 在初始化時就綁定自訂 Page
        
    def createWindow(self, type):
        return self   # 強制在同一個 view 打開
        
class MyPage(QWebEnginePage):
    def acceptNavigationRequest(self, url, type, isMainFrame):
        if type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
            modifiers = QApplication.keyboardModifiers()
            if modifiers & Qt.KeyboardModifier.ControlModifier:
                # new 出一個新的瀏覽器視窗
                full_url = url.toString()
                new_browser = JustBrowse()
                if new_browser.status_expanded:
                    new_browser.toggle_status_label()
                new_browser.url_input.setText(full_url)
                new_browser.fetch_page(full_url)
                QTimer.singleShot(200, lambda: new_browser.dock_space())
                new_browser.show()
                windows.append(new_browser)  # 保留參考
                return False  # 阻止原本的 navigation
        return super().acceptNavigationRequest(url, type, isMainFrame)

app = QApplication(sys.argv)

pixmap = QPixmap(37, 37)
pixmap.fill(Qt.GlobalColor.transparent)

painter = QPainter(pixmap)
painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # 抗鋸齒
painter.setBrush(QColor(127,127,127,25))
painter.setPen(Qt.PenStyle.NoPen)
painter.drawRoundedRect(pixmap.rect(), 7, 7)
painter.end()

splash = QSplashScreen(pixmap)

# 動態文字效果
dots = ["㊀㊉㊁", "㊉㊁㊀", "㊁㊀㊉", "㊀㊉㊁", "㊉㊁㊀", "㊁㊀㊉"]
breath = [11, 7, 5, 4, 5, 7]
index = 0

def update_text():
    global index, pixmap
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(round(127 / (1 + breath[index] / 30)),127,round(127 * (1 + (5 - index) / 9)),round(25 * (1 + breath[index] / 4))))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(pixmap.rect(), breath[index], breath[index])
    painter.end()
    splash.setPixmap(pixmap)
    splash.showMessage(dots[index], Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.white)
    index = (index + 1) % len(dots)

timer = QTimer()
timer.timeout.connect(update_text)
timer.start(77)

splash.show()

def start_main(splash):
    window = JustBrowse()
    window.fetch_page()
    window.show()
    windows.append(window)  # 保留參考
    splash.finish(window)

QTimer.singleShot(777, lambda: start_main(splash))

sys.exit(app.exec())
