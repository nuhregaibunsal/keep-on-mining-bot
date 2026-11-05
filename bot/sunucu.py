"""Kontrol paneli sunucusu: http://127.0.0.1:8770  (sadece bu bilgisayardan erişilebilir)

API:
  GET  /api/durum                 bot + oyun anlık durumu, birikim hedefleri
  GET  /api/istatistik            toplam ve oturum bazlı istatistikler
  GET  /api/olaylar?sonra=ID      günlük (karar gerekçeleriyle)
  GET  /api/ayarlar               ayarlar.toml yapısı (açıklamalarla) + ham metin
  POST /api/ayar                  {"bolum","anahtar","deger"}  tek değer
  POST /api/ayarlar_ham           {"metin"}  tüm dosya
  POST /api/kontrol               {"komut": "baslat" | "duraklat" | "sifirla_istatistik"}
"""
import json
import threading
import time
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import ayar_duzenle, kopru
from .kayit import kayit

KOK = Path(__file__).resolve().parent.parent
ARAYUZ = KOK / "arayuz"
PORT = 8770



ESERLER = [  # oyundaki sıra (Artifacts.artifactChances ile aynı), nadirlik grupları 12/10/8/6
    ("brick", "Tuğla"), ("coolrock", "Havalı kaya"), ("acorn", "Meşe palamudu"), ("wood", "Odun"), ("satchel", "Heybe"),
    ("crystal", "Kristal"), ("stonerune", "Taş rün"), ("hourglass", "Kum saati"), ("compass", "Pusula"),
    ("boxingglove", "Boks eldiveni"), ("magnet", "Mıknatıs"), ("magicwand", "Sihirli değnek"),
    ("sonicring", "Sonik yüzük"), ("knife", "Bıçak"), ("sword", "Kılıç"), ("axe", "Balta"), ("fistsculpture", "Yumruk heykeli"),
    ("goldrune", "Altın rün"), ("envelope", "Zarf"), ("goldring", "Altın yüzük"), ("arrows", "Oklar"), ("creeperhead", "Creeper kafası"),
    ("detonator", "Fünye"), ("fallingstar", "Kayan yıldız"), ("diamondrune", "Elmas rünü"), ("mappiece1", "Harita parçası 1"),
    ("mappiece2", "Harita parçası 2"), ("necklace", "Kolye"), ("estusflask", "Estus şişesi"), ("bluering", "Mavi yüzük"),
    ("chesspiece", "Satranç taşı"), ("mushroom", "Mantar"), ("goldendice", "Altın zar"), ("gemring", "Mücevherli yüzük"),
    ("crown", "Taç"), ("cookie", "Kurabiye"),
]
NADIRLIK = ["Yaygın"] * 12 + ["Nadir"] * 10 + ["Epik"] * 8 + ["Efsanevi"] * 6
KART_METIN = KOK / "kesif" / "kart_metinleri.json"


def eser_ozeti():
    a = kopru.alanlar("Artifacts")
    sans = a.get("artifactChances") or []
    os_ = kayit.ist.get("oturumlar", [])[-10:]
    kaya_os = (sum(o["kaya"] for o in os_) / len(os_)) if os_ else 400
    liste, eksik_p = [], 0.0
    for i, (k, ad) in enumerate(ESERLER):
        p = float(sans[i]) if i < len(sans) else 0.0
        bulundu = bool(a.get(f"{k}_found"))
        if not bulundu:
            eksik_p += p
        liste.append({"ad": ad, "kod": k, "nadirlik": NADIRLIK[i], "bulundu": bulundu, "sans": p,
                      "tahmini_oturum": (1 / (kaya_os * p)) if (p > 0 and not bulundu) else None})
    return {"eserler": liste, "kaya_oturum": round(kaya_os), "bulunan": sum(x["bulundu"] for x in liste),
            "toplam": len(liste), "siradaki_oturum": (1 / (kaya_os * eksik_p)) if eksik_p else None,
            "bot_buldu": kayit.ist.get("eser", 0),
            "not": "Tahmin: kaya başına çıkma şansı × oturum başına kazılan kaya (son 10 oturum ortalaması)."}


