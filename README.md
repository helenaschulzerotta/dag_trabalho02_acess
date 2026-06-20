# dag_trabalho02_acess
Repositório com o Trabalho 02 da disciplina Desenvolvimento de Aplicações Geoespaciais, ofertada pela Profª. Drª. Silvana Camboim para o Programa Pós Graduação em Planejamento Urbano (PPU) da Universidade Federal do Paraná (UFPR). O trabalho apresenta um caderno utilizando a biblioteca r5py e um dashboard com seus resultados.

# Dashboard de Acessibilidade Urbana (itens 11–13)

## Como usar

1. **No notebook**: rode normalmente até a Seção 14 (resultados_A e resultados_B precisam existir e ser exportados).

2. **Copie a pasta `data/`** para o mesmo diretório de `app.py`.

## O que cada aba mostra

- **11 · Comparativo A vs B** — diferença de tempo por hexágono (A − B), médias por tipo de equipamento, % de hexágonos onde A é mais lento, histograma e mapa coroplético da diferença.
- **12 · Mapa interativo** — réplica do mapa Folium do notebook, com controle de camadas por tipo de equipamento × modo de transporte.
- **13 · Zonas críticas** — hexágonos acima do limiar de tempo (padrão 45 min, ajustável na barra lateral), com contagem por tipo e mapa de sobreposição.

O app **não recalcula nada do r5py** — ele só lê os arquivos exportados, então abre em segundos mesmo para municípios grandes.
