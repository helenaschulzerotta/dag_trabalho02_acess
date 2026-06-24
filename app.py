"""
Dashboard de Acessibilidade Urbana — Itens 11, 12 e 13
=========================================================
Lê os resultados já calculados pelo notebook Acessibilidade_Urbana_r5py.ipynb
(GeoJSONs + meta.json exportados na Seção 10.1 — ver export_results.py)
e reproduz:

  11 · Análise comparativa Modo A vs Modo B
  12 · Mapa interativo (Folium)
  13 · Análise de equidade — zonas críticas

Não recalcula nada do r5py — isso é feito uma única vez no notebook.
"""

import io
import json
import requests

import geopandas as gpd
import pandas as pd
import numpy as np
import streamlit as st
import folium
import plotly.express as px
from streamlit_folium import st_folium

st.set_page_config(page_title="Acessibilidade Urbana", page_icon="🗺️", layout="wide")

NOMES = {"saude": "Saúde", "educacao": "Educação", "assist_social": "Assist. Social"}
BINS = [0, 15, 30, 45, 60, float("inf")]
LABELS_CAT = ["≤ 15 min", "16–30 min", "31–45 min", "46–60 min", "> 60 min"]
COR_CAT = {
    "≤ 15 min": "#1a9641",
    "16–30 min": "#a6d96a",
    "31–45 min": "#ffffbf",
    "46–60 min": "#fdae61",
    "> 60 min": "#d7191c",
    "sem dados": "#cccccc",
}


# ──────────────────────────────────────────────────────────────────────────
# Carregamento dos dados (direto do GitHub)
# ──────────────────────────────────────────────────────────────────────────
GITHUB_RAW_BASE = (
    "https://raw.githubusercontent.com/helenaschulzerotta/dag_trabalho02_acess/"
    "604b0e4d2765104ccd367b5ed7ffcb4f2aebc5a1"
)

BAIRROS_URL = (
    "https://raw.githubusercontent.com/helenaschulzerotta/dag_trabalho02_acess/"
    "b0429fca1aff4e7769d2944864eb3e729ac296d7/DIVISA_DE_BAIRROS.geojson"
)

def _get(url: str) -> bytes:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


@st.cache_data(show_spinner="Carregando dados do GitHub...")
def carregar_dados(base_url: str):
    try:
        meta = json.loads(_get(f"{base_url}/meta.json"))
    except Exception as e:
        st.error(f"Não foi possível ler meta.json em {base_url}: {e}")
        return None, None, None

    resultados_A, resultados_B = {}, {}
    try:
        for chave in NOMES:
            resultados_A[chave] = gpd.read_file(
                io.BytesIO(_get(f"{base_url}/resultados_A_{chave}.geojson"))
            )
            resultados_B[chave] = gpd.read_file(
                io.BytesIO(_get(f"{base_url}/resultados_B_{chave}.geojson"))
            )
    except Exception as e:
        st.error(f"Não foi possível ler os GeoJSONs em {base_url}: {e}")
        return None, None, None

    return meta, resultados_A, resultados_B

@st.cache_data(show_spinner="Carregando camada de bairros...")
def carregar_bairros():
    try:
        gdf = gpd.read_file(io.BytesIO(_get(BAIRROS_URL)))
        # SIRGAS 2000 22S (EPSG:31982) → WGS84 para Folium
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:31982")
        gdf = gdf.to_crs("EPSG:4326")
        return gdf
    except Exception as e:
        st.warning(f"Não foi possível carregar a camada de bairros: {e}")
        return None
  
def _cat_tempo(serie: pd.Series) -> pd.Series:
    """Converte coluna de tempo numérico para categoria de faixa."""
    return pd.cut(serie, bins=BINS, labels=LABELS_CAT, right=True).astype(str).fillna("sem dados")

def calcular_diferencas(resultados_A, resultados_B):
    """Item 11 — diferença de tempo (Modo A − Modo B) por hexágono."""
    diferencas = {}
    for chave in NOMES:
        dfA = resultados_A[chave][["id", "tempo_min", "geometry"]].rename(
            columns={"tempo_min": "tempo_A"}
        )
        dfB = resultados_B[chave][["id", "tempo_min"]].rename(
            columns={"tempo_min": "tempo_B"}
        )
        df = dfA.merge(dfB, on="id", how="left")
        df["delta"] = df["tempo_A"] - df["tempo_B"]
        df["cat_A"] = _cat_tempo(df["tempo_A"])
        df["cat_B"] = _cat_tempo(df["tempo_B"])
        diferencas[chave] = df
    return diferencas


