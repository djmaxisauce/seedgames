import csv
import os
import sys
import urllib.parse
from datetime import datetime
from difflib import SequenceMatcher
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# 🌐 Configuración global de cabeceras de red para evitar bloqueos
WIKI_HEADERS = {
    'User-Agent': 'GamesSeederBot/1.0 (maxi@example.com) Requests/2.31.0'
}

def calcular_similitud(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def castear_categoria_wiki(texto_generos_raw):
    """Asigna los géneros del juego a los ENUMs admitidos por tu esquema de Prisma."""
    if not texto_generos_raw:
        return "ACTION"
        
    texto_min = texto_generos_raw.lower().strip()
    texto_limpio = texto_min.replace("-", "").replace(".", "").replace(" ", "")
    
    tags_deportes_carreras = [
        "deporte", "sport", "carreras", "racing", "fútbol", "soccer", "baloncesto", 
        "basketball", "kart", "conducción", "driving", "snowboard", "snowboarding",
        "hockey", "nhl", "nba", "f1", "formula", "skate", "skating", "baseball", "béisbol"
    ]
    tags_combate_wrestling = ["wrestling", "lucha libre", "fighting", "pelea", "beat em up", "wwe", "wwf"]

    if any(p in texto_min for p in tags_combate_wrestling):
        return "ACTION"
    if any(p in texto_min for p in tags_deportes_carreras) or any(p in texto_limpio for p in tags_deportes_carreras):
        return "SPORTS"
    if "plataformas" in texto_min or "platformer" in texto_min or "platform" in texto_min:
        return "PLATFORMER"
    if any(p in texto_min for p in ["aventura", "adventure", "rol", "rpg", "role-playing", "accion-aventura"]):
        return "ADVENTURE_RPG"
        
    return "ACTION"

def obtener_detalles_wikidata(wiki_id):
    """Trae TODAS las fechas de lanzamiento de Wikidata y se queda estrictamente con el menor año en Python."""
    url_sparql = "https://query.wikidata.org/sparql"
    
    # 🚀 Traemos todas las fechas (?date) sin agruparlas con MIN en la BD para que no haga desastres
    query = f"""
    SELECT ?developerLabel ?date ?genreLabel WHERE {{
      OPTIONAL {{ wd:{wiki_id} wdt:P178 ?developer. ?developer rdfs:label ?developerLabel. FILTER(LANG(?developerLabel) = "en" || LANG(?developerLabel) = "es") }}
      OPTIONAL {{ wd:{wiki_id} wdt:P577 ?date. }}
      OPTIONAL {{ wd:{wiki_id} wdt:P136 ?genre. ?genre rdfs:label ?genreLabel. FILTER(LANG(?genreLabel) = "en" || LANG(?genreLabel) = "es") }}
    }}
    """
    try:
        res = requests.get(url_sparql, params={'query': query, 'format': 'json'}, headers=WIKI_HEADERS, timeout=5)
        desarrollador = ""
        texto_generos = set()
        anios_encontrados = []
        
        if res.status_code == 200:
            bindings = res.json().get("results", {}).get("bindings", [])
            for fila in bindings:
                # 1. Capturar desarrollador
                if "developerLabel" in fila and not desarrollador:
                    desarrollador = fila["developerLabel"]["value"]
                
                # 2. Colectar todos los años posibles
                if "date" in fila:
                    raw_date = fila["date"]["value"]
                    if raw_date:
                        posible_anio = raw_date.split("-")[0]
                        if posible_anio.isdigit():
                            anios_encontrados.append(int(posible_anio))
                
                # 3. Colectar géneros
                if "genreLabel" in fila:
                    texto_generos.add(fila["genreLabel"]["value"])
                    
        # 🛡️ FILTRO RADICAL: Ordenamos los años de menor a mayor y nos quedamos con el más viejo
        if anios_encontrados:
            anio = str(min(anios_encontrados))
        else:
            anio = ""
            
        generos_str = ", ".join(texto_generos)
        categoria_enum = castear_categoria_wiki(generos_str)
        return desarrollador, anio, f'["{categoria_enum}"]'
    except:
        return "", "", "[]"

def buscar_metadata_wiki_inteligente(nombre_juego):
    """Busca metadata en Wikidata. Si la búsqueda directa falla, recién ahí prueba variantes."""
    url_search = "https://www.wikidata.org/w/api.php"
    
    # 🧠 Armamos la lista de intentos pero de forma controlada
    variantes_busqueda = [nombre_juego]
    if "-" in nombre_juego:
        variantes_busqueda.append(nombre_juego.replace("-", " ").replace("  ", " ").strip())
        primera_parte = nombre_juego.split("-")[0].strip()
        if len(primera_parte) > 3:
            variantes_busqueda.append(primera_parte)
        
    for i, termino in enumerate(variantes_busqueda):
        params_search = {
            "action": "wbsearchentities",
            "format": "json",
            "language": "es",
            "type": "item",
            "search": termino
        }
        try:
            res = requests.get(url_search, params=params_search, headers=WIKI_HEADERS, timeout=3).json()
            resultados = res.get("search", [])
            
            if resultados:
                mejor_match = None
                mejor_score = -1
                for cand in resultados[:4]:
                    label_cand = cand.get("label", "")
                    desc_cand = cand.get("description", "").lower()
                    
                    if any(p in desc_cand for p in ["película", "film", "canción", "álbum", "musica"]):
                        score = calcular_similitud(termino, label_cand) - 0.3
                    else:
                        score = calcular_similitud(termino, label_cand)
                        
                    if score > mejor_score:
                        mejor_score = score
                        mejor_match = cand
                
                score_minimo = 0.3 if i > 0 else 0.4
                if mejor_match and mejor_score >= score_minimo:
                    wiki_id = mejor_match["id"]
                    titulo_corregido = mejor_match.get("label", nombre_juego)
                    dev, anio, cats_json = obtener_detalles_wikidata(wiki_id)
                    
                    # 🛡️ Si es la búsqueda exacta inicial, nos la quedamos sí o sí, tenga o no año
                    if i == 0:
                        return titulo_corregido, dev, anio, cats_json
                    
                    # Para las búsquedas secundarias de auxilio (como Twisted Edge), exigimos que devuelva año
                    if i > 0 and anio:
                        return titulo_corregido, dev, anio, cats_json
        except:
            pass
            
    return nombre_juego, "", "", "[]"

def limpiar_nombre_retroarch(nombre_juego):
    nombre_limpio = nombre_juego.replace(":", " -")
    return " ".join(nombre_limpio.split())

def verificar_url_real(nombre_carpeta_consola, subcarpeta, nombre_juego):
    nombre_base = limpiar_nombre_retroarch(nombre_juego)
    headers_retro = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    regiones = ["(USA)", "(USA, Europe)", "(World)", "(Europe)", "(Japan)", "", "(Europe) (Alt 1)"]
    
    consola_safe = urllib.parse.quote(nombre_carpeta_consola.strip())
    
    for region in regiones:
        nombre_final = f"{nombre_base} {region}" if region else nombre_base
        nombre_final = nombre_final.replace("Usa", "USA").replace("Bros.", "Bros.")
        
        archivo_safe = urllib.parse.quote(nombre_final.strip())
        url_prospecto = f"https://raw.githubusercontent.com/libretro/libretro-thumbnails/master/{consola_safe}/{subcarpeta}/{archivo_safe}.png"
        
        try:
            check = requests.head(url_prospecto, headers=headers_retro, timeout=1.5)
            if check.status_code == 200:
                return url_prospecto, True
        except:
            pass
            
    archivo_defecto_safe = urllib.parse.quote(f"{nombre_base} (USA)")
    url_fallback = f"https://raw.githubusercontent.com/libretro/libretro-thumbnails/master/{consola_safe}/{subcarpeta}/{archivo_defecto_safe}.png"
    return url_fallback, False

def obtener_urls_retroarch(nombre_juego, nombre_carpeta_consola):
    url_cover, cover_ok = verificar_url_real(nombre_carpeta_consola, "Named_Boxarts", nombre_juego)
    url_gameplay, gameplay_ok = verificar_url_real(nombre_carpeta_consola, "Named_Snaps", nombre_juego)
    return url_cover, url_gameplay, (cover_ok or gameplay_ok)

def interpretar_consola(consola_input):
    c = consola_input.lower().strip().replace(" ", "")
    mapeo = {
        'n64': (1, "Nintendo - Nintendo 64"),
        'snes': (2, "Nintendo - Super Nintendo Entertainment System"),
        'famicom': (2, "Nintendo - Entertainment System"),
        'superfamicom': (4, "Nintendo - Super Nintendo Entertainment System"),
        'nes': (5, "Nintendo - Entertainment System")
    }
    return mapeo.get(c, (999, consola_input.strip()))

def procesar_un_juego(datos_linea, device_type, region):
    nombre_original, consola_str, condicion, autenticidad = datos_linea
    console_id, carpeta_retroarch = interpretar_consola(consola_str)
    
    titulo_oficial, dev, anio, cats_json = buscar_metadata_wiki_inteligente(nombre_original)
    
    url_cover, url_gameplay, hubo_img = obtener_urls_retroarch(titulo_oficial, carpeta_retroarch)
    
    if not hubo_img:
        url_cover, url_gameplay, hubo_img = obtener_urls_retroarch(nombre_original, carpeta_retroarch)
        
    return {
        "hubo_img": hubo_img, "nombre_original": nombre_original, "title": titulo_oficial,
        "dev": dev, "anio": anio, "cats_json": cats_json, "console_id": console_id,
        "condicion": condicion, "autenticidad": autenticidad, "url_cover": url_cover, "url_gameplay": url_gameplay
    }

def procesar_lote_desde_archivo(archivo_txt, archivo_csv, id_inicial, device_type, region):
    if not os.path.exists(archivo_txt):
        print(f"\n❌ ERROR: No se encuentra el archivo '{archivo_txt}'.")
        return

    tareas = []
    with open(archivo_txt, mode='r', encoding='utf-8') as txt_file:
        for linea in txt_file:
            linea = linea.strip()
            if not linea or "," not in linea:
                continue
            partes = [p.strip() for p in linea.split(",")]
            nombre = partes[0]
            consola = partes[1]
            cond = partes[2].upper() if len(partes) > 2 and partes[2] else "GOOD"
            aut = partes[3].upper() if len(partes) > 3 and partes[3] else "ORIGINAL"
            tareas.append((nombre, consola, cond, aut))

    print(f"\n📡 Conectando en paralelo a las APIs para {len(tareas)} juegos...\n")
    ahora_iso = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    resultados_finales = []

    with ThreadPoolExecutor(max_workers=8) as executor:
        futuros = {executor.submit(procesar_un_juego, tarea, device_type, region): tarea for tarea in tareas}
        
        for futuro in as_completed(futuros):
            try:
                res = futuro.result()
                resultados_finales.append(res)
                status = "✅" if res["hubo_img"] else "⚠️"
                print(f" {status} Procesado: {res['title'][:22].ljust(22)} | Cat: {res['cats_json']} | Dev: {res['dev'][:15] or 'NULL'} | Año: {res['anio'] or 'NULL'}")
            except Exception as e:
                print(f" ❌ Error en una línea: {e}")

    headers_csv = [
        "id", "title", "developer", "releaseYear", "isFavorite", "categories", 
        "consoleId", "deviceType", "region", "peripheralId", "authenticity", 
        "condition", "purchasePrice", "purchaseCurrency", "acquisitionDate", 
        "coverUrl", "gameplayPhotoUrl", "realDevicePhotoUrl", "createdAt", "updatedAt"
    ]
    
    try:
        with open(archivo_csv, mode='w', newline='', encoding='utf-8') as csv_file:
            writer = csv.writer(csv_file, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(headers_csv)
            
            id_actual = id_inicial
            for r in resultados_finales:
                writer.writerow([
                    id_actual, r["title"], r["dev"], r["anio"], "false", r["cats_json"], r["console_id"],
                    device_type.upper(), region.upper(), "", r["autenticidad"], r["condicion"],
                    "", "", "", r["url_cover"], r["url_gameplay"], "", ahora_iso, ahora_iso
                ])
                id_actual += 1
                
        print(f"\n==================================================")
        print(f"🏁 ¡PROCESO DE SUBIDA COMPLETADO CON METADATA!")
        print(f" 👍 Total de juegos inyectados en '{archivo_csv}': {len(resultados_finales)}")
        print(f"==================================================")
    except Exception as e:
        print(f"❌ Error al escribir el archivo CSV: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(1)
        
    ARCHIVO_ENTRADA_CLI = sys.argv[1]
    ARCHIVO_SALIDA_CLI = sys.argv[2]
    
    ID_INICIAL_LOTE = 16             
    DEVICE_TYPE_DEFAULT = "CARTRIDGE" 
    REGION_DEFAULT = "USA"           

    procesar_lote_desde_archivo(ARCHIVO_ENTRADA_CLI, ARCHIVO_SALIDA_CLI, ID_INICIAL_LOTE, DEVICE_TYPE_DEFAULT, REGION_DEFAULT)