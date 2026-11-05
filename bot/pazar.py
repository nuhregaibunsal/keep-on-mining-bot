"""Pazar: iksir/yiyecek stoklama, kullanma ve yükseltme.

Oyundan (TheMarket):
  inventoryItemCount[i], shopItemPrice[i], itemUpgradePrice[i], itemLevel[i], isItemUnlocked[i], itemUsedTimes[i]
  PurchasItem(i) satın al, UseItem(i) bir sonraki maden oturumu için kullan, UpgradeItem(i) yükselt.
Ödeme kaynakları (TheMarket IL'inden): satın alma paralarla, yükseltme mücevherlerle (aşağıdaki tablolar).

Planlayıcıya aday verir:
  - stok: envanter < stok_hedefi ise satın alma (değer = eşya ağırlığı)
  - yükseltme: eşya ağırlığı × yukseltme_carpani değerinde (mücevherle; örsle aynı bütçede yarışır)
Her oturum öncesi (MADENE GİT'ten önce) ağırlığı > 0 olan ve stokta olan eşyaları kullanır.
"""
import time

from . import kopru

# Satın alma parası (indeks -> para türü) ve yükseltme mücevheri (indeks -> mücevher)
SATIN_PARA = ["gold", "gold", "silver", "silver", "copper", "copper", "sulfur", "sulfur", "obsidian", "obsidian",
              "titanium", "titanium", "realgar", "realgar", "rhodonite", "rhodonite", "meteorite", "amberite",
              "viridium", "mythril", "digitite", "magisite", "edenite", "prismite", "prismite", "prismite", "prismite"]
YUKSELTME_GEM = ["ruby", "ruby", "quartz", "quartz", "amethyst", "amethyst", "peridot", "peridot", "sphene", "sphene",
                 "emerald", "emerald", "fireOpal", "fireOpal", "diamond", "diamond", "spinel", "slimestone", "tanzanite",
                 "ammolite", "redOpal", "alexandrite", "moonstone", "solarite", "solarite", "solarite", "solarite"]


class Pazar:
    def __init__(self, ayar: dict):
        self.ayar = ayar
        self.a = None

    @property
    def p(self):
        return self.ayar.get("pazar", {})

    def oku(self):
        self.a = kopru.alanlar("TheMarket")
        self.adlar = [x["ad"] for x in self.a.get("useItemIcons", [])]

    def durum_oku(self):
        self.oku()
        self.tur_islem = 0   # planlayıcı her tur başında çağırır

    def _ad(self, i):
        return self.adlar[i] if i < len(self.adlar) else f"esya{i}"

    def _agirlik(self, i):
        return self.p.get("agirliklar", {}).get(self._ad(i), self.p.get("varsayilan_agirlik", 30))

    def _acik(self):
        a = self.a
        return [i for i, u in enumerate(a.get("isItemUnlocked", [])) if u and i < len(SATIN_PARA)]

    def adaylar(self) -> list:
        if not self.p.get("aktif", True) or self.a is None:
            return []
        if getattr(self, "tur_islem", 0) >= self.p.get("tur_basina_en_fazla", 8):
            return []
        a, out = self.a, []
        stok = self.p.get("stok_hedefi", 2)
        for i in self._acik():
            w = self._agirlik(i)
            if w <= 0:
                continue
            if a["inventoryItemCount"][i] < stok:
                out.append({"modul": "pazar", "tur": "al", "i": i, "maliyet": {f"{SATIN_PARA[i]}Coins": float(a["shopItemPrice"][i])},
                            "deger": w, "aciklama": f"{self._ad(i)} satın al ({a['inventoryItemCount'][i]}/{stok})"})
            if self.p.get("yukselt", True):
                out.append({"modul": "pazar", "tur": "yukselt", "i": i,
                            "maliyet": {YUKSELTME_GEM[i]: float(a["itemUpgradePrice"][i])},
                            "deger": w * self.p.get("yukseltme_carpani", 0.8),
                            "aciklama": f"{self._ad(i)} yükselt (seviye {a['itemLevel'][i]} -> {a['itemLevel'][i] + 1})"})
        return out

    def uygula(self, aday: dict) -> bool:
        i = aday["i"]
        if aday["tur"] == "al":
            once = self.a["inventoryItemCount"][i]
            kopru.cagir("TheMarket", "PurchasItem", i)
            time.sleep(0.2)
            self.oku()
            ok = self.a["inventoryItemCount"][i] > once
        else:
            once = self.a["itemLevel"][i]
            kopru.cagir("TheMarket", "UpgradeItem", i)
            time.sleep(0.4)
            self.oku()
            ok = self.a["itemLevel"][i] > once
        if ok:
            print(f"[pazar] {aday['aciklama']} ({aday['maliyet']})")
            self.tur_islem = getattr(self, "tur_islem", 0) + 1
        return ok

    def kullanilacaklar(self) -> list:
        if not self.p.get("aktif", True) or not self.p.get("kullan", True):
            return []
        self.oku()
        a = self.a
        return [i for i in self._acik() if self._agirlik(i) > 0 and a["inventoryItemCount"][i] >= 1
                and a["itemUsedTimes"][i] == 0]

    def kullan(self, liste: list) -> list:
        kullanilan = []
        for i in liste:
            once = self.a["itemUsedTimes"][i]
            kopru.cagir("TheMarket", "UseItem", i)
            time.sleep(0.15)
            self.oku()
            if self.a["itemUsedTimes"][i] > once:
                kullanilan.append(self._ad(i))
        if kullanilan:
            print(f"[pazar] Bu oturum için kullanıldı: {', '.join(kullanilan)}")
        return kullanilan
