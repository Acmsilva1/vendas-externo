import pandas as pd
import gspread
from datetime import datetime, date
import streamlit as st 
import time 

# --- CONFIGURAÇÕES FIXAS ---
# ID da planilha fornecido pelo usuário
SPREADSHEET_ID_UNIFICADO = "1LuqYrfR8ry_MqCS93Pj9_7Vu0i9RUTomJU2n69bEug" 
# ABAS (em minúsculo)
ABA_VENDAS = "vendas"
ABA_GASTOS = "gastos"

# NOME DAS COLUNAS ESSENCIAIS NA SUA PLANILHA (CALIBRADO AGORA!)
# ABA VENDAS
COLUNA_ITEM_VENDIDO = 'SABORES'          # Item vendido (para Produto Campeão)
COLUNA_CLIENTE = 'DADOS DO COMPRADOR'    # Cliente (para Melhor Cliente)
COLUNA_VALOR_VENDA = 'VALOR DA VENDA'
# ABA GASTOS
COLUNA_ITEM_GASTO = 'PRODUTO'            # Item de Gasto (para Maior Gasto)
COLUNA_VALOR_GASTO = 'VALOR'
# COMUM
COLUNA_DATA_HORA = 'DATA E HORA'

# --- FUNÇÃO HELPER PARA FORMATAR BRL ---
def format_brl(value):
    return f"R$ {value:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')

# --- FUNÇÕES DE LIMPEZA E CÁLCULO DE KPIS ---

def limpar_coluna_valor(df, coluna_original, coluna_limpa='Total Limpo'):
    """Limpa e converte a coluna de valor para numérico, removendo R$ e separadores."""
    if coluna_original not in df.columns:
        raise ValueError(f"A coluna de valor '{coluna_original}' não foi encontrada na aba. Verifique o nome da coluna na planilha!")

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
    """Converte e extrai componentes de data/hora."""
    if coluna_data_hora not in df.columns:
        raise ValueError(f"A coluna de data/hora '{coluna_data_hora}' não foi encontrada na aba. Verifique o nome da coluna na planilha!")
        
    df['Data/Hora'] = pd.to_datetime(df[coluna_data_hora], errors='coerce', format='%d/%m/%Y %H:%M:%S')
    df.dropna(subset=['Data/Hora'], inplace=True)
    df['Data'] = df['Data/Hora'].dt.date
    df['Hora'] = df['Data/Hora'].dt.hour
    return df

def filtrar_por_mes_e_dia(df, data_atual: date):
    """Filtra o DataFrame estritamente para o mês e dia atual."""
    mes_atual = data_atual.month
    ano_atual = data_atual.year
    
    df_mes = df[(df['Data/Hora'].dt.month == mes_atual) & (df['Data/Hora'].dt.year == ano_atual)].copy()
    df_dia = df[df['Data'] == data_atual].copy()
    
    return df_mes, df_dia


@st.cache_data(ttl=0) # CORREÇÃO: TTL AGORA É ZERO (Cache desabilitado)
def carregar_e_limpar_dados():
    st.set_page_config(layout="wide", page_title="💰 Dashboard Financeiro Confeitaria")
    
    data_atual = datetime.now().date()
    
    try:
        # 1. AUTENTICAÇÃO
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_key(SPREADSHEET_ID_UNIFICADO)

        # 2. CARREGAMENTO E LIMPEZA DE VENDAS
        df_vendas = pd.DataFrame(sh.worksheet(ABA_VENDAS).get_all_records())
        df_vendas = limpar_coluna_valor(df_vendas, COLUNA_VALOR_VENDA) 
        df_vendas = processar_data(df_vendas, COLUNA_DATA_HORA)
        df_vendas_mes, df_vendas_dia = filtrar_por_mes_e_dia(df_vendas, data_atual)

        # 3. CARREGAMENTO E LIMPEZA DE GASTOS
        df_gastos = pd.DataFrame(sh.worksheet(ABA_GASTOS).get_all_records())
        df_gastos = limpar_coluna_valor(df_gastos, COLUNA_VALOR_GASTO) 
        df_gastos = processar_data(df_gastos, COLUNA_DATA_HORA) 
        df_gastos_mes, df_gastos_dia = filtrar_por_mes_e_dia(df_gastos, data_atual)
        
    except ValueError as ve:
        st.error(f"ERRO CRÍTICO DE CONFIGURAÇÃO DE COLUNA: {ve}") 
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame() 
    except Exception as e:
        # Silencia o erro de conexão/autenticação e retorna DataFrames vazios para acionar o standby.
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame() 


    return df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia

