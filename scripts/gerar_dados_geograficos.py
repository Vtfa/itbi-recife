import os
import json
import pandas as pd
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV_INPUT = os.path.join(BASE_DIR, "data", "processed", "itbi_consolidado_corrigido.csv")
OUTPUT_ENDERECOS = os.path.join(BASE_DIR, "data", "processed", "imoveis_por_endereco_detalhado.csv")
OUTPUT_PREDIOS = os.path.join(BASE_DIR, "data", "processed", "resumo_por_edificio_logradouro.csv")
OUTPUT_HTML_MAPA = os.path.join(BASE_DIR, "mapa_imoveis_recife.html")

def main():
    print(f"Lendo base corrigida ({CSV_INPUT})...")
    df = pd.read_csv(CSV_INPUT, sep=';', encoding='utf-8-sig', low_memory=False)
    
    # Formatar endereço completo padronizado
    df['logradouro_fmt'] = df['logradouro'].fillna('').astype(str).str.strip().str.title()
    df['numero_fmt'] = df['numero'].fillna('').astype(str).str.replace('.0', '', regex=False).str.strip()
    df['complemento_fmt'] = df['complemento'].fillna('').astype(str).str.strip().str.title()
    
    df['endereco_edificio'] = df['logradouro_fmt'] + ', ' + df['numero_fmt'] + ' - ' + df['bairro_padronizado']
    df['endereco_completo'] = df['logradouro_fmt'] + ', ' + df['numero_fmt'] + ' ' + df['complemento_fmt'] + ' - ' + df['bairro_padronizado']
    
    # Salvar base detalhada por imóvel individual
    colunas_detalhe = [
        'endereco_completo', 'endereco_edificio', 'bairro_padronizado', 'logradouro_fmt', 'numero_fmt', 'complemento_fmt',
        'tipo_imovel', 'padrao_acabamento', 'data_transacao', 'ano_arquivo',
        'valor_avaliacao_corrigido', 'valor_num', 'area_privativa_estimada', 'area_total_cadastral',
        'preco_m2_privativo_corrigido', 'preco_m2_total_corrigido', 'latitude', 'longitude'
    ]
    
    df_detalhe = df[colunas_detalhe].copy()
    df_detalhe.to_csv(OUTPUT_ENDERECOS, index=False, sep=';', encoding='utf-8-sig')
    print(f"Base com endereços detalhados salva em: {OUTPUT_ENDERECOS}")
    
    # Agrupar por Edifício / Número de Logradouro (ex: condomínios / prédios específicos)
    valid_m2 = df[(df['preco_m2_privativo_corrigido'] > 500) & (df['preco_m2_privativo_corrigido'] < 30000)].copy()
    
    predios = valid_m2.groupby(['endereco_edificio', 'bairro_padronizado', 'logradouro_fmt', 'numero_fmt']).agg(
        total_transacoes=('valor_avaliacao_corrigido', 'count'),
        m2_privativo_medio=('preco_m2_privativo_corrigido', 'mean'),
        m2_privativo_mediana=('preco_m2_privativo_corrigido', 'median'),
        valor_medio_corrigido=('valor_avaliacao_corrigido', 'mean'),
        valor_min_corrigido=('valor_avaliacao_corrigido', 'min'),
        valor_max_corrigido=('valor_avaliacao_corrigido', 'max'),
        area_privativa_media=('area_privativa_estimada', 'mean'),
        latitude=('latitude', 'first'),
        longitude=('longitude', 'first')
    ).reset_index()
    
    # Arredondar valores
    for c in ['m2_privativo_medio', 'm2_privativo_mediana', 'valor_medio_corrigido', 'valor_min_corrigido', 'valor_max_corrigido', 'area_privativa_media']:
        predios[c] = predios[c].round(2)
        
    predios = predios.sort_values(by='total_transacoes', ascending=False).reset_index(drop=True)
    predios.to_csv(OUTPUT_PREDIOS, index=False, sep=';', encoding='utf-8-sig')
    print(f"Resumo por Edifício / Logradouro salvo em: {OUTPUT_PREDIOS}")
    
    # Criar um mapa HTML interativo usando Leaflet
    print(f"Gerando mapa interativo em {OUTPUT_HTML_MAPA}...")
    
    # Filtrar pontos com coordenadas válidas para o mapa (top 3.000 edifícios com mais transações para performance ágil no browser)
    mapa_pts = predios.dropna(subset=['latitude', 'longitude']).head(2500).to_dict(orient='records')
    
    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mapa Imobiliário de Recife - Preço do m² e Avaliação ITBI</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css" />
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
        #map {{ height: 100vh; width: 100vw; }}
        .info-panel {{
            position: absolute; top: 15px; right: 15px; z-index: 1000;
            background: white; padding: 15px 20px; border-radius: 8px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2); max-width: 350px;
        }}
        .info-panel h2 {{ margin: 0 0 8px 0; font-size: 18px; color: #1e3a8a; }}
        .info-panel p {{ margin: 4px 0; font-size: 13px; color: #475569; }}
        .badge {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-weight: bold; font-size: 12px; }}
        .badge-high {{ background: #fee2e2; color: #991b1b; }}
        .badge-med {{ background: #fef3c7; color: #92400e; }}
        .badge-low {{ background: #dcfce7; color: #166534; }}
    </style>
</head>
<body>
    <div class="info-panel">
        <h2>Recife Imóveis (ITBI)</h2>
        <p>Valores corrigidos pelo <b>IPCA</b> e ajustados para <b>Área Privativa</b>.</p>
        <p>Clique nos pontos para ver valores médios por condomínio/endereço.</p>
    </div>
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
    <script>
        const map = L.map('map').setView([-8.0578, -34.8829], 12);
        L.tileLayer('https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}{{r}}.png?key=cb1_2n9t_1_2003e8cc97c46d8ede889365', {{
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
            subdomains: 'abcd',
            maxZoom: 20
        }}).addTo(map);

        const markers = L.markerClusterGroup({{ chunkedLoading: true }});
        const data = {json.dumps(mapa_pts)};

        data.forEach(p => {{
            const lat = parseFloat(p.latitude);
            const lng = parseFloat(p.longitude);
            if (!isNaN(lat) && !isNaN(lng)) {{
                const precoM2 = p.m2_privativo_medio;
                let cor = '#10b981';
                if (precoM2 > 8000) cor = '#ef4444';
                else if (precoM2 > 6500) cor = '#f59e0b';
                else if (precoM2 > 5000) cor = '#3b82f6';

                const marker = L.circleMarker([lat, lng], {{
                    radius: Math.min(Math.max(p.total_transacoes * 1.2, 5), 14),
                    fillColor: cor,
                    color: '#ffffff',
                    weight: 1.5,
                    opacity: 1,
                    fillOpacity: 0.8
                }});

                const popupContent = `
                    <div style="font-family: sans-serif; min-width: 220px;">
                        <h4 style="margin: 0 0 6px 0; color: #0f172a;">${{p.endereco_edificio}}</h4>
                        <p style="margin: 3px 0; font-size: 13px;"><b>Bairro:</b> ${{p.bairro_padronizado}}</p>
                        <p style="margin: 3px 0; font-size: 13px;"><b>Preço Médio / m² Priv.:</b> <span style="color: #1e3a8a; font-weight: bold;">R$ ${{p.m2_privativo_medio.toLocaleString('pt-BR')}}</span></p>
                        <p style="margin: 3px 0; font-size: 13px;"><b>Valor Médio do Imóvel:</b> R$ ${{p.valor_medio_corrigido.toLocaleString('pt-BR')}}</p>
                        <p style="margin: 3px 0; font-size: 13px;"><b>Área Privativa Média:</b> ${{p.area_privativa_media}} m²</p>
                        <p style="margin: 3px 0; font-size: 12px; color: #64748b;"><b>Transações Registradas:</b> ${{p.total_transacoes}}</p>
                    </div>
                `;
                marker.bindPopup(popupContent);
                markers.addLayer(marker);
            }}
        }});

        map.addLayer(markers);
    </script>
</body>
</html>"""
    
    with open(OUTPUT_HTML_MAPA, 'w', encoding='utf-8') as f:
        f.write(html_content)
        
    print(f"Mapa gerado com sucesso em {OUTPUT_HTML_MAPA}")

if __name__ == "__main__":
    main()
