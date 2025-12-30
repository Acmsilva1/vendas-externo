import pandas as pd
import gspread
from datetime import datetime, date
import streamlit as st 
import time 

# --- CONFIGURAÇÕES FIXAS (NOVOS DADOS) ---
# NOVO ID da planilha fornecido pelo usuário
SPREADSHEET_ID_UNIFICADO = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug" 
# NOVAS ABAS (em minúsculo)
ABA_VENDAS = "vendas"
ABA_GASTOS = "gastos"

# Definindo o nome da coluna de item na planilha de Vendas (Ajustado para Confeitaria)
COLUNA_ITEM_VENDIDO = 'PRODUTO' 
# Definindo o nome da coluna de categoria na planilha de Gastos
COLUNA_CATEGORIA_GASTO = 'CATEGORIA' 

# --- FUNÇÃO HELPER PARA FORMATAR BRL ---
def format_brl(value):
    # Formata para R$ X.XXX,XX
    return f"R$ {value:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')

# --- FUNÇÕES DE LIMPEZA E CÁLCULO DE KPIS ---

def limpar_coluna_valor(df, coluna_original, coluna_limpa='Total Limpo'):
    """Limpa e converte a coluna de valor para numérico, removendo R$ e separadores."""
    if coluna_original not in df.columns:
        # Lança um erro claro se a coluna não for encontrada
        raise ValueError(f"A coluna '{coluna_original}' não foi encontrada no DataFrame. Verifique o nome da coluna na planilha!")

    df[coluna_limpa] = (
        df[coluna_original] 
        .astype(str)
        .str.replace('R$', '', regex=False)
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False)
        .str.strip()
    )
    df[coluna_limpa] = pd.to_numeric(df[coluna_limpa], errors='coerce')
    df.dropna(subset=[coluna_limpa], inplace=True)
    return df

def processar_data(df, coluna_data_hora):
    """Converte e extrai componentes de data/hora (Assume formato %d/%m/%Y %H:%M:%S)."""
    if coluna_data_hora not in df.columns:
        raise ValueError(f"A coluna '{coluna_data_hora}' não foi encontrada no DataFrame. Verifique o nome da coluna na planilha!")
        
    df['Data/Hora'] = pd.to_datetime(df[coluna_data_hora], errors='coerce', format='%d/%m/%Y %H:%M:%S')
    df.dropna(subset=['Data/Hora'], inplace=True)
    df['Data'] = df['Data/Hora'].dt.date
    df['Hora'] = df['Data/Hora'].dt.hour
    return df

def filtrar_por_mes_e_dia(df, data_atual: date):
    """Filtra o DataFrame estritamente para o mês e dia atual."""
    mes_atual = data_atual.month
    ano_atual = data_atual.year
    
    # Filtra pelo mês e ano vigentes
    df_mes = df[(df['Data/Hora'].dt.month == mes_atual) & (df['Data/Hora'].dt.year == ano_atual)].copy()
    # Filtra pelo dia vigente
    df_dia = df[df['Data'] == data_atual].copy()
    
    return df_mes, df_dia


