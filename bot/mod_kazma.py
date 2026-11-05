"""Mod destekli kazma: kayaların türünü ve konumunu doğrudan oyundan alır.

Öncelik = nadirlik. Oyunun kendi çıkma şansları (SkillTree: rubySpawnChance, goldChunkChance,
fullSilverRockChance ...) okunur ve puan = 1 / şans olarak hesaplanır. Böylece:
  en düşük şanslı mücevher > benzer nadirlikteki cevher > bir alt kademe mücevher/cevher > ... > sıradan kaya
Eser taşıyan kaya her zaman en öndedir.
"""
import time

import numpy as np

from . import kopru
from .engeller import EngelCozucu
from .kayit import kayit
from .pencere import OyunPenceresi


def _kucuk_ilk(s: str) -> str:
    return s[:1].lower() + s[1:]


class Nadirlik:
    """Oyundan okunan şanslarla kaya puanlama."""

    def __init__(self, ayar: dict):
        self.ayar = ayar
        self.sans: dict[str, float] = {}

    def yukle(self):
        try:
            alan = kopru.alanlar("SkillTree")
        except kopru.KopruHatasi as e:
            print(f"[mod] Şanslar okunamadı ({e}), sabit değerler kullanılacak.")
            return
        self.sans = {k: float(v) for k, v in alan.items()
                     if isinstance(v, (int, float)) and not isinstance(v, bool)
                     and (k.endswith("SpawnChance") or k.endswith("ChunkChance") or k.endswith("RockChance"))}

    def _sans_puani(self, anahtar: str) -> float:
        s = self.sans.get(anahtar)
        if not s or s <= 0:
            return self.ayar["mod_kazma"]["bilinmeyen_puan"]
        return 100.0 / s

    def kalemler(self, k: dict) -> list[tuple[str, float]]:
        """Kayadaki değerli şeyler: [(ad, puan), ...]"""
        p = self.ayar["mod_kazma"]
        ihtiyac = self.ayar.get("ihtiyac", {}).get("mod_hedef", "").lower()
        carpan = self.ayar.get("ihtiyac", {}).get("carpan", 1.0)
        out = []
        for b in k.get("bayrak", []):
            if b.startswith("did") and b.endswith("Spawn"):          # didRubySpawn -> mücevher
                ad = _kucuk_ilk(b[3:-5])
                puan = self._sans_puani(ad + "SpawnChance") * p["mucevher_carpani"]
            elif b.startswith("isFull"):                               # isFullSilver -> tam cevher kaya
                ad = _kucuk_ilk(b[6:])
                puan = self._sans_puani("full" + b[6:] + "RockChance") * p["cevher_carpani"]
            elif b.startswith("is") and b.endswith("Chunk") and b not in ("isRockBroken",):  # isGoldChunk
                ad = _kucuk_ilk(b[2:-5])
                puan = self._sans_puani(ad + "ChunkChance") * p["cevher_carpani"]
            else:
                continue
            if ad in ("", "gem"):   # isChunk / isFull / didGemSpawn gibi genel bayraklar
                continue
            if ihtiyac and ad.lower() == ihtiyac:
                puan *= carpan
            out.append((ad, puan))
        return out

    def puan(self, k: dict) -> float:
        bayrak = k.get("bayrak", [])
        if "isRockBroken" in bayrak:
            return 0.0
        p = self.ayar["mod_kazma"]
        toplam = p["siradan_kaya"] + sum(x[1] for x in self.kalemler(k))
        if k.get("eser"):
            toplam += p["eser"]
        if "isRainbwoRock" in bayrak:
            toplam += p["gokkusagi"]
        return toplam


