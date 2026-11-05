"""Örs: yeni kazma yapma, en iyi kazmayı kuşanma ve seviye atlatma.

Oyundan okunanlar (TheAnvil):
  pickaxeCrafted[i]         -> yapıldı mı
  pickaxeLevel[i]           -> seviye
  pickaxeTime/Damage/CritChance/CritDamage/CircleSize[i] -> şu anki statlar
  pickaxe{N}{Cevher}Price   -> yapım fiyatı (külçe), örn. pickaxe5SulfurPrice
  pickaxe{N}Price_{mücevher}-> seviye atlatma fiyatı (her seviyede ×1.36), örn. pickaxe4Price_quartz
  pickaxe*Increase          -> seviye başına stat artışı

Karar:
  1. Sıradaki yapılmamış kazmanın külçeleri yetiyorsa yap.
  2. Her yapılmış kazma için "eldeki mücevherle kaç seviye atlar ve sonunda gücü ne olur" hesapla.
     Potansiyeli en yüksek olanı kuşan.
  3. Kuşanılan kazmayı mücevher bütçesi yettiğince seviye atlat.
Güç = hasar / süre × (1 + kritik% × (kritik hasar − 1)) × çember²  (çember alanı: aynı anda vurulan kaya)
"""
import re
import time

from . import kopru

ARTIS = 1.36
import json as _json
from pathlib import Path as _Path
try:
    FIYAT_HARITASI = _json.loads((_Path(__file__).with_name("kazma_fiyat_haritasi.json")).read_text(encoding="utf-8"))
except (OSError, ValueError):
    FIYAT_HARITASI = {}  # oyunda seviye fiyat çarpanı (TheAnvil.LevelUpPickaxe)


