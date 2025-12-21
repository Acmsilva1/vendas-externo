import pandas as pd
import gspread
import os
import plotly.express as px
from datetime import datetime
import json 
import streamlit as st 
import time 
import numpy as np # Adicionado para usar funções matemáticas no delta

# --- FUNÇÃO HELPER PARA FORMATAR BRL (MANTIDA) ---
def format_brl(value):
    # Formata para R$ X.XXX,XX
    return f"R$ {value:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')

# --- CONFIGURAÇÕES E AUTENTICAÇÃO (ADAPTADA AO STREAMLIT) ---
SPREADSHEET_ID = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug"
WORKSHEET_NAME = "vendas"

# Usamos o decorator st.cache_data para manter o código limpo
@st.cache_data(ttl=300) 
def carregar_e_limpar_dados():
    # 1. AUTENTICAÇÃO SEGURA NO STREAMLIT
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    except Exception as e:
        st.error(f"ERRO DE AUTENTICAÇÃO: O Streamlit Secret 'gcp_service_account' não está configurado. Detalhes: {e}")
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
    df['Data'] = df['Data/Hora Venda'].dt.date # Adicionando coluna Data apenas
    df['Hora'] = df['Data/Hora Venda'].dt.hour
    
    if df.empty:
        raise ValueError("O DataFrame está vazio após a limpeza de datas/valores.")

    # 5. FILTRAGEM TEMPORAL (MANTIDO)
    data_atual = datetime.now().date()
    df_dia_atual = df[df['Data'] == data_atual].copy()
    mes_atual = data_atual.month
    ano_atual = data_atual.year
    df_mes_atual = df[(df['Data/Hora Venda'].dt.month == mes_atual) & (df['Data/Hora Venda'].dt.year == ano_atual)].copy()

    return df, df_mes_atual, df_dia_atual

