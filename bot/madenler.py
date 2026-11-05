"""Otomatik madenler (TheMines): satın alma ve hız/miktar yükseltmeleri — planlayıcıya aday verir.

Oyundaki fonksiyonlar ve ödeme kaynakları (TheMines IL'inden):
  UpgradeMines("BarMineSpeed")  / ("BarMineCount")   -> altın külçe
  UpgradeMines("GemMineSpeed")  / ("GemMineCount")   -> yakut
  UpgradeMines("CoinMineSpeed") / ("CountMineCount") -> altın para   (oyundaki yazım hatası: "Count")
  UpgradeMines("XpMineSpeed")                        -> gümüş külçe
  UpgradeMines("XpMineCount")                        -> bakır külçe
  PurchaseMines("BarMine"/"GemMine"/"CoinMine")      -> altın külçe / yakut / altın para
  PurchaseMines("XPMine") mor kitap ister -> bot bunu kendiliğinden ALMAZ (kitaplar dünyalar için).

Değer: maden ağırlığı × kazanç oranı (üretim/saniyedeki artış). Miktar: count -> count+1.
Hız: her yükseltmede süredeki gerçek düşüş öğrenilir (ilk tahmin %5).
"""
import time

from . import kopru

MADENLER = {
    #  ad      fiyat önekleri       satın alma adı, kaynak          hız adı, kaynak               miktar adı, kaynak
    "bar":  {"al": ("BarMine", "gold"),        "hiz": ("BarMineSpeed", "gold"),       "miktar": ("BarMineCount", "gold"),
             "sure": "barMineTime", "adet": "barsMinedCount", "fiyat": "barMinePrice",
             "hiz_fiyat": "barMine_speedUpgradePrice", "miktar_fiyat": "barMine_barsMinedUpgradePrice",
             "alindi": "isBarMinePurchased"},
    "gem":  {"al": ("GemMine", "ruby"),        "hiz": ("GemMineSpeed", "ruby"),       "miktar": ("GemMineCount", "ruby"),
             "sure": "gemMineTime", "adet": "gemsMinedCount", "fiyat": "gemMinePrice",
             "hiz_fiyat": "gemMine_speedUpgradePrice", "miktar_fiyat": "gemMine_gemsMinedUpgradePrice",
             "alindi": "isGemMinePurchased"},
    "coin": {"al": ("CoinMine", "goldCoins"),  "hiz": ("CoinMineSpeed", "goldCoins"), "miktar": ("CountMineCount", "goldCoins"),
             "sure": "coinMineTime", "adet": "coinsMinedCount", "fiyat": "coinMinePrice",
             "hiz_fiyat": "coinMine_speedUpgradePrice", "miktar_fiyat": "coinMine_coinsMinedUpgradePrice",
             "alindi": "isCoinMinePurchased"},
    "xp":   {"al": None,                       "hiz": ("XpMineSpeed", "silver"),      "miktar": ("XpMineCount", "copper"),
             "sure": "xpMineTime", "adet": "xpMinedCount", "fiyat": "xpMinePrice",
             "hiz_fiyat": "xpMine_speedUpgradePrice", "miktar_fiyat": "xpMine_xpMinedUpgradePrice",
             "alindi": "isXpMinePurchased"},
}


class Madenler:
    def __init__(self, ayar: dict):
        self.m = ayar.get("madenler", {})
        self.a = None
        self.hiz_kazanci = {k: 0.05 for k in MADENLER}   # öğrenilen: hız yükseltmesi süreyi ne kadar kısaltıyor

    def oku(self):
        self.a = kopru.alanlar("TheMines")

    def durum_oku(self):
        if self.a is None:
            self.oku()

    def tur_basi(self):
        self.tur_islem = 0

    def _deger(self, maden: str, kazanc: float) -> float:
        w = self.m.get("agirliklar", {}).get(maden, 50)
        return max(5.0, min(120.0, w * kazanc / 0.1))   # %10 üretim artışı = ağırlığın kendisi

    def adaylar(self) -> list:
        if not self.m.get("aktif", True):
            return []
        if getattr(self, "tur_islem", 0) >= self.m.get("tur_basina_en_fazla", 6):
            return []   # bu tur madenlere yeterince harcandı
        a, out = self.a, []
        for k, t in MADENLER.items():
            if not a.get(t["alindi"]):
                if t["al"] and self.m.get("satin_al", True):
                    ad, kaynak = t["al"]
                    out.append({"modul": "madenler", "tur": "al", "maden": k, "ad": ad,
                                "maliyet": {kaynak: float(a[t["fiyat"]])}, "deger": self._deger(k, 1.0),
                                "aciklama": f"{k} madenini satın al"})
                continue
            adet = max(1, int(a.get(t["adet"]) or 1))
            ad, kaynak = t["miktar"]
            out.append({"modul": "madenler", "tur": "yukselt", "maden": k, "ad": ad, "alan": t["adet"],
                        "maliyet": {kaynak: float(a[t["miktar_fiyat"]])}, "deger": self._deger(k, 1 / adet),
                        "aciklama": f"{k} madeni miktar {adet}->{adet + 1}"})
            ad, kaynak = t["hiz"]
            out.append({"modul": "madenler", "tur": "yukselt", "maden": k, "ad": ad, "alan": t["sure"],
                        "maliyet": {kaynak: float(a[t["hiz_fiyat"]])}, "deger": self._deger(k, self.hiz_kazanci[k]),
                        "aciklama": f"{k} madeni hız ({float(a[t['sure']]):.1f} sn)"})
        return out

    def uygula(self, aday: dict) -> bool:
        t = MADENLER[aday["maden"]]
        if aday["tur"] == "al":
            kopru.cagir("TheMines", "PurchaseMines", aday["ad"])
            time.sleep(0.5)
            self.oku()
            ok = bool(self.a.get(t["alindi"]))
            print(f"[maden] {aday['maden']} madeni {'satın alındı' if ok else 'alınamadı'}")
            return ok
        alan = aday["alan"]
        once = float(self.a.get(alan) or 0)
        kopru.cagir("TheMines", "UpgradeMines", aday["ad"])
        time.sleep(0.2)
        self.oku()
        sonra = float(self.a.get(alan) or 0)
        if sonra == once:
            return False
        if alan == t["sure"] and once > 0:
            # gerçek hız kazancını öğren: üretim oranı once/sonra - 1
            self.hiz_kazanci[aday["maden"]] = max(0.005, once / sonra - 1)
        print(f"[maden] {aday['aciklama']} -> {sonra:.2f} ({aday['maliyet']})")
        self.tur_islem = getattr(self, "tur_islem", 0) + 1
        return True
