"""
Dashboard de Acessibilidade Urbana =========================================================
Lê os resultados já calculados pelo notebook Acessibilidade_Urbana_r5py.ipynb e reproduz:

  11 · Análise comparativa Modo A vs Modo B
  12 · Mapa interativo (Folium)
  13 · Análise de equidade — zonas críticas

Não recalcula nada do r5py — isso é feito uma única vez no notebook.
"""

import json
from pathlib import Path

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
# Carregamento dos dados
# ──────────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def carregar_dados(pasta: str):
    pasta = Path(pasta)
    meta_path = pasta / "meta.json"
    if not meta_path.exists():
        return None, None, None

    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    resultados_A, resultados_B = {}, {}
    for chave in NOMES:
        fa = pasta / f"resultados_A_{chave}.geojson"
        fb = pasta / f"resultados_B_{chave}.geojson"
        if not (fa.exists() and fb.exists()):
            return None, None, None
        resultados_A[chave] = gpd.read_file(fa)
        resultados_B[chave] = gpd.read_file(fb)

    return meta, resultados_A, resultados_B


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
        diferencas[chave] = df
    return diferencas


def calcular_criticos(resultados_A, limiar):
    """Item 13 — hexágonos com tempo no Modo A acima do limiar."""
    criticos = {}
    for chave in NOMES:
        df = resultados_A[chave][["id", "tempo_min", "geometry"]].copy()
        criticos[chave] = df[df["tempo_min"] > limiar].copy()
    return criticos


def centro_mapa(resultados_A):
    geom = pd.concat([resultados_A[c] for c in NOMES])["geometry"]
    c = geom.union_all().centroid
    return [c.y, c.x]


# ──────────────────────────────────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────────────────────────────────
st.sidebar.title("🗺️ Acessibilidade Urbana")
pasta_dados = st.sidebar.text_input("Pasta com os dados exportados", value="data")

meta, resultados_A, resultados_B = carregar_dados(pasta_dados)

if meta is None:
    st.warning(
        f"Não encontrei os arquivos esperados em `{pasta_dados}/`.\n\n"
        "Execute a célula de exportação ao final do notebook "
        "(Seção 10.1 · Exportar resultados) para gerar:\n"
        "`meta.json`, `resultados_A_<tipo>.geojson`, `resultados_B_<tipo>.geojson`."
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

tab11, tab12, tab13 = st.tabs(
    ["11 · Comparativo A vs B", "12 · Mapa interativo", "13 · Zonas críticas"]
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
    def montar_mapa_completo(_resultados_A, _resultados_B, centro, label_a, label_b):
        m = folium.Map(location=centro, zoom_start=11, tiles="CartoDB positron")

        def adicionar_camada(resultado_df, nome_camada, mapa):
            fg = folium.FeatureGroup(name=nome_camada, show=True)
            for _, row in resultado_df.iterrows():
                cat = str(row.get("categoria", "sem dados"))
                cor = COR_CAT.get(cat, "#cccccc")
                tval = row.get("tempo_min")
                tip = (
                    f"<b>{nome_camada}</b><br>Tempo: {tval:.0f} min<br>Faixa: {cat}"
                    if pd.notna(tval)
                    else f"<b>{nome_camada}</b><br>Sem acesso"
                )
                folium.GeoJson(
                    row.geometry.__geo_interface__,
                    style_function=lambda f, c=cor: {
                        "fillColor": c, "color": "#888", "weight": 0.3, "fillOpacity": 0.7
                    },
                    tooltip=tip,
                ).add_to(fg)
            fg.add_to(mapa)

        for chave, nome in NOMES.items():
            adicionar_camada(_resultados_A[chave], f"{nome} — {label_a}", m)
            adicionar_camada(_resultados_B[chave], f"{nome} — {label_b}", m)

        folium.LayerControl(collapsed=False).add_to(m)
        return m

    m_completo = montar_mapa_completo(
        resultados_A, resultados_B, centro, meta["LABEL_A"], meta["LABEL_B"]
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

    m_crit = folium.Map(location=centro, zoom_start=11, tiles="CartoDB positron")
    for chave, df_crit in criticos.items():
        fg = folium.FeatureGroup(
            name=f"{NOMES[chave]} — crítico (> {limiar_critico} min)", show=True
        )
        for _, row in df_crit.iterrows():
            cat = pd.cut([row["tempo_min"]], bins=BINS, labels=LABELS_CAT, right=True)[0]
            cor = COR_CAT.get(str(cat), "#cccccc")
            tip = f"<b>{NOMES[chave]} (crítico)</b><br>Tempo: {row['tempo_min']:.0f} min"
            folium.GeoJson(
                row.geometry.__geo_interface__,
                style_function=lambda f, c=cor: {
                    "fillColor": c, "color": "#888", "weight": 0.3, "fillOpacity": 0.7
                },
                tooltip=tip,
            ).add_to(fg)
        fg.add_to(m_crit)
    folium.LayerControl(collapsed=False).add_to(m_crit)
    st_folium(m_crit, height=550, use_container_width=True, key="mapa_criticos")
