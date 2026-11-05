"""Dünyalar ve yetenek kartları.

Kitaplar (LevelMechanics):
  totalTalentPoints  = mor kitap  -> yeni dünya açar (worldNPrice)
  totalMasteryPoints = kırmızı kitap (her 5 levelde) -> seçilmiş bir kartı 1 seviye yükseltir

Yaptıkları (planlayıcı turunda, SADECE hedefe ulaşıldıysa Dünyalar sekmesi açılır):
  1. Mor kitap sıradaki dünyanın fiyatına yetiyorsa dünyayı açar (PurchaseNewWorl).
  2. Açılınca gelen kart ekranında sunulan kartlardan ayarlardaki önceliğe göre en iyi 2'sini seçer.
  3. Kırmızı kitap varsa seçilmiş kartlardan  ağırlık / seviye  puanı en yüksek olanı yükseltir.
     (Oyunun yükseltme fonksiyonu kitabı kontrol etmiyor; bot kendisi kontrol eder.)
  4. Kazılacak en verimli dünyayı seçer:
       kazılabilir kaya = min(tahtadaki kaya × yenilenme, vuruş kapasitesi / kaya başına vuruş)
       verim = kazılabilir kaya × (cevher çarpanı ve XP çarpanı karışımı)
       vuruş kapasitesi her oturum sonunda gerçek sonuçtan öğrenilir.
     XP ağırlığı ayarlanabilir (level atlamak = daha çok kitap).
"""
import math
import time

from . import kopru
from .kayit import kayit


