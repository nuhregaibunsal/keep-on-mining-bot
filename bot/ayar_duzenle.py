"""ayarlar.toml'u yorumları ve düzeni BOZMADAN okuma/düzenleme.

yapi()  -> arayüz için: bölümler, anahtarlar, değerler, açıklamalar (satır içi # yorumlar ve üstteki yorum satırları)
yaz()   -> tek bir anahtarın değerini, sadece o satırı değiştirerek yazar; sonuç geçerli TOML değilse yazmaz.
"""
import json
import re
import tomllib
from pathlib import Path

DOSYA = Path(__file__).resolve().parent.parent / "ayarlar.toml"
_BASLIK = re.compile(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$")
_DIZI_BASLIK = re.compile(r"^\s*\[\[([^\[\]]+)\]\]")
_ANAHTAR = re.compile(r'^(\s*)("?)([A-Za-z0-9_\-]+)\2(\s*=\s*)(.*)$')


def _yorum_ayir(deger: str):
    """'3.0 # açıklama' -> ('3.0', 'açıklama'); tırnak içindeki # sayılmaz."""
    tirnak = None
    for i, ch in enumerate(deger):
        if ch in "\"'" and (i == 0 or deger[i - 1] != "\\"):
            tirnak = None if tirnak == ch else (ch if tirnak is None else tirnak)
        elif ch == "#" and tirnak is None:
            return deger[:i].rstrip(), deger[i + 1:].strip()
    return deger.rstrip(), ""


def _dengeli(metin: str) -> bool:
    acik = 0
    tirnak = None
    for ch in metin:
        if ch in "\"'":
            tirnak = None if tirnak == ch else (ch if tirnak is None else tirnak)
        elif tirnak is None:
            acik += ch == "["
            acik -= ch == "]"
    return acik <= 0


def oku_metin() -> str:
    return DOSYA.read_text(encoding="utf-8")


def yapi() -> dict:
    metin = oku_metin()
    veri = tomllib.loads(metin)
    satirlar = metin.splitlines()
    aciklama, bolum_aciklama = {}, {}
    bolum, onceki_yorum = None, []
    for s in satirlar:
        if _DIZI_BASLIK.match(s):
            bolum, onceki_yorum = None, []
            continue
        m = _BASLIK.match(s)
        if m:
            bolum = m.group(1).strip()
            bolum_aciklama[bolum] = " ".join(onceki_yorum)
            onceki_yorum = []
            continue
        st = s.strip()
        if st.startswith("#"):
            onceki_yorum.append(st.lstrip("# ").strip())
            continue
        m = _ANAHTAR.match(s)
        if m and bolum:
            _, yorum = _yorum_ayir(m.group(5))
            aciklama[f"{bolum}.{m.group(3)}"] = " ".join(onceki_yorum + ([yorum] if yorum else []))
        onceki_yorum = [] if st == "" or m else onceki_yorum

    bolumler = []

    def gez(yol, d):
        alanlar = []
        for k, v in d.items():
            if isinstance(v, dict):
                gez(f"{yol}.{k}" if yol else k, v)
            elif isinstance(v, list) and v and isinstance(v[0], dict):
                continue   # [[cevher]] gibi tablo dizileri: sadece ham düzenleyiciden
            else:
                alanlar.append({"anahtar": k, "deger": v, "tip": type(v).__name__,
                                "aciklama": aciklama.get(f"{yol}.{k}", "")})
        if yol and alanlar:
            bolumler.append({"bolum": yol, "aciklama": bolum_aciklama.get(yol, ""), "alanlar": alanlar})

    gez("", veri)
    return {"bolumler": bolumler}


def _toml_deger(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_deger(x) for x in v) + "]"
    raise ValueError(f"desteklenmeyen değer: {v!r}")


def yaz(bolum: str, anahtar: str, deger) -> dict:
    metin = oku_metin()
    satirlar = metin.split("\n")
    icinde = False
    for i, s in enumerate(satirlar):
        m = _BASLIK.match(s)
        if m or _DIZI_BASLIK.match(s):
            icinde = bool(m) and m.group(1).strip() == bolum
            continue
        if not icinde:
            continue
        m = _ANAHTAR.match(s)
        if not m or m.group(3) != anahtar:
            continue
        ham = m.group(5)
        eski_deger, yorum = _yorum_ayir(ham)
        bosluk_orj = ham[len(eski_deger):ham.find("#", len(eski_deger))] if yorum else " "
        son = i
        if eski_deger.startswith("[") and not _dengeli(eski_deger):   # çok satırlı dizi
            while son + 1 < len(satirlar) and not _dengeli("\n".join(satirlar[i:son + 1])):
                son += 1
            yorum = ""
        yeni = f"{m.group(1)}{m.group(2)}{anahtar}{m.group(2)}{m.group(4)}{_toml_deger(deger)}"
        if yorum:
            # değer uzunluğu değişse de yorum sütunu mümkün olduğunca aynı kalsın
            hedef_sutun = len(m.group(1) + m.group(2) + anahtar + m.group(2) + m.group(4)) + len(eski_deger) + len(bosluk_orj)
            yeni += " " * max(1, hedef_sutun - len(yeni)) + "# " + yorum
        aday = "\n".join(satirlar[:i] + [yeni] + satirlar[son + 1:])
        tomllib.loads(aday)  # geçersizse hata fırlatır, dosyaya yazılmaz
        DOSYA.write_text(aday, encoding="utf-8")
        return {"tamam": True}
    raise KeyError(f"[{bolum}] içinde '{anahtar}' bulunamadı")


def ham_yaz(metin: str) -> dict:
    tomllib.loads(metin)  # doğrula
    DOSYA.write_text(metin, encoding="utf-8")
    return {"tamam": True}


def derin_guncelle(hedef: dict, kaynak: dict):
    """Çalışan modüllerin tuttuğu alt sözlükler de güncellensin diye YERİNDE günceller."""
    for k, v in kaynak.items():
        if isinstance(v, dict) and isinstance(hedef.get(k), dict):
            derin_guncelle(hedef[k], v)
        else:
            hedef[k] = v
    for k in list(hedef):
        if k not in kaynak:
            del hedef[k]
