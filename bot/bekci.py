"""Bekçi: botu gece boyu başında kimse olmadan ayakta tutar.

Her 10 saniyede kontrol eder:
  - Bilgisayar uykuya geçmesin (bot çalışırken; ekran kapanabilir).
  - Oyun penceresi kayboldu mu (çöktü / kapandı / Steam güncellemesi)?  -> oyunu yeniden aç, devam et.
  - Köprü (mod) 60 sn yanıt vermiyor mu (oyun dondu)?                   -> oyunu kapat-aç, devam et.
  - 4 dakikadır hiç maden oturumu başlamadı/bitmedi mi (takıldı)?       -> engel çözücüyle kurtarmayı dene;
    8 dakika olursa oyunu yeniden başlat.
  - Çalışma saatleri tanımlıysa (örn. "23:00-08:00") dışında botu duraklatır, saat gelince başlatır.
Kurtarmalar günlüğe ve istatistiğe yazılır.
"""
import ctypes
import time
from datetime import datetime

from . import kopru
from .kayit import kayit
from .pencere import pencere_bul

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001


def uyku_engelle(acik: bool):
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | (ES_SYSTEM_REQUIRED if acik else 0))
    except Exception:
        pass


def _saat_icinde(aralik: str) -> bool:
    if not aralik:
        return True
    try:
        a, b = [datetime.strptime(x.strip(), "%H:%M").time() for x in aralik.split("-")]
    except ValueError:
        return True
    simdi = datetime.now().time()
    return a <= simdi < b if a <= b else (simdi >= a or simdi < b)   # gece yarısını geçen aralık


class Bekci:
    def __init__(self, yon):
        self.yon = yon            # sunucu.Yonetici
        self.ayar = yon.ayar
        self.kopru_yok_bas = None
        self.saat_duraklatti = False
        self.kurtarma_sayisi = 0

    @property
    def b(self):
        return self.ayar.get("bekci", {})

    def _ilerleme_yasi(self) -> float:
        return time.time() - kayit.canli.get("son_ilerleme", time.time())

    def oyunu_yeniden_baslat(self, neden: str):
        from .oyun_ac import oyunu_hazirla, oyunu_kapat
        self.kurtarma_sayisi += 1
        kayit.olay("bekçi", f"Oyun yeniden başlatılıyor: {neden}", seviye="hata",
                   neden={"neden": neden, "bu oturumdaki kurtarma": self.kurtarma_sayisi})
        calisiyordu = self.yon.durum.calisiyor
        self.yon.durum.calisiyor = False       # kazma döngüsü dursun
        time.sleep(3)
        baslik = self.ayar["pencere"]["baslik"]
        try:
            oyunu_kapat(baslik)
            if pencere_bul(baslik):   # kapanmadıysa zorla
                import subprocess
                subprocess.run(["taskkill", "/F", "/IM", "Keep on Mining! - Worlds.exe"], capture_output=True)
                time.sleep(3)
            oyunu_hazirla(baslik)
            self.yon.oyun_yenile()
            kayit.canli["son_ilerleme"] = time.time()
            kayit.olay("bekçi", "Oyun yeniden açıldı, bot devam ediyor.")
        except Exception as e:
            kayit.olay("bekçi", f"Yeniden başlatma başarısız: {e}", seviye="hata")
        self.yon.durum.calisiyor = calisiyordu

    def dongu(self):
        kayit.canli.setdefault("son_ilerleme", time.time())
        while not self.yon.durum.bitti:
            time.sleep(10)
            if not self.b.get("aktif", True):
                continue
            try:
                self._kontrol()
            except Exception as e:
                kayit.olay("bekçi", f"Kontrol hatası: {e}", seviye="hata")

    def _kontrol(self):
        durum = self.yon.durum
        # Çalışma saatleri
        aralik = self.b.get("calisma_saatleri", "")
        if aralik:
            icinde = _saat_icinde(aralik)
            if not icinde and durum.calisiyor:
                durum.calisiyor = False
                self.saat_duraklatti = True
                kayit.olay("bekçi", f"Çalışma saatleri ({aralik}) dışında, duraklatıldı.")
            elif icinde and self.saat_duraklatti:
                self.saat_duraklatti = False
                durum.calisiyor = True
                kayit.olay("bekçi", f"Çalışma saati ({aralik}) başladı, bot başlatıldı.")
        uyku_engelle(durum.calisiyor and self.b.get("uyku_engelle", True))
        if not durum.calisiyor or self.yon.asama != "hazır":
            self.kopru_yok_bas = None
            kayit.canli["son_ilerleme"] = time.time()   # duraklatmada "ilerleme yok" sayacı işlemesin
            return
        baslik = self.ayar["pencere"]["baslik"]
        if not pencere_bul(baslik):
            self.oyunu_yeniden_baslat("oyun penceresi yok (çöktü ya da kapandı)")
            return
        if not kopru.var_mi():
            self.kopru_yok_bas = self.kopru_yok_bas or time.time()
            if time.time() - self.kopru_yok_bas > self.b.get("kopru_zaman_asimi", 60):
                self.kopru_yok_bas = None
                self.oyunu_yeniden_baslat("köprü yanıt vermiyor (oyun donmuş olabilir)")
            return
        self.kopru_yok_bas = None
        yas = self._ilerleme_yasi()
        if yas > self.b.get("yeniden_baslatma_dk", 8) * 60:
            self.oyunu_yeniden_baslat(f"{yas / 60:.0f} dakikadır ilerleme yok")
        elif yas > self.b.get("takilma_dk", 4) * 60 and not getattr(self, "_kurtarma_denendi", False):
            self._kurtarma_denendi = True
            kayit.olay("bekçi", f"{yas / 60:.0f} dakikadır ilerleme yok, açılır pencere kurtarması deneniyor.")
            from .engeller import EngelCozucu
            e = EngelCozucu(self.ayar)
            e.kurtar(None)
            try:
                kopru.bas("MADENE GİT!")
            except kopru.KopruHatasi:
                pass
        if yas < 60:
            self._kurtarma_denendi = False
