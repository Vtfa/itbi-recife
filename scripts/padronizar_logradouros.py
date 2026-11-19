import os
import sqlite3
import unicodedata
import pandas as pd

try:
    from scripts.criar_banco_sqlite import (
        DB_PATH,
        build_sqlite_db,
        format_numero,
        read_consolidated_csv,
    )
except ImportError:
    from criar_banco_sqlite import (
        DB_PATH,
        build_sqlite_db,
        format_numero,
        read_consolidated_csv,
    )

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")

ABBREV_MAP = {
    'R': 'Rua',
    'R.': 'Rua',
    'Av': 'Avenida',
    'Av.': 'Avenida',
    'Gen': 'General',
    'Gen.': 'General',
    'Dr': 'Doutor',
    'Dr.': 'Doutor',
    'Dra': 'Doutora',
    'Dra.': 'Doutora',
    'Prof': 'Professor',
    'Prof.': 'Professor',
    'Profa': 'Professora',
    'Profa.': 'Professora',
    'Gov': 'Governador',
    'Gov.': 'Governador',
    'Mal': 'Marechal',
    'Mal.': 'Marechal',
    'Cel': 'Coronel',
    'Cel.': 'Coronel',
    'Cap': 'Capitão',
    'Cap.': 'Capitão',
    'Dep': 'Deputado',
    'Dep.': 'Deputado',
    'Des': 'Desembargador',
    'Des.': 'Desembargador',
    'Pres': 'Presidente',
    'Pres.': 'Presidente',
    'Pe': 'Padre',
    'Pe.': 'Padre',
    'Maest': 'Maestro',
    'Maest.': 'Maestro',
    'Prc': 'Praça',
    'Prc.': 'Praça',
    'Tv': 'Travessa',
    'Tv.': 'Travessa',
    'Est': 'Estrada',
    'Est.': 'Estrada'
}

def clean_text(text):
    if pd.isna(text): return ''
    nfkd = unicodedata.normalize('NFKD', str(text))
    clean = ''.join([c for c in nfkd if not unicodedata.combining(c)]).strip()
    return clean

def expand_abbreviations(street_name):
    clean = clean_text(street_name)
    tokens = clean.split()
    expanded = []
    for t in tokens:
        # Title case check
        t_title = t.title()
        if t_title in ABBREV_MAP:
            expanded.append(ABBREV_MAP[t_title])
        else:
            expanded.append(t_title)
    return ' '.join(expanded)

def build_canonical_street_map(df):
    """
    Para cada cod_logradouro oficial, escolhe a versão mais completa e expande abreviações.
    Garante que duas ruas distintas (códigos diferentes) NUNCA sejam unificadas.
    """
    print("Mapeando nomes canônicos por cod_logradouro...")
    cod_to_names = df.groupby('cod_logradouro')['logradouro'].unique().to_dict()
    
    canonical_map = {}
    for cod, names in cod_to_names.items():
        # Expandir todas as variações e pegar a mais longa / completa
        expanded_names = [expand_abbreviations(n) for n in names if n]
        if not expanded_names:
            expanded_names = [f"Logradouro {cod}"]
        # Escolher a versão mais completa
        best_name = max(expanded_names, key=len)
        canonical_map[cod] = best_name
        
    return canonical_map

def main():
    print(f"Lendo base consolidada ({CSV_INPUT})...")
    df = read_consolidated_csv(CSV_INPUT)
    
    canonical_map = build_canonical_street_map(df)
    
    # Atribuir logradouro canônico oficial
    df['logradouro_canonico'] = df['cod_logradouro'].map(canonical_map)
    df['numero_fmt'] = format_numero(df['numero'])
    df['complemento_fmt'] = df['complemento'].fillna('').astype(str).str.strip().str.title()
    
    # Endereço do edifício unificado e seguro: Logradouro Canônico + Número + Bairro
    df['endereco_edificio'] = df['logradouro_canonico'] + ', ' + df['numero_fmt'] + ' - ' + df['bairro_padronizado']
    df['endereco_completo'] = (
        df['logradouro_canonico'] + ', ' + df['numero_fmt'] + ' ' + df['complemento_fmt'] + ' - ' + df['bairro_padronizado']
    ).str.replace(r'\s+', ' ', regex=True).str.strip()
    
    # Salvar no CSV consolidado
    df.to_csv(CSV_INPUT, index=False, sep=';', encoding='utf-8-sig')
    print("Dataset consolidado atualizado com logradouros canônicos.")
    
    # Atualizar banco de dados SQLite usando o construtor unificado
    build_sqlite_db(df)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Testar caso específico de General Polidoro, 320
    print("\n" + "="*80)
    print("VERIFICAÇÃO: RUA GENERAL POLIDORO, 320 - VÁRZEA")
    print("="*80)
    cursor.execute("""
        SELECT endereco_edificio, total_transacoes, m2_privativo_medio, valor_medio_corrigido, latitude, longitude
        FROM edifcios_resumo
        WHERE endereco_edificio LIKE '%Polidoro, 320%'
    """)
    for row in cursor.fetchall():
        print(row)
        
    conn.close()
    print("\nBanco de dados reconstruído e unificado com sucesso!")

if __name__ == "__main__":
    main()
