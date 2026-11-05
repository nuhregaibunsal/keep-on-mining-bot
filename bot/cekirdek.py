"""Dünya Çekirdeği (oyun sonu, TheEnding): 32 düğüm, her biri kendi külçesi/mücevheriyle alınır.

Oyun kodundan (TheEnding.UpgradeTheCore):
  - Her TEK düğüm alımı çekirdeği 1 seviye yükseltir (theCoreLevel = timesBuyedAll + 1).
  - Düğüm i'nin fiyatı corePrices[i]; alındıkça artar. coreUpgrades[i] adı ödeme kaynağını verir.
  - Her seviye cevher/XP/mücevher çarpanlarını artırır; seviye 100'de Steam başarımı var.
Planlayıcıya aday verir: her düğüm = {kaynak: fiyat}, değer = [cekirdek] deger.
Puan = değer × (cüzdan / fiyat) olduğu için bot doğal olarak cüzdana göre en ucuz düğümleri önce alır.
"""
import time

from . import kopru


def _kaynak(ad: str) -> str:
    k = ad.replace("CoreUpgrade_", "")
    return k[:1].lower() + k[1:]   # Gold -> gold, FireOpal -> fireOpal


class Cekirdek:
    def __init__(self, ayar: dict):
        self.ayar = ayar
        self.a = None

    @property
    def c(self):
        return self.ayar.get("cekirdek", {})

    def durum_oku(self):
        try:
            self.a = kopru.alanlar("TheEnding")
        except kopru.KopruHatasi:
            self.a = None

    def acik_mi(self) -> bool:
        return bool(self.a and self.a.get("isEndingCompleted") and self.a.get("corePrices"))

    def adaylar(self) -> list:
        if not self.c.get("aktif", True) or not self.acik_mi():
            return []
        hedef = self.c.get("hedef_seviye", 0)
        seviye = int(self.a.get("theCoreLevel") or 0)
        if hedef and seviye >= hedef:
            return []
        out = []
        for i, (ad, fiyat) in enumerate(zip(self.a["coreUpgrades"], self.a["corePrices"])):
            isim = ad["ad"] if isinstance(ad, dict) else str(ad)
            k = _kaynak(isim)
            out.append({"modul": "cekirdek", "i": i, "ad": isim, "maliyet": {k: float(fiyat)},
                        "deger": self.c.get("deger", 85),
                        "aciklama": f"Çekirdek: {k} düğümü (seviye {seviye} -> {seviye + 1})"})
        return out

    def uygula(self, aday: dict) -> bool:
        once = int(self.a.get("theCoreLevel") or 0)
        kopru.cagir("TheEnding", "UpgradeTheCore", aday["i"])
        time.sleep(0.3)
        self.durum_oku()
        sonra = int(self.a.get("theCoreLevel") or 0)
        if sonra > once:
            print(f"[çekirdek] Seviye {sonra} ({aday['ad'].replace('CoreUpgrade_', '')}, {aday['maliyet']})")
            if sonra == 100:
                print("[çekirdek] Seviye 100'e ulaşıldı! (Steam başarımı)")
            return True
        return False
