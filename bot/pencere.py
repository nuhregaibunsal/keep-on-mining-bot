"""Oyun penceresini bulma, iç alan koordinatları, ekran görüntüsü ve fare/tuş girdisi.
Sadece ctypes + mss kullanır (pywin32 gerekmez)."""
import ctypes
import ctypes.wintypes as wt
import time

import mss
import numpy as np

user32 = ctypes.windll.user32

# Yüksek DPI ekranlarda koordinatların doğru olması için
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

VK = {f"F{i}": 0x6F + i for i in range(1, 13)}
VK.update({"ESC": 0x1B})


def tus_basili(ad: str) -> bool:
    return bool(user32.GetAsyncKeyState(VK[ad.upper()]) & 0x8000)


def pencere_bul(baslik: str):
    bulunan = []

    @ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n:
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            if baslik.lower() in buf.value.lower():
                # Sadece Unity oyun penceresi (aynı adlı Dosya Gezgini vb. pencereleri atla)
                sinif = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, sinif, 256)
                if sinif.value == "UnityWndClass":
                    bulunan.append(hwnd)
        return True

    user32.EnumWindows(cb, 0)
    return bulunan[0] if bulunan else None


class OyunPenceresi:
    def __init__(self, baslik: str):
        self.hwnd = pencere_bul(baslik)
        if not self.hwnd:
            raise RuntimeError(f"'{baslik}' başlıklı pencere bulunamadı. Oyun açık mı?")
        self._sct = mss.mss()
        self.guncelle()

    def guncelle(self):
        r = wt.RECT()
        user32.GetClientRect(self.hwnd, ctypes.byref(r))
        p = wt.POINT(0, 0)
        user32.ClientToScreen(self.hwnd, ctypes.byref(p))
        self.x, self.y, self.w, self.h = p.x, p.y, r.right, r.bottom
        # 1080p'ye göre ölçek (piksel eşiklerini çözünürlükten bağımsız yapmak için)
        self.olcek = self.h / 1080.0

    def one_getir(self):
        user32.SetForegroundWindow(self.hwnd)
        time.sleep(0.15)

    def on_planda_mi(self) -> bool:
        return user32.GetForegroundWindow() == self.hwnd

    def goruntu(self, bolge=None) -> np.ndarray:
        """BGR görüntü döndürür. bolge = (sol, üst, sağ, alt) oransal."""
        self.guncelle()
        if bolge:
            l, t, r, b = bolge
            mon = {"left": self.x + int(l * self.w), "top": self.y + int(t * self.h),
                   "width": int((r - l) * self.w), "height": int((b - t) * self.h)}
        else:
            mon = {"left": self.x, "top": self.y, "width": self.w, "height": self.h}
        img = np.array(self._sct.grab(mon))
        return img[:, :, :3].copy()

    # --- fare ---
    def ekran_noktasi(self, ox: float, oy: float):
        return self.x + int(ox * self.w), self.y + int(oy * self.h)

    def fare_git(self, ox: float, oy: float):
        sx, sy = self.ekran_noktasi(ox, oy)
        user32.SetCursorPos(sx, sy)

    @staticmethod
    def fare_bas():
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN

    @staticmethod
    def fare_birak():
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP

    def tikla(self, ox: float, oy: float, bekle=0.08):
        self.fare_git(ox, oy)
        time.sleep(0.03)
        self.fare_bas()
        time.sleep(0.05)
        self.fare_birak()
        time.sleep(bekle)
