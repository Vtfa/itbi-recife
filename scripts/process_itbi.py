import os
import re
import sys
import json
import urllib.request
from datetime import datetime, timezone
import pandas as pd

try:
    from scripts.criar_banco_sqlite import safe_to_csv
except ImportError:
    from criar_banco_sqlite import safe_to_csv

API_URL = "https://dados.recife.pe.gov.br/api/3/action/package_show?id=imposto-sobre-transmissao-de-bens-imoveis-itbi"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
CONSOLIDATED_CSV = os.path.join(PROCESSED_DIR, "itbi_consolidado.csv")

os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

def get_resources():
    print(f"Buscando metadados em {API_URL}...")
    req = urllib.request.Request(API_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode('utf-8'))
    resources = data.get('result', {}).get('resources', [])
    csv_resources = [r for r in resources if r.get('format', '').upper() == 'CSV' or r.get('url', '').lower().endswith('.csv')]
    return csv_resources

def download_file(url, target_path):
    print(f"Baixando: {url} -> {target_path}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        with open(target_path, 'wb') as f:
            f.write(resp.read())

def detect_csv_format(file_path):
    encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                sample = [f.readline() for _ in range(5)]
                sample_text = "".join(sample)
                if not sample_text.strip():
                    continue
                first_line = sample[0]
                semicolons = first_line.count(';')
                commas = first_line.count(',')
                tabs = first_line.count('\t')
                sep = ';' if semicolons > commas and semicolons > tabs else (',' if commas > tabs else '\t')
                return enc, sep
        except (UnicodeDecodeError, Exception):
            continue
    return 'utf-8', ';'

def extract_year(name, url):
    match = re.search(r'20\d\d', name + " " + url)
    if match:
        return match.group(0)
    return "desconhecido"

def should_download(file_path, resource, year, max_year, force_all=False):
    if force_all or not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
        return True, "arquivo local ausente ou atualização completa forçada"

    # Sempre verificar atualização para o ano mais recente
    if year == max_year:
        remote_mod = resource.get('last_modified') or resource.get('created')
        if remote_mod:
            try:
                remote_dt = datetime.fromisoformat(remote_mod.replace('Z', '+00:00')).replace(tzinfo=None)
                local_dt = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc).replace(tzinfo=None)
                if remote_dt > local_dt:
                    return True, f"atualizado no portal em {remote_mod[:10]}"
                return True, f"ano corrente ({year}) - baixando versão mais recente"
            except Exception:
                pass
        return True, f"ano corrente ({year})"

    # Para anos anteriores, baixar apenas se last_modified remoto for mais novo que o arquivo local
    remote_mod = resource.get('last_modified')
    if remote_mod:
        try:
            remote_dt = datetime.fromisoformat(remote_mod.replace('Z', '+00:00')).replace(tzinfo=None)
            local_dt = datetime.fromtimestamp(os.path.getmtime(file_path), tz=timezone.utc).replace(tzinfo=None)
            if remote_dt > local_dt:
                return True, f"atualizado no portal em {remote_mod[:10]}"
        except Exception:
            pass

    return False, "cache local atualizado"


def main(force_all=False):
    resources = get_resources()
    print(f"\nForam encontrados {len(resources)} arquivos CSV de ITBI no portal da Prefeitura.")
    
    sorted_resources = []
    for r in resources:
        year = extract_year(r.get('name', ''), r.get('url', ''))
        sorted_resources.append((year, r))
    sorted_resources.sort(key=lambda x: x[0])

    numeric_years = [y for y, _ in sorted_resources if y.isdigit()]
    max_year = max(numeric_years) if numeric_years else ""
    
    dfs = []
    summary = []
    
    for year, r in sorted_resources:
        file_name = f"itbi_{year}.csv" if year != "desconhecido" else os.path.basename(r.get('url', 'itbi.csv'))
        file_path = os.path.join(RAW_DIR, file_name)
        
        url = r.get('url')
        need_dl, reason = should_download(file_path, r, year, max_year, force_all=force_all)
        if need_dl:
            print(f"[{year}] Baixando ({reason})...")
            download_file(url, file_path)
        else:
            print(f"[{year}] Usando arquivo local {file_name} ({reason}).")
        
        enc, sep = detect_csv_format(file_path)
        print(f"Lendo {file_name} (Encoding: {enc}, Separador: '{sep}')...")
        
        try:
            df = pd.read_csv(file_path, sep=sep, encoding=enc, dtype=str, on_bad_lines='skip')
        except Exception as e:
            print(f"Erro ao ler com sep '{sep}', tentando fallback automático: {e}")
            df = pd.read_csv(file_path, sep=None, engine='python', encoding=enc, dtype=str, on_bad_lines='skip')
        
        df.columns = [str(c).strip() for c in df.columns]
        df['ano_arquivo'] = year
        
        rows_count = len(df)
        cols_count = len(df.columns)
        print(f"-> {file_name}: {rows_count:,} linhas, {cols_count} colunas.")
        summary.append({
            'ano': year,
            'arquivo': file_name,
            'linhas': rows_count,
            'colunas': cols_count
        })
        dfs.append(df)
    
    print("\n--- Consolidando todos os anos em um dataset único ---")
    combined_df = pd.concat(dfs, ignore_index=True)
    
    print(f"Total consolidado: {len(combined_df):,} registros e {len(combined_df.columns)} colunas.")
    print(f"Salvando em: {CONSOLIDATED_CSV}...")
    
    safe_to_csv(combined_df, CONSOLIDATED_CSV)
    print("Dataset consolidado salvo com sucesso!")

if __name__ == "__main__":
    force = "--all" in sys.argv or "--force" in sys.argv
    main(force_all=force)
