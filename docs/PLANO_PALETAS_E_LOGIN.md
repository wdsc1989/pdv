# Paletas de tema e tela de login editável (plano atualizado)

## 1. Tema: paletas predefinidas com variantes

Substituir os quatro color pickers por **paletas** em que cada uma usa variantes da mesma família (ex.: rosa claro, rosa médio, rosa escuro). Pelo menos **20 paletas**, cada uma com as 4 chaves: `primaryColor`, `backgroundColor`, `secondaryBackgroundColor`, `textColor`.

### 1.1 Lista de paletas (20+)

Cada linha é uma paleta: nome; depois `backgroundColor`, `secondaryBackgroundColor`, `textColor`, `primaryColor` (todas em hex). Variantes: fundo mais escuro, secundário médio, texto legível, primária como destaque da família.

| # | Nome | backgroundColor | secondaryBackgroundColor | textColor | primaryColor |
|---|------|-----------------|--------------------------|-----------|--------------|
| 0 | Padrão Streamlit | (vazio – sem override) |
| 1 | Rosa claro | #fff0f5 | #ffd6e3 | #4a0e29 | #c71585 |
| 2 | Rosa médio | #ffc0cb | #ff69b4 | #2d0d1a | #db7093 |
| 3 | Rosa escuro | #4a0e29 | #6b1d3d | #ffe4ec | #ff69b4 |
| 4 | Azul claro | #e6f3ff | #b3d9ff | #0a1628 | #0066cc |
| 5 | Azul médio | #4682b4 | #6b9ed4 | #e8f4fc | #1e3a5f |
| 6 | Azul escuro | #0d2137 | #1a3a52 | #e8f4fc | #38bdf8 |
| 7 | Verde claro | #e8f5e9 | #a5d6a7 | #1b2e1b | #2e7d32 |
| 8 | Verde médio | #388e3c | #66bb6a | #e8f5e9 | #1b5e20 |
| 9 | Verde escuro | #0f1419 | #1c2d24 | #e6f0e6 | #22c55e |
| 10 | Roxo claro | #f3e5f5 | #e1bee7 | #2d1b3d | #7b1fa2 |
| 11 | Roxo médio | #7b1fa2 | #9c27b0 | #f3e5f5 | #4a148c |
| 12 | Roxo escuro | #1e0a2e | #2d1b4e | #e8daef | #bb86fc |
| 13 | Laranja claro | #fff8e1 | #ffecb3 | #2e2100 | #ff8f00 |
| 14 | Laranja médio | #e65100 | #ff9800 | #fff8e1 | #ffb74d |
| 15 | Laranja escuro | #2e2100 | #4a3300 | #fff8e1 | #ffb74d |
| 16 | Vermelho claro | #ffebee | #ffcdd2 | #2d0a0a | #c62828 |
| 17 | Vermelho médio | #c62828 | #ef5350 | #ffebee | #b71c1c |
| 18 | Vermelho escuro | #2d0a0a | #5c1a1a | #ffebee | #ef5350 |
| 19 | Cinza claro | #fafafa | #eeeeee | #212121 | #616161 |
| 20 | Cinza escuro | #121212 | #262730 | #e0e0e0 | #b0b0b0 |
| 21 | Turquesa claro | #e0f7fa | #b2ebf2 | #0d2d30 | #00838f |
| 22 | Turquesa escuro | #0d2d30 | #1a4a4f | #e0f7fa | #26c6da |
| 23 | Índigo claro | #e8eaf6 | #c5cae9 | #1a1a2e | #3949ab |
| 24 | Índigo escuro | #1a1a2e | #2d2d44 | #e8eaf6 | #7986cb |
| 25 | Âmbar escuro | #1a1510 | #2d2518 | #fff8e1 | #ffb300 |

Implementação em código: em [utils/theme_config.py](utils/theme_config.py) definir um dicionário `THEME_PALETTES` com essas 26 entradas (chave = nome exibido, valor = dict com as 4 chaves; "Padrão Streamlit" = `{}`). Na Admin, um único `st.selectbox` com as opções; ao Salvar, gravar o dict da paleta em `theme_config.json` (igual ao fluxo atual).

### 1.2 UI em [pages/10_Admin.py](pages/10_Admin.py)

- Expander "Cores das páginas (tema)": remover os 4 color pickers; usar `st.selectbox("Paleta", options=list(THEME_PALETTES.keys()))`; Salvar grava `save_theme_config(THEME_PALETTES[selecionado])`; Restaurar padrão grava `save_theme_config({})`. Pré-seleção: comparar `load_theme_config()` com cada paleta; se coincidir, selecionar essa opção; senão "Padrão Streamlit".

---

## 2. Tela de login editável

- **Criar** [utils/login_config.py](utils/login_config.py): mesmo padrão de `receipt_config`; `config/login_config.json`; DEFAULTS com `login_title`, `login_subtitle`, `login_show_logo`; `load_login_config()`, `save_login_config()`.
- **Alterar** [app.py](app.py) em `login_page()`: usar `load_login_config()` para título e subtítulo; se `get_sidebar_logo_path()` existir e `login_show_logo` True, exibir logo no topo; depois título e subtítulo; resto do formulário igual.
- **Alterar** [pages/10_Admin.py](pages/10_Admin.py): novo expander **"Tela de login"** com campos título e subtítulo, texto explicando que a logo é a mesma do menu, checkbox "Exibir logo na tela de login", botão Salvar.

---

## 3. Resumo de arquivos

| Ação | Arquivo |
|------|---------|
| Alterar | utils/theme_config.py – adicionar THEME_PALETTES com as 26 paletas acima |
| Alterar | pages/10_Admin.py – tema: selectbox de paletas; novo expander "Tela de login" |
| Criar | utils/login_config.py |
| Alterar | app.py – login_page() com login_config e logo |
