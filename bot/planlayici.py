"""Planlayıcı: örs ve yetenek ağacının harcamalarını TEK bütçe üzerinden yönetir.

Her modül "aday" verir:  {modul, maliyet: {kaynak: miktar}, deger, aciklama, ...}
Planlayıcı:
  1. Cüzdanı tek çağrıyla okur (külçeler + mücevherler).
  2. Birikim hedefleri: her kaynak için, henüz alınamayan EN DEĞERLİ önemli aday (modül fark etmez)
     o kaynağı "kilitler". O kaynaktan daha az değerli şeylere sadece cüzdanın küçük bir kısmı harcanabilir.
     Örn. 6. kazma (değer 150) obsidyen istiyorsa, yetenek ağacındaki obsidyenli düşük önemli düğümler beklemeye alınır.
  3. Alınabilir adaylar arasında puanı en yüksek olanı uygular:  puan = değer × min(cüzdan / maliyet)
  4. Hiçbir hedefe ulaşılmadıysa menülere HİÇ girilmez (bot doğrudan madene döner).
  Sekmeler (Örs, Yetenek Ağacı) sadece o sekmede yapılacak iş varsa ve bir kez açılır.
"""
import time

from . import kopru
from .kayit import kayit

KULCELER = ["gold", "silver", "copper", "sulfur", "obsidian", "titanium", "realgar", "rhodonite",
            "meteorite", "amberite", "viridium", "mythril", "digitite", "magisite", "edenite", "prismite"]
MUCEVHERLER = ["ruby", "quartz", "amethyst", "peridot", "sphene", "emerald", "fireOpal", "diamond", "spinel",
               "slimestone", "tanzanite", "ammolite", "redOpal", "alexandrite", "moonstone", "solarite"]
SEKME = {"ors": "TheAnvilText_Tab", "yetenek": "SkillTreeText_Tab", "dunyalar": "WordlsText_Tab",
         "madenler": "TheMinesText_Tab", "pazar": "TheMarketText_Tab",
         "cekirdek": "SkillTreeText_Tab"}   # oyun sonunda yetenek ağacı sekmesi Dünya Çekirdeği'ni gösterir


def cuzdan_oku() -> dict:
    g = kopru.alanlar("OreGemsAndCoins")
    c = {k: float(g.get(f"total{k.capitalize()}Bars", 0) or 0) for k in KULCELER}
    c.update({k: float(g.get("total" + k[:1].upper() + k[1:], 0) or 0) for k in MUCEVHERLER})
    c.update({f"{k}Coins": float(g.get(f"total{k.capitalize()}Coins", 0) or 0) for k in KULCELER})
    c["_ham"] = g
    return c