class Ors:
    def __init__(self, ayar: dict):
        self.o = ayar.get("ors", {})

    # ---------- okuma ----------
    def _oku(self):
        a = kopru.alanlar("TheAnvil")
        g = kopru.alanlar("OreGemsAndCoins")
        self.a, self.g = a, g
        self.adet = len(a["pickaxeCrafted"])
        self.yapim = {}   # i -> {cevher: fiyat}
        self.seviye_fiyat = {}  # i -> (mücevher, fiyat)
        for k, v in a.items():
            m = re.fullmatch(r"pickaxe(\d+)([A-Z][a-z]+)Price", k)
            if m and isinstance(v, (int, float)) and v > 0:
                i = int(m.group(1)) - 1
                # Oyun hatası: bazı alan adları gerçekte düşülen külçeyle uyuşmuyor (örn. pickaxe12MeteoritePrice
                # aslında AMBERİT düşer). Gerçek eşleşme oyunun CraftButton kodundan çıkarıldı.
                kulce = FIYAT_HARITASI.get(str(i), {}).get(k, m.group(2).lower())
                self.yapim.setdefault(i, {})[kulce] = float(v)
            m = re.fullmatch(r"pickaxe(\d+)Price_(\w+)", k)
            if m and isinstance(v, (int, float)):
                self.seviye_fiyat[int(m.group(1)) - 1] = (m.group(2), float(v))

    def _kulce(self, cevher: str) -> float:
        return float(self.g.get(f"total{cevher.capitalize()}Bars", 0) or 0)

    def _mucevher(self, ad: str) -> float:
        return float(self.g.get("total" + ad[:1].upper() + ad[1:], 0) or 0)

    def _stat(self, i: int, ek_seviye: int = 0) -> float:
        a = self.a
        sure = max(0.05, a["pickaxeTime"][i] - ek_seviye * a["pickaxeTimeDecrease"])
        hasar = a["pickaxeDamage"][i] + ek_seviye * a["pickaxeDamageIncreaxe"]
        kritik = (a["pickaxeCritChance"][i] + ek_seviye * a["pickaxeCritChanceIncrease"]) / 100
        kh = a["pickaxeCritDamage"][i] + ek_seviye * a["pickaxeCritDamageIncrease"]
        cember = a["pickaxeCircleSize"][i] + ek_seviye * a["pickaxeCircleSizeIncrease"]
        guc = hasar / sure * (1 + kritik * (kh - 1)) * cember ** 2
        return guc * self.o.get("kazma_bonus", {}).get(str(i + 1), 1.0)

    def _atlanabilir_seviye(self, i: int) -> int:
        """Mücevher bütçesiyle bu kazma kaç seviye atlayabilir (fiyat her seviyede ×1.36)."""
        if i not in self.seviye_fiyat:
            return 0
        gem, fiyat = self.seviye_fiyat[i]
        butce = self._mucevher(gem) * self.o.get("mucevher_harcama_orani", 0.8)
        n = 0
        while fiyat <= butce and n < 200:
            butce -= fiyat
            fiyat *= ARTIS
            n += 1
        return n

    # ---------- işlemler ----------
    def _yap(self) -> list:
        yapilan = []
        oran = self.o.get("kulce_harcama_orani", 1.0)
        for i in range(self.adet):
            if self.a["pickaxeCrafted"][i]:
                continue
            fiyat = self.yapim.get(i)
            if not fiyat:
                break
            if not all(self._kulce(c) * oran >= f for c, f in fiyat.items()):
                break   # sıradakini yapamıyorsak sonrakilere bakma (sırayla açılıyor)
            kopru.cagir("TheAnvil", "SelectPickaxe", i)
            kopru.cagir("TheAnvil", "CraftButton")
            time.sleep(2.5)   # yapım animasyonu
            self._oku()
            if self.a["pickaxeCrafted"][i]:
                print(f"[örs] Yeni kazma yapıldı: #{i + 1}  ({', '.join(f'{f:.0f} {c}' for c, f in fiyat.items())})")
                yapilan.append(i)
                break   # her yapım planlayıcıda ayrı karar
            else:
                print(f"[örs] Kazma #{i + 1} yapılamadı.")
                break
        return yapilan

    def _en_iyi_kazma(self) -> int:
        adaylar = [i for i in range(self.adet) if self.a["pickaxeCrafted"][i]]
        return max(adaylar, key=lambda i: self._stat(i, self._atlanabilir_seviye(i)))

    def _kusan(self, i: int):
        if self.a["pickaxeNumberEquipped"] == i:
            return
        kopru.cagir("TheAnvil", "SelectPickaxe", i)
        kopru.cagir("TheAnvil", "EquipPickaxe")
        time.sleep(0.3)
        self._oku()
        if self.a["pickaxeNumberEquipped"] == i:
            print(f"[örs] Kuşanıldı: kazma #{i + 1} (seviye {self.a['pickaxeLevel'][i]})")

    def _seviye_atlat(self) -> int:
        i = self.a["pickaxeNumberEquipped"]
        hedef = self._atlanabilir_seviye(i)
        sayi = 0
        for _ in range(hedef):
            once = self.a["pickaxeLevel"][i]
            kopru.cagir("TheAnvil", "LevelUpPickaxe")
            time.sleep(0.15)
            self._oku()
            if self.a["pickaxeLevel"][i] <= once:
                break
            sayi += 1
        if sayi:
            gem, fiyat = self.seviye_fiyat[i]
            print(f"[örs] Kazma #{i + 1} {sayi} seviye atladı -> seviye {self.a['pickaxeLevel'][i]} "
                  f"(sıradaki: {fiyat:.0f} {gem})")
        return sayi

    # ---------- planlayıcı arayüzü (hedef bazlı: sekme sadece gerekince açılır) ----------
    def durum_oku(self, cuzdan: dict | None = None):
        """Örs verisi önbellekte yoksa okur; cüzdan dışarıdan (planlayıcıdan) verilebilir."""
        if not hasattr(self, "a"):
            self._oku()
        if cuzdan is not None:
            self.g = cuzdan["_ham"]

    def _guc_potansiyel(self, i: int) -> float:
        return self._stat(i, self._atlanabilir_seviye(i))

    def adaylar(self) -> list:
        out = []
        yapilmis = [i for i in range(self.adet) if self.a["pickaxeCrafted"][i]]
        en_iyi = max(yapilmis, key=self._guc_potansiyel) if yapilmis else None
        en_iyi_guc = self._guc_potansiyel(en_iyi) if en_iyi is not None else 1e-9
        # 1) Sıradaki kazmayı yap
        sira = next((i for i in range(self.adet) if not self.a["pickaxeCrafted"][i]), None)
        if sira is not None and self.yapim.get(sira):
            # yeni kazmanın potansiyeli: seviye 1 statı + mücevher bütçesiyle atlayabileceği seviye
            oran = self._guc_potansiyel(sira) / en_iyi_guc
            w = self.o.get("yapim_agirlik", 70)
            deger = max(20, min(150, w * oran))
            out.append({"modul": "ors", "tur": "yap", "i": sira, "maliyet": dict(self.yapim[sira]),
                        "deger": deger, "aciklama": f"kazma #{sira + 1} yap (güç oranı {oran:.2f})"})
        # 2) En iyi kazmayı kuşan (bedava)
        if en_iyi is not None and en_iyi != self.a["pickaxeNumberEquipped"]:
            out.append({"modul": "ors", "tur": "kusan", "i": en_iyi, "maliyet": {}, "deger": 1000,
                        "aciklama": f"kazma #{en_iyi + 1} kuşan"})
        # 3) Kuşanılı kazmanın sıradaki seviyesi (mücevherle)
        i = self.a["pickaxeNumberEquipped"]
        if i in self.seviye_fiyat:
            gem, fiyat = self.seviye_fiyat[i]
            butce_orani = self.o.get("mucevher_harcama_orani", 0.8)
            out.append({"modul": "ors", "tur": "seviye", "i": i, "maliyet": {gem: fiyat / butce_orani},
                        "gercek_maliyet": {gem: fiyat}, "deger": self.o.get("seviye_agirlik", 60),
                        "aciklama": f"kazma #{i + 1} seviye {self.a['pickaxeLevel'][i] + 1}"})
        return out

    def uygula(self, aday: dict) -> bool:
        """Örs sekmesi açıkken çağrılır."""
        i = aday["i"]
        if aday["tur"] == "yap":
            return i in self._yap()
        if aday["tur"] == "kusan":
            self._kusan(i)
            return self.a["pickaxeNumberEquipped"] == i
        if aday["tur"] == "seviye":
            once = self.a["pickaxeLevel"][i]
            kopru.cagir("TheAnvil", "LevelUpPickaxe")
            time.sleep(0.1)
            self._oku()
            if self.a["pickaxeLevel"][i] > once:
                gem, fiyat = self.seviye_fiyat[i]
                print(f"[örs] Kazma #{i + 1} -> seviye {self.a['pickaxeLevel'][i]} (sıradaki: {fiyat:.0f} {gem})")
                return True
            return False
        return False

    # ---------- paylaşılan güçlendirmeler (SharedBuffs kartı) ----------
    def _bonus_metinleri(self) -> dict:
        """Kazma bonus açıklamaları (önbellek: kesif/kazma_bonuslari.json; eksikse oyundan okunur)."""
        dosya = _Path(__file__).resolve().parent.parent / "kesif" / "kazma_bonuslari.json"
        try:
            veri = _json.loads(dosya.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            veri = {}
        eksik = [i for i in range(self.adet) if self.a["pickaxeCrafted"][i]
                 and "?" in str((veri.get(str(i + 1)) or {}).get("bonus", "?"))]
        if eksik:
            esk = self.a["pickaxeNumberSelected"]
            for i in eksik:
                kopru.cagir("TheAnvil", "SelectPickaxe", i)
                time.sleep(0.1)
                l = kopru.alanlar("LocalizationScript")
                b = l.get("pickaxeBuffText1")
                veri[str(i + 1)] = {"ad": l.get(f"pickaxe{i + 1}Name"), "bonus": b.get("metin") if isinstance(b, dict) else b}
            kopru.cagir("TheAnvil", "SelectPickaxe", esk)
            dosya.parent.mkdir(exist_ok=True)
            dosya.write_text(_json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
        return veri

    def paylasilan_plani(self):
        """(istenen küme, mevcut küme, kapasite) — kapasite 0 ise kart seçilmemiş demektir."""
        p = self.o.get("paylasilan", {})
        if not p.get("aktif", True):
            return None
        kapasite = int(kopru.alanlar("Worlds").get("totalSharedBuffs") or 0)
        if kapasite <= 0:
            return None
        esit = self.a["pickaxeNumberEquipped"]
        w = p.get("agirliklar", {})
        adaylar = [i for i in range(self.adet) if self.a["pickaxeCrafted"][i] and i != esit
                   and w.get(str(i + 1), p.get("varsayilan", 40)) > 0]
        adaylar.sort(key=lambda i: -w.get(str(i + 1), p.get("varsayilan", 40)))
        istenen = set(adaylar[:kapasite])
        mevcut = {i for i, v in enumerate(self.a["sharedBuffsEquipped"]) if v}
        return istenen, mevcut, kapasite

    def paylasilan_gerekli_mi(self) -> bool:
        plan = self.paylasilan_plani()
        return bool(plan) and plan[0] != plan[1]

    def paylasilan_ayarla(self) -> bool:
        plan = self.paylasilan_plani()
        if not plan or plan[0] == plan[1]:
            return False
        istenen, mevcut, kapasite = plan
        esk = self.a["pickaxeNumberSelected"]
        for i in sorted(mevcut - istenen) + sorted(istenen - mevcut):   # önce çıkar, sonra ekle
            kopru.cagir("TheAnvil", "SelectPickaxe", i)
            time.sleep(0.1)
            kopru.cagir("TheAnvil", "SharedBuffsEquipped")
            time.sleep(0.15)
        kopru.cagir("TheAnvil", "SelectPickaxe", esk)
        self._oku()
        yeni = {i for i, v in enumerate(self.a["sharedBuffsEquipped"]) if v}
        metin = self._bonus_metinleri()
        w = self.o.get("paylasilan", {}).get("agirliklar", {})
        from .kayit import kayit
        kayit.olay("karar", "Paylaşılan güçlendirmeler: " + ", ".join(f"#{i + 1}" for i in sorted(yeni)), neden={
            "kural": f"kuşanılı kazma (#{self.a['pickaxeNumberEquipped'] + 1}) hariç, yapılmış kazmalar arasında ağırlığı en yüksek {kapasite} bonus",
            "seçilen": [f"#{i + 1} {(metin.get(str(i + 1)) or {}).get('bonus', '')} (ağırlık {w.get(str(i + 1), 40)})" for i in sorted(yeni)],
            "çıkarılan": [f"#{i + 1} {(metin.get(str(i + 1)) or {}).get('bonus', '')}" for i in sorted(mevcut - yeni)]})
        print(f"[örs] Paylaşılan güçlendirmeler: {sorted(i + 1 for i in mevcut)} -> {sorted(i + 1 for i in yeni)}")
        return yeni == istenen

    def calis(self):
        if not self.o.get("aktif", True):
            return
        try:
            kopru.bas("TheAnvilText_Tab")
            time.sleep(0.8)
        except kopru.KopruHatasi:
            pass
        self._oku()
        self._yap()
        self._kusan(self._en_iyi_kazma())
        self._seviye_atlat()

    def rapor(self) -> list:
        self._oku()
        out = []
        for i in range(self.adet):
            if not self.a["pickaxeCrafted"][i]:
                continue
            n = self._atlanabilir_seviye(i)
            out.append({"kazma": i + 1, "seviye": self.a["pickaxeLevel"][i], "guc": round(self._stat(i), 2),
                        "atlanabilir": n, "potansiyel": round(self._stat(i, n), 2),
                        "kusanili": self.a["pickaxeNumberEquipped"] == i})
        sira = next((i for i in range(self.adet) if not self.a["pickaxeCrafted"][i]), None)
        if sira is not None:
            out.append({"siradaki_yapim": sira + 1, "fiyat": self.yapim.get(sira)})
        return out
