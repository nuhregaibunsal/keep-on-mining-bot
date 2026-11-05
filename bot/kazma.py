"""Maden kazma döngüsü: en değerli / en yakın cevhere git, kırılana kadar basılı tut."""
import math
import time

from .gorus import CevherGorusu, Hedef
from .pencere import OyunPenceresi


class Kazici:
    def __init__(self, oyun: OyunPenceresi, ayar: dict, durum):
        self.oyun = oyun
        self.ayar = ayar
        self.k = ayar["kazma"]
        self.gorus = CevherGorusu(ayar)
        self.durum = durum  # .calisiyor / .bitti bayrakları olan nesne
        self.tahta = self.k["tahta"]
        self.imlec = None  # tahta içi piksel konumu

    # tahta pikseli -> pencere oransal koordinatı
    def _oran(self, px, py, tw, th):
        l, t, r, b = self.tahta
        return l + (px / tw) * (r - l), t + (py / th) * (b - t)

    def _yasakta_mi(self, ox: float, oy: float) -> bool:
        return any(l <= ox <= r and t <= oy <= b for l, t, r, b in self.k.get("yasak", []))

    def _filtrele(self, hedefler: list[Hedef], tw, th) -> list[Hedef]:
        return [h for h in hedefler if not self._yasakta_mi(*self._oran(h.x, h.y, tw, th))]

    def _sec(self, hedefler: list[Hedef]) -> Hedef:
        # Puan / mesafe dengesi: değerli ama uzak bir cevher, yakın ucuz olanı yenebilir
        if self.imlec is None:
            return max(hedefler, key=lambda h: h.puan)
        ix, iy = self.imlec
        olcek = self.oyun.olcek
        return max(hedefler, key=lambda h: h.puan / (1.0 + math.hypot(h.x - ix, h.y - iy) / (300 * olcek)))

    def _supur(self):
        """Değerli hedef kalmadıysa tahtayı zikzak süpür (sıradan kayaları da kırar)."""
        l, t, r, b = self.tahta
        satir = 9
        for i in range(satir):
            if not self.durum.calisiyor:
                return
            y = t + (b - t) * (i + 0.5) / satir
            xs = [l + 0.05, r - 0.05] if i % 2 == 0 else [r - 0.05, l + 0.05]
            adim = 25
            for j in range(adim + 1):
                if not self.durum.calisiyor:
                    return
                x = xs[0] + (xs[1] - xs[0]) * j / adim
                if self._yasakta_mi(x, y):
                    continue
                self.oyun.fare_git(x, y)
                time.sleep(0.02)

    def calis(self):
        k = self.k
        ihtiyac = self.ayar.get("ihtiyac", {})
        ilk = self.oyun.goruntu(self.tahta)
        if k["zemin_ogren"]:
            self.gorus.zemin_ogren(ilk)
            print("[kazma] Zemin renkleri öğrenildi.")
        bos_sayac = 0
        basili = False
        try:
            while self.durum.calisiyor and not self.durum.bitti:
                if not self.oyun.on_planda_mi():
                    if basili:
                        self.oyun.fare_birak(); basili = False
                    time.sleep(0.3)
                    continue
                img = self.oyun.goruntu(self.tahta)
                th, tw = img.shape[:2]
                hedefler = self._filtrele(
                    self.gorus.bul(img, self.oyun.olcek, ihtiyac.get("hedef", ""), ihtiyac.get("carpan", 1.0)), tw, th)
                if not hedefler:
                    bos_sayac += 1
                    if bos_sayac >= 4 and k["bos_kalinca_supur"]:
                        if not basili:
                            self.oyun.fare_bas(); basili = True
                        self._supur()
                        bos_sayac = 0
                        # Süpürmeden sonra zemin değişmiş olabilir (kayalar kırıldı) -> yeniden öğren
                        if k["zemin_ogren"]:
                            self.gorus.zemin_ogren(self.oyun.goruntu(self.tahta))
                    time.sleep(k["tarama_araligi"])
                    continue
                bos_sayac = 0
                h = self._sec(hedefler)
                ox, oy = self._oran(h.x, h.y, tw, th)
                self.oyun.fare_git(ox, oy)
                self.imlec = (h.x, h.y)
                if not basili:
                    self.oyun.fare_bas(); basili = True
                self._kirilana_kadar_bekle(h, tw, th)
        finally:
            if basili:
                self.oyun.fare_birak()

    def _kirilana_kadar_bekle(self, h: Hedef, tw, th):
        bas = time.time()
        yaricap = 25 * self.oyun.olcek
        while self.durum.calisiyor and time.time() - bas < self.k["hedef_zaman_asimi"]:
            time.sleep(self.k["tarama_araligi"])
            img = self.oyun.goruntu(self.tahta)
            kalan = [x for x in self.gorus.bul(img, self.oyun.olcek)
                     if x.sinif == h.sinif and math.hypot(x.x - h.x, x.y - h.y) < yaricap]
            if not kalan:
                return