class Planlayici:
    def __init__(self, ayar: dict, agac, ors, engel=None, dunya=None, madenler=None, pazar=None, cekirdek=None):
        self.ayar = ayar
        self.dunya = dunya    # Dunyalar (kitaplarla çalışır, külçe bütçesinden bağımsız)
        self.madenler = madenler  # Otomatik madenler (külçe/yakut/para ile, ortak bütçede)
        self.pazar = pazar        # Pazar: iksir/yiyecek (paralarla alınır, mücevherle yükselir)
        self.cekirdek = cekirdek  # Dünya Çekirdeği (oyun sonu): tüm külçe ve mücevherlerle
        self.p = ayar.get("planlayici", {})
        self.agac = agac      # YetenekAgaci (önbellekli)
        self.ors = ors        # Ors
        self.engel = engel
        self.acik_sekme = None
        self.menude = False

    # ---------- menü / sekme ----------
    def _menuye_gir(self):
        if self.menude:
            return
        try:
            kopru.bas("YÜKSELT!")
        except kopru.KopruHatasi:
            pass
        time.sleep(1.2)
        if self.engel:
            self.engel.temizle()
        self.menude = True

    def _sekme(self, modul: str):
        if self.acik_sekme == modul:
            return
        self._menuye_gir()
        kopru.bas(SEKME[modul])
        time.sleep(0.8)
        self.acik_sekme = modul

    # ---------- karar ----------
    def _adaylar(self) -> list:
        out = []
        if self.ayar.get("yetenek", {}).get("aktif", False):
            out += self.agac.adaylar()
        if self.ayar.get("ors", {}).get("aktif", False):
            out += self.ors.adaylar()
        if self.madenler is not None:
            out += self.madenler.adaylar()
        if self.pazar is not None:
            out += self.pazar.adaylar()
        if self.cekirdek is not None:
            out += self.cekirdek.adaylar()
        return out

    @staticmethod
    def _anahtar(a):
        return (a["modul"], a.get("ad"), a.get("tur"), a.get("i"))

    def _gelir_hesapla(self):
        """Son oturumlardaki ortalama kaynak geliri (oturum başına). Geliri olmayan kaynak = ulaşılamaz hedef."""
        os_ = kayit.ist.get("oturumlar", [])[-10:]
        self.gelir = {}
        for o in os_:
            for k, v in o.get("kazanc", {}).items():
                self.gelir[k] = self.gelir.get(k, 0) + v / len(os_)
        self.gelir_bilinir = len(os_) >= 3

    def _ulasilamaz(self, a, cuzdan) -> bool:
        if not getattr(self, "gelir_bilinir", False):
            return False
        return any(cuzdan.get(k, 0) < v and self.gelir.get(k, 0) <= 0 for k, v in a["maliyet"].items())

    def _birikimler(self, adaylar, cuzdan) -> dict:
        esik = self.p.get("birikim_esigi", 70)
        hedef = {}
        for a in adaylar:
            if self._ulasilamaz(a, cuzdan):
                continue   # geliri olmayan kaynağa bağlı hedef kimseyi kilitlemesin
            # Alınabilir hale gelen önemli hedef de kilidi korur: yoksa ucuz düşük değerli şeyler
            # (yüksek cüzdan/fiyat oranıyla) önce harcanır ve hedef yine kaçar.
            if a["deger"] < esik:
                continue
            for k in a["maliyet"]:
                if k not in hedef or a["deger"] > hedef[k]["deger"]:
                    hedef[k] = a
        return hedef

    def _alinabilir(self, a, cuzdan) -> bool:
        yedek = self.p.get("yedek_oran", 0.0)
        return all(cuzdan.get(k, 0) * (1 - yedek) >= v for k, v in a["maliyet"].items())

    def _engelli(self, a, cuzdan, hedefler) -> bool:
        kucuk = self.p.get("kucuk_harcama_orani", 0.1)
        for k, v in a["maliyet"].items():
            h = hedefler.get(k)
            if h is None or h is a or a["deger"] >= h["deger"]:
                continue
            mevcut = cuzdan.get(k, 0)
            if mevcut >= h["maliyet"][k]:
                # hedef şu an alınabilir: onu alınamaz hale getirecek hiçbir harcama yapma
                if mevcut - v < h["maliyet"][k]:
                    return True
            elif v > mevcut * kucuk:
                return True
        return False

    def sec(self, cuzdan, haric=frozenset()):
        kara = getattr(self, "kara_liste", {})
        adaylar = [a for a in self._adaylar() if self._anahtar(a) not in haric and self._anahtar(a) not in kara]
        self.hedefler = self._birikimler(adaylar, cuzdan)
        puanli, engelli = [], []
        for a in adaylar:
            if not self._alinabilir(a, cuzdan):
                continue
            if self._engelli(a, cuzdan, self.hedefler):
                engelli.append(a)
                continue
            if a["maliyet"]:
                oran = min(cuzdan.get(k, 0) / v for k, v in a["maliyet"].items() if v > 0)
            else:
                oran = 1e6   # bedava (kuşanma)
            puanli.append((a["deger"] * oran, oran, a))
        puanli.sort(key=lambda x: -x[0])
        # Arayüzdeki günlük için karar gerekçesi
        self.son_neden = None
        if puanli:
            p, oran, a = puanli[0]
            self.son_neden = {
                "secilen": a["aciklama"], "modul": a["modul"], "deger": round(a["deger"], 1),
                "cuzdan/maliyet": round(oran, 2) if oran < 1e5 else "bedava", "puan": round(p, 1),
                "maliyet": {k: round(v) for k, v in a["maliyet"].items()},
                "alternatifler": [f"{x[2]['aciklama']} (puan {x[0]:.0f})" for x in puanli[1:4]],
                "birikim_yuzunden_bekleyen": [f"{x['aciklama']} -> {self._hedef_adi(x)}" for x in engelli[:3]],
                "formul": "puan = değer × (cüzdan / maliyet)",
            }
        return puanli[0][2] if puanli else None

    def _hedef_adi(self, a):
        for k in a["maliyet"]:
            h = self.hedefler.get(k)
            if h is not None and h is not a:
                return f"{k}: {h['aciklama']}"
        return ""

    def hedef_ozeti(self, cuzdan) -> list:
        out = []
        for k, h in (getattr(self, "hedefler", None) or {}).items():
            g = getattr(self, "gelir", {}).get(k, 0)
            eksik = max(0.0, h["maliyet"][k] - cuzdan.get(k, 0))
            out.append({"kaynak": k, "hedef": h["aciklama"], "modul": h["modul"], "mevcut": round(cuzdan.get(k, 0)),
                        "gereken": round(h["maliyet"][k]), "deger": round(h["deger"]), "gelir_oturum": round(g),
                        "tahmini_oturum": round(eksik / g, 1) if g > 0 and eksik > 0 else (0 if eksik == 0 else None)})
        return out

    # ---------- tur ----------
    def tur(self) -> list:
        """Oturum arası: hedefe ulaşılan her şeyi uygula. Menüye sadece gerekirse girer."""
        bas = time.time()
        self.acik_sekme, self.menude = None, False
        self.agac.tur_basi()
        cuzdan = cuzdan_oku()
        self.ors.durum_oku(cuzdan)
        if self.madenler is not None:
            self.madenler.durum_oku()
            self.madenler.tur_basi()
        if self.pazar is not None:
            self.pazar.durum_oku()
        if self.cekirdek is not None:
            self.cekirdek.durum_oku()
        # Yetenek önbelleği boşsa/dünya değiştiyse bir kez tarama gerekir (sekme açık olmalı)
        if self.ayar.get("yetenek", {}).get("aktif", False) and not self.agac.hazir_mi():
            self._sekme("yetenek")
            self.agac.guncelle()
        yapilan = []
        basarisiz = set()
        self._gelir_hesapla()
        # Önceki turlarda başarısız olanlar birkaç tur dinlensin (her tur aynı hataya takılmasın)
        self.kara_liste = {k: n - 1 for k, n in getattr(self, "kara_liste", {}).items() if n > 1}
        for _ in range(self.p.get("tur_basina_en_fazla", 40)):
            a = self.sec(cuzdan, frozenset(basarisiz))
            if a is None:
                break
            anahtar = self._anahtar(a)
            self._sekme(a["modul"])
            ok = {"yetenek": self.agac, "ors": self.ors, "madenler": self.madenler,
                  "pazar": self.pazar, "cekirdek": self.cekirdek}[a["modul"]].uygula(a)
            if ok:
                yapilan.append(a)
                gercek = a.get("gercek_maliyet", a["maliyet"])
                kayit.harcama(a["modul"], gercek, a["aciklama"])
                kayit.olay("karar", f"{a['aciklama']}", neden=self.son_neden)
                if a["modul"] == "yetenek":
                    d = self.agac.dugum.get(a["ad"], {})
                    print(f"[plan] Alındı: {a['ad'].replace('TreeUpgrade_', '')} "
                          f"({d.get('alinan')}/{d.get('max')}, {a['maliyet']})")
            else:
                print(f"[plan] Olmadı: {a['aciklama']} -> {self.p.get('basarisiz_bekleme_turu', 10)} tur atlanacak")
                basarisiz.add(anahtar)
                self.kara_liste[anahtar] = self.p.get("basarisiz_bekleme_turu", 10)
            cuzdan = cuzdan_oku()
            self.ors.durum_oku(cuzdan)
        # Paylaşılan kazma güçlendirmeleri (SharedBuffs kartı): sadece değişiklik gerekiyorsa örs sekmesi açılır
        if self.ayar.get("ors", {}).get("aktif", False):
            try:
                if self.ors.paylasilan_gerekli_mi():
                    self._sekme("ors")
                    if self.ors.paylasilan_ayarla():
                        yapilan.append({"modul": "ors", "tur": "paylasilan"})
            except (kopru.KopruHatasi, KeyError, IndexError) as e:
                print(f"[örs] Paylaşılan güçlendirme hatası: {e}")
        # Pazar: stoktaki iksir/yiyecekleri bir sonraki oturum için kullan (sadece kullanılacak varsa sekme açılır)
        if self.pazar is not None:
            try:
                liste = self.pazar.kullanilacaklar()
                if liste:
                    self._sekme("pazar")
                    kullanilan = self.pazar.kullan(liste)
                    if kullanilan:
                        kayit.olay("karar", f"Oturum için kullanıldı: {', '.join(kullanilan)}", neden={
                            "kural": "ağırlığı > 0 olan ve stokta bulunan her eşyadan 1 tane (bir sonraki oturumda etkili)"})
            except (kopru.KopruHatasi, KeyError, IndexError) as e:
                print(f"[pazar] Hata: {e}")
        # Dünyalar ve kartlar: kitaplarla çalışır; sadece hedefe ulaşıldıysa sekme açılır
        if self.dunya is not None:
            try:
                for is_ in self.dunya.yapilacaklar():
                    self._sekme("dunyalar")
                    if self.dunya.uygula(is_):
                        yapilan.append({"modul": "dunyalar", "is": is_})
                if self.dunya.w.get("isInChooseCards"):   # kart ekranı bir şekilde açık kaldıysa
                    self._sekme("dunyalar")
                    self.dunya.kart_sec()
            except (kopru.KopruHatasi, KeyError, IndexError) as e:
                print(f"[dünya] Hata: {e}")
        try:
            son_c = cuzdan_oku()
            if not getattr(self, "hedefler", None):
                self.sec(son_c)   # hedefleri güncel cüzdanla hesapla
            kayit.canli["hedefler"] = self.hedef_ozeti(son_c)
        except kopru.KopruHatasi:
            pass
        if self.p.get("hedefleri_yaz", True) and getattr(self, "hedefler", None):
            print("[plan] Birikim hedefleri: " + ", ".join(
                f"{k} -> {h['aciklama']}" for k, h in self.hedefler.items()))
        print(f"[plan] {len(yapilan)} işlem, {time.time() - bas:.1f} sn"
              + ("" if self.menude else " (menüye girilmedi)"))
        return yapilan
