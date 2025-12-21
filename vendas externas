import pandas as pd
import gspread
import os
import plotly.express as px
from datetime import datetime
import json 
import streamlit as st # 🌟 Novo Import
import time # Para simular o loading

# --- FUNÇÃO HELPER PARA FORMATAR BRL (MANTIDA) ---
def format_brl(value):
    # Formata para R$ X.XXX,XX
    return f"R$ {value:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')

# --- CONFIGURAÇÕES E AUTENTICAÇÃO (ADAPTADA AO STREAMLIT) ---
# O Streamlit lida com segredos via 'st.secrets'.
# Usaremos a configuração do gspread diretamente no st.secrets.
SPREADSHEET_ID = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug"
WORKSHEET_NAME = "vendas"

# Usamos o decorator st.cache_data para manter o código limpo
# e garantir que a leitura da planilha só ocorra a cada 5 minutos (ttl=300s)
# ou quando o usuário apertar 'Rerun'.
@st.cache_data(ttl=300) 
def carregar_e_limpar_dados():
    # 1. AUTENTICAÇÃO SEGURA NO STREAMLIT
    # O arquivo de credenciais é injetado automaticamente como st.secrets["gcp_service_account"]
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception as e:
        # 🚨 AVISO DE GOVERNANÇA: Se o segredo não estiver configurado, avisa
        st.error(f"ERRO DE AUTENTICAÇÃO: O Streamlit Secret 'gcp_service_account' não está configurado. Detalhes: {e}")
        # Retorna DataFrames vazios para evitar crash total
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df

    # 2. CARREGAMENTO
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        worksheet = sh.worksheet(WORKSHEET_NAME)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
    except Exception as e:
        st.error(f"ERRO AO ABRIR PLANILHA: {e}. Verifique o ID e o nome da aba.")
        empty_df = pd.DataFrame()
        return empty_df, empty_df, empty_df

    # 3. Limpeza da Coluna 'VALOR DA VENDA' e criação de 'Total Limpo' (MANTIDO)
    df['Total Limpo'] = (
        df['VALOR DA VENDA'] 
        .astype(str)
        .str.replace('R$', '', regex=False)
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False)
        .str.strip()
    )
    df['Total Limpo'] = pd.to_numeric(df['Total Limpo'], errors='coerce')
    df.dropna(subset=['Total Limpo'], inplace=True)

    # 4. Conversão da Coluna de Data/Hora (MANTIDO)
    df['Data/Hora Venda'] = pd.to_datetime(df['DATA E HORA'], errors='coerce', format='%d/%m/%Y %H:%M:%S')
    df.dropna(subset=['Data/Hora Venda'], inplace=True)
    df['Hora'] = df['Data/Hora Venda'].dt.hour
    
    if df.empty:
        raise ValueError("O DataFrame está vazio após a limpeza de datas/valores.")

    # 5. FILTRAGEM TEMPORAL (MANTIDO)
    data_atual = datetime.now().date()
    df_dia_atual = df[df['Data/Hora Venda'].dt.date == data_atual].copy()
    mes_atual = data_atual.month
    ano_atual = data_atual.year
    df_mes_atual = df[(df['Data/Hora Venda'].dt.month == mes_atual) & (df['Data/Hora Venda'].dt.year == ano_atual)].copy()

    return df, df_mes_atual, df_dia_atual

# --- FUNÇÃO HELPER PARA CÁLCULOS ROBUSTOS (MANTIDA) ---
# Não precisa de cache, pois opera sobre DF que já está cacheado
def calcular_kpis(df, periodo="Dia"):
    if df.empty:
        return {
            'total': 0.0,
            'total_fmt': format_brl(0.0),
            'sabor': f'Sem Vendas ({periodo})',
            'cliente': f'N/A ({periodo})',
            'cliente_gasto_fmt': format_brl(0.0),
            'pico_hora': 'N/A'
        }
    
    total_vendas = df['Total Limpo'].sum()
    sabor_mais_vendido = df['SABORES'].mode().iloc[0] if not df['SABORES'].empty else f'N/A ({periodo})'
    
    # 🚨 PONTO DE ATENÇÃO LGPD: Usando 'DADOS DO COMPRADOR'
    melhor_cliente_df = df.groupby('DADOS DO COMPRADOR')['Total Limpo'].sum().sort_values(ascending=False)
    
    # TRATAMENTO DE ERRO NO CLIENTE
    melhor_cliente = melhor_cliente_df.index[0] if not melhor_cliente_df.empty else f'N/A ({periodo})'
    melhor_cliente_gasto = melhor_cliente_df.iloc[0] if not melhor_cliente_df.empty else 0.0
    
    pico_hora_df = df['Hora'].value_counts()
    pico_hora = pico_hora_df.index[0] if not pico_hora_df.empty else 'N/A'
    
    return {
        'total': total_vendas,
        'total_fmt': format_brl(total_vendas),
        'sabor': sabor_mais_vendido,
        'cliente': melhor_cliente,
        'cliente_gasto_fmt': format_brl(melhor_cliente_gasto),
        'pico_hora': pico_hora
    }

