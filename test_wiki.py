import requests
from datetime import datetime

def obtener_detalles_wikidata(wiki_id):
    """
    Usa el ID de Wikidata para traer Desarrollador, Año de lanzamiento,
    Géneros y la descripción corta mediante una consulta SPARQL limpia.
    """
    url_sparql = "https://query.wikidata.org/sparql"
    headers = {
        'User-Agent': 'GamesSeederBot/1.0 (maxi@example.com) Requests/2.31.0',
        'Accept': 'application/json'
    }
    
    # Query estructurada para traer las etiquetas reales en español (o inglés como fallback)
    query = f"""
    SELECT ?developerLabel ?releaseDate ?genreLabel WHERE {{
      OPTIONAL {{ wd:{wiki_id} wdt:P178 ?developer. }}
      OPTIONAL {{ wd:{wiki_id} wdt:P577 ?releaseDate. }}
      OPTIONAL {{ wd:{wiki_id} wdt:P136 ?genre. }}
      
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "[AUTO_LANGUAGE],es,en". }}
    }}
    LIMIT 5
    """
    
    try:
        res = requests.get(url_sparql, params={'query': query, 'format': 'json'}, headers=headers, timeout=8)
        if res.status_code != 200:
            return "", "", [], ""
            
        resultados = res.json().get("results", {}).get("bindings", [])
        
        desarrollador = ""
        anio = ""
        generos = set()
        
        for fila in resultados:
            # 1. Extraer Desarrollador
            if "developerLabel" in fila and not desarrollador:
                desarrollador = fila["developerLabel"]["value"]
                
            # 2. Extraer Año de Lanzamiento (Viene en formato ISO, ej: 1999-11-22T00:00:00Z)
            if "releaseDate" in fila and not anio:
                fecha_str = fila["releaseDate"]["value"]
                try:
                    anio = fecha_str.split("-")[0] # Nos quedamos con los primeros 4 dígitos
                except:
                    pass
                    
            # 3. Ir agrupando los géneros que devuelva
            if "genreLabel" in fila:
                generos.add(fila["genreLabel"]["value"])
                
        # 4. Traer una descripción genérica de la API de entidades básica
        desc_url = "https://www.wikidata.org/w/api.php"
        desc_params = {
            "action": "wbgetentities",
            "ids": wiki_id,
            "props": "descriptions",
            "languages": "es",
            "format": "json"
        }
        res_desc = requests.get(desc_url, params=desc_params, headers=headers, timeout=5).json()
        descripcion = res_desc.get("entities", {}).get(wiki_id, {}).get("descriptions", {}).get("es", {}).get("value", "")
        
        return desarrollador, anio, list(generos), descripcion

    except Exception as e:
        print(f"⚠️ Error al extraer detalles de SPARQL: {e}")
        return "", "", [], ""

def buscar_juego_completo(nombre_juego):
    print(f"🔍 Buscando '{nombre_juego}'...")
    url_search = "https://www.wikidata.org/w/api.php"
    headers = {'User-Agent': 'GamesSeederBot/1.0 (maxi@example.com)'}
    
    params_search = {
        "action": "wbsearchentities",
        "format": "json",
        "language": "es",
        "type": "item",
        "search": nombre_juego
    }
    
    try:
        res_search = requests.get(url_search, params=params_search, headers=headers, timeout=5).json()
        resultados = res_search.get("search", [])
        
        if resultados:
            wiki_id = resultados[0]["id"]
            
            # Lanzamos la extracción profunda
            dev, anio, gens, desc = obtener_detalles_wikidata(wiki_id)
            
            print(f"\n✨ DATOS EXTRAÍDOS REALES:")
            print(f" • Desarrollador: {dev if dev else 'No encontrado'}")
            print(f" • Año Release:  {anio if anio else 'No encontrado'}")
            print(f" • Géneros Wiki:  {gens}")
            print(f" • Descripción:   {desc if desc else 'No encontrada'}")
        else:
            print("❌ No se encontró el juego.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    buscar_juego_completo("Donkey Kong 64")