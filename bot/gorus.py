"""Madendeki cevherleri ekrandan tanıma.

Arka plan sorunu nasıl çözülüyor:
  Dünya değişince zemin (kar, taş, çim...) değişiyor. Bu yüzden zemini sabit bir renkle
  tanımlamıyoruz. Her madene girişte tahtanın renk dağılımına bakıyoruz: tahtanın büyük
  bir kısmını kaplayan renkler (zemin + sıradan gri kayalar) "zemin" olarak öğreniliyor ve
  cevher maskelerinden çıkarılıyor. Cevherler küçük, parlak, doygun lekeler olduğu için
  geriye sadece onlar kalıyor. Yani yeni dünyada ekstra ayar gerekmez.
"""
from dataclasses import dataclass

import cv2
import numpy as np

# Renk kutulama: H 18 kutu, S 8 kutu, V 8 kutu
_HB, _SB, _VB = 10, 32, 32


@dataclass
class Hedef:
    sinif: str
    x: float  # tahta görüntüsü içinde piksel
    y: float
    alan: int
    puan: float


class CevherGorusu:
    def __init__(self, ayar: dict):
        self.ayar = ayar
        self.siniflar = ayar["cevher"]
        self.zemin_kutulari: np.ndarray | None = None

    @staticmethod
    def _kutu_indeksi(hsv: np.ndarray) -> np.ndarray:
        h = hsv[..., 0].astype(np.int32) // _HB
        s = hsv[..., 1].astype(np.int32) // _SB
        v = hsv[..., 2].astype(np.int32) // _VB
        return h * 64 + s * 8 + v  # 0..1151

    def zemin_ogren(self, bgr: np.ndarray):
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        idx = self._kutu_indeksi(hsv)
        say = np.bincount(idx.ravel(), minlength=18 * 64)
        oran = say / idx.size
        self.zemin_kutulari = oran > self.ayar["kazma"]["zemin_esigi"]

    def zemin_maskesi(self, hsv: np.ndarray) -> np.ndarray:
        if self.zemin_kutulari is None:
            return np.zeros(hsv.shape[:2], bool)
        return self.zemin_kutulari[self._kutu_indeksi(hsv)]

    def bul(self, bgr: np.ndarray, olcek: float, ihtiyac: str = "", carpan: float = 1.0):
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        zemin = self.zemin_maskesi(hsv)
        min_alan = max(4, int(self.ayar["kazma"]["min_alan"] * olcek * olcek))
        cekirdek = np.ones((3, 3), np.uint8)
        hedefler: list[Hedef] = []
        for s in self.siniflar:
            m = cv2.inRange(hsv, np.array(s["hsv_alt"]), np.array(s["hsv_ust"]))
            m[zemin] = 0
            m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cekirdek)
            m = cv2.dilate(m, cekirdek, iterations=2)
            n, _, stats, merk = cv2.connectedComponentsWithStats(m)
            puan = s["puan"] * (carpan if ihtiyac and s["ad"].startswith(ihtiyac) else 1.0)
            for i in range(1, n):
                alan = int(stats[i, cv2.CC_STAT_AREA])
                if alan >= min_alan:
                    hedefler.append(Hedef(s["ad"], float(merk[i][0]), float(merk[i][1]), alan, puan))
        return self._birlestir(hedefler, 32 * olcek)

    @staticmethod
    def _birlestir(hedefler: list[Hedef], yaricap: float) -> list[Hedef]:
        """Aynı kayaya ait yakın lekeleri tek hedefte topla (en yüksek puanlı sınıf kazanır)."""
        hedefler = sorted(hedefler, key=lambda h: -h.puan)
        sonuc: list[Hedef] = []
        r2 = yaricap * yaricap
        for h in hedefler:
            for s in sonuc:
                if (s.x - h.x) ** 2 + (s.y - h.y) ** 2 < r2:
                    toplam = s.alan + h.alan
                    s.x = (s.x * s.alan + h.x * h.alan) / toplam
                    s.y = (s.y * s.alan + h.y * h.alan) / toplam
                    s.alan = toplam
                    break
            else:
                sonuc.append(Hedef(h.sinif, h.x, h.y, h.alan, h.puan))
        return sonuc

    @staticmethod
    def ciz(bgr: np.ndarray, hedefler: list[Hedef]) -> np.ndarray:
        out = bgr.copy()
        for h in hedefler:
            c = (int(h.x), int(h.y))
            cv2.circle(out, c, 10, (0, 255, 0), 2)
            cv2.putText(out, f"{h.sinif}:{int(h.puan)}", (c[0] + 12, c[1]),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1, cv2.LINE_AA)
        return out
