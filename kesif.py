"""Oyunun canlı durumunu incelemek için yardımcı.

    python kesif.py durum                 -> kayalar, süre, level
    python kesif.py alanlar TheAnvil      -> sınıfın tüm değerleri  (kesif/TheAnvil.json'a da kaydeder)
    python kesif.py metotlar SkillTree    -> sınıfın fonksiyonları
"""
import json
import sys
from pathlib import Path

from bot import kopru

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    k = sys.argv[1]
    if k == "durum":
        veri = kopru.durum()
    elif k == "alanlar":
        veri = kopru.alanlar(sys.argv[2])
    elif k == "metotlar":
        veri = kopru.metotlar(sys.argv[2])
    else:
        print(__doc__); sys.exit(1)
    metin = json.dumps(veri, ensure_ascii=False, indent=1)
    klasor = Path(__file__).parent / "kesif"
    klasor.mkdir(exist_ok=True)
    ad = "_".join(sys.argv[1:]) + ".json"
    (klasor / ad).write_text(metin, encoding="utf-8")
    print(metin[:4000] + ("\n... (tamamı kesif/" + ad + ")" if len(metin) > 4000 else ""))
