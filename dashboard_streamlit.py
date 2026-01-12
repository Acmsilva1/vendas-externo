import pandas as pd
import gspread
from datetime import datetime, date, timedelta
import streamlit as st 
import time 
import pytz 
import plotly.express as px # NOVO: Importação do Plotly para os gráficos

# --- CONFIGURAÇÕES FIXAS ---
# ID da planilha fornecido pelo usuário
SPREADSHEET_ID_UNIFICADO = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug" 
# ABAS (em minúsculo)
ABA_VENDAS = "vendas"
ABA_GASTOS = "gastos"

# NOME DAS COLUNAS ESSENCIAIS NA SUA PLANILHA
# ABA VENDAS
COLUNA_ITEM_VENDIDO = 'SABORES'          
COLUNA_CLIENTE = 'DADOS DO COMPRADOR'    
COLUNA_VALOR_VENDA = 'VALOR DA VENDA'
# ABA GASTOS
COLUNA_ITEM_GASTO = 'PRODUTO'            
COLUNA_VALOR_GASTO = 'VALOR'
# COMUM
COLUNA_DATA_HORA = 'DATA E HORA'

# --- FUNÇÃO HELPER PARA FORMATAR BRL ---
def format_brl(value):
    """Formata valor float para a representação R$ X.XXX,XX."""
    return f"R$ {value:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')

# --- FUNÇÕES DE LIMPEZA E CÁLCULO DE KPIS ---

def limpar_coluna_valor(df, coluna_original, coluna_limpa='Total Limpo'):
    """Limpa e converte a coluna de valor para numérico, removendo R$ e separadores."""
    if coluna_original not in df.columns:
        raise ValueError(f"A coluna de valor '{coluna_original}' está vazia!")

    df[coluna_limpa] = (
        df[coluna_original] 
        .astype(str)
        .str.replace('R$', '', regex=False)
        .str.replace('.', '', regex=False)
        .str.replace(',', '.', regex=False) # Troca vírgula por ponto (separador decimal)
        .str.strip()
    )
    df[coluna_limpa] = pd.to_numeric(df[coluna_limpa], errors='coerce')
    df.dropna(subset=[coluna_limpa], inplace=True)
    return df

def processar_data(df, coluna_data_hora):
    """Converte e extrai componentes de data/hora (Assume formato %d/%m/%Y %H:%M:%S)."""
    if coluna_data_hora not in df.columns:
        raise ValueError(f"A coluna de data/hora '{coluna_data_hora}' está vazia!")
        
    df['Data/Hora'] = pd.to_datetime(df[coluna_data_hora], errors='coerce', format='%d/%m/%Y %H:%M:%S')
    df.dropna(subset=['Data/Hora'], inplace=True)
    df['Data'] = df['Data/Hora'].dt.date
    df['Hora'] = df['Data/Hora'].dt.hour
    return df

def filtrar_por_mes_e_dia(df, data_foco: date):
    """Filtra o DataFrame estritamente para o mês e dia de foco."""
    mes_foco = data_foco.month
    ano_foco = data_foco.year
        
    if 'Data/Hora' not in df.columns:
        return pd.DataFrame(), pd.DataFrame() 
        
    df_mes = df[(df['Data/Hora'].dt.month == mes_foco) & (df['Data/Hora'].dt.year == ano_foco)].copy()
    df_dia = df[df['Data'] == data_foco].copy()
    
    return df_mes, df_dia