@st.cache_data(ttl=300) 
def carregar_e_limpar_dados():
    st.set_page_config(layout="wide", page_title="💰 Dashboard Financeiro Confeitaria")
    
    data_atual = datetime.now().date()
    
    try:
        # 1. AUTENTICAÇÃO
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_key(SPREADSHEET_ID_UNIFICADO)

        # 2. CARREGAMENTO E LIMPEZA DE VENDAS
        df_vendas = pd.DataFrame(sh.worksheet(ABA_VENDAS).get_all_records())
        # Coluna de valor na ABA_VENDAS é 'VALOR DA VENDA'
        df_vendas = limpar_coluna_valor(df_vendas, 'VALOR DA VENDA') 
        # Coluna de data/hora na ABA_VENDAS é 'DATA E HORA'
        df_vendas = processar_data(df_vendas, 'DATA E HORA')
        df_vendas_mes, df_vendas_dia = filtrar_por_mes_e_dia(df_vendas, data_atual)

        # 3. CARREGAMENTO E LIMPEZA DE GASTOS
        df_gastos = pd.DataFrame(sh.worksheet(ABA_GASTOS).get_all_records())
        # Coluna de valor na ABA_GASTOS é 'VALOR' <--- AJUSTADO
        df_gastos = limpar_coluna_valor(df_gastos, 'VALOR') 
        # Coluna de data/hora na ABA_GASTOS é 'DATA E HORA'
        df_gastos = processar_data(df_gastos, 'DATA E HORA') 
        df_gastos_mes, df_gastos_dia = filtrar_por_mes_e_dia(df_gastos, data_atual)
        
    except ValueError as ve:
        st.error(f"ERRO CRÍTICO DE CONFIGURAÇÃO DE COLUNA: {ve}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    except Exception as e:
        st.error(f"ERRO DE CONEXÃO/AUTENTICAÇÃO: Verifique o ID '{SPREADSHEET_ID_UNIFICADO}', os nomes das abas ('{ABA_VENDAS}' e '{ABA_GASTOS}') e o Streamlit Secret. Detalhes: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()


    return df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia

def calcular_kpis_vendas(df_mes, df_dia):
    """Calcula KPIs essenciais de VENDAS para o painel clean."""
    kpis = {}
    
    # KPIs do Mês
    kpis['total_mes'] = df_mes['Total Limpo'].sum() if not df_mes.empty else 0.0
    kpis['contagem_mes'] = df_mes.shape[0]
    
    # KPIs do Dia
    kpis['total_dia'] = df_dia['Total Limpo'].sum() if not df_dia.empty else 0.0
    kpis['contagem_dia'] = df_dia.shape[0]

    # Dados Adicionais (Para texto descritivo)
    if not df_mes.empty and COLUNA_ITEM_VENDIDO in df_mes.columns:
        # Produto Campeão (Bolo Mais Vendido)
        kpis['item_campeao_mes'] = df_mes[COLUNA_ITEM_VENDIDO].mode().iloc[0] 
    else:
        kpis['item_campeao_mes'] = 'N/A'
        
    if not df_dia.empty:
        # Pico de Hora
        pico_hora_df = df_dia['Hora'].value_counts()
        kpis['pico_hora_dia'] = pico_hora_df.index[0] if not pico_hora_df.empty else 'N/A'
    else:
        kpis['pico_hora_dia'] = 'N/A'

    return kpis

def calcular_kpis_gastos(df_mes, df_dia):
    """Calcula KPIs essenciais de GASTOS para o painel clean."""
    kpis = {}
    
    # KPIs do Mês e Dia
    kpis['total_mes'] = df_mes['Total Limpo'].sum() if not df_mes.empty else 0.0
    kpis['total_dia'] = df_dia['Total Limpo'].sum() if not df_dia.empty else 0.0

    # Dados Adicionais (Para texto descritivo)
    if not df_mes.empty and COLUNA_CATEGORIA_GASTO in df_mes.columns:
        # Categoria de Gasto Principal
        gasto_por_categoria = df_mes.groupby(COLUNA_CATEGORIA_GASTO)['Total Limpo'].sum().sort_values(ascending=False)
        kpis['categoria_principal_mes'] = gasto_por_categoria.index[0] 
        kpis['gasto_principal_valor'] = gasto_por_categoria.iloc[0]
    else:
        kpis['categoria_principal_mes'] = 'N/A'
        kpis['gasto_principal_valor'] = 0.0
        
    return kpis
    
# --- FUNÇÃO PRINCIPAL DE MONTAGEM DO DASHBOARD STREAMLIT ---
def montar_dashboard(kpis_vendas, kpis_gastos):
    
    st.title(f"🎂 Painel de Confeitaria: Mês de {datetime.now().strftime('%B/%Y').upper()}")
    
    st.caption(f"Última atualização: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}** (Cache de 5 minutos)")

    
    # --- 1. RESULTADO LÍQUIDO DO MÊS (KPI CHAVE) ---
    st.header("🎯 Resultado Líquido do Mês Vigente")
    
    total_vendas_mes = kpis_vendas['total_mes']
    total_gastos_mes = kpis_gastos['total_mes']
    resultado_liquido = total_vendas_mes - total_gastos_mes
    
    # Analogia: É o que sobrou na vasilha depois que você tirou todos os ingredientes (gastos)
    cor_resultado = "normal" if resultado_liquido >= 0 else "inverse" 

    col_res_a, col_res_b = st.columns([2, 1])
    
    col_res_a.metric(
        label="LUCRO / PREJUÍZO (MÊS)", 
        value=format_brl(resultado_liquido),
        delta=f"Total Vendas: {format_brl(total_vendas_mes)} | Total Gastos: {format_brl(total_gastos_mes)}",
        delta_color=cor_resultado
    )
    
    # CMV Simplificado (Custos sobre Vendas)
    if total_vendas_mes > 0:
        custo_percentual = (total_gastos_mes / total_vendas_mes) * 100
        col_res_b.metric(
            label="% CUSTO/RECEITA",
            value=f"{custo_percentual:.1f}%",
            help="O custo operacional representa esta porcentagem da receita total. Quanto menor, melhor!"
        )

    st.divider()

    # --- 2. KPIS DE VENDAS E GASTOS (LINHA PRINCIPAL) ---
    st.header("💰 Vendas x Despesas (Valores e Quantidades)")
    
    col1, col2, col3, col4 = st.columns(4) 
    
    # Vendas Hoje (Valor)
    col1.metric(
        label="R$ VENDAS HOJE", 
        value=format_brl(kpis_vendas['total_dia']),
        delta=f"{kpis_vendas['contagem_dia']} unds vendidas",
        delta_color="off" 
    )

    # Vendas Mês (Valor)
    col2.metric(
        label="R$ VENDAS MÊS", 
        value=format_brl(kpis_vendas['total_mes']), 
        delta=f"{kpis_vendas['contagem_mes']} unds vendidas",
        delta_color="off"
    )
    
    # Gastos Hoje (Valor)
    col3.metric(
        label="R$ GASTOS HOJE", 
        value=format_brl(kpis_gastos['total_dia']),
        delta_color="inverse", 
        help="Gastos registrados na data atual."
    )
    
    # Gastos Mês (Valor)
    col4.metric(
        label="R$ GASTOS MÊS", 
        value=format_brl(kpis_gastos['total_mes']),
        delta_color="inverse", 
        help="Gastos totais registrados no mês vigente."
    )
    
    st.divider()

    # --- 3. DETALHES E INSIGHTS RÁPIDOS (UX CLEAN) ---
    st.header("🍰 Insights Rápidos")
    
    col_detalhe_a, col_detalhe_b, col_detalhe_c = st.columns(3)
    
    # Vendas: Produto Campeão
    col_detalhe_a.info(
        f"**Produto Campeão (Mês):** {kpis_vendas['item_campeao_mes']}. Foque no estoque e marketing dele!"
    )
    
    # Vendas: Pico de Vendas
    col_detalhe_b.info(
        f"**Pico de Vendas (Hoje):** {kpis_vendas['pico_hora_dia']}h. Prepare-se para este horário!"
    )

    # Gastos: Categoria mais cara
    col_detalhe_c.warning(
        f"**Maior Gasto (Mês):** {kpis_gastos['categoria_principal_mes']} ({format_brl(kpis_gastos['gasto_principal_valor'])}). Revise este custo!"
    )

# --- EXECUÇÃO PRINCIPAL STREAMLIT ---
if __name__ == "__main__":
    
    # Sarcasmo: O spinner está fazendo o trabalho pesado, como um batedor de claras elétrico.
    with st.spinner('Assando os dados, limpando e unificando Vendas e Gastos...'):
        time.sleep(1) 
        
        try:
            df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia = carregar_e_limpar_dados()
            
            if not df_vendas_mes.empty or not df_gastos_mes.empty:
                
                # 1. Calcula os KPIs
                kpis_vendas = calcular_kpis_vendas(df_vendas_mes, df_vendas_dia)
                kpis_gastos = calcular_kpis_gastos(df_gastos_mes, df_gastos_dia)
                
                # 2. Monta o Dashboard
                montar_dashboard(kpis_vendas, kpis_gastos)
                
            else:
                 st.info("⚠️ Nenhum dado de Vendas ou Gastos encontrado para o mês vigente. Verifique suas planilhas e o Streamlit Secrets.")

        except Exception as e:
            # Se o código quebrar, mostramos o traceback completo para debug.
            st.exception(f"Ocorreu um erro INESPERADO. Algo deu errado na sua receita de código! Detalhes: {e}")
