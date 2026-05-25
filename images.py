"""
images.py — Búsqueda de URLs de imágenes en los thumbnails de libretro/RetroArch.

Estrategia:
  1. Pide la lista real de archivos al API de GitHub para la consola+subcarpeta.
     El resultado se cachea por (consola, subcarpeta) para no repetir llamadas.
     Los fallos NO se cachean: si GitHub da rate-limit, se reintenta por juego.
  2. Matchea por similitud contra esa lista.
  3. Si la API de GitHub no está disponible, cae al método HEAD clásico por regiones.
"""

import logging
import urllib.parse
from difflib import SequenceMatcher

import requests

logger = logging.getLogger(__name__)

_RETRO_HEADERS  = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
_GITHUB_HEADERS = {
    'User-Agent': 'GamesSeederBot/1.0',
    'Accept': 'application/vnd.github+json',
}
_RAW_BASE = "https://raw.githubusercontent.com/libretro/libretro-thumbnails/master"
_API_BASE = "https://api.github.com/repos/libretro/libretro-thumbnails/contents"

_REGIONES = ["(USA)", "(USA, Europe)", "(World)", "(Europe)", "(Japan)", "", "(Europe) (Alt 1)"]
_SIMILITUD_MINIMA = 0.60

# Caché manual: solo guarda éxitos (listas reales), nunca None
_cache_archivos: dict[tuple[str, str], list[str]] = {}


# ── normalización ─────────────────────────────────────────────────────────────

def _limpiar_nombre(nombre: str) -> str:
    """Convierte ':' en ' -' y colapsa espacios. Formato RetroArch."""
    return " ".join(nombre.replace(":", " -").split())


def _normalizar(nombre: str) -> str:
    """Para comparación: sin extensión, sin región, sin artículo, sin puntuación."""
    n = nombre.lower()
    if n.endswith(".png"):
        n = n[:-4]
    for region in ("(usa, europe)", "(usa)", "(world)", "(europe)", "(japan)", "(europe) (alt 1)"):
        if n.endswith(region):
            n = n[: -len(region)].strip()
            break
    for art in ("the ", "a ", "an "):
        if n.startswith(art):
            n = n[len(art):]
            break
    for ch in (":", "-", "_", ".", ",", "!", "?", "'", '"'):
        n = n.replace(ch, " ")
    return " ".join(n.split())


def _similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# ── GitHub API ────────────────────────────────────────────────────────────────

def _listar_archivos_github(consola: str, subcarpeta: str) -> list[str] | None:
    """
    Devuelve la lista de archivos del repo para consola+subcarpeta.
    Cachea solo éxitos. Retorna None si falla.
    """
    clave = (consola, subcarpeta)
    if clave in _cache_archivos:
        return _cache_archivos[clave]

    consola_enc = urllib.parse.quote(consola, safe='')
    url = f"{_API_BASE}/{consola_enc}/{subcarpeta}"

    try:
        res = requests.get(url, headers=_GITHUB_HEADERS, timeout=8)
        if res.status_code in (403, 429):
            logger.debug("GitHub rate-limit para %s/%s", consola, subcarpeta)
            return None
        if res.status_code == 404:
            logger.debug("Carpeta GitHub no encontrada: %s/%s", consola, subcarpeta)
            return None
        res.raise_for_status()
        archivos = [item["name"] for item in res.json() if item.get("type") == "file"]
        _cache_archivos[clave] = archivos
        return archivos
    except requests.Timeout:
        logger.debug("Timeout GitHub API %s/%s", consola, subcarpeta)
    except requests.RequestException as exc:
        logger.debug("Error GitHub API: %s", exc)
    except Exception as exc:
        logger.debug("Error inesperado GitHub API: %s", exc)
    return None


# ── búsqueda por similitud ────────────────────────────────────────────────────

def _match_por_similitud(
    nombre_juego: str, archivos: list[str], consola: str, subcarpeta: str
) -> tuple[str, bool]:
    nombre_norm = _normalizar(nombre_juego)
    mejor_score = 0.0
    mejor_archivo = None

    for archivo in archivos:
        score = _similitud(nombre_norm, _normalizar(archivo))
        if score > mejor_score:
            mejor_score = score
            mejor_archivo = archivo

    if mejor_archivo and mejor_score >= _SIMILITUD_MINIMA:
        logger.debug("Match '%s' → '%s' (%.2f)", nombre_juego, mejor_archivo, mejor_score)
        consola_enc  = urllib.parse.quote(consola, safe='')
        archivo_enc  = urllib.parse.quote(mejor_archivo)
        return f"{_RAW_BASE}/{consola_enc}/{subcarpeta}/{archivo_enc}", True

    logger.debug("Sin match similitud para '%s' (mejor score=%.2f)", nombre_juego, mejor_score)
    return "", False


# ── fallback HEAD por regiones ────────────────────────────────────────────────

def _fallback_head(nombre_juego: str, consola: str, subcarpeta: str) -> tuple[str, bool]:
    """Prueba URLs por región con HEAD. Método original, siempre disponible."""
    nombre_base = _limpiar_nombre(nombre_juego)
    consola_enc = urllib.parse.quote(consola, safe='')

    for region in _REGIONES:
        nombre_final = f"{nombre_base} {region}".strip() if region else nombre_base
        url = f"{_RAW_BASE}/{consola_enc}/{subcarpeta}/{urllib.parse.quote(nombre_final)}.png"
        try:
            r = requests.head(url, headers=_RETRO_HEADERS, timeout=2)
            if r.status_code == 200:
                return url, True
        except requests.Timeout:
            logger.debug("Timeout HEAD %s", url)
        except requests.RequestException as exc:
            logger.debug("Error HEAD: %s", exc)

    # URL de último recurso sin verificar
    consola_enc = urllib.parse.quote(consola, safe='')
    url_fallback = f"{_RAW_BASE}/{consola_enc}/{subcarpeta}/{urllib.parse.quote(nombre_base + ' (USA)')}.png"
    return url_fallback, False


# ── búsqueda combinada ────────────────────────────────────────────────────────

def _buscar_en_subcarpeta(nombre_juego: str, consola: str, subcarpeta: str) -> tuple[str, bool]:
    # Intento 1: lista real de GitHub + similitud
    archivos = _listar_archivos_github(consola, subcarpeta)
    if archivos is not None:
        url, ok = _match_por_similitud(nombre_juego, archivos, consola, subcarpeta)
        if ok:
            return url, True
        # Lista obtenida pero sin match → el archivo realmente no existe
        consola_enc  = urllib.parse.quote(consola, safe='')
        nombre_base  = _limpiar_nombre(nombre_juego)
        return f"{_RAW_BASE}/{consola_enc}/{subcarpeta}/{urllib.parse.quote(nombre_base + ' (USA)')}.png", False

    # Intento 2: GitHub no disponible → HEAD clásico
    return _fallback_head(nombre_juego, consola, subcarpeta)


# ── API pública ───────────────────────────────────────────────────────────────

def obtener_urls(nombre_juego: str, carpeta_consola: str) -> tuple[str, str, bool]:
    """Retorna (url_cover, url_gameplay, al_menos_una_encontrada)."""
    url_cover,    cover_ok    = _buscar_en_subcarpeta(nombre_juego, carpeta_consola, "Named_Boxarts")
    url_gameplay, gameplay_ok = _buscar_en_subcarpeta(nombre_juego, carpeta_consola, "Named_Snaps")
    return url_cover, url_gameplay, (cover_ok or gameplay_ok)