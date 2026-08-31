import os
import re
import json
import urllib.request
import pandas as pd

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

def main():
    resources = get_resources()
    print(f"\nForam encontrados {len(resources)} arquivos CSV de ITBI.")
    
    sorted_resources = []
    for r in resources:
        year = extract_year(r.get('name', ''), r.get('url', ''))
        sorted_resources.append((year, r))
    sorted_resources.sort(key=lambda x: x[0])
    
    dfs = []
    summary = []
    
    for year, r in sorted_resources:
        file_name = f"itbi_{year}.csv" if year != "desconhecido" else os.path.basename(r.get('url', 'itbi.csv'))
        file_path = os.path.join(RAW_DIR, file_name)
        
        url = r.get('url')
        download_file(url, file_path)
        
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
    
    combined_df.to_csv(CONSOLIDATED_CSV, index=False, sep=';', encoding='utf-8-sig')
    print("Dataset consolidado salvo com sucesso!")

if __name__ == "__main__":
    main()
