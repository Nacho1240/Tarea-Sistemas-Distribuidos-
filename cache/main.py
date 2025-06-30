from http.server import BaseHTTPRequestHandler, HTTPServer
import redis
import json
import os
import time
import requests
import hashlib
from urllib.parse import urlparse

# Config Redis
eviction_policy = os.environ.get('EVICTION_POLICY', 'allkeys-lru')
valid_policies = ['allkeys-lru', 'allkeys-random']
if eviction_policy not in valid_policies:
    raise ValueError(f"Política no válida: {eviction_policy}")

r = redis.Redis(host='redis', port=6379, db=0)
r.config_set('maxmemory', '10mb')
r.config_set('maxmemory-policy', eviction_policy)

# Estadísticas
total, hits, miss = 0, 0, 0

# Host de ElasticSearch
ELASTIC_HOST = 'http://elasticsearch:9200'

def get_cache_key(index: str, json_data: str):
    """Crea una clave de cache única usando el índice y el cuerpo de la query"""
    return f"{index}:{hashlib.sha256(json_data.encode()).hexdigest()}"

class ListenServer(BaseHTTPRequestHandler):

    def do_POST(self):
        global total, hits, miss

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        total += 1

        try:
            # Obtener el índice desde la URL (e.g., /calles, /comunas)
            parsed_path = urlparse(self.path)
            path_parts = parsed_path.path.strip('/').split('/')
            if len(path_parts) < 1 or not path_parts[0]:
                raise ValueError("Debe especificar un índice en la URL. Ejemplo: /calles")

            index_name = path_parts[0]
            query_json = body.decode("utf-8")
            cache_key = get_cache_key(index_name, query_json)

            if r.exists(cache_key):
                hits += 1
                cached_response = r.get(cache_key).decode()
                print(f"HIT: índice={index_name}")
                response_data = cached_response
            else:
                miss += 1
                print(f"MISS: consultando índice={index_name} en ElasticSearch")
                elastic_url = f"{ELASTIC_HOST}/{index_name}/_search?scroll=10m&size=50"
                elastic_response = requests.get(
                    elastic_url,
                    headers={"Content-Type": "application/json"},
                    data=query_json
                )
                response_data = elastic_response.text
                r.set(cache_key, response_data)

            # Log de stats
            hitrate = hits / total
            missrate = miss / total
            print(f"HITRATE: {hitrate:.2f}, MISSRATE: {missrate:.2f}, TOTAL: {len(r.keys())}")

            self.send_response(200)
            self.end_headers()
            self.wfile.write(response_data.encode())

        except Exception as e:
            print(f"Error: {e}")
            self.send_response(400)
            self.end_headers()
            self.wfile.write(f"Error: {str(e)}".encode())

def main():
    hostName = "cachechito"
    serverPort = 9090
    webServer = HTTPServer((hostName, serverPort), ListenServer)
    print(f"Escuchando en http://{hostName}:{serverPort}/<indice>")
    print(f"Política de remoción: {eviction_policy}")
    try:
        webServer.serve_forever()
    except KeyboardInterrupt:
        pass
    webServer.server_close()
    print("Servidor detenido.")

if __name__ == "__main__":
    time.sleep(3)
    main()

