"""Yetenek ağacı: açık düğümler arasından en mantıklı yükseltmeyi seçip satın alır.

Önbellek (hız için):
  - Düğümler İLK SEFERDE bir kez taranır (fiyat, alınan/max, ödeme kaynağı) ve hafızada tutulur.
  - Her kaynak (altın, gümüş, bakır...) için ayrı, önem sırasına göre dizilmiş bir liste vardır.
  - Bir yükseltme alınınca SADECE o düğüm yeniden okunur ve listesinde yerine konur.
  - Alım sonrası ağaçta yeni açılan düğümler (tek bir hızlı listeyle) fark edilir ve sadece onlar okunur.
  - Dünya değişirse ya da bir alım beklenmedik şekilde başarısız olursa ilgili kısım tazelenir.
  Önbellek kesif/yetenek_onbellek.json dosyasına da yazılır (incelemek için).

Puan = kategori ağırlığı × (eldeki külçe / fiyat)
  -> önemli ve cüzdana göre ucuz olan önce alınır. Kategori ağırlıkları ayarlar.toml -> [yetenek].
Satın alma oyunun kendi fonksiyonuyla yapılır (üzerine gel + butona bas), yani oyunun kuralları geçerlidir.
"""
import json
import time
from pathlib import Path

from . import kopru

PARALAR = ["gold", "silver", "copper", "sulfur", "obsidian", "titanium", "realgar", "rhodonite",
           "meteorite", "amberite", "viridium", "mythril", "digitite", "magisite", "edenite", "prismite"]
ONBELLEK_DOSYA = Path(__file__).resolve().parent.parent / "kesif" / "yetenek_onbellek.json"