# --- FUNÇÃO HELPER PARA CÁLCULOS ROBUSTOS (MANTIDA) ---
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
    
    st.caption(f"Dados atualizados em: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}** (Cache de 5 minutos)")

    # --- 1. CÁLCULOS DOS KPIS ---
    kpis_mes = calcular_kpis(df_mes, periodo="Mês")
    kpis_dia = calcular_kpis(df_dia, periodo="Dia")
    
    # --- NOVOS CÁLCULOS DE CONTAGEM E DELTA ---
    
    # 1.1. Contagem Diária (HOJE)
    vendas_hoje_count = df_dia.shape[0]
    
    # 1.2. Contagem Diária (ONTEM - Para o Delta)
    data_ontem = datetime.now().date() - pd.Timedelta(days=1)
    df_ontem = df_completo[df_completo['Data'] == data_ontem]
    vendas_ontem_count = df_ontem.shape[0]
    
    # 1.3. Contagem Mensal (Este Mês)
    vendas_mes_count = df_mes.shape[0]
    
    # 1.4. Contagem Mensal (Mês Passado - Para o Delta)
    data_mes_passado = datetime.now().date().replace(day=1) - pd.Timedelta(days=1)
    mes_passado = data_mes_passado.month
    ano_mes_passado = data_mes_passado.year
    df_mes_passado = df_completo[
        (df_completo['Data/Hora Venda'].dt.month == mes_passado) & 
        (df_completo['Data/Hora Venda'].dt.year == ano_mes_passado)
    ]
    vendas_mes_passado_count = df_mes_passado.shape[0]

    # --- 2. KPIS DE CONTAGEM E VALOR (LINHA PRINCIPAL) ---
    st.header("Visão Geral Rápida")
    col0_a, col0_b, col0_c, col0_d = st.columns(4) # Quatro colunas para as métricas mais importantes
    
    # Métrica 1: Vendas Hoje (Contagem)
    delta_diario_count = ventas_hoje_count - vendas_ontem_count
    col0_a.metric(
        label="VENDAS HOJE", 
        value=f"{vendas_hoje_count} un", 
        delta=f"{delta_diario_count} vs Ontem",
        delta_color="normal"
    )

    # Métrica 2: Vendas Mês (Contagem)
    # Delta simples: Vendas do Mês Atual vs Vendas Totais do Mês Passado
    if vendas_mes_passado_count == 0:
        delta_mensal_count = "N/A"
    else:
        # Calcula o percentual de crescimento em relação ao mês passado
        delta_mensal_count = f"{((vendas_mes_count / vendas_mes_passado_count) - 1) * 100:.1f}%"
        # Garante que o delta seja exibido como número positivo/negativo no st.metric
        # Usamos numpy.sign para determinar a cor do delta
        delta_color = "normal" if np.sign(float(delta_mensal_count.replace('%', ''))) >= 0 else "inverse" 

    col0_b.metric(
        label="VENDAS MÊS", 
        value=f"{vendas_mes_count} un", 
        delta=delta_mensal_count if vendas_mes_passado_count > 0 else None,
        delta_color=delta_color if vendas_mes_passado_count > 0 else "off"
    )

    # Métrica 3: Arrecadação Hoje
    delta_arrecadado_diario = kpis_dia['total'] - df_ontem['Total Limpo'].sum()
    col0_c.metric(
        label="R$ HOJE", 
        value=kpis_dia['total_fmt'], 
        delta=format_brl(delta_arrecadado_diario) if delta_arrecadado_diario != 0 else None,
        delta_color="normal"
    )
    
    # Métrica 4: Arrecadação Mês
    delta_arrecadado_mensal = kpis_mes['total'] - df_mes_passado['Total Limpo'].sum()
    col0_d.metric(
        label="R$ MÊS", 
        value=kpis_mes['total_fmt'], 
        delta=format_brl(delta_arrecadado_mensal) if delta_arrecadado_mensal != 0 else None,
        delta_color="normal"
    )
    
    st.divider()
    
    # --- 3. KPIS MENSAIS (MÉTRICAS SECUNDÁRIAS) ---
    st.header("Contexto Mensal (Acumulado)")
    col1, col2, col3 = st.columns(3)

    col1.metric("Sabor Campeão (MÊS)", kpis_mes['sabor'], delta=None, delta_color="normal", help="O item mais vendido em quantidade.")
    col2.metric("Pico de Vendas (HOJE)", f"{kpis_dia['pico_hora']}h", delta=None, delta_color="normal", help="Hora com maior frequência de vendas.")

    # 🚨 ALERTA DE LGPD no Dashboard Público
    col3.metric("Melhor Cliente (MÊS)", f"{kpis_mes['cliente']} | {kpis_mes['cliente_gasto_fmt']}", delta=None, delta_color="normal", help="Cliente que mais gastou (Mês). Considere anonimizar no código!")

    st.divider()

    # --- 4. VISUALIZAÇÕES COM PLOTLY (EM COLUNAS DE WIDE SCREEN) ---
    st.header("Visualizações Chave")
    
    # O restante dos gráficos... (MANTIDOS)
    
# --- EXECUÇÃO PRINCIPAL STREAMLIT ---
if __name__ == "__main__":
    
    with st.spinner('Puxando os dados da planilha, limpando e analisando...'):
        time.sleep(1) 
        
        try:
            df_completo, df_mes, df_dia = carregar_e_limpar_dados()
            
            if not df_completo.empty:
                montar_dashboard(df_completo, df_mes, df_dia)
            else:
                 st.warning("⚠️ Sem dados disponíveis ou erro de carregamento. Verifique a planilha.")

        except ValueError as ve:
            st.error(f"🛑 ERRO CRÍTICO DE DADOS: Ocorreu um problema na limpeza ou filtragem. Detalhes: {ve}")
        except Exception as e:
            st.exception(f"Ocorreu um erro INESPERADO. Tente novamente mais tarde. {e}")
