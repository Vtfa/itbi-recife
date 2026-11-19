import os
import pandas as pd

try:
    from scripts.criar_banco_sqlite import read_consolidated_csv
except ImportError:
    from criar_banco_sqlite import read_consolidated_csv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_CONSOLIDADO = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
RELATORIO_CSV = os.path.join(BASE_DIR, "data", "processed", "imoveis_recuperados_georreferenciados.csv")
RELATORIO_BAIRRO_CSV = os.path.join(BASE_DIR, "data", "processed", "resumo_imoveis_recuperados_por_bairro.csv")


def main():
    df_cons = read_consolidated_csv(CSV_CONSOLIDADO)
    print(f"Total de registros no consolidado: {len(df_cons):,}")

    if "metodo_geolocalizacao" in df_cons.columns:
        mask_recuperados = df_cons["metodo_geolocalizacao"] != "Original da Prefeitura"
    elif "latitude_original" in df_cons.columns:
        mask_recuperados = pd.to_numeric(df_cons["latitude_original"], errors="coerce").isna()
    else:
        raise RuntimeError(
            "Colunas 'metodo_geolocalizacao' ou 'latitude_original' não encontradas. Execute recuperar_coordenadas_itbi.py primeiro."
        )

    print(f"Total marcado como recuperado (sem coordenada original): {mask_recuperados.sum():,}")

    df_recup = df_cons.loc[mask_recuperados].copy()

    relatorio_edificios = (
        df_recup.groupby(["bairro_padronizado", "endereco_edificio", "logradouro_canonico", "metodo_geolocalizacao"])
        .agg(
            total_transacoes=("valor_avaliacao_corrigido", "count"),
            total_revendas=("eh_revenda", lambda s: pd.Series(s).fillna(False).astype(bool).sum()),
            m2_privativo_medio=("preco_m2_privativo_corrigido", "mean"),
            valor_medio_corrigido=("valor_avaliacao_corrigido", "mean"),
            area_privativa_media=("area_privativa_estimada", "mean"),
            latitude=("latitude", "first"),
            longitude=("longitude", "first"),
        )
        .reset_index()
    )

    for c in ["m2_privativo_medio", "valor_medio_corrigido", "area_privativa_media"]:
        relatorio_edificios[c] = relatorio_edificios[c].round(2)

    relatorio_edificios = relatorio_edificios.sort_values(
        by=["bairro_padronizado", "total_transacoes"], ascending=[True, False]
    ).reset_index(drop=True)
    relatorio_edificios.to_csv(RELATORIO_CSV, index=False, sep=";", encoding="utf-8-sig")
    print(f"Relatório detalhado de {len(relatorio_edificios):,} edifícios recuperados salvo em: {RELATORIO_CSV}")

    # Resumo agregado por bairro
    resumo_bairro = (
        relatorio_edificios.groupby("bairro_padronizado")
        .agg(
            edificios_recuperados=("endereco_edificio", "count"),
            transacoes_recuperadas=("total_transacoes", "sum"),
            m2_privativo_medio_bairro=("m2_privativo_medio", "mean"),
            valor_medio_imovel=("valor_medio_corrigido", "mean"),
        )
        .reset_index()
        .sort_values(by="transacoes_recuperadas", ascending=False)
        .reset_index(drop=True)
    )

    resumo_bairro["ranking"] = range(1, len(resumo_bairro) + 1)
    resumo_bairro["m2_privativo_medio_bairro"] = resumo_bairro["m2_privativo_medio_bairro"].round(2)
    resumo_bairro["valor_medio_imovel"] = resumo_bairro["valor_medio_imovel"].round(2)

    resumo_bairro = resumo_bairro[
        [
            "ranking",
            "bairro_padronizado",
            "edificios_recuperados",
            "transacoes_recuperadas",
            "m2_privativo_medio_bairro",
            "valor_medio_imovel",
        ]
    ]
    resumo_bairro.to_csv(RELATORIO_BAIRRO_CSV, index=False, sep=";", encoding="utf-8-sig")
    print(f"Resumo por bairro salvo em: {RELATORIO_BAIRRO_CSV}")

    print("\n" + "=" * 95)
    print("TOP 25 BAIRROS COM MAIS IMÓVEIS/TRANSAÇÕES QUE ESTAVAM OCULTOS NO MAPA E FORAM RECUPERADOS:")
    print("=" * 95)
    print(resumo_bairro.head(25).to_string(index=False))


if __name__ == "__main__":
    main()