def calcular_kpis_vendas(df_mes, df_dia):
    """Calcula KPIs essenciais de VENDAS para o painel clean, com robustez a DataFrames vazios."""
    kpis = {}
    
    # KPIs de Totais (Seguros)
    kpis['total_mes'] = df_mes['Total Limpo'].sum() if not df_mes.empty else 0.0
    kpis['contagem_mes'] = df_mes.shape[0]
    kpis['total_dia'] = df_dia['Total Limpo'].sum() if not df_dia.empty else 0.0
    kpis['contagem_dia'] = df_dia.shape[0]

    # --- INSIGHTS ROBUSTOS (CORRIGIDOS PARA DATAFRAMES VAZIOS) ---

    # 1. Produto Campeão (Mês)
    kpis['item_campeao_mes'] = 'N/A'
    if not df_mes.empty and COLUNA_ITEM_VENDIDO in df_mes.columns:
        try:
             mode_result = df_mes[COLUNA_ITEM_VENDIDO].mode()
             kpis['item_campeao_mes'] = mode_result.iloc[0] if not mode_result.empty else 'Nenhum'
        except Exception:
             kpis['item_campeao_mes'] = 'N/A' 

    # 2. Melhor Cliente (Mês)
    kpis['melhor_cliente_mes'] = 'N/A'
    kpis['melhor_cliente_gasto'] = 0.0
    if not df_mes.empty and COLUNA_CLIENTE in df_mes.columns:
        try:
            melhor_cliente_df = df_mes.groupby(COLUNA_CLIENTE)['Total Limpo'].sum().sort_values(ascending=False)
            kpis['melhor_cliente_mes'] = melhor_cliente_df.index[0] if not melhor_cliente_df.empty else 'N/A'
            kpis['melhor_cliente_gasto'] = melhor_cliente_df.iloc[0] if not melhor_cliente_df.empty else 0.0
        except Exception:
            kpis['melhor_cliente_mes'] = 'N/A'
            kpis['melhor_cliente_gasto'] = 0.0

    # 3. Pico de Vendas (Hoje)
    pico_hora_str = 'N/A'
    if not df_dia.empty:
        pico_hora_df = df_dia['Hora'].value_counts()
        pico_hora_str = f"{pico_hora_df.index[0]}h" if not pico_hora_df.empty else 'N/A'
    kpis['pico_hora_dia'] = pico_hora_str

    return kpis

def calcular_kpis_gastos(df_mes, df_dia):
    """Calcula KPIs essenciais de GASTOS para o painel clean, com robustez a DataFrames vazios."""
    kpis = {}
    
    # KPIs do Mês e Dia (Seguros)
    kpis['total_mes'] = df_mes['Total Limpo'].sum() if not df_mes.empty else 0.0
    kpis['contagem_mes'] = df_mes.shape[0]
    kpis['total_dia'] = df_dia['Total Limpo'].sum() if not df_dia.empty else 0.0
    kpis['contagem_dia'] = df_dia.shape[0]

    # Dados Adicionais (Insights)
    kpis['item_principal_gasto_mes'] = 'N/A'
    kpis['gasto_principal_valor'] = 0.0
    if not df_mes.empty and COLUNA_ITEM_GASTO in df_mes.columns:
        try:
            gasto_por_item = df_mes.groupby(COLUNA_ITEM_GASTO)['Total Limpo'].sum().sort_values(ascending=False)
            kpis['item_principal_gasto_mes'] = gasto_por_item.index[0] if not gasto_por_item.empty else 'N/A' 
            kpis['gasto_principal_valor'] = gasto_por_item.iloc[0] if not gasto_por_item.empty else 0.0
        except Exception:
             kpis['item_principal_gasto_mes'] = 'N/A' 
             kpis['gasto_principal_valor'] = 0.0
        
    return kpis
    