def carregar_e_limpar_dados():
    st.set_page_config(layout="wide", page_title="💰 Controle de vendas diário")
    
    # AJUSTE: Definindo o FUSO HORÁRIO de São Paulo (Brasília)
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    agora_brasilia = datetime.now(fuso_brasilia) 
    data_atual = agora_brasilia.date()
    data_anterior = data_atual - timedelta(days=1) # Data do dia anterior
    
    # Inicializa DataFrames
    df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia, df_vendas_anterior = [pd.DataFrame() for _ in range(5)]

    try:
        # 1. AUTENTICAÇÃO
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_key(SPREADSHEET_ID_UNIFICADO)

        # 2. CARREGAMENTO E LIMPEZA DE VENDAS (CRÍTICO)
        try:
            df_vendas = pd.DataFrame(sh.worksheet(ABA_VENDAS).get_all_records())
            df_vendas = limpar_coluna_valor(df_vendas, COLUNA_VALOR_VENDA) 
            df_vendas = processar_data(df_vendas, COLUNA_DATA_HORA)
            
            # FILTROS DE DATAS
            df_vendas_mes, df_vendas_dia = filtrar_por_mes_e_dia(df_vendas, data_atual)
            df_vendas_anterior = df_vendas[df_vendas['Data'] == data_anterior].copy() 

        except ValueError as ve:
            raise ValueError(f"Erro CRÍTICO na aba VENDAS: {ve}")


        # 3. CARREGAMENTO E LIMPEZA DE GASTOS (TOLERANTE)
        try:
            df_gastos = pd.DataFrame(sh.worksheet(ABA_GASTOS).get_all_records())
            df_gastos = limpar_coluna_valor(df_gastos, COLUNA_VALOR_GASTO) 
            df_gastos = processar_data(df_gastos, COLUNA_DATA_HORA) 
            df_gastos_mes, df_gastos_dia = filtrar_por_mes_e_dia(df_gastos, data_atual)
        except Exception as e:
             st.warning(f"⚠️ Sem dados de gasto para análise. Erro de conexão/processamento da aba GASTOS: {e}")
             # Deixa os DataFrames de Gasto vazios
             pass 


    except ValueError as ve:
        st.error(f"ERRO CRÍTICO DE CONFIGURAÇÃO: {ve}")
        return [pd.DataFrame()] * 5
    except Exception as e:
        st.error(f"ERRO DE CONEXÃO/AUTENTICAÇÃO GERAL: Verifique o ID, abas e Secret. Detalhes: {e}")
        return [pd.DataFrame()] * 5


    return df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia, df_vendas_anterior

def calcular_kpis_vendas(df_mes, df_dia, df_anterior):
    """Calcula KPIs essenciais de VENDAS para o painel clean, incluindo a comparação com o Dia Anterior."""
    kpis = {}
        
    def contar_itens(df):
        if df.empty or COLUNA_ITEM_VENDIDO not in df.columns:
            return 0
        contagens = df[COLUNA_ITEM_VENDIDO].fillna('').astype(str).str.split(',').apply(len)
        return contagens.sum()

    kpis['contagem_mes'] = contar_itens(df_mes)
    kpis['contagem_dia'] = contar_itens(df_dia)
    kpis['contagem_anterior'] = contar_itens(df_anterior)

    # KPIs de Totais de Valor
    kpis['total_mes'] = df_mes['Total Limpo'].sum() if not df_mes.empty else 0.0
    kpis['total_dia'] = df_dia['Total Limpo'].sum() if not df_dia.empty else 0.0
    kpis['total_anterior'] = df_anterior['Total Limpo'].sum() if not df_anterior.empty else 0.0

    # --- INSIGHTS ---

    # 1. Produto Campeão (Mês)
    if not df_mes.empty and COLUNA_ITEM_VENDIDO in df_mes.columns:
        try:
             kpis['item_campeao_mes'] = df_mes[COLUNA_ITEM_VENDIDO].mode().iloc[0] 
        except IndexError:
             kpis['item_campeao_mes'] = 'Nenhum item vendido em quantidade'
    else:
        kpis['item_campeao_mes'] = 'N/A'
        
    # 2. Melhor Cliente (Mês)
    if not df_mes.empty and COLUNA_CLIENTE in df_mes.columns:
        melhor_cliente_df = df_mes.groupby(COLUNA_CLIENTE)['Total Limpo'].sum().sort_values(ascending=False)
        kpis['melhor_cliente_mes'] = melhor_cliente_df.index[0] if not melhor_cliente_df.empty else 'N/A'
        kpis['melhor_cliente_gasto'] = melhor_cliente_df.iloc[0] if not melhor_cliente_df.empty else 0.0
    else:
        kpis['melhor_cliente_mes'] = 'N/A'
        kpis['melhor_cliente_gasto'] = 0.0

    # 3. Pico de Vendas (Hoje)
    if not df_dia.empty:
        pico_hora_df = df_dia['Hora'].value_counts()
        pico_hora_str = f"{pico_hora_df.index[0]}h" if not pico_hora_df.empty else 'N/A'
    else:
        pico_hora_str = 'N/A'
        
    kpis['pico_hora_dia'] = pico_hora_str

    return kpis

def calcular_kpis_gastos(df_mes, df_dia):
    """Calcula KPIs essenciais de GASTOS para o painel clean."""
    kpis = {}
    
    # KPIs do Mês e Dia
    kpis['total_mes'] = df_mes['Total Limpo'].sum() if not df_mes.empty else 0.0
    kpis['contagem_mes'] = df_mes.shape[0]
    kpis['total_dia'] = df_dia['Total Limpo'].sum() if not df_dia.empty else 0.0
    kpis['contagem_dia'] = df_dia.shape[0]

    # Dados Adicionais (Insights)
    if not df_mes.empty and COLUNA_ITEM_GASTO in df_mes.columns:
        gasto_por_item = df_mes.groupby(COLUNA_ITEM_GASTO)['Total Limpo'].sum().sort_values(ascending=False)
        kpis['item_principal_gasto_mes'] = gasto_por_item.index[0] if not gasto_por_item.empty else 'N/A'
        kpis['gasto_principal_valor'] = gasto_por_item.iloc[0] if not gasto_por_item.empty else 0.0
    else:
        kpis['item_principal_gasto_mes'] = 'N/A'
        kpis['gasto_principal_valor'] = 0.0
        
    return kpis