def calcular_criticos(resultados_A, limiar):
    """Item 13 — hexágonos com tempo no Modo A acima do limiar."""
    criticos = {}
    for chave in NOMES:
        df = resultados_A[chave][["id", "tempo_min", "geometry"]].copy()
        df["cat"] = _cat_tempo(df["tempo_min"])
        criticos[chave] = df[df["tempo_min"] > limiar].copy()
    return criticos


def centro_mapa(resultados_A):
    geom = pd.concat([resultados_A[c] for c in NOMES])["geometry"]
    c = geom.union_all().centroid
    return [c.y, c.x]

def _adicionar_bairros(m: folium.Map, gdf_bairros):
    """Adiciona camada de divisas de bairros ao mapa Folium."""
    if gdf_bairros is None:
        return
    fg = folium.FeatureGroup(name="Divisas de Bairros", show=True)
    nome_col = "NOME" if "NOME" in gdf_bairros.columns else None
    tooltip_fields = [nome_col] if nome_col else []
    tooltip_aliases = ["Bairro:"] if nome_col else []
    folium.GeoJson(
        gdf_bairros.__geo_interface__,
        style_function=lambda f: {
            "fillColor": "none",
            "color": "#333333",
            "weight": 1.2,
            "fillOpacity": 0,
            "dashArray": "4 3",
        },
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields,
            aliases=tooltip_aliases,
            sticky=False,
        ) if tooltip_fields else None,
    ).add_to(fg)
    fg.add_to(m)
 
 
def _legenda_html(titulo: str = "Tempo de acesso") -> str:
    """Gera HTML de legenda flutuante para os mapas Folium."""
    itens = ""
    for label, cor in COR_CAT.items():
        itens += (
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">'
            f'<div style="width:18px;height:14px;background:{cor};'
            f'border:1px solid #888;border-radius:2px;flex-shrink:0"></div>'
            f'<span style="font-size:12px">{label}</span></div>'
        )
    return (
        '<div style="'
        "position:fixed;bottom:30px;right:10px;"
        "background:rgba(255,255,255,0.92);padding:10px 14px;"
        "border-radius:6px;border:1px solid #ccc;"
        "box-shadow:2px 2px 6px rgba(0,0,0,.2);"
        "z-index:9999;font-family:sans-serif;min-width:130px;"
        '">'
        f'<b style="font-size:12px">{titulo}</b><br><br>'
        f"{itens}"
        "</div>"
    )

# ──────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────
st.sidebar.title("🗺️ Acessibilidade Urbana")
base_url = st.sidebar.text_input("URL base dos dados (GitHub raw)", value=GITHUB_RAW_BASE)

meta, resultados_A, resultados_B = carregar_dados(base_url)
bairros_gdf = carregar_bairros()

if meta is None:
    st.warning(
        f"Não encontrei os arquivos esperados em `{base_url}/`.\n\n"
        "São necessários: `meta.json`, `resultados_A_<tipo>.geojson`, "
        "`resultados_B_<tipo>.geojson` para `<tipo>` em saude, educacao, assist_social."
    )
    st.stop()

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Município:** {meta['CIDADE']}")
st.sidebar.markdown(f"**Partida:** {meta.get('DEPARTURE', '—')}")
st.sidebar.markdown(f"**Modo A:** {meta['LABEL_A']}")
st.sidebar.markdown(f"**Modo B:** {meta['LABEL_B']}")
st.sidebar.markdown(f"**Resolução H3:** {meta.get('H3_RES', '—')}")

limiar_critico = st.sidebar.slider(
    "Limiar crítico (min) — item 13", 15, 90, int(meta.get("LIMIAR_CRITICO", 45)), step=5
)

diferencas = calcular_diferencas(resultados_A, resultados_B)
criticos = calcular_criticos(resultados_A, limiar_critico)
centro = centro_mapa(resultados_A)

st.title("Acessibilidade Urbana com r5py")
st.caption(
    f"{meta['CIDADE']} · {meta['LABEL_A']} vs {meta['LABEL_B']} · "
    f"partida {meta.get('DEPARTURE', '—')}"
)

