"""Beklenmedik ekranlar (eser bulundu, level atladı, öğretici, bilgi pencereleri...) için engel çözücü.

Mantık:
  1. Ekrandaki tıklanabilir butonlara bakılır. Yazısı/adı 'kapatma listesi'nde olan varsa basılır.
  2. Bot belirli bir süre ilerleyemezse (takıldıysa) ekrandaki butonlar + ekran görüntüsü
     engeller/ klasörüne kaydedilir ve kapatmaya benzeyen butonlar denenir.
  Tanınmayan ekranlar kaydedildiği için sonradan listeye eklenebilir (ayarlar.toml -> [engeller]).
"""
import json
import time
from datetime import datetime
from pathlib import Path

from . import kopru

KOK = Path(__file__).resolve().parent.parent
KAYIT = KOK / "engeller"

# Bu kelimeler buton ADINDA geçerse "kapatma" butonu olabilir (son çare denemesi)
KAPATMA_BENZERI = ("close", "kapat", "exit", "ok_", "okbtn", "continue", "devam", "awesome", "great", "x_btn", "closebtn")


def _normal(s: str) -> str:
    import re
    return re.sub(r"<[^>]*>", "", s or "").strip().lower()


class EngelCozucu:
    def __init__(self, ayar: dict):
        e = ayar.get("engeller", {})
        self.kapat = [_normal(x) for x in e.get("kapatma_butonlari", [])]
        self.asla = [_normal(x) for x in e.get("asla_basma", [])]
        self.takilma_suresi = e.get("takilma_suresi", 20)
        self._son_ilerleme = time.time()
        self._son_kayit = 0.0

    def ilerledi(self):
        """Bot bir şey başardığında çağrılır (oturum başladı, satın aldı...)."""
        self._son_ilerleme = time.time()

    def _butonlar(self):
        try:
            return [b for b in kopru.butonlar() if b.get("tiklanabilir")]
        except kopru.KopruHatasi:
            return []

    def _yasak(self, b) -> bool:
        metin = _normal(b.get("metin", ""))
        return any(a and (a == metin or a == b["ad"].lower()) for a in self.asla)

    def temizle(self) -> int:
        """Bilinen açılır pencereleri kapatır. Kaç butona basıldığını döndürür."""
        basilan = 0
        for _ in range(5):  # üst üste birkaç pencere olabilir (örn. 2 eser)
            hedef = None
            for b in self._butonlar():
                metinler = [_normal(m) for m in b.get("metin", "").split("|")]
                if self._yasak(b):
                    continue
                if any(m in self.kapat for m in metinler if m) or b["ad"].lower() in self.kapat:
                    hedef = b
                    break
            if not hedef:
                break
            try:
                r = kopru.bas(hedef["ad"])
            except kopru.KopruHatasi:
                break
            if not r.get("tamam"):
                break
            print(f"[engel] Açılır pencere kapatıldı: '{_normal(hedef.get('metin')) or hedef['ad']}'")
            basilan += 1
            self.ilerledi()
            time.sleep(0.6)
        return basilan

    def takildi_mi(self) -> bool:
        return time.time() - self._son_ilerleme > self.takilma_suresi

    def kurtar(self, oyun=None):
        """Takılınca: durumu kaydet, kapatmaya benzeyen butonları dene."""
        if time.time() - self._son_kayit > 30:
            self._kaydet(oyun)
            self._son_kayit = time.time()
        if self.temizle():
            return True
        for b in self._butonlar():
            if self._yasak(b):
                continue
            if any(k in b["ad"].lower() for k in KAPATMA_BENZERI):
                try:
                    if kopru.bas(b["ad"]).get("tamam"):
                        print(f"[engel] Takılma: '{b['ad']}' butonu denendi.")
                        self.ilerledi()
                        return True
                except kopru.KopruHatasi:
                    pass
        return False

    def _kaydet(self, oyun):
        KAYIT.mkdir(exist_ok=True)
        zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
        try:
            veri = {"butonlar": kopru.butonlar(),
                    "durum": {k: v for k, v in kopru.durum().items() if k != "kayalar"}}
        except kopru.KopruHatasi as e:
            veri = {"hata": str(e)}
        (KAYIT / f"{zaman}.json").write_text(json.dumps(veri, ensure_ascii=False, indent=1), encoding="utf-8")
        if oyun is not None:
            try:
                import cv2
                cv2.imwrite(str(KAYIT / f"{zaman}.png"), oyun.goruntu())
            except Exception:
                pass
        print(f"[engel] Bot takıldı, ekran kaydedildi: engeller/{zaman}.json")
