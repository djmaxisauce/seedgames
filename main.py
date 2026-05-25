"""
main.py — Entry point del seeder de juegos.

Uso:
    python main.py entrada.txt salida.csv [id_inicial] [device_type] [region]

Ejemplo:
    python main.py mis_juegos.txt salida.csv 10 CARTRIDGE USA
"""

import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from consoles import interpretar_consola
from images import obtener_urls
from wiki import buscar_metadata
from csv_writer import escribir_csv

# ── logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ── parseo de la entrada ──────────────────────────────────────────────────────

def _parsear_linea(linea: str) -> tuple[str, str, str, str] | None:
    """
    Parsea una línea del archivo de entrada.
    Formato esperado: nombre,consola[,condicion][,autenticidad]
    Devuelve None si la línea está vacía o es inválida.
    """
    linea = linea.strip()
    if not linea or "," not in linea:
        return None

    def _campo(partes: list, idx: int, default: str) -> str:
        """
        Devuelve el valor del campo, el default si está ausente o vacío,
        o "" si el usuario escribió explícitamente NULL (→ celda vacía en Supabase).
        """
        if idx >= len(partes):
            return default
        val = partes[idx].strip()
        if not val:
            return default
        if val.upper() == "NULL":
            return ""       # celda vacía → NULL en Supabase
        return val.upper()

    partes       = [p.strip() for p in linea.split(",")]
    nombre       = partes[0]
    consola      = partes[1] if len(partes) > 1 else ""
    condicion    = _campo(partes, 2, "GOOD")
    autenticidad = _campo(partes, 3, "ORIGINAL")

    if not nombre or not consola:
        return None

    return nombre, consola, condicion, autenticidad


def _leer_tareas(archivo_txt: Path) -> list[tuple[str, str, str, str]]:
    tareas = []
    with archivo_txt.open(encoding='utf-8') as f:
        for n, linea in enumerate(f, 1):
            parsed = _parsear_linea(linea)
            if parsed is None and linea.strip():
                logger.warning("Línea %d ignorada (formato inválido): %r", n, linea.strip())
            elif parsed:
                tareas.append(parsed)
    return tareas


# ── procesamiento de un juego ─────────────────────────────────────────────────

def _procesar_juego(datos: tuple[str, str, str, str]) -> dict:
    nombre_original, consola_str, condicion, autenticidad = datos
    console_id, carpeta_retroarch = interpretar_consola(consola_str)

    titulo_oficial, dev, anio, cats_json = buscar_metadata(nombre_original)

    url_cover, url_gameplay, hubo_img = obtener_urls(titulo_oficial, carpeta_retroarch)

    # Si el título corregido no tiene imágenes, intentamos con el nombre original
    if not hubo_img and titulo_oficial != nombre_original:
        url_cover, url_gameplay, hubo_img = obtener_urls(nombre_original, carpeta_retroarch)

    return {
        "hubo_img":        hubo_img,
        "nombre_original": nombre_original,
        "title":           titulo_oficial,
        "dev":             dev,
        "anio":            anio,
        "cats_json":       cats_json,
        "console_id":      console_id,
        "condicion":       condicion,
        "autenticidad":    autenticidad,
        "url_cover":       url_cover,
        "url_gameplay":    url_gameplay,
    }


# ── orquestación principal ────────────────────────────────────────────────────

def procesar_lote(
    archivo_entrada: str | Path,
    archivo_salida:  str | Path,
    id_inicial:  int  = 10,
    device_type: str  = "CARTRIDGE",
    region:      str  = "USA",
    max_workers: int  = 8,
) -> None:
    archivo_entrada = Path(archivo_entrada)

    if not archivo_entrada.exists():
        logger.error("No se encuentra el archivo de entrada '%s'.", archivo_entrada)
        sys.exit(1)

    tareas = _leer_tareas(archivo_entrada)
    if not tareas:
        logger.warning("El archivo '%s' no contiene líneas válidas.", archivo_entrada)
        return

    print(f"\n📡 Procesando {len(tareas)} juego(s) en paralelo...\n")
    resultados: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {executor.submit(_procesar_juego, t): t for t in tareas}

        for futuro in as_completed(futuros):
            tarea = futuros[futuro]
            try:
                res = futuro.result()
                resultados.append(res)
                icono = "✅" if res["hubo_img"] else "⚠️ "
                print(
                    f" {icono} {res['title'][:28].ljust(28)} "
                    f"| Cat: {res['cats_json']:20} "
                    f"| Dev: {(res['dev'] or 'NULL')[:18].ljust(18)} "
                    f"| Año: {res['anio'] or 'NULL'}"
                )
            except Exception as exc:
                logger.error("Error procesando %r: %s", tarea[0], exc)

    escribir_csv(resultados, archivo_salida, id_inicial, device_type, region)

    total = len(resultados)
    con_img = sum(1 for r in resultados if r["hubo_img"])
    print(f"\n{'='*54}")
    print(f"🏁  Proceso completado")
    print(f"   Juegos procesados : {total}")
    print(f"   Con imágenes      : {con_img}/{total}")
    print(f"   CSV generado      : {archivo_salida}")
    print(f"{'='*54}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    procesar_lote(
        archivo_entrada = sys.argv[1],
        archivo_salida  = sys.argv[2],
        id_inicial      = int(sys.argv[3])   if len(sys.argv) > 3 else 10,
        device_type     = sys.argv[4]        if len(sys.argv) > 4 else "CARTRIDGE",
        region          = sys.argv[5]        if len(sys.argv) > 5 else "USA",
    )