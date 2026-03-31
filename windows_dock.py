import platform

if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes
    import win32gui
    import psutil
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QWindow
    from PyQt6.QtWidgets import QWidget, QListWidgetItem

    def get_pid_from_hwnd(hwnd):
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def get_exe_name_from_pid(pid):
        try:
            return psutil.Process(pid).name()
        except psutil.NoSuchProcess:
            return None

    def enum_windows():
        windows = []
        def callback(hwnd, extra):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                title = win32gui.GetWindowText(hwnd)
                pid = get_pid_from_hwnd(hwnd)
                windows.append((hwnd, title, pid))
        win32gui.EnumWindows(callback, None)
        return windows

    def reload_app_list(app_list):
        app_list.clear()
        for hwnd, title, pid in enum_windows():
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, {
                "hwnd": hwnd,
                "title": title,
                "pid": pid
            })
            app_list.addItem(item)
        app_list.setCurrentRow(0)

    def dock_window(tabs, hwnd, app_list):
        qwindow = QWindow.fromWinId(hwnd)
        pid = get_pid_from_hwnd(hwnd)
        exe_name = get_exe_name_from_pid(pid)
        container = QWidget.createWindowContainer(qwindow)
        index = tabs.addTab(container, exe_name)
        tabs.tabBar().setTabData(tabs.indexOf(container), {"type": "Dock", "title": exe_name, "pid": pid, "hwnd": hwnd})
        reload_app_list(app_list)
        return index
        
    import psutil

    def dock_parent_cmd(self, tabs, app_list):
        """
        嘗試找到當前視窗的父/祖父行程是否是 cmd.exe，
        如果是，就從 app_list 找到對應 hwnd 並 dock。
        """

        hwnd = int(self.winId())  # 取得主視窗 hwnd
        proc = psutil.Process(get_pid_from_hwnd(hwnd))
        parent = proc.parent()
        grandparent = parent.parent() if parent else None

        target_pid = None
        for candidate in [parent, grandparent]:
            if candidate and get_exe_name_from_pid(candidate.pid) == "cmd.exe":
                target_pid = candidate.pid
                break

        if not target_pid:
            return  # 沒有找到 cmd.exe，就直接跳過

        # 從 app_list 找到 cmd.exe 的 hwnd
        for i in range(app_list.count()):
            item = app_list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if data and data["pid"] == target_pid:
                hwnd = data["hwnd"]
                dock_window(tabs, hwnd, app_list)
                break

else:
    # stub 版：非 Windows 平台直接定義空函式
    def get_pid_from_hwnd(hwnd): return None
    def get_exe_name_from_pid(pid): return None
    def enum_windows(): return []
    def reload_app_list(app_list): pass
    def dock_window(tabs, hwnd, exe_name): pass
    def dock_parent_cmd(tabs, app_list): pass
