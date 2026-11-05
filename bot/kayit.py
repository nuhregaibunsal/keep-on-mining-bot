"""Botun hafızası: olay günlüğü (neyi neden yaptı), oturum istatistikleri ve harcamalar.

- olay(): her karar/eylem bir olay olarak saklanır (son 1000'i hafızada, hepsi kayitlar/olaylar.jsonl'de).
- Oturum başı/sonu cüzdan farkından KAZANÇ, planlayıcı işlemlerinden HARCAMA hesaplanır.
- İstatistikler kayitlar/istatistik.json'a yazılır, bot yeniden başlasa da korunur.
- print() çıktıları da (Tee ile) günlüğe düşer: "[örs] ..." -> modül "örs".
"""
import json
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path

KOK = Path(__file__).resolve().parent.parent
KLASOR = KOK / "kayitlar"
_kilit = threading.Lock()


def _bos_istatistik():
    return {"ilk_baslangic": time.time(), "calisma_suresi": 0.0, "oturum_sayisi": 0, "kaya": 0, "eser": 0,
            "xp": 0.0, "kazanc": {}, "harcama": {}, "islem": {}, "oturumlar": []}


class Kayit:
    def __init__(self):
        KLASOR.mkdir(exist_ok=True)
        self.olaylar = deque(maxlen=1000)
        self.sayac = 0
        self.ist = self._yukle()
        self.canli = {}          # arayüz için anlık durum (bot durumu, oyun özeti, hedefler...)
        self._oturum = None
        self._son_kayit = 0.0

    # ---------- olaylar ----------
    def olay(self, modul: str, mesaj: str, neden=None, seviye: str = "bilgi"):
        with _kilit:
            self.sayac += 1
            o = {"id": self.sayac, "t": time.time(), "modul": modul, "mesaj": mesaj, "seviye": seviye}
            if neden is not None:
                o["neden"] = neden
            self.olaylar.append(o)
        try:
            with open(KLASOR / "olaylar.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(o, ensure_ascii=False) + "\n")
        except OSError:
            pass
        return o

    def son_olaylar(self, sonra: int = 0) -> list:
        with _kilit:
            return [o for o in self.olaylar if o["id"] > sonra]

    # ---------- istatistik ----------
    def _yukle(self):
        try:
            return json.loads((KLASOR / "istatistik.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _bos_istatistik()

    def kaydet(self, zorla=False):
        if not zorla and time.time() - self._son_kayit < 5:
            return
        self._son_kayit = time.time()
        with _kilit:
            veri = json.dumps(self.ist, ensure_ascii=False)
        try:
            (KLASOR / "istatistik.json").write_text(veri, encoding="utf-8")
        except OSError:
            pass

    def sifirla(self):
        with _kilit:
            self.ist = _bos_istatistik()
        self.kaydet(True)

    @staticmethod
    def _temiz(c: dict) -> dict:
        return {k: v for k, v in c.items() if not k.startswith("_") and isinstance(v, (int, float))}

    def oturum_basla(self, cuzdan: dict, eser: int, dunya, seviye):
        self.canli["son_ilerleme"] = time.time()
        self._oturum = {"bas": time.time(), "cuzdan": self._temiz(cuzdan), "eser": eser, "dunya": dunya,
                        "seviye": seviye}

    def oturum_bitti(self, cuzdan: dict, eser: int, kaya: int, xp: float):
        self.canli["son_ilerleme"] = time.time()
        o = self._oturum
        self._oturum = None
        if not o:
            return None
        son = self._temiz(cuzdan)
        kazanc = {k: round(son.get(k, 0) - v, 2) for k, v in o["cuzdan"].items() if son.get(k, 0) - v > 0}
        sure = time.time() - o["bas"]
        kayit = {"t": time.time(), "sure": round(sure, 1), "kaya": kaya, "eser": max(0, eser - o["eser"]),
                 "xp": round(xp or 0, 1), "dunya": o["dunya"], "kazanc": kazanc}
        with _kilit:
            ist = self.ist
            ist["oturum_sayisi"] += 1
            ist["kaya"] += kaya
            ist["eser"] += kayit["eser"]
            ist["xp"] += kayit["xp"]
            for k, v in kazanc.items():
                ist["kazanc"][k] = ist["kazanc"].get(k, 0) + v
            ist["oturumlar"].append(kayit)
            ist["oturumlar"] = ist["oturumlar"][-300:]
        self.kaydet(True)
        return kayit

    def harcama(self, modul: str, maliyet: dict, aciklama: str):
        with _kilit:
            h = self.ist["harcama"].setdefault(modul, {})
            for k, v in maliyet.items():
                h[k] = h.get(k, 0) + v
            self.ist["islem"][modul] = self.ist["islem"].get(modul, 0) + 1
        self.kaydet()

    def calisma_ekle(self, saniye: float):
        with _kilit:
            self.ist["calisma_suresi"] += saniye


kayit = Kayit()


class Tee:
    """print() çıktısını hem konsola hem günlüğe yazar."""
    _desen = re.compile(r"^\[([^\]]+)\]\s*(.*)$")

    def __init__(self, asil):
        self.asil = asil
        self._tampon = ""

    def write(self, s):
        try:
            self.asil.write(s)
        except Exception:
            pass
        self._tampon += s
        while "\n" in self._tampon:
            satir, self._tampon = self._tampon.split("\n", 1)
            satir = satir.strip()
            if not satir:
                continue
            m = self._desen.match(satir)
            modul, mesaj = (m.group(1), m.group(2)) if m else ("bot", satir)
            if getattr(kayit, "_sessiz", False):
                continue
            kayit.olay(modul, mesaj, seviye="hata" if "hata" in satir.lower() else "bilgi")
        return len(s)

    def flush(self):
        try:
            self.asil.flush()
        except Exception:
            pass


def tee_kur():
    if not isinstance(sys.stdout, Tee):
        sys.stdout = Tee(sys.stdout)
