import os
import csv
import subprocess
import time
import re
import shutil
import requests
import json
from pymongo import MongoClient

mongoClient = MongoClient(
    host="mongodb",
    port=27017,
    username="admin",
    password="password",
    authSource="admin",
    authMechanism='SCRAM-SHA-256'
)

def get_events_db():
    db = mongoClient.admin
    events_collection = db.waze_events
    return list(events_collection.find({}))

def aplanar_documento(doc, prefix=''):
    plano = {}
    for k, v in doc.items():
        nombre = f"{prefix}{k}" if prefix == '' else f"{prefix}.{k}"
        if isinstance(v, dict):
            plano.update(aplanar_documento(v, nombre))
        elif isinstance(v, list):
            plano[nombre] = ','.join(map(str, v))
        else:
            plano[nombre] = v if v is not None else ''
    return plano

def homogeneizar_documentos(datos):
    planos = [aplanar_documento(doc) for doc in datos]
    claves = sorted(set().union(*(d.keys() for d in planos)))
    datos_homogeneos = []
    for doc in planos:
        fila = {clave: doc.get(clave, "") for clave in claves}
        datos_homogeneos.append(fila)
    return claves, datos_homogeneos

def export_to_csv(datos, ruta_csv):
    claves, datos_homogeneos = homogeneizar_documentos(datos)

    with open(ruta_csv, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=claves, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(datos_homogeneos)

    return claves

# pig es un exquisito qliao
def pig_sanitizar_clave(nombre):
    """Convierte una clave a un nombre válido de campo en Pig"""
    # Reemplazar todo lo que no sea letra, número o _ por _
    nombre = re.sub(r'\W+', '_', nombre)
    # Evitar que empiece por número o guion bajo
    if nombre.startswith('_') or re.match(r'^\d', nombre):
        nombre = f'f_{nombre}'
    return nombre

def generar_script_pig(ruta_csv, claves, salida='salida'):
    claves_limpias = {clave: pig_sanitizar_clave(clave) for clave in claves}

    esquema = [f"{valor}:chararray" for valor in claves_limpias.values()]
    esquema_str = ", ".join(esquema)

    campo_filtrado = list(claves_limpias.values())[0]

    with open("procesar_alertas.pig", "w") as f:
        f.write(f"""
datos = LOAD '{ruta_csv}' USING PigStorage(',') AS ({esquema_str});

-- Eliminar encabezados
datos_limpios = FILTER datos BY NOT ({campo_filtrado} == '{campo_filtrado}');

datos_filtrados = FILTER datos_limpios BY
    NOT (street MATCHES '.*\\\\{{.*') AND
    NOT (street MATCHES '.*\\\\}}.*') AND
    NOT (street MATCHES '.*[^a-zA-Z0-9_]text[^a-zA-Z0-9_].*') AND
    NOT (street MATCHES '.*[^a-zA-Z0-9_]report[^a-zA-Z0-9_].*') AND
    NOT (street MATCHES '.*reportMillis.*');

-- Eliminar duplicados por uuid
agrupado_por_uuid = GROUP datos_filtrados BY uuid;
sin_duplicar = FOREACH agrupado_por_uuid {{
    ordenado = ORDER datos_filtrados BY uuid;
    limitado = LIMIT ordenado 1;
    GENERATE FLATTEN(limitado);
}};

-- Eliminar filas duplicadas completamente
datos_unicos = DISTINCT sin_duplicar;

-- Contar alertas por comuna
por_comuna = GROUP datos_unicos BY city;
conteo_comuna = FOREACH por_comuna GENERATE group AS comuna, COUNT(datos_unicos) AS total;
STORE conteo_comuna INTO '{salida}_por_comuna' USING PigStorage(',');

-- Contar alertas por calle
por_calle = GROUP datos_unicos BY street;
conteo_calle = FOREACH por_calle GENERATE group AS calle, COUNT(datos_unicos) AS total;
STORE conteo_calle INTO '{salida}_por_calle' USING PigStorage(',');


""")

def ejecutar_pig(script_path="procesar_alertas.pig"):
    resultado = subprocess.run(["pig", script_path], capture_output=True, text=True)
    print("STDOUT:\n", resultado.stdout)
    print("STDERR:\n", resultado.stderr)

def subir_csv_a_elasticsearch(csv_file, index_name, es_url="http://localhost:9200"):
    with open(csv_file, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            doc = {
                "nombre": row[0].strip('"'),
                "cantidad": int(row[1])
            }

            response = requests.post(
                f"{es_url}/{index_name}/_doc",
                headers={"Content-Type": "application/json"},
                data=json.dumps(doc)
            )

            print(response.status_code, response.json())

def main():
    datos = get_events_db()
    if not datos:
        print("No se encontraron documentos en MongoDB.")
        return

    ruta_csv = "alertas.csv"
    claves = export_to_csv(datos, ruta_csv)

    generar_script_pig(ruta_csv, claves, salida='salida')
    ejecutar_pig("procesar_alertas.pig")

if __name__ == "__main__":
    main()
    shutil.copytree("./salida_por_calle", "./salidas_calle", dirs_exist_ok=True)
    shutil.copytree("./salida_por_comuna", "./salidas_comuna", dirs_exist_ok=True)

    #subir_csv_a_elasticsearch("./salida_por_calle/part-r-00000", "calles")
    #subir_csv_a_elasticsearch("./salida_por_comuna/part-r-00000", "comunas")
    time.sleep(12122222)