def kart_ozeti(ayar):
    import json as _j
    w = kopru.alanlar("Worlds")
    try:
        metin = _j.loads(KART_METIN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        metin = {}
    if len(metin) < len(w.get("cards", [])):
        for c in w["cards"]:
            if c["ad"] not in metin:
                try:
                    metin[c["ad"]] = [x["metin"] for x in kopru._al("metinler", ad=c["ad"])]
                except kopru.KopruHatasi:
                    metin[c["ad"]] = []
        KART_METIN.parent.mkdir(exist_ok=True)
        KART_METIN.write_text(_j.dumps(metin, ensure_ascii=False, indent=1), encoding="utf-8")
    agir = ayar.get("dunyalar", {}).get("kart_agirliklari", {})
    out = []
    for i, c in enumerate(w.get("cards", [])):
        kisa = c["ad"].split("_", 1)[-1]
        m = [t for t in metin.get(c["ad"], []) if t and t.strip() not in ("=", "0", "ÜCRETSİZ!")]
        aciklama = max(m, key=len) if m else ""
        baslik = next((t for t in m if t != aciklama and not t.startswith("Level") and len(t) < 50
                       and not t[:1].isdigit()), kisa)
        import re as _re
        out.append({"i": i, "kod": kisa, "baslik": _re.sub(r"<[^>]*>", "", baslik), "aciklama": aciklama,
                    "secili": bool(w["cardsChosen"][i]), "seviye": w["cardLevel"][i],
                    "agirlik": agir.get(kisa, ayar.get("dunyalar", {}).get("varsayilan_kart", 50))})
    return {"kartlar": out, "kirmizi_kitap": kopru.alanlar("LevelMechanics").get("totalMasteryPoints")}


class Yonetici:
    """Bot iş parçacığını, ayarları ve canlı oyun özetini yönetir."""

    def __init__(self, ayar: dict, durum, oyun_getir):
        self.ayar = ayar
        self.durum = durum
        self.oyun_getir = oyun_getir   # OyunPenceresi döndüren fonksiyon (oyun açılınca)
        self.kazici = None
        self.asama = "hazırlanıyor"
        from .deney import Deney
        self.deney = Deney(ayar)

    def sure_sayaci(self):
        """Bot çalıştığı sürece çalışma süresini sayar (kazma döngüsü uzun süre bloklasa da)."""
        while not self.durum.bitti:
            time.sleep(1)
            if self.durum.calisiyor:
                kayit.calisma_ekle(1.0)

    def bot_dongusu(self):
        from .mod_kazma import ModKazici
        while not self.durum.bitti:
            if self.durum.calisiyor:
                try:
                    if self.kazici is None:
                        self.kazici = ModKazici(self.oyun_getir(), self.ayar, self.durum)
                        self.kazici.deney = self.deney
                    self.kazici.calis()
                except Exception as e:  # bot asla sessizce ölmesin
                    if self.ayar.get("bekci", {}).get("aktif", True):
                        print(f"[bot] Hata: {e} -> 5 sn sonra yeniden denenecek (bekçi açık)")
                        time.sleep(5)
                    else:
                        print(f"[bot] Hata: {e} -> duraklatıldı")
                        self.durum.calisiyor = False
            time.sleep(0.2)

    def oyun_ozeti_dongusu(self):
        """Panel için 2 sn'de bir hafif oyun özeti (bot kendi işini ayrıca yapar)."""
        from .planlayici import cuzdan_oku
        while not self.durum.bitti:
            try:
                d = kopru.durum()
                lv = kopru.alanlar("LevelMechanics")
                an = kopru.alanlar("TheAnvil")
                w = kopru.alanlar("Worlds")
                c = cuzdan_oku()
                i = an.get("pickaxeNumberEquipped", 0)
                kayit.canli["oyun"] = {
                    "bagli": True, "madende": bool(d.get("isInMiningSession")), "kalan": d.get("timeLeft"),
                    "kaya_tahtada": len(d.get("kayalar", [])), "kazilan": d.get("rocksMinedThisRound"),
                    "level": lv.get("level"), "xp": lv.get("currentXP"), "xp_gereken": lv.get("xpNeedForNextLvl"),
                    "mor_kitap": lv.get("totalTalentPoints"), "kirmizi_kitap": lv.get("totalMasteryPoints"),
                    "dunya": w.get("levelSelected"), "kazma": i + 1, "kazma_seviye": an.get("pickaxeLevel", [0])[i],
                    "hasar": an.get("currentPickaxeDamage"),
                    "cuzdan": {k: round(v) for k, v in c.items() if not k.startswith("_") and v},
                }
                self.asama = "hazır"
            except kopru.KopruHatasi:
                kayit.canli["oyun"] = {"bagli": False}
            except Exception:
                pass
            time.sleep(2)

    def oyun_yenile(self):
        """Oyun yeniden açıldıktan sonra pencere tutamacını tazele (önbellekler korunur)."""
        temizle = getattr(self, "oyun_temizle", None)
        if temizle:
            temizle()
        if self.kazici is not None:
            try:
                self.kazici.oyun = self.oyun_getir()
            except Exception:
                self.kazici = None

    def ayarlari_yenile(self):
        with open(ayar_duzenle.DOSYA, "rb") as f:
            yeni = tomllib.load(f)
        ayar_duzenle.derin_guncelle(self.ayar, yeni)


def _isleyici(yon: Yonetici):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, veri, kod=200):
            b = json.dumps(veri, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(kod)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(b)

        def _govde(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n).decode("utf-8") or "{}")

        def do_GET(self):
            yol, _, sorgu = self.path.partition("?")
            if yol in ("/", "/index.html"):
                b = (ARAYUZ / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
            elif yol == "/api/durum":
                self._json({"bot": {"calisiyor": yon.durum.calisiyor, "asama": yon.asama},
                            "oyun": kayit.canli.get("oyun", {}), "hedefler": kayit.canli.get("hedefler", [])})
            elif yol == "/api/istatistik":
                self._json(kayit.ist)
            elif yol == "/api/olaylar":
                sonra = 0
                for p in sorgu.split("&"):
                    if p.startswith("sonra="):
                        sonra = int(p[6:] or 0)
                self._json(kayit.son_olaylar(sonra))
            elif yol == "/api/eserler":
                try:
                    self._json(eser_ozeti())
                except kopru.KopruHatasi as e:
                    self._json({"hata": str(e)})
            elif yol == "/api/kartlar":
                try:
                    self._json(kart_ozeti(yon.ayar))
                except kopru.KopruHatasi as e:
                    self._json({"hata": str(e)})
            elif yol == "/api/deney":
                self._json({"deney": yon.deney.d, "ozet": yon.deney.ozet()})
            elif yol == "/api/ayarlar":
                try:
                    self._json({**ayar_duzenle.yapi(), "ham": ayar_duzenle.oku_metin()})
                except Exception as e:
                    self._json({"hata": str(e), "ham": ayar_duzenle.oku_metin()}, 200)
            else:
                self._json({"hata": "yok"}, 404)

        def do_POST(self):
            try:
                g = self._govde()
                if self.path == "/api/ayar":
                    deger = g["deger"]
                    if g.get("tip") == "float":
                        deger = float(deger)
                    elif g.get("tip") == "int":
                        deger = int(round(float(deger)))
                    r = ayar_duzenle.yaz(g["bolum"], g["anahtar"], deger)
                    yon.ayarlari_yenile()
                    kayit.olay("ayar", f"[{g['bolum']}] {g['anahtar']} = {g['deger']}")
                    self._json(r)
                elif self.path == "/api/ayarlar_ham":
                    r = ayar_duzenle.ham_yaz(g["metin"])
                    yon.ayarlari_yenile()
                    kayit.olay("ayar", "ayarlar.toml elle düzenlendi")
                    self._json(r)
                elif self.path == "/api/kart_agirlik":
                    ayar_duzenle.yaz("dunyalar.kart_agirliklari", g["kod"], float(g["deger"]) if "." in str(g["deger"]) else int(g["deger"]))
                    yon.ayarlari_yenile()
                    kayit.olay("ayar", f"Kart önemi: {g['kod']} = {g['deger']}")
                    self._json({"tamam": True})
                elif self.path == "/api/deney":
                    if g.get("komut") == "baslat":
                        if yon.deney.d.get("aktif"):
                            raise ValueError("zaten çalışan bir deney var")
                        yon.deney.baslat(g["bolum"], g["anahtar"], g["A"], g["B"], g.get("hedef", 8),
                                         g.get("metrik", "kaya"), g.get("kazanani_uygula", False))
                    elif g.get("komut") == "durdur":
                        yon.deney.durdur()
                    self._json({"tamam": True, "ozet": yon.deney.ozet()})
                elif self.path == "/api/kontrol":
                    k = g.get("komut")
                    if k == "baslat":
                        yon.durum.calisiyor = True
                        kayit.olay("bot", "Panelden başlatıldı")
                    elif k == "duraklat":
                        yon.durum.calisiyor = False
                        kayit.olay("bot", "Panelden duraklatıldı")
                    elif k == "sifirla_istatistik":
                        kayit.sifirla()
                        kayit.olay("bot", "İstatistikler sıfırlandı")
                    self._json({"tamam": True, "calisiyor": yon.durum.calisiyor})
                else:
                    self._json({"hata": "yok"}, 404)
            except Exception as e:
                self._json({"hata": str(e)}, 400)
    return H


def baslat(yon: Yonetici):
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), _isleyici(yon))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    threading.Thread(target=yon.oyun_ozeti_dongusu, daemon=True).start()
    threading.Thread(target=yon.bot_dongusu, daemon=True).start()
    threading.Thread(target=yon.sure_sayaci, daemon=True).start()
    from .bekci import Bekci
    yon.bekci = Bekci(yon)
    threading.Thread(target=yon.bekci.dongu, daemon=True).start()
    return srv
