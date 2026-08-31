import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "itbi_recife.db")

def main():
    print(f"Lendo base consolidada para importar no SQLite ({CSV_INPUT})...")
    df = pd.read_csv(CSV_INPUT, sep=';', encoding='utf-8-sig', low_memory=False)
    
    # Padronizações
    df['logradouro_fmt'] = df['logradouro'].fillna('').astype(str).str.strip().str.title()
    df['numero_fmt'] = df['numero'].fillna('').astype(str).str.replace('.0', '', regex=False).str.strip()
    df['complemento_fmt'] = df['complemento'].fillna('').astype(str).str.strip().str.title()
    df['endereco_edificio'] = df['logradouro_fmt'] + ', ' + df['numero_fmt'] + ' - ' + df['bairro_padronizado']
    df['endereco_completo'] = df['logradouro_fmt'] + ', ' + df['numero_fmt'] + ' ' + df['complemento_fmt'] + ' - ' + df['bairro_padronizado']
    
    # Tipagem limpa
    df['ano_construcao'] = pd.to_numeric(df['ano_construcao'], errors='coerce')
    df['latitude'] = pd.to_numeric(df['latitude'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['longitude'], errors='coerce')
    
    print(f"Criando banco de dados SQLite em {DB_PATH}...")
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        
    conn = sqlite3.connect(DB_PATH)
    
    # Salvar tabela transacoes
    df.to_sql('transacoes', conn, index=False, if_exists='replace')
    
    cursor = conn.cursor()
    print("Criando índices...")
    cursor.execute("CREATE INDEX idx_endereco_edificio ON transacoes(endereco_edificio);")
    cursor.execute("CREATE INDEX idx_bairro ON transacoes(bairro_padronizado);")
    cursor.execute("CREATE INDEX idx_logradouro ON transacoes(logradouro_fmt);")
    cursor.execute("CREATE INDEX idx_data ON transacoes(data_transacao);")
    cursor.execute("CREATE INDEX idx_coords ON transacoes(latitude, longitude);")
    
    # Criar tabela agregada de edifícios
    cursor.execute("""
    CREATE TABLE edifcios_resumo AS
    SELECT 
        endereco_edificio,
        bairro_padronizado,
        logradouro_fmt,
        numero_fmt,
        COUNT(*) as total_transacoes,
        ROUND(AVG(preco_m2_privativo_corrigido), 2) as m2_privativo_medio,
        ROUND(AVG(valor_avaliacao_corrigido), 2) as valor_medio_corrigido,
        ROUND(MIN(valor_avaliacao_corrigido), 2) as valor_min_corrigido,
        ROUND(MAX(valor_avaliacao_corrigido), 2) as valor_max_corrigido,
        ROUND(AVG(area_privativa_estimada), 2) as area_privativa_media,
        AVG(latitude) as latitude,
        AVG(longitude) as longitude
    FROM transacoes
    WHERE preco_m2_privativo_corrigido > 500 AND preco_m2_privativo_corrigido < 35000
    GROUP BY endereco_edificio, bairro_padronizado, logradouro_fmt, numero_fmt;
    """)
    cursor.execute("CREATE INDEX idx_predios_bairro ON edifcios_resumo(bairro_padronizado);")
    cursor.execute("CREATE INDEX idx_predios_coords ON edifcios_resumo(latitude, longitude);")
    
    conn.commit()
    conn.close()
    print(f"Banco SQLite configurado com sucesso! Total de transações: {len(df):,}")

if __name__ == "__main__":
    main()
