"""
consoles.py — Mapeo de alias de consola → (console_id, carpeta_RetroArch).

El usuario completará este archivo con todos los alias que necesite.
El mapeo es case-insensitive y tolera espacios extra.
"""

_MAPEO: dict[str, tuple[int, str]] = {
    # ── Nintendo 64 ────────────────────────────────────────────────────────────
    "n64":              (1, "Nintendo - Nintendo 64"),
    "nintendo64":       (1, "Nintendo - Nintendo 64"),
    "nintendo 64":      (1, "Nintendo - Nintendo 64"),

    # ── Super Nintendo ─────────────────────────────────────────────────────────
    "snes":             (2, "Nintendo - Super Nintendo Entertainment System"),
    "superfamicom":     (2, "Nintendo - Super Nintendo Entertainment System"),
    "super famicom":    (2, "Nintendo - Super Nintendo Entertainment System"),
    "super nintendo":   (2, "Nintendo - Super Nintendo Entertainment System"),

    # ── NES / Famicom ──────────────────────────────────────────────────────────
    "nes":              (5, "Nintendo - Nintendo Entertainment System"),
    "famicom":          (5, "Nintendo - Nintendo Entertainment System"),
    "nintendo":         (5, "Nintendo - Nintendo Entertainment System"),

    # ▸ Agrega más alias aquí siguiendo el mismo patrón:
    # "alias_lowercase": (console_id, "Carpeta RetroArch exacta"),
}


def interpretar_consola(consola_input: str) -> tuple[int, str]:
    """
    Devuelve (console_id, carpeta_RetroArch) para el alias dado.
    Si no se reconoce, devuelve (999, consola_input.strip()) y lo loguea.
    """
    import logging
    logger = logging.getLogger(__name__)

    clave = consola_input.lower().strip().replace(" ", "")

    # Primero buscamos la clave compacta (sin espacios)
    if clave in _MAPEO:
        return _MAPEO[clave]

    # Si no, buscamos con espacios normalizados
    clave_con_espacios = consola_input.lower().strip()
    if clave_con_espacios in _MAPEO:
        return _MAPEO[clave_con_espacios]

    logger.warning(
        "Consola no reconocida: '%s'. Usando id=999 y carpeta='%s'. "
        "Agregá el alias en consoles.py.",
        consola_input.strip(),
        consola_input.strip(),
    )
    return 999, consola_input.strip()