# --- FUNÇÃO PRINCIPAL DE MONTAGEM DO DASHBOARD STREAMLIT ---
def montar_dashboard(kpis_vendas, kpis_gastos):
    
    st.title(f"🎂 Painel de Confeitaria: Mês de {datetime.now().strftime('%B/%Y').upper()}")
    
    st.caption(f"Última atualização: **{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}** (Recarga automática a cada 20s)")

    
    # --- 1. RESULTADO LÍQUIDO DO MÊS (KPI CHAVE) ---
    st.header("🎯 Resultado Líquido do Mês Vigente")
    
    total_vendas_mes = kpis_vendas['total_mes']
    total_gastos_mes = kpis_gastos['total_mes']
    resultado_liquido = total_vendas_mes - total_gastos_mes
    
    cor_resultado = "normal" if resultado_liquido >= 0 else "inverse" 

    col_res_a, col_res_b = st.columns([2, 1])
    
    col_res_a.metric(
        label="LUCRO / PREJUÍZO (MÊS)", 
        value=format_brl(resultado_liquido),
        delta=f"Total Vendas: {format_brl(total_vendas_mes)} | Total Gastos: {format_brl(total_gastos_mes)}",
        delta_color=cor_resultado
    )
    
    if total_vendas_mes > 0:
        custo_percentual = (total_gastos_mes / total_vendas_mes) * 100
        col_res_b.metric(
            label="% CUSTO/RECEITA",
            value=f"{custo_percentual:.1f}%",
            help="O custo operacional representa esta porcentagem da receita total."
        )
        
    # Sugestão de UX para dados incompletos
    if kpis_gastos['total_mes'] == 0 and total_vendas_mes > 0:
         st.warning("Atenção: Os gastos do mês ainda não foram registrados! O lucro exibido é provisório (Vendas - 0).")


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
        delta=f"{kpis_gastos['contagem_dia']} registros de gasto",
        delta_color="inverse", 
        help="Gastos registrados na data atual."
    )
    
    # Gastos Mês (Valor) 
    col4.metric(
        label="R$ GASTOS MÊS", 
        value=format_brl(kpis_gastos['total_mes']),
        delta=f"{kpis_gastos['contagem_mes']} registros de gasto",
        delta_color="inverse", 
        help="Gastos totais registrados no mês vigente."
    )
    
    st.divider()

    # --- 3. DETALHES E INSIGHTS RÁPIDOS (UX CLEAN) ---
    st.header("🍰 Insights Rápidos")
    
    col_detalhe_a, col_detalhe_b, col_detalhe_c, col_detalhe_d = st.columns(4)
    
    # Insight 1: Produto Campeão (Sabor)
    col_detalhe_a.info(
        f"**Sabor Mais Vendido (Mês):** {kpis_vendas['item_campeao_mes']}"
    )
    
    # Insight 2: Melhor Cliente 
    cliente_valor = format_brl(kpis_vendas['melhor_cliente_gasto'])
    col_detalhe_b.info(
        f"**Melhor Cliente (Mês):** {kpis_vendas['melhor_cliente_mes']} ({cliente_valor})."
    )
    
    # Insight 3: Pico de Vendas
    col_detalhe_c.info(
        f"**Pico de Vendas (Hoje):** {kpis_vendas['pico_hora_dia']}. Prepare-se para este horário!"
    )

    # Insight 4: Item/Produto de maior Gasto 
    gasto_valor = format_brl(kpis_gastos['gasto_principal_valor'])
    col_detalhe_d.warning(
        f"**Item de Maior Gasto (Mês):** {kpis_gastos['item_principal_gasto_mes']} ({gasto_valor}). Revise este custo!"
    )

# --- EXECUÇÃO PRINCIPAL STREAMLIT (FINAL) ---
if __name__ == "__main__":
    
    with st.spinner('Assando os dados, limpando e unificando Vendas e Gastos...'):
        time.sleep(1) 
        
        try:
            df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia = carregar_e_limpar_dados()
            
            # Checa se há dados (vendas ou gastos) para o mês atual. 
            dados_do_mes_encontrados = not df_vendas_mes.empty or not df_gastos_mes.empty
            
            if dados_do_mes_encontrados:
                
                # 1. Calcula os KPIs
                kpis_vendas = calcular_kpis_vendas(df_vendas_mes, df_vendas_dia)
                kpis_gastos = calcular_kpis_gastos(df_gastos_mes, df_gastos_dia)
                
                # 2. Monta o Dashboard
                montar_dashboard(kpis_vendas, kpis_gastos)
                
                # --- NOVO BLOCO: RECARGA AUTOMÁTICA ---
                # A tela de dados foi montada, então programamos a próxima recarga
                time.sleep(20) # Aguarda 20 segundos
                st.rerun() # Força a reexecução do script (Streamlit > 1.25.0)

            else:
                 # Mensagem de Standby (Aguardando dados ou erro de conexão)
                 st.info("Novo mês! Aguardando dados para análise.")
                 
                 # Se estiver em standby, espera 20s e tenta carregar novamente.
                 time.sleep(20) 
                 st.rerun()

        except Exception as e:
            st.exception(f"Ocorreu um erro INESPERADO. Algo deu errado na sua receita de código! Detalhes: {e}")
