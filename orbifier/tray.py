"""
tray.py – Lightweight Windows system tray icon using ctypes (no external deps).
"""

import sys
import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Optional

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    shell32 = ctypes.windll.shell32

    LRESULT = ctypes.c_int64
    WPARAM = ctypes.c_uint64
    LPARAM = ctypes.c_int64
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM)

    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
    user32.DefWindowProcW.restype = LRESULT

    WM_USER = 0x0400
    WM_TRAY = WM_USER + 42
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205

    NIM_ADD = 0
    NIM_MODIFY = 1
    NIM_DELETE = 2
    NIF_MESSAGE = 1
    NIF_ICON = 2
    NIF_TIP = 4

    MF_STRING = 0x0000
    MF_SEPARATOR = 0x0800
    TPM_RIGHTBUTTON = 0x0002
    TPM_RETURNCMD = 0x0100

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.UINT),
            ('style', wintypes.UINT),
            ('lpfnWndProc', WNDPROC),
            ('cbClsExtra', ctypes.c_int),
            ('cbWndExtra', ctypes.c_int),
            ('hInstance', wintypes.HINSTANCE),
            ('hIcon', wintypes.HICON),
            ('hCursor', wintypes.HANDLE),
            ('hbrBackground', wintypes.HBRUSH),
            ('lpszMenuName', wintypes.LPCWSTR),
            ('lpszClassName', wintypes.LPCWSTR),
            ('hIconSm', wintypes.HICON),
        ]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ('cbSize', wintypes.DWORD),
            ('hWnd', wintypes.HWND),
            ('uID', wintypes.UINT),
            ('uFlags', wintypes.UINT),
            ('uCallbackMessage', wintypes.UINT),
            ('hIcon', wintypes.HICON),
            ('szTip', wintypes.WCHAR * 128),
            ('dwState', wintypes.DWORD),
            ('dwStateMask', wintypes.DWORD),
            ('szInfo', wintypes.WCHAR * 256),
            ('uTimeoutOrVersion', wintypes.UINT),
            ('szInfoTitle', wintypes.WCHAR * 64),
            ('dwInfoFlags', wintypes.DWORD),
        ]


class TrayIcon:
    """Manages a Windows notification area (tray) icon with a click handler."""

    def __init__(
        self,
        tooltip: str = "Orbifier",
        icon_path: Optional[str] = None,
        on_open: Optional[Callable[[], None]] = None,
        on_exit: Optional[Callable[[], None]] = None,
    ):
        self.tooltip = tooltip[:127]
        self.icon_path = icon_path
        self.on_open = on_open
        self.on_exit = on_exit

        self._hwnd = None
        self._thread = None
        self._running = False
        self._wndproc_ref = None

    def start(self) -> None:
        if sys.platform != "win32" or self._running:
            return
        self._running = True
        self._ready_event = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready_event.wait(timeout=2.0)

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._hwnd:
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = 1
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            user32.PostMessageW(self._hwnd, 0x0012, 0, 0)  # WM_QUIT
            self._hwnd = None

    def update_tooltip(self, text: str) -> None:
        self.tooltip = text[:127]
        if self._hwnd and self._running:
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = 1
            nid.uFlags = NIF_TIP
            nid.szTip = self.tooltip
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _run(self) -> None:
        cls_name = f"OrbifierTray_{id(self)}"
        hinst = kernel32.GetModuleHandleW(None)

        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_TRAY:
                if lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    if self.on_open:
                        self.on_open()
                    return 0
                elif lparam == WM_RBUTTONUP:
                    self._show_menu(hwnd)
                    return 0
            elif msg == 0x0002:  # WM_DESTROY
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(wndproc)

        wcls = WNDCLASSEXW()
        wcls.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wcls.lpfnWndProc = self._wndproc_ref
        wcls.hInstance = hinst
        wcls.lpszClassName = cls_name

        user32.RegisterClassExW(ctypes.byref(wcls))
        self._hwnd = user32.CreateWindowExW(
            0, cls_name, cls_name, 0, 0, 0, 0, 0, 0, 0, hinst, None
        )

        h_icon = 0
        if self.icon_path:
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x0010
            LR_DEFAULTSIZE = 0x0040
            h_icon = user32.LoadImageW(
                0, str(self.icon_path), IMAGE_ICON, 0, 0,
                LR_LOADFROMFILE | LR_DEFAULTSIZE
            )
        if not h_icon:
            IDI_APPLICATION = ctypes.c_wchar_p(32512)
            h_icon = user32.LoadIconW(0, IDI_APPLICATION)

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = h_icon
        nid.szTip = self.tooltip

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        self._ready_event.set()

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        user32.UnregisterClassW(cls_name, hinst)

    def _show_menu(self, hwnd: int) -> None:
        hmenu = user32.CreatePopupMenu()
        ID_OPEN = 1001
        ID_EXIT = 1002

        user32.AppendMenuW(hmenu, MF_STRING, ID_OPEN, "Open")
        user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(hmenu, MF_STRING, ID_EXIT, "Stop & Exit")

        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(hwnd)

        cmd = user32.TrackPopupMenu(
            hmenu,
            TPM_RIGHTBUTTON | TPM_RETURNCMD,
            pt.x, pt.y,
            0, hwnd, None
        )
        user32.DestroyMenu(hmenu)

        if cmd == ID_OPEN and self.on_open:
            self.on_open()
        elif cmd == ID_EXIT and self.on_exit:
            self.on_exit()