tab11, tab12, tab13, tab_sobre = st.tabs(
    ["11 · Comparativo A vs B", "12 · Mapa interativo", "13 · Zonas críticas", "ℹ️ Sobre"]
)

# ──────────────────────────────────────────────────────────────────────────
# Item 11 — Análise comparativa Modo A vs Modo B
# ──────────────────────────────────────────────────────────────────────────
with tab11:
    st.subheader("Análise comparativa: Modo A vs Modo B")
    st.markdown(
        f"Diferença de tempo (**{meta['LABEL_A']} − {meta['LABEL_B']}**) por hexágono. "
        "Valores positivos indicam que o Modo A é mais lento; negativos, mais rápido."
    )

    cols = st.columns(3)
    for col, chave in zip(cols, NOMES):
        df = diferencas[chave]
        pct_a_pior = (df["delta"] > 0).mean() * 100
        with col:
            st.metric(NOMES[chave], f"{df['delta'].mean():+.1f} min (média)")
            st.caption(f"Modo A mais lento em {pct_a_pior:.1f}% dos hexágonos")
            st.caption(
                f"Médias: A = {df['tempo_A'].mean():.1f} min · "
                f"B = {df['tempo_B'].mean():.1f} min"
            )

    chave_sel = st.selectbox(
        "Tipo de equipamento", list(NOMES.keys()), format_func=lambda k: NOMES[k], key="sel11"
    )
    df_sel = diferencas[chave_sel]

    # ── Gráficos de barras por faixa de tempo (cores alinhadas com o mapa) ──
    st.markdown("#### Distribuição por faixa de tempo")
    c_bar1, c_bar2 = st.columns(2)
 
    for col_bar, modo_col, label_modo in [
        (c_bar1, "cat_A", meta["LABEL_A"]),
        (c_bar2, "cat_B", meta["LABEL_B"]),
    ]:
        contagem = (
            df_sel[modo_col]
            .value_counts()
            .reindex(LABELS_CAT + ["sem dados"], fill_value=0)
            .reset_index()
        )
        contagem.columns = ["Faixa", "Hexágonos"]
        contagem = contagem[contagem["Hexágonos"] > 0]
 
        fig_bar = px.bar(
            contagem,
            x="Faixa",
            y="Hexágonos",
            color="Faixa",
            color_discrete_map=COR_CAT,
            title=f"{label_modo} — {NOMES[chave_sel]}",
            labels={"Faixa": "Faixa de tempo", "Hexágonos": "Nº de hexágonos"},
            category_orders={"Faixa": LABELS_CAT + ["sem dados"]},
        )
        fig_bar.update_layout(showlegend=False)
        with col_bar:
            st.plotly_chart(fig_bar, use_container_width=True)
 
    # ── Histograma de diferenças + mapa delta ──
    st.markdown("#### Diferença A − B por hexágono")
    c1, c2 = st.columns([1, 1])
    with c1:
        fig = px.histogram(
            df_sel, x="delta", nbins=30,
            labels={"delta": "Diferença A − B (min)"},
            title=f"Distribuição das diferenças — {NOMES[chave_sel]}",
        )
        fig.add_vline(x=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig, width="stretch")

    with c2:
        gdf_delta = gpd.GeoDataFrame(df_sel, geometry="geometry", crs="EPSG:4326")
        m_delta = folium.Map(location=centro, zoom_start=11, tiles="CartoDB positron")
        folium.Choropleth(
            geo_data=gdf_delta.__geo_interface__,
            data=gdf_delta,
            columns=["id", "delta"],
            key_on="feature.properties.id",
            fill_color="RdYlGn_r",
            fill_opacity=0.75,
            line_weight=0.3,
            legend_name=f"Diferença A − B (min) — {NOMES[chave_sel]}",
        ).add_to(m_delta)
        _adicionar_bairros(m_delta, bairros_gdf)
        folium.LayerControl(collapsed=False).add_to(m_delta)
        st_folium(m_delta, height=380, use_container_width=True, key="mapa_delta")

