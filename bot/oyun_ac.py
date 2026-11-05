"""Oyunu Steam üzerinden açma, köprü eklentisini güncel tutma ve ana menüden geçme."""
import os
import shutil
import time
from pathlib import Path

from . import kopru
from .pencere import pencere_bul

STEAM_APP_ID = 4286550
OYUN_KLASORU = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Keep on Mining! - Worlds")
KOK = Path(__file__).resolve().parent.parent
EKLENTI_KAYNAK = KOK / "mod" / "KomKopru.dll"
EKLENTI_HEDEF = OYUN_KLASORU / "BepInEx" / "plugins" / "KomKopru.dll"


def eklentiyi_guncelle() -> bool:
    """Oyun kapalıyken, mod klasöründeki yeni derlenmiş eklentiyi oyuna kopyalar."""
    if not EKLENTI_KAYNAK.exists():
        return False
    if EKLENTI_HEDEF.exists() and EKLENTI_HEDEF.read_bytes() == EKLENTI_KAYNAK.read_bytes():
        return False
    EKLENTI_HEDEF.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EKLENTI_KAYNAK, EKLENTI_HEDEF)
    print("[açılış] Köprü eklentisi güncellendi.")
    return True


def bekle(kosul, sure: float, aralik: float = 1.0) -> bool:
    son = time.time() + sure
    while time.time() < son:
        if kosul():
            return True
        time.sleep(aralik)
    return False


def oyunu_kapat(baslik: str) -> bool:
    """Oyunu düzgünce kapatır (pencere kapatma mesajı, oyun kendi kaydını yapar)."""
    from .pencere import user32
    h = pencere_bul(baslik)
    if not h:
        return True
    user32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE
    ok = bekle(lambda: not pencere_bul(baslik), 30, 0.5)
    time.sleep(2)
    return ok


def oyunu_hazirla(baslik: str, menuden_gec: bool = True, yeniden_baslat: bool = False):
    """Oyun kapalıysa açar, köprüyü bekler, ana menüdeyse 'Oyna!'ya basar."""
    eski = (pencere_bul(baslik) and EKLENTI_KAYNAK.exists() and EKLENTI_HEDEF.exists()
            and EKLENTI_HEDEF.read_bytes() != EKLENTI_KAYNAK.read_bytes())
    if eski and yeniden_baslat:
        print("[açılış] Yeni köprü eklentisi var, oyun yeniden başlatılıyor...")
        oyunu_kapat(baslik)
    if not pencere_bul(baslik):
        eklentiyi_guncelle()
        print("[açılış] Oyun Steam üzerinden açılıyor...")
        os.startfile(f"steam://rungameid/{STEAM_APP_ID}")
        if not bekle(lambda: pencere_bul(baslik), 120):
            raise RuntimeError("Oyun penceresi 2 dakikada açılmadı.")
    elif EKLENTI_KAYNAK.exists() and EKLENTI_HEDEF.exists() \
            and EKLENTI_HEDEF.read_bytes() != EKLENTI_KAYNAK.read_bytes():
        print("[açılış] UYARI: Daha yeni bir köprü eklentisi var ama oyun açık. "
              "Yenisinin yüklenmesi için oyunu kapatıp botu yeniden başlat.")

    print("[açılış] Köprü bekleniyor...")
    if not bekle(kopru.var_mi, 90):
        raise RuntimeError("Köprü eklentisine ulaşılamadı. BepInEx kurulu mu?")

    if menuden_gec:
        ana_menuden_gec()


def ana_menuden_gec():
    # Menü yüklenip butonlar aktif olana kadar birkaç kez dene
    for _ in range(30):
        try:
            r = kopru.bas("Oyna!")
        except kopru.KopruHatasi:
            r = {}
        if r.get("tamam"):
            print("[açılış] 'Oyna!' butonuna basıldı.")
            time.sleep(3)
            return True
        if r.get("neden") == "buton bulunamadi":
            # Menüde değiliz (zaten oyundayız) ya da menü daha gelmedi
            d = kopru.durum()
            if d.get("isInMiningSession") or _oyun_ici_mi():
                return False
        time.sleep(1)
    return False


def _oyun_ici_mi() -> bool:
    try:
        metinler = " ".join(b.get("metin", "") for b in kopru.butonlar()).lower()
    except kopru.KopruHatasi:
        return False
    return any(s in metinler for s in ("madene", "yükselt", "yetenek", "dünyalar", "örs"))
