"""
csv_writer.py — Escritura del CSV de salida con la metadata procesada.
"""

import csv
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_HEADERS = [
    "id", "title", "developer", "releaseYear", "isFavorite", "categories",
    "consoleId", "deviceType", "region", "peripheralId", "authenticity",
    "condition", "purchasePrice", "purchaseCurrency", "acquisitionDate",
    "coverUrl", "gameplayPhotoUrl", "realDevicePhotoUrl", "createdAt", "updatedAt",
]


def escribir_csv(
    resultados: list[dict],
    archivo_salida: str | Path,
    id_inicial: int,
    device_type: str,
    region: str,
) -> None:
    """
    Escribe *resultados* en *archivo_salida* como CSV.

    Lanza IOError si no puede crear el archivo.
    """
    ahora = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    archivo_salida = Path(archivo_salida)

    try:
        with archivo_salida.open(mode='w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(_HEADERS)

            for id_actual, r in enumerate(resultados, start=id_inicial):
                writer.writerow([
                    id_actual,
                    r["title"],
                    r["dev"],
                    r["anio"],
                    "false",
                    r["cats_json"],
                    r["console_id"],
                    device_type.upper(),
                    region.upper(),
                    "",                    # peripheralId
                    r["autenticidad"],
                    r["condicion"],
                    "",                    # purchasePrice
                    "",                    # purchaseCurrency
                    "",                    # acquisitionDate
                    r["url_cover"],
                    r["url_gameplay"],
                    "",                    # realDevicePhotoUrl
                    ahora,
                    ahora,
                ])

        logger.info("CSV escrito en '%s' con %d juegos.", archivo_salida, len(resultados))

    except OSError as exc:
        logger.error("No se pudo escribir '%s': %s", archivo_salida, exc)
        raise
