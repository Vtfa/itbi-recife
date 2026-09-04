import os
import json
import sqlite3
import urllib.parse
import traceback
import subprocess
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "itbi_recife.db")
GEOJSON_PATH = os.path.join(BASE_DIR, "data", "raw", "bairros_recife.geojson")
HTML_INDEX = os.path.join(BASE_DIR, "dashboard_interativo.html")

_GEOJSON_CACHE = None

class ITBIHandler(BaseHTTPRequestHandler):
    def get_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def do_GET(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            path = parsed.path
            query = urllib.parse.parse_qs(parsed.query)
            
            if path == '/' or path == '/index.html':
                self.serve_html()
            elif path == '/api/geojson':
                self.serve_geojson()
            elif path == '/api/bairros':
                self.handle_bairros()
            elif path == '/api/destaques':
                self.handle_destaques(query)
            elif path == '/api/busca':
                self.handle_busca(query)
            elif path == '/api/edificio':
                self.handle_edificio(query)
            elif path == '/api/mapa_pontos':
                self.handle_mapa_pontos(query)
            else:
                self.send_error(404, "Not Found")
        except Exception as e:
            traceback.print_exc()
            self.send_json({"error": str(e)}, status=500)

    def serve_html(self):
        if not os.path.exists(HTML_INDEX):
            self.send_error(404, "HTML Dashboard não encontrado")
            return
        with open(HTML_INDEX, 'rb') as f:
            content = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_geojson(self):
        global _GEOJSON_CACHE
        if _GEOJSON_CACHE is None:
            if not os.path.exists(GEOJSON_PATH):
                self.send_error(404, "GeoJSON não encontrado")
                return
            with open(GEOJSON_PATH, 'rb') as f:
                _GEOJSON_CACHE = f.read()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(_GEOJSON_CACHE)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(_GEOJSON_CACHE)

    def send_json(self, data, status=200):
        content = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content)

    def handle_bairros(self):
        conn = self.get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                bairro_padronizado as bairro,
                COUNT(*) as total_transacoes,
                ROUND(AVG(preco_m2_privativo_corrigido), 2) as m2_medio,
                ROUND(AVG(valor_avaliacao_corrigido), 2) as valor_medio
            FROM transacoes
            WHERE preco_m2_privativo_corrigido > 500 AND preco_m2_privativo_corrigido < 35000
            GROUP BY bairro_padronizado
            HAVING total_transacoes >= 5
            ORDER BY total_transacoes DESC
        """)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        self.send_json(rows)

    def handle_destaques(self, query):
        bairro = query.get('bairro', [''])[0].strip()
        conn = self.get_db()
        cursor = conn.cursor()
        
        sql = """
            SELECT 
                endereco_edificio,
                bairro_padronizado,
                logradouro_canonico,
                numero_fmt,
                total_transacoes,
                total_revendas,
                m2_privativo_medio,
                valor_medio_corrigido,
                area_privativa_media,
                latitude,
                longitude
            FROM edifcios_resumo
        """
        params = []
        if bairro:
            sql += " WHERE bairro_padronizado = ?"
            params.append(bairro)
            
        sql += " ORDER BY total_transacoes DESC LIMIT 50"
        cursor.execute(sql, params)
        top_edificios = [dict(r) for r in cursor.fetchall()]
        
        # Últimas transações registradas
        sql_recentes = """
            SELECT 
                endereco_edificio,
                complemento_fmt as unidade,
                bairro_padronizado,
                data_transacao,
                valor_avaliacao_corrigido,
                area_privativa_estimada,
                preco_m2_privativo_corrigido,
                eh_revenda,
                ordem_venda,
                var_real_pct
            FROM transacoes
        """
        params_rec = []
        if bairro:
            sql_recentes += " WHERE bairro_padronizado = ?"
            params_rec.append(bairro)
            
        sql_recentes += " ORDER BY data_transacao DESC LIMIT 40"
        cursor.execute(sql_recentes, params_rec)
        recentes = [dict(r) for r in cursor.fetchall()]
        
        # Casos destacados de Revenda (mesmo imóvel vendido 2+ vezes com intervalo >= 1 ano)
        sql_revendas = """
            SELECT 
                endereco_edificio,
                complemento_fmt as unidade,
                bairro_padronizado,
                data_transacao,
                data_venda_anterior,
                anos_entre_vendas,
                valor_real_anterior,
                valor_avaliacao_corrigido as valor_real_atual,
                valor_nom_anterior,
                valor_num as valor_nom_atual,
                var_real_pct,
                var_nom_pct,
                taxa_anual_real_pct,
                preco_m2_privativo_corrigido,
                area_privativa_estimada,
                ordem_venda
            FROM transacoes
            WHERE ordem_venda >= 2 AND anos_entre_vendas >= 0.8
        """
        params_rev = []
        if bairro:
            sql_revendas += " AND bairro_padronizado = ?"
            params_rev.append(bairro)
            
        sql_revendas += " ORDER BY ABS(var_real_pct) DESC LIMIT 50"
        cursor.execute(sql_revendas, params_rev)
        revendas_destaque = [dict(r) for r in cursor.fetchall()]
        
        conn.close()
        self.send_json({
            "top_edificios": top_edificios,
            "recentes": recentes,
            "revendas_destaque": revendas_destaque
        })

    def handle_busca(self, query):
        q = query.get('q', [''])[0].strip()
        bairro = query.get('bairro', [''])[0].strip()
        
        conn = self.get_db()
        cursor = conn.cursor()
        
        sql = """
            SELECT 
                endereco_edificio,
                bairro_padronizado,
                logradouro_canonico,
                numero_fmt,
                total_transacoes,
                total_revendas,
                m2_privativo_medio,
                valor_medio_corrigido,
                area_privativa_media,
                latitude,
                longitude
            FROM edifcios_resumo
            WHERE 1=1
        """
        params = []
        if bairro:
            sql += " AND bairro_padronizado = ?"
            params.append(bairro)
        if q:
            sql += " AND (endereco_edificio LIKE ? OR logradouro_canonico LIKE ?)"
            params.extend([f"%{q}%", f"%{q}%"])
            
        sql += " ORDER BY total_transacoes DESC LIMIT 100"
        
        cursor.execute(sql, params)
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        self.send_json(rows)

    def handle_mapa_pontos(self, query):
        bairro = query.get('bairro', [''])[0].strip()
        conn = self.get_db()
        cursor = conn.cursor()
        
        if bairro:
            cursor.execute("""
                SELECT endereco_edificio, bairro_padronizado, total_transacoes, total_revendas, m2_privativo_medio, valor_medio_corrigido, area_privativa_media, latitude, longitude
                FROM edifcios_resumo
                WHERE bairro_padronizado = ? AND latitude IS NOT NULL AND longitude IS NOT NULL
                ORDER BY total_transacoes DESC
            """, (bairro,))
        else:
            cursor.execute("""
                SELECT endereco_edificio, bairro_padronizado, total_transacoes, total_revendas, m2_privativo_medio, valor_medio_corrigido, area_privativa_media, latitude, longitude
                FROM edifcios_resumo
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                ORDER BY total_transacoes DESC
            """)
            
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        self.send_json(rows)

    def handle_edificio(self, query):
        endereco = query.get('endereco', [''])[0].strip()
        if not endereco:
            self.send_json({"error": "Endereco nao informado"})
            return
            
        conn = self.get_db()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM edifcios_resumo WHERE endereco_edificio = ? LIMIT 1
        """, (endereco,))
        resumo_row = cursor.fetchone()
        resumo = dict(resumo_row) if resumo_row else {}
        
        cursor.execute("""
            SELECT 
                complemento_fmt as unidade,
                data_transacao,
                ano_arquivo,
                tipo_imovel,
                padrao_acabamento,
                estado_conservacao,
                ano_construcao,
                valor_avaliacao_corrigido,
                valor_num as valor_nominal,
                area_privativa_estimada,
                area_total_cadastral,
                preco_m2_privativo_corrigido,
                preco_m2_total_corrigido,
                fator_ipca,
                eh_revenda,
                ordem_venda,
                total_vendas_imovel,
                data_venda_anterior,
                valor_real_anterior,
                valor_nom_anterior,
                var_real_pct,
                var_nom_pct,
                anos_entre_vendas,
                taxa_anual_real_pct
            FROM transacoes
            WHERE endereco_edificio = ?
            ORDER BY complemento_fmt ASC, data_transacao DESC
        """, (endereco,))
        
        transacoes = [dict(r) for r in cursor.fetchall()]
        conn.close()
        
        self.send_json({
            "resumo": resumo,
            "transacoes": transacoes
        })