# --- FUNÇÃO PRINCIPAL DE MONTAGEM DO DASHBOARD STREAMLIT ---
def montar_dashboard(df_completo, df_mes, df_dia):
    st.set_page_config(layout="wide", page_title="Dashboard Multicamadas de Vendas")
    
    st.title("🍦 Painel de Controle de Vendas (Ativo) 🚀")
    
    # Exibe o status da atualização
    st.caption(f"Dados atualizados em: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}** (Cache de 5 minutos)")

    # --- 1. CÁLCULOS DOS KPIS ---
    kpis_mes = calcular_kpis(df_mes, periodo="Mês")
    kpis_dia = calcular_kpis(df_dia, periodo="Dia")
    
    # --- 2. KPIS MENSAIS (COLUNAS) ---
    st.header("Contexto Mensal (Acumulado)")
    col1, col2, col3 = st.columns(3)

    col1.metric("Total Arrecadado (MÊS)", kpis_mes['total_fmt'], delta=None, delta_color="normal", help="Total de vendas brutas do mês atual.")
    col2.metric("Sabor Campeão (MÊS)", kpis_mes['sabor'], delta=None, delta_color="normal", help="O item mais vendido em quantidade.")
    
    # 🚨 ALERTA DE LGPD no Dashboard Público
    col3.metric("Melhor Cliente (MÊS)", f"{kpis_mes['cliente']} | {kpis_mes['cliente_gasto_fmt']}", delta=None, delta_color="normal", help="Cliente que mais gastou (Mês). Considere anonimizar no código!")

    # --- 3. KPIS DIÁRIOS (COLUNAS) ---
    st.divider()
    st.header("Foco Diário (Hoje)")
    col_a, col_b, col_c = st.columns(3)

    col_a.metric("Total Arrecadado (HOJE)", kpis_dia['total_fmt'], delta=None, delta_color="normal", help="Total de vendas brutas do dia atual.")
    col_b.metric("Sabor Campeão (HOJE)", kpis_dia['sabor'], delta=None, delta_color="normal", help="O item mais vendido hoje em quantidade.")
    col_c.metric("Pico de Vendas (HOJE)", f"{kpis_dia['pico_hora']}h", delta=None, delta_color="normal", help="Hora com maior frequência de vendas.")

    st.divider()

    # --- 4. VISUALIZAÇÕES COM PLOTLY (EM COLUNAS DE WIDE SCREEN) ---
    
    st.header("Visualizações Chave")
    
    # Dividindo a tela para gráficos
    chart_col1, chart_col2 = st.columns(2)

    # Gráfico 1: Vendas por Sabor/Item (Mensal)
    with chart_col1:
        st.subheader("Top 10 Sabores/Itens Mais Vendidos (Mês)")
        vendas_por_item = df_mes['SABORES'].value_counts().reset_index() 
        vendas_por_item.columns = ['Item', 'Contagem']
        
        fig_sabor = px.bar(
            vendas_por_item.head(10).sort_values(by='Contagem', ascending=True), 
            x='Contagem', y='Item', 
            orientation='h', 
            template='plotly_dark'
        )
        st.plotly_chart(fig_sabor, use_container_width=True)

    # Gráfico 3: Melhores Clientes por Gasto Total (Mensal)
    with chart_col2:
        st.subheader("Top 5 Clientes (Mês) ⚠️ LGPD")
        melhor_cliente_df_mes = df_mes.groupby('DADOS DO COMPRADOR')['Total Limpo'].sum().sort_values(ascending=False)
        fig_cliente = px.bar(
            melhor_cliente_df_mes.head(5).reset_index().rename(columns={'Total Limpo': 'Gasto Total'}),
            x='Gasto Total', y='DADOS DO COMPRADOR', # Invertendo para melhor leitura de nomes longos
            orientation='h',
            template='plotly_dark'
        )
        st.plotly_chart(fig_cliente, use_container_width=True)

    # Gráfico 2: Pico de Vendas por Hora do Dia (Diário) - Em linha cheia
    st.subheader(f'Frequência de Vendas por Hora (Hoje)')
    pico_hora_df_dia = df_dia['Hora'].value_counts().sort_index().reset_index()
    pico_hora_df_dia.columns = ['Hora', 'Número de Vendas']
    
    fig_hora = px.bar(
        pico_hora_df_dia, 
        x='Hora', y='Número de Vendas', 
        template='plotly_dark',
        title=f'Pico: {kpis_dia["pico_hora"]}h'
    )
    fig_hora.update_xaxes(tick0=0, dtick=1)
    st.plotly_chart(fig_hora, use_container_width=True)
    
# --- EXECUÇÃO PRINCIPAL STREAMLIT ---
if __name__ == "__main__":
    
    # Simula um loading bar/spinner para UX
    with st.spinner('Puxando os dados da planilha, limpando e analisando...'):
        time.sleep(1) # Simula um pequeno delay
        
        try:
            df_completo, df_mes, df_dia = carregar_e_limpar_dados()
            
            # Execução final, se não houver erro
            if not df_completo.empty:
                montar_dashboard(df_completo, df_mes, df_dia)
            else:
                 st.warning("⚠️ Sem dados disponíveis ou erro de carregamento. Verifique a planilha.")

        except ValueError as ve:
            st.error(f"🛑 ERRO CRÍTICO DE DADOS: Ocorreu um problema na limpeza ou filtragem. Detalhes: {ve}")
        except Exception as e:
            st.exception(f"Ocorreu um erro INESPERADO. Tente novamente mais tarde. {e}")
