import os
import sqlite3
import pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
DB_PATH = os.path.join(BASE_DIR, "data", "processed", "itbi_recife.db")

# Coordenada real exata do Cais José Estelita, 862 (Torres do Mirante do Cais / Novo Recife)
ESTELITA_LAT = -8.072834
ESTELITA_LNG = -34.887812

def main():
    print("Atualizando coordenadas do Cais José Estelita no CSV e SQLite...")
    df = pd.read_csv(CSV_INPUT, sep=';', encoding='utf-8-sig', low_memory=False)
    
    cond_estelita = (df['cod_logradouro'] == 35807) & (df['latitude'].isna())
    df.loc[cond_estelita, 'latitude'] = ESTELITA_LAT
    df.loc[cond_estelita, 'longitude'] = ESTELITA_LNG
    
    df.to_csv(CSV_INPUT, index=False, sep=';', encoding='utf-8-sig')
    print(f"Coordenadas atualizadas para {cond_estelita.sum()} transações no CSV.")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE transacoes 
        SET latitude = ?, longitude = ? 
        WHERE cod_logradouro = 35807 AND (latitude IS NULL OR latitude = '')
    """, (ESTELITA_LAT, ESTELITA_LNG))
    
    cursor.execute("""
        UPDATE edifcios_resumo 
        SET latitude = ?, longitude = ? 
        WHERE cod_logradouro = 35807
    """, (ESTELITA_LAT, ESTELITA_LNG))
    
    conn.commit()
    conn.close()
    print("Banco SQLite atualizado com sucesso!")

if __name__ == "__main__":
    main()
