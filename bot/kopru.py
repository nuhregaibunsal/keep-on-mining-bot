"""Oyunun içindeki KomKopru eklentisiyle konuşan istemci (127.0.0.1:8765)."""
import json
import urllib.parse
import urllib.request

ADRES = "http://127.0.0.1:8765"


class KopruHatasi(Exception):
    pass


def _al(yol: str, **params):
    q = []
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            q += [(k, str(x)) for x in v]
        elif v is not None:
            q.append((k, str(v)))
    url = f"{ADRES}/{yol}" + ("?" + urllib.parse.urlencode(q) if q else "")
    try:
        with urllib.request.urlopen(url, timeout=4) as r:
            veri = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        veri = json.loads(e.read().decode("utf-8"))
    except Exception as e:
        raise KopruHatasi(f"Köprüye ulaşılamadı ({e}). Oyun modlu açık mı?") from e
    if isinstance(veri, dict) and "hata" in veri:
        raise KopruHatasi(veri["hata"])
    return veri


def var_mi() -> bool:
    try:
        return _al("ping") == "ok"
    except KopruHatasi:
        return False


def durum() -> dict:
    return _al("durum")


def alanlar(sinif: str) -> dict:
    return _al("alanlar", sinif=sinif)["alanlar"]


def metotlar(sinif: str) -> list:
    return _al("metotlar", sinif=sinif)


def imlec(x: float, y: float):
    """Kazma dairesini ekranın bu noktasına koy (gerçek fare oynamaz)."""
    return _al("imlec", x=f"{x:.1f}", y=f"{y:.1f}")


def imleci_birak():
    """Daire tekrar gerçek fareyi takip etsin."""
    return _al("imlec", birak=1)


def butonlar() -> list:
    return _al("butonlar")


def bas(metin: str) -> dict:
    """Üzerinde bu yazı olan (veya bu adı taşıyan) aktif butona basar."""
    return _al("bas", metin=metin)


def cagir(sinif: str, metot: str, *args):
    return _al("cagir", sinif=sinif, metot=metot, a=list(args))