class Dunyalar:
    def __init__(self, ayar: dict):
        self.d = ayar.get("dunyalar", {})
        self.w = self.l = self.an = None

    def oku(self):
        self.w = kopru.alanlar("Worlds")
        self.l = kopru.alanlar("LevelMechanics")
        self.an = kopru.alanlar("TheAnvil")

    # ---------- hesaplar ----------
    def acik_dunyalar(self) -> list[int]:
        return [1] + [n for n in range(2, 13) if self.w.get(f"isWorld{n}Unlocked")]

    def siradaki_dunya(self):
        for n in range(2, 13):
            if not self.w.get(f"isWorld{n}Unlocked"):
                return n, int(self.w.get(f"world{n}Price") or 0)
        return None, None

    def _vurus(self, n: int) -> int:
        hasar = max(0.1, float(self.an.get("currentPickaxeDamage") or 1))
        return max(1, math.ceil(float(self.w.get(f"world{n}_rockHP") or 1) / hasar))

    def kapasite_ogren(self, kazilan_kaya: int):
        """Oturum sonunda çağrılır: bu oturumda kaç vuruş yapabildik? (kazılan kaya × kaya başına vuruş)"""
        if not self.w:
            self.oku()
        n = self.w.get("levelSelected") or 1
        yeni = kazilan_kaya * self._vurus(n)
        eski = getattr(self, "kapasite", None)
        self.kapasite = yeni if eski is None else 0.7 * eski + 0.3 * yeni   # yumuşatılmış ortalama

    def verim(self, n: int) -> float:
        """Bir oturumda beklenen değer: kazılabilecek kaya × (cevher/XP çarpanı)."""
        kaya = float(self.w.get(f"totalRocks_world{n}") or 1) * self.d.get("tahta_yenilenme", 2.0)
        kapasite = getattr(self, "kapasite", None) or float("inf")
        kazilabilir = min(kaya, kapasite / self._vurus(n))
        cevher = 1 + float(self.w.get(f"world{n}_oreMultiplier") or 0)
        xp = 1 + float(self.w.get(f"world{n}_xpMultiplier") or 0)
        xa = self.d.get("xp_agirlik", 0.3)
        return kazilabilir * (cevher * (1 - xa) + xp * xa)

    def en_iyi_dunya(self) -> int:
        return max(self.acik_dunyalar(), key=self.verim)

    def _kart_adi(self, i: int) -> str:
        return self.w["cards"][i]["ad"].split("_", 1)[-1]

    def _kart_agirlik(self, i: int) -> float:
        return self.d.get("kart_agirliklari", {}).get(self._kart_adi(i), self.d.get("varsayilan_kart", 50))

    # ---------- planlayıcı arayüzü ----------
    def yapilacaklar(self) -> list:
        """Hedefe ulaşılan işler (boşsa sekme hiç açılmaz)."""
        self.oku()
        isler = []
        n, fiyat = self.siradaki_dunya()
        mor = int(self.l.get("totalTalentPoints") or 0)
        if n and self.d.get("dunya_ac", True) and mor >= fiyat > 0:
            isler.append(("dunya_ac", n))
        if int(self.l.get("totalMasteryPoints") or 0) >= 1 and self.d.get("kart_yukselt", True):
            secili = [i for i, s in enumerate(self.w["cardsChosen"]) if s]
            if secili:
                en = max(secili, key=lambda i: self._kart_agirlik(i) / self.w["cardLevel"][i])
                isler.append(("kart_yukselt", en))
        if self.d.get("dunya_sec", True):
            hedef = self.en_iyi_dunya()
            if hedef != self.w.get("levelSelected"):
                isler.append(("dunya_sec", hedef))
        return isler

    def uygula(self, is_: tuple) -> bool:
        tur, n = is_
        if tur == "dunya_ac":
            mor_once = int(self.l.get("totalTalentPoints") or 0)
            kopru.cagir("Worlds", "PurchaseNewWorl", n)
            time.sleep(4)   # yeni dünya animasyonu + kart dağıtımı
            self.oku()
            if not self.w.get(f"isWorld{n}Unlocked"):
                print(f"[dünya] Dünya {n} açılamadı (mor kitap {mor_once}).")
                return False
            print(f"[dünya] Yeni dünya açıldı: {n}")
            self.kart_sec()
            return True
        if tur == "kart_yukselt":
            if int(self.l.get("totalMasteryPoints") or 0) < 1:
                return False
            once = self.w["cardLevel"][n]
            kopru.cagir("Worlds", "OpenUpgradeTalentCard", n)
            time.sleep(0.6)
            kopru.cagir("Worlds", "UpgradeTalentCard")
            time.sleep(1.5)
            try:
                kopru.cagir("Worlds", "CloseUpgradeCard")
            except kopru.KopruHatasi:
                pass
            self.oku()
            ok = self.w["cardLevel"][n] > once
            if ok:
                secili = [i for i, s in enumerate(self.w["cardsChosen"]) if s]
                kayit.olay("karar", f"Kart yükseltildi: {self._kart_adi(n)}", neden={
                    "adaylar (ağırlık/seviye)": {self._kart_adi(i): round(self._kart_agirlik(i) / max(1, self.w['cardLevel'][i] - (1 if i == n else 0)), 1) for i in secili},
                    "kural": "seçili kartlar arasında ağırlık / seviye en yüksek olan"})
            print(f"[dünya] Kart yükseltme {'tamam' if ok else 'olmadı'}: {self._kart_adi(n)} -> seviye {self.w['cardLevel'][n]}")
            return ok
        if tur == "dunya_sec":
            kopru.cagir("Worlds", "SelectLevel", n)
            time.sleep(0.8)
            self.oku()
            ok = self.w.get("levelSelected") == n
            if ok:
                kayit.olay("karar", f"Kazma dünyası {n} seçildi", neden={
                    "verimler": {d: round(self.verim(d), 1) for d in self.acik_dunyalar()},
                    "kapasite (vuruş/oturum)": round(getattr(self, "kapasite", 0) or 0),
                    "formul": "kazılabilir kaya × (cevher çarpanı·0.7 + XP çarpanı·0.3)"})
                print(f"[dünya] Kazma dünyası: {n} (verim {self.verim(n):.1f}, "
                      f"açık dünyalar: {', '.join(f'{d}={self.verim(d):.1f}' for d in self.acik_dunyalar())})")
            return ok
        return False

    def kart_sec(self, bekle: float = 15.0) -> bool:
        """Kart seçim ekranı açıkken sunulan kartlardan en iyi 2'sini seç ve onayla."""
        son = time.time() + bekle
        while time.time() < son:
            self.oku()
            sunulan = [i for i, c in enumerate(self.w["cards"]) if c.get("aktif") and not self.w["cardsChosen"][i]]
            if self.w.get("isInChooseCards") and len(sunulan) >= 2 and not self.w.get("isCardMoving"):
                break
            time.sleep(0.5)
        else:
            print("[dünya] Kart seçim ekranı gelmedi.")
            return False
        sirali = sorted(sunulan, key=self._kart_agirlik, reverse=True)
        secilen = sirali[:2]
        kayit.olay("karar", f"Kartlar seçildi: {', '.join(self._kart_adi(i) for i in secilen)}", neden={
            "sunulan": {self._kart_adi(i): self._kart_agirlik(i) for i in sunulan},
            "kural": "ayarlardaki kart ağırlığı en yüksek 2 kart"})
        print(f"[dünya] Sunulan kartlar: {[self._kart_adi(i) for i in sunulan]} -> seçilen: "
              f"{[self._kart_adi(i) for i in secilen]}")
        for i in secilen:
            kopru.cagir("Worlds", "SelectCard", i)
            time.sleep(0.8)
        kopru.cagir("Worlds", "ChooseCardsBTN")
        time.sleep(3)
        self.oku()
        return all(self.w["cardsChosen"][i] for i in secilen)
