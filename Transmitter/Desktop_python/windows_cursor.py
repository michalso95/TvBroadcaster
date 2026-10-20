"""Windows cursor capture and compositing using a small reusable GDI buffer."""

import ctypes
from ctypes import wintypes

import numpy as np

from settings import CURSOR_BUFFER_SIZE, CURSOR_PAD

CURSOR_SHOWING = 0x00000001
DI_NORMAL = 0x0003
BI_RGB = 0
DIB_RGB_COLORS = 0

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class CURSORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hCursor", wintypes.HANDLE), ("ptScreenPos", POINT)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HANDLE), ("hbmColor", wintypes.HANDLE)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG), ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD), ("bmBits", ctypes.c_void_p)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


user32.GetCursorInfo.argtypes = [ctypes.POINTER(CURSORINFO)]
user32.GetCursorInfo.restype = wintypes.BOOL
user32.GetIconInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(ICONINFO)]
user32.GetIconInfo.restype = wintypes.BOOL
user32.DrawIconEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int, wintypes.HANDLE, ctypes.c_int, ctypes.c_int, wintypes.UINT, wintypes.HANDLE, wintypes.UINT]
user32.DrawIconEx.restype = wintypes.BOOL
gdi32.CreateCompatibleDC.argtypes = [wintypes.HANDLE]
gdi32.CreateCompatibleDC.restype = wintypes.HANDLE
gdi32.DeleteDC.argtypes = [wintypes.HANDLE]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.CreateDIBSection.argtypes = [wintypes.HANDLE, ctypes.POINTER(BITMAPINFO), wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD]
gdi32.CreateDIBSection.restype = wintypes.HANDLE
gdi32.SelectObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
gdi32.SelectObject.restype = wintypes.HANDLE
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p]
gdi32.GetObjectW.restype = ctypes.c_int


class WindowsCursor:
    """Capture and blend the current cursor without allocating per frame."""

    def __init__(self, buffer_size: int = CURSOR_BUFFER_SIZE) -> None:
        self.size, self.pad, self.closed = buffer_size, CURSOR_PAD, False
        self.hdc, self.bitmap, self.old_bitmap = None, None, None
        self.bits = ctypes.c_void_p()
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = self.size
        bitmap_info.bmiHeader.biHeight = -self.size
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = BI_RGB
        self.hdc = gdi32.CreateCompatibleDC(None)
        if not self.hdc:
            raise ctypes.WinError(ctypes.get_last_error())
        self.bitmap = gdi32.CreateDIBSection(self.hdc, ctypes.byref(bitmap_info), DIB_RGB_COLORS, ctypes.byref(self.bits), None, 0)
        if not self.bitmap or not self.bits:
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        self.old_bitmap = gdi32.SelectObject(self.hdc, self.bitmap)
        if not self.old_bitmap:
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        self.layer = np.ctypeslib.as_array(ctypes.cast(self.bits, ctypes.POINTER(ctypes.c_uint8)), shape=(self.size, self.size, 4))

    @staticmethod
    def _cursor_size(icon_info: ICONINFO) -> tuple[int, int]:
        bitmap = BITMAP()
        if icon_info.hbmColor and gdi32.GetObjectW(icon_info.hbmColor, ctypes.sizeof(BITMAP), ctypes.byref(bitmap)):
            return max(1, bitmap.bmWidth), max(1, bitmap.bmHeight)
        if icon_info.hbmMask and gdi32.GetObjectW(icon_info.hbmMask, ctypes.sizeof(BITMAP), ctypes.byref(bitmap)):
            return max(1, bitmap.bmWidth), max(1, bitmap.bmHeight // 2)
        return 32, 32

    def draw(self, image: np.ndarray, monitor: dict) -> np.ndarray:
        if self.closed:
            return image
        cursor_info = CURSORINFO(cbSize=ctypes.sizeof(CURSORINFO))
        if not user32.GetCursorInfo(ctypes.byref(cursor_info)) or not (cursor_info.flags & CURSOR_SHOWING) or not cursor_info.hCursor:
            return image
        icon_info = ICONINFO()
        if not user32.GetIconInfo(cursor_info.hCursor, ctypes.byref(icon_info)):
            return image
        try:
            mouse_x, mouse_y = cursor_info.ptScreenPos.x - monitor["left"], cursor_info.ptScreenPos.y - monitor["top"]
            if not (0 <= mouse_x < monitor["width"] and 0 <= mouse_y < monitor["height"]):
                return image
            scale_x, scale_y = image.shape[1] / monitor["width"], image.shape[0] / monitor["height"]
            cursor_w, cursor_h = self._cursor_size(icon_info)
            draw_w, draw_h = max(1, round(cursor_w * scale_x)), max(1, round(cursor_h * scale_y))
            if draw_w + self.pad > self.size or draw_h + self.pad > self.size:
                return image
            ctypes.memset(self.bits, 0, self.size * self.size * 4)
            if not user32.DrawIconEx(self.hdc, self.pad, self.pad, cursor_info.hCursor, draw_w, draw_h, 0, None, DI_NORMAL):
                return image
            cursor_x = round(mouse_x * scale_x) - round(icon_info.xHotspot * scale_x)
            cursor_y = round(mouse_y * scale_y) - round(icon_info.yHotspot * scale_y)
            height, width = image.shape[:2]
            x0, y0 = max(0, cursor_x), max(0, cursor_y)
            x1, y1 = min(width, cursor_x + draw_w), min(height, cursor_y + draw_h)
            if x0 >= x1 or y0 >= y1:
                return image
            cx0, cy0 = self.pad + x0 - cursor_x, self.pad + y0 - cursor_y
            cursor_roi = self.layer[cy0:cy0 + y1 - y0, cx0:cx0 + x1 - x0]
            image_roi = image[y0:y1, x0:x1]
            alpha = cursor_roi[:, :, 3:4]
            if np.any(alpha):
                blended = (cursor_roi[:, :, :3].astype(np.uint16) * alpha.astype(np.uint16) + image_roi[:, :, :3].astype(np.uint16) * (255 - alpha.astype(np.uint16)) + 127) // 255
                image_roi[:, :, :3] = blended.astype(np.uint8)
            else:
                mask = np.any(cursor_roi[:, :, :3] != 0, axis=2)
                image_roi[:, :, :3][mask] = cursor_roi[:, :, :3][mask]
            return image
        finally:
            if icon_info.hbmColor:
                gdi32.DeleteObject(icon_info.hbmColor)
            if icon_info.hbmMask:
                gdi32.DeleteObject(icon_info.hbmMask)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if self.hdc:
            if self.old_bitmap:
                gdi32.SelectObject(self.hdc, self.old_bitmap)
            if self.bitmap:
                gdi32.DeleteObject(self.bitmap)
            gdi32.DeleteDC(self.hdc)
        self.hdc = self.bitmap = self.old_bitmap = self.bits = None