class YetenekAgaci:
    def __init__(self, ayar: dict):
        self.y = ayar.get("yetenek", {})
        self.dugum: dict[str, dict] = {}            # ad -> {ad, para, fiyat, alinan, max, agirlik}
        self.listeler: dict[str, list[str]] = {}     # para -> önem sırasına göre düğüm adları
        self.dunya = None
        self.birikimler: dict[str, dict] = {}

    # ---------- oyundan okuma ----------
    @staticmethod
    def kulceler() -> dict:
        a = kopru.alanlar("OreGemsAndCoins")
        return {p: float(a.get(f"total{p.capitalize()}Bars", 0) or 0) for p in PARALAR}

    @staticmethod
    def _gorunen_dugumler() -> dict:
        """Tek çağrıyla: görünen düğümlerin adı -> (ödeme kaynağı, tıklanabilir)."""
        out = {}
        for d in kopru._al("bilesenler", onek="TreeUpgrade_", tip="Tooltip"):
            para = next((p for p in PARALAR if d["alanlar"].get(f"{p}Price")), None)
            if para:
                out[d["ad"]] = (para, d.get("tiklanabilir", True))
        return out

    @staticmethod
    def _detay(ad: str) -> dict:
        kopru._al("uzerine_gel", ad=ad)
        try:
            a = kopru.alanlar("LocalizationScript")
        finally:
            kopru._al("uzerine_gel", ad=ad, cik=1)
        return {"fiyat": float(a.get("currentHoverPrice") or 0),
                "alinan": int(a.get("currentPurchaseCount") or 0),
                "max": int(a.get("currentTotalPurchaseCount") or 0)}

    @staticmethod
    def _mevcut_dunya():
        try:
            return kopru.alanlar("Worlds").get("levelSelected")
        except kopru.KopruHatasi:
            return None

    def agirlik(self, ad: str) -> float:
        kisa = ad.replace("TreeUpgrade_", "").lower()
        en = None
        for anahtar, w in self.y.get("agirliklar", {}).items():
            if anahtar.lower() in kisa:
                en = w if en is None else max(en, w)
        return en if en is not None else self.y.get("varsayilan_agirlik", 20)

    # ---------- önbellek ----------
    def _oku_ve_yerlestir(self, ad: str, para: str):
        d = {"ad": ad, "para": para, **self._detay(ad), "agirlik": self.agirlik(ad)}
        self.dugum[ad] = d
        self._listeye_koy(d)

    def _listeye_koy(self, d: dict):
        """Düğümü kendi kaynağının listesinde doğru yere koy (önce eskisini çıkar)."""
        for liste in self.listeler.values():
            if d["ad"] in liste:
                liste.remove(d["ad"])
        if self._bitti(d):
            return
        liste = self.listeler.setdefault(d["para"], [])
        # sıralama ölçütü: önem büyük önce, eşitse ucuz önce
        anahtar = (-d["agirlik"], d["fiyat"])
        i = 0
        while i < len(liste):
            o = self.dugum[liste[i]]
            if (-o["agirlik"], o["fiyat"]) > anahtar:
                break
            i += 1
        liste.insert(i, d["ad"])

    @staticmethod
    def _bitti(d: dict) -> bool:
        return (d["max"] and d["alinan"] >= d["max"]) or d["fiyat"] <= 0

    def guncelle(self, tam: bool = False):
        """İlk seferde (ya da dünya değişince) her şeyi okur; sonra sadece yeni görünen düğümleri."""
        dunya = self._mevcut_dunya()
        if tam or dunya != self.dunya or not self.dugum:
            self.dugum.clear()
            self.listeler.clear()
            self.dunya = dunya
        gorunen = self._gorunen_dugumler()
        yeni = [ad for ad in gorunen if ad not in self.dugum]
        for ad in yeni:
            self._oku_ve_yerlestir(ad, gorunen[ad][0])
        if yeni:
            print(f"[yetenek] {len(yeni)} düğüm okundu (önbellekte toplam {len(self.dugum)}).")
        self._kaydet()
        return gorunen

    def _kaydet(self):
        try:
            ONBELLEK_DOSYA.parent.mkdir(exist_ok=True)
            ONBELLEK_DOSYA.write_text(json.dumps(
                {"dunya": self.dunya, "listeler": {p: [self.dugum[a] for a in l] for p, l in self.listeler.items()}},
                ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    # ---------- karar ----------
    def _birikim_hedefleri(self, kulce: dict, yedek: float):
        esik = self.y.get("birikim_esigi", 70)
        self.birikimler = {}
        for para, liste in self.listeler.items():
            for ad in liste:  # liste önem sırasında: ilk alınamayan önemli düğüm hedeftir
                d = self.dugum[ad]
                if d["agirlik"] < esik:
                    break
                if d["fiyat"] > kulce[para] * (1 - yedek):
                    self.birikimler[para] = d
                    break

    def en_iyi(self, kulce: dict, gorunen: dict):
        """Önbellekten (oyuna sormadan) şu an alınacak en iyi düğüm."""
        yedek = self.y.get("yedek_oran", 0.0)
        kucuk = self.y.get("kucuk_harcama_orani", 0.1)
        self._birikim_hedefleri(kulce, yedek)
        en, en_puan = None, 0.0
        for para, liste in self.listeler.items():
            butce = kulce[para] * (1 - yedek)
            hedef = self.birikimler.get(para)
            for ad in liste:
                d = self.dugum[ad]
                if ad not in gorunen or not gorunen[ad][1]:
                    continue
                if d["fiyat"] > butce:
                    continue
                if hedef and d["agirlik"] < hedef["agirlik"] and d["fiyat"] > kulce[para] * kucuk:
                    continue
                puan = d["agirlik"] * (kulce[para] / d["fiyat"])
                if puan > en_puan:
                    en, en_puan = d, puan
        return en

    def secenekler(self) -> list:
        """İnceleme için: önbellekteki tüm düğümler, puana göre."""
        kulce = self.kulceler()
        self.guncelle()
        out = [dict(d, puan=d["agirlik"] * kulce[d["para"]] / d["fiyat"]) for l in self.listeler.values()
               for d in (self.dugum[a] for a in l)]
        return sorted(out, key=lambda x: -x["puan"])

    # ---------- planlayıcı arayüzü ----------
    def hazir_mi(self) -> bool:
        """Önbellek dolu ve dünya değişmemişse oyuna (ve sekmeye) gitmeden karar verilebilir."""
        return bool(self.dugum) and self._mevcut_dunya() == self.dunya

    def adaylar(self) -> list:
        """Önbellekten alınabilecek düğümler (oyuna sormadan)."""
        out = []
        for liste in self.listeler.values():
            for ad in liste:
                d = self.dugum[ad]
                if ad in getattr(self, "_basarisiz", set()):
                    continue
                out.append({"modul": "yetenek", "ad": ad, "maliyet": {d["para"]: d["fiyat"]},
                            "deger": d["agirlik"], "aciklama": f"{ad.replace('TreeUpgrade_', '')} "
                            f"({d['alinan']}/{d['max']})"})
        return out

    def uygula(self, aday: dict) -> bool:
        """Planlayıcı seçti: yetenek sekmesi açıkken çağrılır."""
        d = self.dugum.get(aday["ad"])
        if not d:
            return False
        ok = self.satin_al(d)
        if ok:
            self.guncelle()   # yeni açılan düğümleri yakala (tek hızlı çağrı)
        else:
            self._basarisiz = getattr(self, "_basarisiz", set()) | {aday["ad"]}
        self._kaydet()
        return ok

    def tur_basi(self):
        self._basarisiz = set()

    # ---------- satın alma ----------
    def satin_al(self, d: dict) -> bool:
        ad = d["ad"]
        kopru._al("uzerine_gel", ad=ad)
        try:
            kopru.bas(ad)
        finally:
            kopru._al("uzerine_gel", ad=ad, cik=1)
        time.sleep(0.2)
        once = d["alinan"]
        self._oku_ve_yerlestir(ad, d["para"])   # sadece bu düğümü yeniden oku ve listeye yerleştir
        return self.dugum[ad]["alinan"] > once

    def harca(self, en_fazla: int | None = None) -> list:
        en_fazla = en_fazla or self.y.get("tur_basina_en_fazla", 30)
        bas = time.time()
        gorunen = self.guncelle()
        kulce = self.kulceler()
        alinanlar, basarisiz = [], set()
        for _ in range(en_fazla):
            d = self.en_iyi(kulce, {k: v for k, v in gorunen.items() if k not in basarisiz})
            if not d:
                break
            fiyat = d["fiyat"]
            if self.satin_al(d):
                kulce[d["para"]] -= fiyat
                print(f"[yetenek] Alındı: {d['ad']}  ({fiyat:.0f} {d['para']}, "
                      f"{self.dugum[d['ad']]['alinan']}/{d['max']})")
                alinanlar.append(d)
                # Alım ağaçta yeni düğüm açmış olabilir: tek hızlı liste çağrısıyla kontrol et
                gorunen = self.guncelle()
            else:
                print(f"[yetenek] Alınamadı: {d['ad']} -> bu turda atlanıyor")
                basarisiz.add(d["ad"])
                kulce = self.kulceler()   # cüzdan beklenenden farklı olabilir, tazele
        self._kaydet()
        print(f"[yetenek] Harcama {time.time() - bas:.1f} sn sürdü.")
        return alinanlar
