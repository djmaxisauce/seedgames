"""
wiki.py — Búsqueda de metadata de juegos en Wikidata.
"""

import logging
import time
from difflib import SequenceMatcher

import requests

# Errores HTTP de Wikidata que vale la pena reintentar
_RETRY_STATUS = {429, 500, 502, 503, 504}
_RETRY_INTENTOS = 3
_RETRY_ESPERA   = 2   # segundos entre intentos

logger = logging.getLogger(__name__)

WIKI_HEADERS = {
    'User-Agent': 'GamesSeederBot/1.0 (maxi@example.com) Requests/2.31.0'
}

SPARQL_URL  = "https://query.wikidata.org/sparql"
SEARCH_URL  = "https://www.wikidata.org/w/api.php"

NOISE_WORDS_IN_DESC = ("película", "film", "canción", "álbum", "musica")

# ── similitud ─────────────────────────────────────────────────────────────────

def _similitud(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# ── detalles wikidata ──────────────────────────────────────────────────────────

def obtener_detalles_wikidata(wiki_id: str) -> tuple[str, str, str]:
    """
    Dado un Wikidata ID devuelve (desarrollador, año_minimo, cats_json).
    Retorna ('', '', '[]') si algo falla, nunca lanza excepción.
    """
    # P178 = desarrollador, P123 = publicador (fallback para juegos japoneses)
    # P577 = fecha de publicación, P136 = género
    # El FILTER de idioma acepta "en", "es" y "ja" para juegos japoneses;
    # luego en Python priorizamos en > es > ja
    query = f"""
    SELECT ?developerLabel ?publisherLabel ?date ?genreLabel WHERE {{
      OPTIONAL {{
        wd:{wiki_id} wdt:P178 ?developer.
        ?developer rdfs:label ?developerLabel.
        FILTER(LANG(?developerLabel) = "en" || LANG(?developerLabel) = "es" || LANG(?developerLabel) = "ja")
      }}
      OPTIONAL {{
        wd:{wiki_id} wdt:P123 ?publisher.
        ?publisher rdfs:label ?publisherLabel.
        FILTER(LANG(?publisherLabel) = "en" || LANG(?publisherLabel) = "es" || LANG(?publisherLabel) = "ja")
      }}
      OPTIONAL {{ wd:{wiki_id} wdt:P577 ?date. }}
      OPTIONAL {{
        wd:{wiki_id} wdt:P136 ?genre.
        ?genre rdfs:label ?genreLabel.
        FILTER(LANG(?genreLabel) = "en" || LANG(?genreLabel) = "es")
      }}
    }}
    """
    bindings = None
    for intento in range(1, _RETRY_INTENTOS + 1):
        try:
            res = requests.get(
                SPARQL_URL,
                params={'query': query, 'format': 'json'},
                headers=WIKI_HEADERS,
                timeout=6,
            )
            if res.status_code in _RETRY_STATUS:
                raise requests.HTTPError(response=res)
            res.raise_for_status()
            bindings = res.json().get("results", {}).get("bindings", [])
            break   # éxito
        except requests.Timeout:
            logger.debug("Timeout SPARQL %s (intento %d/%d)", wiki_id, intento, _RETRY_INTENTOS)
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response is not None else "?"
            logger.debug("HTTP %s SPARQL %s (intento %d/%d)", code, wiki_id, intento, _RETRY_INTENTOS)
        except requests.RequestException as exc:
            logger.debug("Error de red SPARQL %s: %s", wiki_id, exc)
        except Exception as exc:
            logger.error("Error inesperado SPARQL %s: %s", wiki_id, exc)
            return "", "", "[]"   # error no recuperable, no reintentamos

        if intento < _RETRY_INTENTOS:
            time.sleep(_RETRY_ESPERA)

    if bindings is None:
        logger.warning("SPARQL falló tras %d intentos para %s", _RETRY_INTENTOS, wiki_id)
        return "", "", "[]"

    # Recolectamos labels de desarrollador por idioma para priorizar en > es > ja
    dev_por_idioma: dict[str, str] = {}
    pub_por_idioma: dict[str, str] = {}
    generos: set[str] = set()
    anios: list[int] = []

    for fila in bindings:
        if "developerLabel" in fila:
            label = fila["developerLabel"]["value"]
            lang  = fila["developerLabel"].get("xml:lang", "")
            if lang not in dev_por_idioma:
                dev_por_idioma[lang] = label

        if "publisherLabel" in fila:
            label = fila["publisherLabel"]["value"]
            lang  = fila["publisherLabel"].get("xml:lang", "")
            if lang not in pub_por_idioma:
                pub_por_idioma[lang] = label

        if "date" in fila:
            raw = fila["date"]["value"].split("-")[0]
            if raw.isdigit():
                anio_int = int(raw)
                # Descartamos años imposibles para videojuegos
                if 1970 <= anio_int <= 2030:
                    anios.append(anio_int)

        if "genreLabel" in fila:
            generos.add(fila["genreLabel"]["value"])

    # Prioridad de idioma: en > es > ja > lo que haya
    def _mejor_label(por_idioma: dict[str, str]) -> str:
        for lang in ("en", "es", "ja"):
            if lang in por_idioma:
                return por_idioma[lang]
        return next(iter(por_idioma.values()), "")

    # Usamos desarrollador; si no hay, caemos al publicador
    desarrollador = _mejor_label(dev_por_idioma) or _mejor_label(pub_por_idioma)

    anio       = str(min(anios)) if anios else ""
    cats_json  = f'["{_castear_categoria(", ".join(generos))}"]' if generos else "[]"
    return desarrollador, anio, cats_json


# ── categorías ────────────────────────────────────────────────────────────────

_TAGS_DEPORTES = {
    "deporte", "sport", "carreras", "racing", "fútbol", "futbol", "soccer",
    "baloncesto", "basketball", "kart", "conducción", "conduccion", "driving",
    "snowboard", "snowboarding", "hockey", "nhl", "nba", "f1", "formula",
    "skate", "skating", "baseball", "béisbol", "beisbol",
}
_TAGS_COMBATE = {
    "wrestling", "lucha libre", "luchaLibre", "fighting", "pelea",
    "beat em up", "beatemup", "wwe", "wwf",
}
_TAGS_PLATAFORMAS = {"plataformas", "platformer", "platform"}
_TAGS_AVENTURA   = {"aventura", "adventure", "rol", "rpg", "role-playing", "accion-aventura", "action-adventure"}


def _castear_categoria(texto_generos_raw: str) -> str:
    """Mapea texto libre de géneros al ENUM de Prisma."""
    if not texto_generos_raw:
        return "ACTION"

    texto = texto_generos_raw.lower().strip()
    # Versión compacta (sin separadores) para matchear tags pegados
    compacto = texto.replace("-", "").replace(".", "").replace(" ", "")

    if any(t in texto or t in compacto for t in _TAGS_COMBATE):
        return "ACTION"
    if any(t in texto or t in compacto for t in _TAGS_DEPORTES):
        return "SPORTS"
    if any(t in texto or t in compacto for t in _TAGS_PLATAFORMAS):
        return "PLATFORMER"
    if any(t in texto or t in compacto for t in _TAGS_AVENTURA):
        return "ADVENTURE_RPG"
    return "ACTION"


# ── búsqueda inteligente ───────────────────────────────────────────────────────

def _variantes(nombre: str) -> list[str]:
    """Genera variantes de búsqueda a partir del nombre original."""
    variantes = [nombre]

    # Sin artículos iniciales comunes
    for articulo in ("The ", "A ", "An "):
        if nombre.startswith(articulo):
            variantes.append(nombre[len(articulo):])

    # Variantes de guión
    if "-" in nombre:
        sin_guion = nombre.replace("-", " ").replace("  ", " ").strip()
        variantes.append(sin_guion)
        primera_parte = nombre.split("-")[0].strip()
        if len(primera_parte) > 3:
            variantes.append(primera_parte)

    # Deduplica preservando orden
    seen: set[str] = set()
    result = []
    for v in variantes:
        if v not in seen:
            seen.add(v)
            result.append(v)
    return result


def buscar_metadata(nombre_juego: str) -> tuple[str, str, str, str]:
    """
    Busca metadata en Wikidata para un juego.

    Retorna: (titulo_oficial, desarrollador, año, cats_json)
    Nunca lanza excepción.
    """
    for intento, termino in enumerate(_variantes(nombre_juego)):
        params = {
            "action": "wbsearchentities",
            "format": "json",
            "language": "es",
            "type": "item",
            "search": termino,
        }
        try:
            res = requests.get(SEARCH_URL, params=params, headers=WIKI_HEADERS, timeout=4)
            res.raise_for_status()
            resultados = res.json().get("search", [])
        except requests.Timeout:
            logger.warning("Timeout buscando '%s'", termino)
            continue
        except requests.RequestException as exc:
            logger.warning("Error de red buscando '%s': %s", termino, exc)
            continue
        except Exception as exc:
            logger.error("Error inesperado buscando '%s': %s", termino, exc)
            continue

        if not resultados:
            continue

        # Elegir el candidato con mayor score de similitud
        mejor_match = None
        mejor_score = -1.0

        for cand in resultados[:5]:
            label = cand.get("label", "")
            desc  = cand.get("description", "").lower()
            score = _similitud(termino, label)

            # Penalizar resultados que claramente no son videojuegos
            if any(p in desc for p in NOISE_WORDS_IN_DESC):
                score -= 0.3

            if score > mejor_score:
                mejor_score = score
                mejor_match = cand

        # Para el intento inicial exigimos 0.35; para variantes secundarias, 0.30
        umbral = 0.35 if intento == 0 else 0.30

        if mejor_match and mejor_score >= umbral:
            wiki_id          = mejor_match["id"]
            titulo_corregido = mejor_match.get("label", nombre_juego)
            dev, anio, cats  = obtener_detalles_wikidata(wiki_id)

            # Búsqueda inicial: aceptamos incluso si no hay año
            if intento == 0:
                return titulo_corregido, dev, anio, cats

            # Búsquedas secundarias: solo si hay año (evita falsos positivos)
            if anio:
                return titulo_corregido, dev, anio, cats

    logger.info("Sin resultados en Wikidata para '%s'", nombre_juego)
    return nombre_juego, "", "", "[]"