# --- FUNÇÃO NOVA: ADICIONA GRÁFICOS INTERATIVOS ---
def adicionar_graficos(df_vendas_mes, df_vendas_dia, df_gastos_mes):

    st.divider()
    st.header("📈 Visualização Detalhada")
    
    # Gráficos lado a lado
    col_grafico_a, col_grafico_b = st.columns([1, 1]) 

    # 1. GRÁFICO DE VENDAS POR HORA (HOJE)
    if not df_vendas_dia.empty:
        vendas_por_hora = df_vendas_dia.groupby('Hora')['Total Limpo'].sum().reset_index()
        vendas_por_hora.columns = ['Hora', 'Total Vendido']
        
        fig_hora = px.bar(
            vendas_por_hora, 
            x='Hora', 
            y='Total Vendido', 
            title='Total Vendido por Hora (Hoje)',
            labels={'Hora': 'Hora do Dia (24h)', 'Total Vendido': 'R$ Total'},
            color_discrete_sequence=['#4CAF50'] # Verde
        )
        fig_hora.update_layout(xaxis=dict(tick0=0, dtick=1))
        col_grafico_a.plotly_chart(fig_hora, use_container_width=True)
    else:
        col_grafico_a.info("Sem dados de vendas para gerar o gráfico horário hoje.")


    # 2. GRÁFICO TOP 5 ITENS VENDIDOS (MÊS)
    if not df_vendas_mes.empty and COLUNA_ITEM_VENDIDO in df_vendas_mes.columns:
        # Contagem simples de ocorrências na coluna de itens
        top_sabores = df_vendas_mes[COLUNA_ITEM_VENDIDO].value_counts().head(5).reset_index()
        top_sabores.columns = ['Sabor', 'Contagem de Transações']
        
        fig_top = px.pie(
            top_sabores, 
            values='Contagem de Transações', 
            names='Sabor', 
            title='Top 5 Itens Mais Vendidos (Mês)',
            hole=.3 
        )
        col_grafico_b.plotly_chart(fig_top, use_container_width=True)
    else:
        col_grafico_b.info("Sem dados de itens vendidos para gerar o gráfico Top 5.")

    st.divider()

    # 3. GRÁFICO DE LINHA: VENDAS vs. GASTOS (MÊS) - Largura Total
    if not df_vendas_mes.empty or not df_gastos_mes.empty:
        
        # Agregando por data
        vendas_diarias = df_vendas_mes.groupby('Data')['Total Limpo'].sum().reset_index()
        vendas_diarias.rename(columns={'Total Limpo': 'Vendas'}, inplace=True)
        
        gastos_diarios = df_gastos_mes.groupby('Data')['Total Limpo'].sum().reset_index()
        gastos_diarios.rename(columns={'Total Limpo': 'Gastos'}, inplace=True)
        
        # União e formatação longa
        df_unificado = pd.merge(vendas_diarias, gastos_diarios, on='Data', how='outer').fillna(0)
        df_longo = df_unificado.melt(
            id_vars='Data', 
            value_vars=['Vendas', 'Gastos'],
            var_name='Tipo', 
            value_name='Valor'
        )
        
        fig_linha = px.line(
            df_longo, 
            x='Data', 
            y='Valor', 
            color='Tipo', 
            title='Tendência Diária: Vendas vs. Gastos (Mês)',
            line_shape='spline',
            color_discrete_map={'Vendas': '#4CAF50', 'Gastos': '#F44336'}
        )
        st.plotly_chart(fig_linha, use_container_width=True)

    else:
        st.info("Sem dados suficientes no mês para gerar o gráfico de tendência Vendas vs. Gastos.")