# ──────────────────────────────────────────────────────────────────────────
# Item 12 — Mapa interativo
# ──────────────────────────────────────────────────────────────────────────
with tab12:
    st.subheader("Mapa interativo")
    st.markdown(
        "Use o controle de camadas para alternar entre tipo de equipamento e modo de transporte."
    )

    @st.cache_resource(show_spinner="Montando mapa...")
    def montar_mapa_completo(_resultados_A, _resultados_B, _bairros, centro, label_a, label_b):
        m = folium.Map(location=centro, zoom_start=11, tiles="CartoDB positron")

        for i, (chave, nome) in enumerate(NOMES.items()):
            for j, (res, label) in enumerate(
                [(_resultados_A, label_a), (_resultados_B, label_b)]
            ):
                fg_name = f"{nome} — {label}"
                fg = folium.FeatureGroup(name=fg_name, show=(i == 0 and j == 0))
                for _, row in res[chave].iterrows():
                    cat = str(row.get("categoria", "sem dados"))
                    cor = COR_CAT.get(cat, "#cccccc")
                    tval = row.get("tempo_min")
                    tip = (
                        f"<b>{fg_name}</b><br>Tempo: {tval:.0f} min<br>Faixa: {cat}"
                        if pd.notna(tval)
                        else f"<b>{fg_name}</b><br>Sem acesso"
                    )
                    folium.GeoJson(
                        row.geometry.__geo_interface__,
                        style_function=lambda f, c=cor: {
                            "fillColor": c, "color": "#888", "weight": 0.3, "fillOpacity": 0.7
                        },
                        tooltip=tip,
                    ).add_to(fg)
                fg.add_to(m)

        _adicionar_bairros(m, _bairros)
        folium.LayerControl(collapsed=False).add_to(m)
        m.get_root().html.add_child(folium.Element(_legenda_html("Tempo de acesso")))
        return m

    m_completo = montar_mapa_completo(
        resultados_A, resultados_B, bairros_gdf, centro, meta["LABEL_A"], meta["LABEL_B"]
    )
    st_folium(m_completo, height=600, use_container_width=True, key="mapa_completo")

    with st.expander("Paleta de cores"):
        st.write({k: v for k, v in COR_CAT.items()})

# ──────────────────────────────────────────────────────────────────────────
# Item 13 — Análise de equidade: zonas críticas
# ──────────────────────────────────────────────────────────────────────────
with tab13:
    st.subheader("Análise de equidade — zonas críticas")
    st.markdown(
        f"Hexágonos onde o tempo de acesso pelo **{meta['LABEL_A']}** supera "
        f"**{limiar_critico} min** para pelo menos um tipo de equipamento."
    )

    cols = st.columns(3)
    for col, chave in zip(cols, NOMES):
        total = len(resultados_A[chave])
        n_crit = len(criticos[chave])
        pct = n_crit / total * 100 if total else 0
        with col:
            st.metric(NOMES[chave], f"{n_crit} hexágonos", f"{pct:.1f}% do total")

    all_critical_ids = pd.concat(
        [d["id"] for d in criticos.values()]
    ).unique() if any(len(d) for d in criticos.values()) else []
    st.info(f"**Total geral** — hexágonos críticos em ao menos um serviço: {len(all_critical_ids)}")

    chave_sel13 = st.selectbox(
        "Tipo de equipamento", list(NOMES.keys()), format_func=lambda k: NOMES[k], key="sel13"
    )
    df_crit_sel = criticos[chave_sel13]
    if len(df_crit_sel) > 0:
        contagem_crit = (
            df_crit_sel["cat"]
            .value_counts()
            .reindex(LABELS_CAT + ["sem dados"], fill_value=0)
            .reset_index()
        )
        contagem_crit.columns = ["Faixa", "Hexágonos"]
        contagem_crit = contagem_crit[contagem_crit["Hexágonos"] > 0]
        fig_crit = px.bar(
            contagem_crit,
            x="Faixa", y="Hexágonos",
            color="Faixa",
            color_discrete_map=COR_CAT,
            title=f"Zonas críticas — {NOMES[chave_sel13]} (> {limiar_critico} min)",
            category_orders={"Faixa": LABELS_CAT + ["sem dados"]},
        )
        fig_crit.update_layout(showlegend=False)
        st.plotly_chart(fig_crit, use_container_width=True)
  
    m_crit = folium.Map(location=centro, zoom_start=11, tiles="CartoDB positron")
    for chave, df_crit in criticos.items():
        fg = folium.FeatureGroup(
            name=f"{NOMES[chave]} — crítico (> {limiar_critico} min)", show=True
        )
        for _, row in df_crit.iterrows():
            cat = str(row.get("cat", "sem dados"))
            cor = COR_CAT.get(cat, "#cccccc")
            tip = (
                f"<b>{NOMES[chave]} (crítico)</b><br>"
                f"Tempo: {row['tempo_min']:.0f} min<br>Faixa: {cat}"
            )
            folium.GeoJson(
                row.geometry.__geo_interface__,
                style_function=lambda f, c=cor: {
                    "fillColor": c, "color": "#888", "weight": 0.3, "fillOpacity": 0.7
                },
                tooltip=tip,
            ).add_to(fg)
        fg.add_to(m_crit)
    _adicionar_bairros(m_crit, bairros_gdf)
    folium.LayerControl(collapsed=False).add_to(m_crit)
    m_crit.get_root().html.add_child(folium.Element(_legenda_html("Tempo de acesso")))
    st_folium(m_crit, height=550, use_container_width=True, key="mapa_criticos")