class ModKazici:
    """Kazma döngüsü.

    Gruplama: kazma dairesi içindeki TÜM kayalara aynı anda vurur. Bu yüzden tek bir kayaya değil,
    daire içine giren kayaların toplam puanı en yüksek olan noktaya gidilir.
    Sanal imleç: daire eklenti tarafından konumlandırılır, gerçek fare serbest kalır.
    """

    def __init__(self, oyun: OyunPenceresi, ayar: dict, durum):
        self.oyun = oyun
        self.ayar = ayar
        self.p = ayar["mod_kazma"]
        self.durum = durum
        self.nadirlik = Nadirlik(ayar)
        self.nokta = None        # şu an daireyi tuttuğumuz nokta (ekran px)
        self.sanal = self.p.get("sanal_imlec", True)
        self._basili = False
        self.engel = EngelCozucu(ayar)
        self.plan = None   # planlayıcı (yetenek önbelleği + örs durumu) oturumlar boyunca korunur

    # --- gruplama ---
    def _en_iyi_nokta(self, kayalar, yaricap):
        pts = np.array([[k["x"], k["y"]] for k in kayalar], dtype=np.float32)
        puan = np.array([self.nadirlik.puan(k) for k in kayalar], dtype=np.float32)
        canli = puan > 0
        if not canli.any():
            return None, 0.0
        pts, puan = pts[canli], puan[canli]
        r = yaricap * self.p["cember_kullanim"]
        # adaylar: tüm kayalar + değerli kayaların yakın komşularıyla orta noktaları
        aday = [pts]
        degerli = np.where(puan > self.p["siradan_kaya"])[0]
        if len(degerli):
            dp = pts[degerli]
            fark = dp[:, None, :] - pts[None, :, :]
            mesafe = np.sqrt((fark ** 2).sum(-1))
            i, j = np.where((mesafe > 0) & (mesafe < 2 * r))
            if len(i):
                aday.append((dp[i] + pts[j]) / 2)
        aday = np.concatenate(aday)
        if self.nokta is not None:
            aday = np.vstack([aday, np.array(self.nokta, dtype=np.float32)[None]])
        d2 = ((aday[:, None, :] - pts[None, :, :]) ** 2).sum(-1)
        degerler = (puan[None, :] * (d2 <= r * r)).sum(1)
        en = int(degerler.argmax())
        en_deger = float(degerler[en])
        # Histerezis: mevcut nokta hâlâ iyiyse zıplama (vuruş ritmi bozulmasın)
        if self.nokta is not None:
            simdiki = float(degerler[-1])
            if simdiki >= en_deger * self.p["kalma_orani"] and simdiki > 0:
                return self.nokta, simdiki
        return (float(aday[en][0]), float(aday[en][1])), en_deger

    # --- daireyi taşıma ---
    def _git(self, x, y, ekran):
        if self.sanal:
            kopru.imlec(x, y)
        else:
            if not self.oyun.on_planda_mi():
                return
            self.oyun.fare_git(x / ekran[0], y / ekran[1])
            if not self._basili:
                self.oyun.fare_bas(); self._basili = True

    def _birak(self):
        if self.sanal:
            try:
                kopru.imleci_birak()
            except kopru.KopruHatasi:
                pass
        elif self._basili:
            self.oyun.fare_birak(); self._basili = False

    def calis(self):
        bekleme = self.p["tarama_araligi"]
        oturum_bitti_zamani = None
        oturumda = False
        harcandi = True   # bot madende başlarsa ilk tur harcama yok; menüde başlarsa da sorun değil
        try:
            while self.durum.calisiyor and not self.durum.bitti:
                d = kopru.durum()
                if not d.get("isInMiningSession") or not d.get("kayalar"):
                    if oturumda:
                        self._birak()
                        oturumda = False
                        self.nokta = None
                        print(f"[mod] Oturum bitti: {d.get('rocksMinedThisRound')} kaya kazıldı.")
                        try:
                            p = self._plan_al()
                            if p.dunya is not None:
                                p.dunya.kapasite_ogren(int(d.get("rocksMinedThisRound") or 0))
                        except (kopru.KopruHatasi, KeyError):
                            pass
                    oturum_bitti_zamani = oturum_bitti_zamani or time.time()
                    # Önce açılır pencereleri (eser bulundu vb.) kapat, sonra madene dön
                    self.engel.temizle()
                    if not harcandi and time.time() - oturum_bitti_zamani > 2.0:
                        self._oturum_istatistigi(bitti=True, kaya=int(d.get("rocksMinedThisRound") or 0))
                        self._oturum_arasi_yukselt()
                        harcandi = True
                    if self.p["otomatik_yeniden_baslat"] and harcandi and time.time() - oturum_bitti_zamani > 2.5:
                        if self._madene_git():
                            oturum_bitti_zamani = None
                        elif self.engel.takildi_mi():
                            self.engel.kurtar(self.oyun)
                    time.sleep(0.5)
                    continue
                if not oturumda:
                    self.nadirlik.yukle()   # her yeni madende güncel şansları oku
                    oturumda = True
                    print("[mod] Yeni maden oturumu, şanslar güncellendi.")
                    harcandi = False
                    self._oturum_istatistigi(bitti=False)
                self.engel.ilerledi()
                oturum_bitti_zamani = None
                c = d.get("cember") or {}
                yaricap = c.get("r") if c.get("r", -1) > 0 else 60 * d["ekran"][1] / 1080
                halolar = d.get("halolar") or []
                if halolar and self.p.get("halo_oncelik", True):
                    # Halo: çember üzerinde ~1.3 sn tutulunca emilir, oturum boyunca +0.25X cevher çarpanı
                    ref = self.nokta or (halolar[0]["x"], halolar[0]["y"])
                    h = min(halolar, key=lambda h: (h["x"] - ref[0]) ** 2 + (h["y"] - ref[1]) ** 2)
                    if not getattr(self, "_halo_yazildi", False):
                        print("[kazma] Halo görüldü, emiliyor.")
                        self._halo_yazildi = True
                    self.nokta = (h["x"], h["y"])
                    self._git(h["x"], h["y"], d["ekran"])
                    time.sleep(bekleme)
                    continue
                self._halo_yazildi = False
                nokta, _ = self._en_iyi_nokta(d["kayalar"], yaricap)
                if nokta:
                    self.nokta = nokta
                    self._git(nokta[0], nokta[1], d["ekran"])
                time.sleep(bekleme)
        finally:
            self._birak()

    def _oturum_istatistigi(self, bitti: bool, kaya: int = 0):
        """Oturum başı/sonu cüzdan farkından kazancı hesaplar; kazma önceliğini günlüğe yazar."""
        try:
            from .planlayici import cuzdan_oku
            c = cuzdan_oku()
            eser = int(kopru.alanlar("Artifacts").get("totalArtifactsFound") or 0)
            lv = kopru.alanlar("LevelMechanics")
            dunya = kopru.alanlar("Worlds").get("levelSelected")
        except (kopru.KopruHatasi, ValueError):
            return
        deney = getattr(self, "deney", None)
        if not bitti:
            kayit.oturum_basla(c, eser, dunya, lv.get("level"))
            if deney is not None:
                deney.oturum_basladi()
            ilk = sorted(((100 / v, k.replace("SpawnChance", "").replace("ChunkChance", " (benekli)")
                           .replace("RockChance", " (tam)").replace("full", ""))
                          for k, v in self.nadirlik.sans.items() if v and v > 0), reverse=True)[:8]
            kayit.olay("karar", f"Maden oturumu başladı (dünya {dunya})", neden={
                "kural": "puan = 100 / çıkma şansı; eser taşıyan kaya her zaman önce; daire içindeki kayaların puanları toplanır",
                "en öncelikli türler": [f"{ad}: {p:.0f}" for p, ad in ilk]})
        else:
            r = kayit.oturum_bitti(c, eser, kaya, float(lv.get("xpThisRound") or 0))
            if deney is not None:
                deney.oturum_bitti(r)
            if r:
                k = r["kazanc"]
                ozet = ", ".join(f"{v:,.0f} {n}" for n, v in sorted(k.items(), key=lambda x: -x[1])[:4])
                kayit.olay("oturum", f"{kaya} kaya, {r['eser']} eser, {r['xp']:,.0f} XP — {ozet}", neden=r)

    def _plan_al(self):
        if self.plan is None:
            from .dunyalar import Dunyalar
            from .madenler import Madenler
            from .ors import Ors
            from .pazar import Pazar
            from .cekirdek import Cekirdek
            from .planlayici import Planlayici
            from .yetenek import YetenekAgaci
            self.plan = Planlayici(self.ayar, YetenekAgaci(self.ayar), Ors(self.ayar), self.engel,
                                   Dunyalar(self.ayar) if self.ayar.get("dunyalar") else None,
                                   Madenler(self.ayar) if self.ayar.get("madenler", {}).get("aktif") else None,
                                   Pazar(self.ayar) if self.ayar.get("pazar") else None,
                                   Cekirdek(self.ayar) if self.ayar.get("cekirdek", {}).get("aktif", True) else None)
        return self.plan

    def _oturum_arasi_yukselt(self):
        """Süre bitince: planlayıcı ortak bütçeyle örs + yetenek ağacı + dünyalar kararlarını verir."""
        self._plan_al()
        try:
            self.plan.tur()
        except (kopru.KopruHatasi, KeyError, ValueError) as e:
            print(f"[plan] Hata: {e}")
        self.engel.temizle()
        self.engel.ilerledi()

    def _madene_git(self) -> bool:
        """Süre bitti ekranında / menüde 'MADENE GİT!' butonuna basar."""
        for metin in ("MADENE GİT!", "Oyna!"):
            try:
                r = kopru.bas(metin)
                if r.get("tamam"):
                    print(f"[mod] '{metin}' butonuna basıldı")
                    return True
            except kopru.KopruHatasi:
                pass
        return False