# --- FUNÇÃO PRINCIPAL DE MONTAGEM DO DASHBOARD STREAMLIT ---
# AGORA ELA RECEBE OS DF's
def montar_dashboard(df_vendas_mes, df_vendas_dia, df_gastos_mes, kpis_vendas, kpis_gastos):
    
    # AJUSTE: Usamos o fuso de Brasília para a hora de atualização
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    agora_brasilia = datetime.now(fuso_brasilia)
    hora_atualizacao = agora_brasilia.strftime('%d/%m/%Y %H:%M:%S')
    mes_titulo = agora_brasilia.strftime('%B/%Y').upper()
    
    if st.button("🔴 CLIQUE AQUI PARA ATUALIZAR DADOS AGORA (FORÇAR RECARGA)", type="primary"):
        st.rerun() 
    
    st.title(f"🎂 Painel de Confeitaria: Mês de {mes_titulo}")
    
    st.caption(f"Última atualização de dados da planilha: **{hora_atualizacao}**")
    
    st.divider() 
    
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

    st.divider()

    # --- 2. KPIS DE VENDAS E GASTOS (LINHA PRINCIPAL) ---
    st.header("💰 Vendas x Despesas (Valores e Quantidades)")
    
    diferenca_valor = kpis_vendas['total_dia'] - kpis_vendas['total_anterior']
    diferenca_itens = kpis_vendas['contagem_dia'] - kpis_vendas['contagem_anterior'] 
    
    cor_neutra = "off" 
    
    col1, col_comp_valor, col_comp_und, col2, col3, col4 = st.columns([1, 1, 1, 1, 1, 1]) 
    
    # Vendas Hoje (Valor)
    col1.metric(
        label="R$ VENDAS HOJE", 
        value=format_brl(kpis_vendas['total_dia']),
        delta=f"{kpis_vendas['contagem_dia']} itens vendidos", 
        delta_color="off" 
    )
    
    # Comparação de VALOR (HOJE vs. ONTEM)
    delta_valor_formatado = format_brl(diferenca_valor)

    col_comp_valor.metric(
        label="R$ DIF. (HOJE vs. ONTEM)",
        value=format_brl(diferenca_valor),
        delta=delta_valor_formatado, 
        delta_color=cor_neutra, 
        help=f"Comparação com o total de R$ {kpis_vendas['total_anterior']:,.2f} vendido ontem."
    )

    # Comparação de QUANTIDADE DE ITENS (HOJE vs. ONTEM)
    delta_itens_formatado = f"{diferenca_itens:.0f} itens" 

    col_comp_und.metric(
        label="ITENS DIF. (HOJE vs. ONTEM)", 
        value=f"{diferenca_itens:.0f} itens",
        delta=delta_itens_formatado,
        delta_color=cor_neutra, 
        help=f"Variação no número de ITENS vendidos. Ontem: {kpis_vendas['contagem_anterior']:.0f} itens."
    )
    
    # Vendas Mês (Valor)
    col2.metric(
        label="R$ VENDAS MÊS", 
        value=format_brl(kpis_vendas['total_mes']), 
        delta=f"{kpis_vendas['contagem_mes']} itens vendidos",
        delta_color="off"
    )
    
    # Gastos Hoje (Valor)
    col3.metric(
        label="R$ GASTOS HOJE", 
        value=format_brl(kpis_gastos['total_dia']),
        delta=f"{kpis_gastos['contagem_dia']} registros de gasto",
        delta_color=cor_neutra, 
        help="Gastos registrados na data atual."
    )
    
    # Gastos Mês (Valor)
    col4.metric(
        label="R$ GASTOS MÊS", 
        value=format_brl(kpis_gastos['total_mes']),
        delta=f"{kpis_gastos['contagem_mes']} registros de gasto",
        delta_color=cor_neutra, 
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
    
    # --- 4. GRÁFICOS (CHAMADA DA FUNÇÃO) ---
    adicionar_graficos(df_vendas_mes, df_vendas_dia, df_gastos_mes)


# --- EXECUÇÃO PRINCIPAL STREAMLIT ---
if __name__ == "__main__":
    
    with st.spinner('Assando os dados, limpando e unificando Vendas e Gastos...'):
        
        try:
            # Carrega todos os 5 DataFrames
            df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia, df_vendas_anterior = carregar_e_limpar_dados()
            
            # Condição para exibir o dashboard:
            if not df_vendas_mes.empty or not df_gastos_mes.empty:
                
                # 1. Calcula os KPIs (Envia o df_vendas_anterior)
                kpis_vendas = calcular_kpis_vendas(df_vendas_mes, df_vendas_dia, df_vendas_anterior) 
                kpis_gastos = calcular_kpis_gastos(df_gastos_mes, df_gastos_dia)
                
                # 2. Monta o Dashboard (Passando TUDO, incluindo os DataFrames para os gráficos)
                montar_dashboard(df_vendas_mes, df_vendas_dia, df_gastos_mes, kpis_vendas, kpis_gastos)
                
            else:
                 st.info("⚠️ Aguardando dados para análise! O mês parece estar de folga. Adicione Vendas ou Gastos para começar a trabalhar.")

        except Exception as e:
            st.exception(f"Ocorreu um erro INESPERADO. Algo deu errado na sua receita de código! Detalhes: {e}")