# ──────────────────────────────────────────────────────────────────────────
# Sobre
# ──────────────────────────────────────────────────────────────────────────
with tab_sobre:
    st.subheader("Sobre este trabalho")
 
    st.markdown(
        "Este dashboard é o **Trabalho 02** da disciplina "
        "**Desenvolvimento de Aplicações Geoespaciais**, ofertada pela "
        "**Profª. Drª. Silvana Camboim** para o "
        "**Programa de Pós-Graduação em Planejamento Urbano (PPU)** "
        "da **Universidade Federal do Paraná (UFPR)**."
    )
 
    st.markdown("---")
    st.markdown("### O que é acessibilidade urbana?")
    st.markdown(
        "Acessibilidade urbana mede a **facilidade com que pessoas alcançam oportunidades** — "
        "empregos, serviços de saúde, educação, assistência social — a partir de onde vivem, "
        "considerando o sistema de transporte e o uso do solo.\n\n"
        "Na perspectiva do **IPEA (Instituto de Pesquisa Econômica Aplicada)**, acessibilidade "
        "urbana vai além da simples mobilidade (capacidade de se deslocar): ela indica "
        "**quantas oportunidades estão disponíveis a uma determinada distância ou tempo de "
        "viagem**. Métricas de acessibilidade revelam desigualdades territoriais ao mostrar "
        "que populações em periferias ou com acesso restrito ao transporte coletivo enfrentam "
        "barreiras estruturais para atingir serviços essenciais, mesmo quando esses serviços "
        "existem na cidade."
    )
 
    st.markdown("---")
    st.markdown("### Dados e metodologia")
 
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(
            "**Fontes de dados**\n"
            "- 🗺️ **Malha viária:** OpenStreetMap (OSM), recortada para a área de estudo\n"
            "- 🏥 **Equipamentos públicos:** OpenStreetMap — unidades de saúde, escolas e "
            "centros de assistência social\n"
            "- 🚌 **GTFS (transporte coletivo):** disponibilizado pela "
            "**Prefeitura Municipal de Curitiba**\n"
            "- 🏘️ **Divisas de bairros:** Prefeitura Municipal de Curitiba (SIRGAS 2000 22S)"
        )
    with col_b:
        st.markdown(
            "**Ferramentas e bibliotecas**\n"
            "- 🐍 **Python:** r5py, geopandas, pandas, H3, Folium, Streamlit, Plotly\n"
            "- 🔷 **Grade espacial:** hexágonos H3 como unidades de origem\n"
            "- ⏱️ **Matriz de tempo:** calculada via `r5py.TravelTimeMatrix` para cada modo "
            "e tipo de equipamento\n"
            "- 📓 **Notebook de cálculo:** disponível no "
            "[repositório GitHub](https://github.com/helenaschulzerotta/dag_trabalho02_acess)"
        )
 
    st.markdown("---")
    st.info(
        "O cálculo das matrizes de tempo de viagem é realizado **uma única vez no notebook "
        "Colab** (`Acessibilidade_Urbana_r5py.ipynb`), e os resultados são exportados como "
        "GeoJSONs. Este dashboard apenas lê e visualiza esses resultados — não há "
        "reprocessamento em tempo real.\n\n"
        "📂 **Repositório:** "
        "[github.com/helenaschulzerotta/dag_trabalho02_acess]"
        "(https://github.com/helenaschulzerotta/dag_trabalho02_acess)"
    )
