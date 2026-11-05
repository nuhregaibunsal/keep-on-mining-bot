"""Ayar karşılaştırma (A/B deneyi).

Bir ayarın iki değeri (A ve B) oturum oturum SIRAYLA denenir (A, B, A, B...). Sırayla denemek önemli:
bot sürekli yükseltme aldığı için kazanç zamanla artar; ardışık oturumları eşleştirmek bu eğilimi dengeler.
Her oturumun sonucu (kaya, XP, kaynak kazançları) varyantıyla kaydedilir. İki taraf da hedef sayıya
ulaşınca deney biter, ayar eski değerine döner ve sonuç günlüğe yazılır (istenirse kazanan uygulanır).
Durum kayitlar/deney.json'da tutulur (bot yeniden başlasa da sürer).
"""
import json
import math
import time

from .kayit import KLASOR, kayit

DOSYA = KLASOR / "deney.json"


def _yol(ayar: dict, bolum: str):
    d = ayar
    for p in bolum.split("."):
        d = d.setdefault(p, {})
    return d


class Deney:
    def __init__(self, ayar: dict):
        self.ayar = ayar
        self.d = self._yukle()
        self.aktif_varyant = None

    def _yukle(self):
        try:
            return json.loads(DOSYA.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"aktif": False}

    def _kaydet(self):
        DOSYA.write_text(json.dumps(self.d, ensure_ascii=False, indent=1), encoding="utf-8")

    def baslat(self, bolum, anahtar, a, b, hedef=8, metrik="kaya", kazanani_uygula=False):
        bolum_d = _yol(self.ayar, bolum)
        self.d = {"aktif": True, "bolum": bolum, "anahtar": anahtar, "A": a, "B": b, "hedef": int(hedef),
                  "metrik": metrik, "kazanani_uygula": bool(kazanani_uygula), "orijinal": bolum_d.get(anahtar),
                  "baslangic": time.time(), "sonuclar": {"A": [], "B": []}, "sira": "A"}
        self._kaydet()
        kayit.olay("deney", f"Deney başladı: [{bolum}] {anahtar}  A={a}  B={b}  ({hedef}'er oturum, ölçü: {metrik})")

    def durdur(self, neden="elle durduruldu"):
        if not self.d.get("aktif"):
            return
        self._geri_al()
        self.d["aktif"] = False
        self.d["bitis"] = time.time()
        self.d["bitis_nedeni"] = neden
        self._kaydet()
        kayit.olay("deney", f"Deney bitti ({neden}).", neden=self.ozet())

    def _geri_al(self):
        _yol(self.ayar, self.d["bolum"])[self.d["anahtar"]] = self.d.get("orijinal")

    # ---- maden oturumu kancaları ----
    def oturum_basladi(self):
        if not self.d.get("aktif"):
            self.aktif_varyant = None
            return
        v = self.d.get("sira", "A")
        _yol(self.ayar, self.d["bolum"])[self.d["anahtar"]] = self.d[v]
        self.aktif_varyant = v
        kayit.olay("deney", f"Bu oturum varyant {v}: {self.d['anahtar']} = {self.d[v]}")

    def oturum_bitti(self, sonuc: dict):
        v = self.aktif_varyant
        self.aktif_varyant = None
        if not self.d.get("aktif") or v is None or not sonuc:
            return
        self.d["sonuclar"][v].append({"kaya": sonuc.get("kaya", 0), "xp": sonuc.get("xp", 0),
                                      "eser": sonuc.get("eser", 0), "kazanc": sonuc.get("kazanc", {})})
        diger = "B" if v == "A" else "A"
        if len(self.d["sonuclar"][diger]) < self.d["hedef"]:
            self.d["sira"] = diger
        elif len(self.d["sonuclar"][v]) < self.d["hedef"]:
            self.d["sira"] = v
        self._kaydet()
        if all(len(self.d["sonuclar"][x]) >= self.d["hedef"] for x in "AB"):
            oz = self.ozet()
            kazanan = oz.get("kazanan")
            self.durdur("tamamlandı")
            if self.d.get("kazanani_uygula") and kazanan in ("A", "B"):
                from . import ayar_duzenle
                try:
                    ayar_duzenle.yaz(self.d["bolum"], self.d["anahtar"], self.d[kazanan])
                    _yol(self.ayar, self.d["bolum"])[self.d["anahtar"]] = self.d[kazanan]
                    kayit.olay("deney", f"Kazanan uygulandı: {self.d['anahtar']} = {self.d[kazanan]}")
                except Exception as e:
                    kayit.olay("deney", f"Kazanan uygulanamadı: {e}", seviye="hata")
        else:
            self._geri_al()

    # ---- sonuç ----
    def _deger(self, s, metrik):
        if metrik in ("kaya", "xp", "eser"):
            return float(s.get(metrik, 0))
        return float(s.get("kazanc", {}).get(metrik, 0))

    def ozet(self) -> dict:
        d = self.d
        if not d.get("bolum"):
            return {}
        m = d.get("metrik", "kaya")
        oz = {"ayar": f"[{d['bolum']}] {d['anahtar']}", "metrik": m, "hedef": d.get("hedef"), "aktif": d.get("aktif")}
        for v in "AB":
            x = [self._deger(s, m) for s in d["sonuclar"][v]]
            n = len(x)
            ort = sum(x) / n if n else 0
            sd = math.sqrt(sum((t - ort) ** 2 for t in x) / (n - 1)) if n > 1 else 0
            oz[v] = {"deger": d[v], "n": n, "ortalama": round(ort, 1), "sapma": round(sd, 1)}
        a, b = oz["A"], oz["B"]
        if a["n"] >= 2 and b["n"] >= 2 and a["ortalama"] > 0:
            fark = (b["ortalama"] - a["ortalama"]) / a["ortalama"] * 100
            hata = math.sqrt(a["sapma"] ** 2 / a["n"] + b["sapma"] ** 2 / b["n"]) or 1e-9
            z = (b["ortalama"] - a["ortalama"]) / hata
            oz["fark_yuzde"] = round(fark, 1)
            oz["guven"] = "yüksek" if abs(z) > 2 else ("orta" if abs(z) > 1 else "düşük (fark gürültü olabilir)")
            oz["kazanan"] = ("B" if fark > 0 else "A") if abs(z) > 1 else "belirsiz"
        return oz