def check_database():
    gz_path = DB_PATH + ".gz"
    need_decompress = False
    
    if not os.path.exists(DB_PATH):
        need_decompress = True
    else:
        size = os.path.getsize(DB_PATH)
        if size < 10000: # LFS pointer or empty
            need_decompress = True

    if need_decompress and os.path.exists(gz_path):
        print(f"[INIT] Descompactando base de dados ({os.path.getsize(gz_path) / (1024*1024):.1f} MB) para {DB_PATH}...")
        try:
            import gzip
            import shutil
            with gzip.open(gz_path, 'rb') as f_in:
                with open(DB_PATH, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            print(f"[OK] Base de dados descompactada com sucesso ({os.path.getsize(DB_PATH) / (1024*1024):.1f} MB).")
        except Exception as e:
            print(f"[ERRO] Falha ao descompactar {gz_path}: {e}")

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM transacoes")
        count = cursor.fetchone()[0]
        conn.close()
        print(f"[OK] Banco SQLite validado: {count:,} transações disponíveis.")
        return True
    except Exception as e:
        print(f"[ERRO CRÍTICO] Falha ao abrir banco SQLite {DB_PATH}: {e}")
        return False

def run_server(port=8050):
    check_database()
    port = int(os.environ.get('PORT', port))
    server_address = ('0.0.0.0', port)
    httpd = ThreadingHTTPServer(server_address, ITBIHandler)
    print(f"Servidor ITBI Recife ativo em http://0.0.0.0:{port}")
    httpd.serve_forever()

if __name__ == "__main__":
    run_server()
