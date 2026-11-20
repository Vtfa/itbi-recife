import os
import pandas as pd
import numpy as np

try:
    from scripts.criar_banco_sqlite import build_sqlite_db, read_consolidated_csv
except ImportError:
    from criar_banco_sqlite import build_sqlite_db, read_consolidated_csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
RELATORIO_CSV = os.path.join(BASE_DIR, "data", "processed", "imoveis_recuperados_georreferenciados.csv")

# Coordenada exata do Cais José Estelita, 862 (Mirante do Cais / Novo Recife)
ESTELITA_COD_LOGRADOURO = 35807
ESTELITA_LAT = -8.072834
ESTELITA_LNG = -34.887812


def main():
    print("Iniciando recuperação de coordenadas geográficas dos imóveis...")
    df = read_consolidated_csv(CSV_INPUT)

    # Usar coordenadas originais preservadas para garantir idempotência em reexecuções
    if "latitude_original" in df.columns and "longitude_original" in df.columns:
        lat_orig = pd.to_numeric(df["latitude_original"], errors="coerce")
        lng_orig = pd.to_numeric(df["longitude_original"], errors="coerce")
    else:
        lat_orig = pd.to_numeric(df["latitude"], errors="coerce")
        lng_orig = pd.to_numeric(df["longitude"], errors="coerce")
        df["latitude_original"] = lat_orig
        df["longitude_original"] = lng_orig

    # Mapa de coordenadas conhecidas a partir de registros originais válidos
    tem_orig = lat_orig.notna() & lng_orig.notna()
    df_com_coords = df.loc[tem_orig].copy()
    df_com_coords["_lat"] = lat_orig.loc[tem_orig]
    df_com_coords["_lng"] = lng_orig.loc[tem_orig]

    # Média de coordenadas por logradouro
    coords_por_rua = df_com_coords.groupby("cod_logradouro").agg(
        lat_rua=("_lat", "mean"),
        lng_rua=("_lng", "mean"),
    )

    # Média de coordenadas por bairro
    coords_por_bairro = df_com_coords.groupby("bairro_padronizado").agg(
        lat_bairro=("_lat", "mean"),
        lng_bairro=("_lng", "mean"),
    )

    mapa_rua_lat = coords_por_rua["lat_rua"].round(6).to_dict()
    mapa_rua_lng = coords_por_rua["lng_rua"].round(6).to_dict()
    mapa_bairro_lat = coords_por_bairro["lat_bairro"].round(6).to_dict()
    mapa_bairro_lng = coords_por_bairro["lng_bairro"].round(6).to_dict()

    cond_sem_coord = ~tem_orig
    print(f"Total de transações sem coordenadas originais: {cond_sem_coord.sum():,}")

    lat_rua_mapped = df["cod_logradouro"].map(mapa_rua_lat)
    lng_rua_mapped = df["cod_logradouro"].map(mapa_rua_lng)
    lat_bairro_mapped = df["bairro_padronizado"].map(mapa_bairro_lat)
    lng_bairro_mapped = df["bairro_padronizado"].map(mapa_bairro_lng)

    cod_estelita = pd.to_numeric(df["cod_logradouro"], errors="coerce") == ESTELITA_COD_LOGRADOURO

    cond_orig = tem_orig
    cond_estelita_fill = cond_sem_coord & cod_estelita
    cond_rua = cond_sem_coord & (~cod_estelita) & lat_rua_mapped.notna() & lng_rua_mapped.notna()
    cond_bairro = cond_sem_coord & (~cod_estelita) & (~cond_rua) & lat_bairro_mapped.notna() & lng_bairro_mapped.notna()

    df["latitude"] = np.select(
        [cond_orig, cond_estelita_fill, cond_rua, cond_bairro],
        [lat_orig, ESTELITA_LAT, lat_rua_mapped, lat_bairro_mapped],
        default=-8.0578,
    )
    df["longitude"] = np.select(
        [cond_orig, cond_estelita_fill, cond_rua, cond_bairro],
        [lng_orig, ESTELITA_LNG, lng_rua_mapped, lng_bairro_mapped],
        default=-34.8829,
    )
    df["metodo_geolocalizacao"] = np.select(
        [cond_orig, cond_estelita_fill, cond_rua, cond_bairro],
        [
            "Original da Prefeitura",
            "Geocodificação Direta (Logradouro)",
            "Interpolação de Logradouro (Mesma Rua)",
            "Centroide Geográfico do Bairro",
        ],
        default="Centro de Recife",
    )

    # Salvar dataset corrigido
    df.to_csv(CSV_INPUT, index=False, sep=";", encoding="utf-8-sig")
    print("CSV consolidado atualizado com 100% de coordenadas preenchidas.")

    # Gerar relatório dos imóveis recuperados agrupados por edifício
    df_recuperados = df[df["metodo_geolocalizacao"] != "Original da Prefeitura"].copy()

    relatorio_predios = (
        df_recuperados.groupby(["bairro_padronizado", "endereco_edificio", "metodo_geolocalizacao"])
        .agg(
            total_transacoes=("valor_avaliacao_corrigido", "count"),
            m2_privativo_medio=("preco_m2_privativo_corrigido", "mean"),
            valor_medio_corrigido=("valor_avaliacao_corrigido", "mean"),
            area_privativa_media=("area_privativa_estimada", "mean"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
        )
        .reset_index()
    )

    for col in ["m2_privativo_medio", "valor_medio_corrigido", "area_privativa_media"]:
        relatorio_predios[col] = relatorio_predios[col].round(2)

    relatorio_predios = relatorio_predios.sort_values(
        by=["bairro_padronizado", "total_transacoes"], ascending=[True, False]
    ).reset_index(drop=True)
    relatorio_predios.to_csv(RELATORIO_CSV, index=False, sep=";", encoding="utf-8-sig")
    print(f"Relatório de edifícios recuperados salvo em: {RELATORIO_CSV}")

    # Atualizar o banco SQLite via construtor unificado
    build_sqlite_db(df)
    print("Banco SQLite atualizado com 100% de cobertura espacial!")

    # Resumo por bairro dos imóveis recuperados
    resumo_bairro = (
        relatorio_predios.groupby("bairro_padronizado")
        .agg(
            edificios_recuperados=("endereco_edificio", "count"),
            transacoes_recuperadas=("total_transacoes", "sum"),
        )
        .reset_index()
        .sort_values(by="transacoes_recuperadas", ascending=False)
    )

    print("\n" + "=" * 80)
    print("TOP 25 BAIRROS COM MAIS IMÓVEIS/TRANSAÇÕES RECUPERADAS:")
    print("=" * 80)
    print(resumo_bairro.head(25).to_string(index=False))


if __name__ == "__main__":
    main()
