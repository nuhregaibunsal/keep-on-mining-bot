"""Keep on Mining Bot - başlatıcı.

Kullanım:
    python main.py            -> kazma botu (F8 başlat/duraklat, F9 çık)
    python main.py --test     -> sadece ekranı okur, tespitleri debug/ klasörüne kaydeder (fare oynamaz)

Güvenlik: Fareyi ekranın sol üst köşesine götürürsen bot durur.
"""
import argparse
import threading
import time
import tomllib
from pathlib import Path

import cv2

from bot.kazma import Kazici
from bot.pencere import OyunPenceresi, tus_basili, user32

KOK = Path(__file__).parent


class Durum:
    calisiyor = False
    bitti = False


def ayar_yukle():
    with open(KOK / "ayarlar.toml", "rb") as f:
        return tomllib.load(f)


def test_modu(oyun: OyunPenceresi, ayar):
    from bot.gorus import CevherGorusu
    (KOK / "debug").mkdir(exist_ok=True)
    tam = oyun.goruntu()
    tahta = oyun.goruntu(ayar["kazma"]["tahta"])
    g = CevherGorusu(ayar)
    g.zemin_ogren(tahta)
    hedefler = g.bul(tahta, oyun.olcek)
    cv2.imwrite(str(KOK / "debug" / "tam_ekran.png"), tam)
    cv2.imwrite(str(KOK / "debug" / "tespit.png"), g.ciz(tahta, hedefler))
    print(f"Pencere: {oyun.w}x{oyun.h}  ölçek={oyun.olcek:.2f}")
    print(f"{len(hedefler)} hedef bulundu:")
    sayim = {}
    for h in hedefler:
        sayim[h.sinif] = sayim.get(h.sinif, 0) + 1
    for k, v in sorted(sayim.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print("Görüntüler debug/ klasörüne kaydedildi (tam_ekran.png, tespit.png).")


def koruyucu(durum: Durum, ayar):
    """Tuşları ve güvenlik köşesini dinler."""
    import ctypes.wintypes as wt
    bt, dt = ayar["tuslar"]["baslat_duraklat"], ayar["tuslar"]["durdur"]
    onceki = False
    while not durum.bitti:
        b = tus_basili(bt)
        if b and not onceki:
            durum.calisiyor = not durum.calisiyor
            print("[bot] ÇALIŞIYOR" if durum.calisiyor else "[bot] DURAKLATILDI")
        onceki = b
        if tus_basili(dt):
            durum.calisiyor = False
            durum.bitti = True
            print("[bot] Kapatılıyor...")
        p = wt.POINT()
        user32.GetCursorPos(ctypes_byref(p))
        if durum.calisiyor and p.x <= 2 and p.y <= 2:
            durum.calisiyor = False
            print("[bot] Güvenlik köşesi -> DURAKLATILDI")
        time.sleep(0.03)


def ctypes_byref(o):
    import ctypes
    return ctypes.byref(o)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", action="store_true", help="Sadece tespit et, debug görüntüsü kaydet")
    ap.add_argument("--ekran", action="store_true", help="Mod olsa bile ekran okuma modunu kullan")
    ap.add_argument("--konsol", action="store_true", help="Paneli açmadan eski konsol modunda çalış")
    args = ap.parse_args()
    ayar = ayar_yukle()
    if not args.test and not args.ekran and not args.konsol:
        return panel_modu(ayar)
    if not args.test and not args.ekran:
        from bot.oyun_ac import oyunu_hazirla
        oyunu_hazirla(ayar["pencere"]["baslik"],
                      yeniden_baslat=ayar["mod_kazma"].get("eklenti_guncellenince_yeniden_baslat", False))
    oyun = OyunPenceresi(ayar["pencere"]["baslik"])
    print(f"Oyun penceresi bulundu: {oyun.w}x{oyun.h}")

    if args.test:
        oyun.one_getir()
        test_modu(oyun, ayar)
        return

    from bot import kopru
    mod = kopru.var_mi() and not args.ekran
    print("Mod köprüsü bulundu -> oyundan doğrudan okuma modu." if mod
          else "Mod köprüsü yok -> ekran okuma modu.")

    durum = Durum()
    threading.Thread(target=koruyucu, args=(durum, ayar), daemon=True).start()
    print(f"Madene gir, sonra {ayar['tuslar']['baslat_duraklat']} ile başlat. "
          f"{ayar['tuslar']['durdur']} ile çık.")
    while not durum.bitti:
        if durum.calisiyor:
            try:
                if mod:
                    from bot.mod_kazma import ModKazici
                    ModKazici(oyun, ayar, durum).calis()
                else:
                    Kazici(oyun, ayar, durum).calis()
            except Exception as e:
                print(f"[bot] Hata: {e} -> duraklatıldı")
                durum.calisiyor = False
        time.sleep(0.1)


def panel_modu(ayar):
    """Varsayılan: kontrol paneli (tarayıcıda) + bot. Oyun kapalıysa açılır."""
    import webbrowser
    from bot import sunucu
    from bot.kayit import kayit, tee_kur
    tee_kur()
    durum = Durum()
    oyun_kutusu = {}

    def oyun_getir():
        if "oyun" not in oyun_kutusu:
            oyun_kutusu["oyun"] = OyunPenceresi(ayar["pencere"]["baslik"])
        return oyun_kutusu["oyun"]

    yon = sunucu.Yonetici(ayar, durum, oyun_getir)
    yon.oyun_temizle = oyun_kutusu.clear
    sunucu.baslat(yon)
    adres = f"http://127.0.0.1:{sunucu.PORT}"
    print(f"[bot] Kontrol paneli: {adres}")
    import os
    if os.environ.get("KOM_TARAYICI", "1") != "0":
        webbrowser.open(adres)
    threading.Thread(target=koruyucu, args=(durum, ayar), daemon=True).start()

    try:
        yon.asama = "oyun açılıyor"
        from bot.oyun_ac import oyunu_hazirla
        oyunu_hazirla(ayar["pencere"]["baslik"],
                      yeniden_baslat=ayar["mod_kazma"].get("eklenti_guncellenince_yeniden_baslat", False))
        oyun_getir()
        yon.asama = "hazır"
        print("[bot] Oyun hazır. Panelden 'Başlat' ya da F8.")
        if ayar.get("panel", {}).get("otomatik_baslat", False):
            durum.calisiyor = True
    except Exception as e:
        yon.asama = f"hata: {e}"
        print(f"[bot] Hata: {e}")
    try:
        while not durum.bitti:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    durum.calisiyor = False
    durum.bitti = True
    kayit.kaydet(True)
    print("[bot] Kapatıldı.")


if __name__ == "__main__":
    main()
