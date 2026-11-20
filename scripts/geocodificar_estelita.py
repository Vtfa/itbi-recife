import os
import pandas as pd

try:
    from scripts.criar_banco_sqlite import build_sqlite_db, read_consolidated_csv
except ImportError:
    from criar_banco_sqlite import build_sqlite_db, read_consolidated_csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")

# Coordenada real exata do Cais José Estelita, 862 (Torres do Mirante do Cais / Novo Recife)
ESTELITA_LAT = -8.072834
ESTELITA_LNG = -34.887812


def main():
    print("Atualizando coordenadas do Cais José Estelita no CSV e SQLite...")
    df = read_consolidated_csv(CSV_INPUT)

    cod_num = pd.to_numeric(df["cod_logradouro"], errors="coerce")
    if "metodo_geolocalizacao" in df.columns:
        sem_orig = df["latitude"].isna() | (df["metodo_geolocalizacao"] != "Original da Prefeitura")
    else:
        sem_orig = df["latitude"].isna()

    cond_estelita = (cod_num == 35807) & sem_orig
    df.loc[cond_estelita, "latitude"] = ESTELITA_LAT
    df.loc[cond_estelita, "longitude"] = ESTELITA_LNG
    df.loc[cond_estelita, "metodo_geolocalizacao"] = "Geocodificação Direta (Logradouro)"

    df.to_csv(CSV_INPUT, index=False, sep=";", encoding="utf-8-sig")
    print(f"Coordenadas atualizadas para {cond_estelita.sum()} transações no CSV.")

    build_sqlite_db(df)
    print("Banco SQLite atualizado com sucesso!")


if __name__ == "__main__":
    main()
