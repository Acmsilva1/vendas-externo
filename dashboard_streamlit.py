import pandas as pd
import gspread
from datetime import datetime, date, timedelta
import streamlit as st 
import time 
import pytz 
import plotly.express as px 
import warnings 
from prophet import Prophet 
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Suprimir warnings do Prophet (que são comuns)
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=RuntimeWarning)

# --- CONFIGURAÇÕES FIXAS ---
# ID da planilha fornecido pelo usuário (dados atuais/vigentes)
SPREADSHEET_ID_UNIFICADO = "1LuqYrfR8ry_MqCS93Mpj9_7Vu0i9RUTomJU2n69bEug" 
# ID DA PLANILHA HISTÓRICA DO USUÁRIO (Apenas para a IA Vidente)
SPREADSHEET_ID_HISTORICO = "1XWdRbHqY6DWOlSO-oJbBSyOsXmYhM_NEA2_yvWbfq2Y" 

# NOVAS CONSTANTES ISOLADAS
# Planilha ATUAL (ID: 1Luq...Eug) -> USAR MINÚSCULO, conforme sua instrução
ABA_VENDAS_ATUAL = "vendas"
ABA_GASTOS_ATUAL = "gastos"

# Planilha HISTÓRICA (ID: 1XWd...bfq2Y) -> USAR MAIÚSCULO, conforme sua instrução
ABA_VENDAS_HISTORICO = "VENDAS"
# GASTOS HISTÓRICO não é usado, mas defino para consistência
ABA_GASTOS_HISTORICO = "GASTOS"


# NOME DAS COLUNAS ESSENCIAIS NA SUA PLANILHA (ASSUME QUE SÃO AS MESMAS NAS DUAS)
# ABA VENDAS
COLUNA_ITEM_VENDIDO = 'SABORES'          
COLUNA_CLIENTE = 'DADOS DO COMPRADOR'    
COLUNA_VALOR_VENDA = 'VALOR DA VENDA'
# ABA GASTOS
COLUNA_ITEM_GASTO = 'PRODUTO'            
COLUNA_VALOR_GASTO = 'VALOR'
# COMUM
COLUNA_DATA_HORA = 'DATA E HORA'

# CONSTANTES PARA ORDENAÇÃO DE GRÁFICO DE DIA DA SEMANA
DIA_SEMANA_ORDEM = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
DIA_SEMANA_MAP = {
    0: 'Segunda', 1: 'Terça', 2: 'Quarta', 3: 'Quinta', 4: 'Sexta', 5: 'Sábado', 6: 'Domingo'
}


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
        .str.replace(',', '.', regex=False)
        .str.replace('R$', '', regex=False)
        .str.replace(',', '.', regex=False)
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

# --- FUNÇÃO PRINCIPAL: APENAS DADOS ATUAIS (KPIs) ---
def carregar_e_limpar_dados():
    st.set_page_config(layout="wide", page_title="💰 Controle de vendas diário")
    
    # Datas definidas no topo da função para uso em todos os filtros
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    agora_brasilia = datetime.now(fuso_brasilia) 
    data_atual = agora_brasilia.date()
    data_anterior = data_atual - timedelta(days=1) 
    
    # Inicializa DataFrames de retorno
    df_vendas_atual = pd.DataFrame() 
    df_gastos_mes = pd.DataFrame()
    df_gastos_dia = pd.DataFrame()
    df_vendas_anterior = pd.DataFrame()
    df_vendas_mes = pd.DataFrame()
    df_vendas_dia = pd.DataFrame()
    df_gastos_anterior = pd.DataFrame() 

    try:
        # 1. AUTENTICAÇÃO
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh_atual = gc.open_by_key(SPREADSHEET_ID_UNIFICADO)

        # 2. CARREGAMENTO E LIMPEZA DE VENDAS (USANDO MINÚSCULO)
        try:
            df_vendas_atual = pd.DataFrame(sh_atual.worksheet(ABA_VENDAS_ATUAL).get_all_records()) 
            
            # Processa e limpa o DataFrame ATUAL
            df_vendas_atual = limpar_coluna_valor(df_vendas_atual, COLUNA_VALOR_VENDA) 
            df_vendas_atual = processar_data(df_vendas_atual, COLUNA_DATA_HORA)
            
            # Filtra os DataFrames de KPI a partir do ATUAL
            df_vendas_mes, df_vendas_dia = filtrar_por_mes_e_dia(df_vendas_atual, data_atual)
            df_vendas_anterior = df_vendas_atual[df_vendas_atual['Data'] == data_anterior].copy() 

        except Exception as e:
            # NOVO TRATAMENTO DE ERRO: Mais específico para o problema da aba
            raise Exception(f"Falha CRÍTICA ao carregar a aba '{ABA_VENDAS_ATUAL}' na planilha ATUAL (ID: {SPREADSHEET_ID_UNIFICADO}). Verifique se a aba está em minúsculo. Detalhe: {e}")


        # 3. CARREGAMENTO E LIMPEZA DE GASTOS (USANDO MINÚSCULO)
        try:
            df_gastos = pd.DataFrame(sh_atual.worksheet(ABA_GASTOS_ATUAL).get_all_records())
            df_gastos = limpar_coluna_valor(df_gastos, COLUNA_VALOR_GASTO) 
            df_gastos = processar_data(df_gastos, COLUNA_DATA_HORA) 
            df_gastos_mes, df_gastos_dia = filtrar_por_mes_e_dia(df_gastos, data_atual)
            df_gastos_anterior = df_gastos[df_gastos['Data'] == data_anterior].copy() 
        except Exception as e:
             # O erro em GASTOS não é crítico para o funcionamento do painel de VENDAS
             st.warning(f"⚠️ Sem dados de gasto para análise (Aba '{ABA_GASTOS_ATUAL}' não encontrada ou inválida). Detalhe Técnico: {e}")
             df_gastos_mes = pd.DataFrame()
             df_gastos_dia = pd.DataFrame()
             df_gastos_anterior = pd.DataFrame()


    except Exception as e:
        # Erro de conexão/autenticação geral (ID incorreto, Secret inválido, ou exceção do bloco acima)
        st.error(f"ERRO GERAL DE DADOS/CONEXÃO: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame() 


    return df_vendas_atual, df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia, df_vendas_anterior, df_gastos_anterior


# [ ... Funções calcular_kpis_vendas e calcular_kpis_gastos (mantidas e refinadas) ... ]
def calcular_kpis_vendas(df_mes, df_dia, df_anterior):
    """Calcula KPIs essenciais de VENDAS para o painel clean, incluindo a comparação com o Dia Anterior."""
    kpis = {}
        
    if COLUNA_ITEM_VENDIDO in df_mes.columns:
        def contar_itens(df):
            if df.empty or COLUNA_ITEM_VENDIDO not in df.columns:
                 return 0
            # FIX: Modificado para usar split/apply(len)/sum para contagem precisa de itens
            contagens = df[COLUNA_ITEM_VENDIDO].fillna('').astype(str).str.split(',').apply(len)
            return contagens.sum()

        kpis['contagem_mes'] = contar_itens(df_mes)
        kpis['contagem_dia'] = contar_itens(df_dia)
        kpis['contagem_anterior'] = contar_itens(df_anterior)

    else: 
        kpis['contagem_mes'] = df_mes.shape[0]
        kpis['contagem_dia'] = df_dia.shape[0]
        kpis['contagem_anterior'] = df_anterior.shape[0]

    # KPIs de Valor
    kpis['total_mes'] = df_mes['Total Limpo'].sum() if not df_mes.empty else 0.0
    kpis['total_dia'] = df_dia['Total Limpo'].sum() if not df_dia.empty else 0.0
    kpis['total_anterior'] = df_anterior['Total Limpo'].sum() if not df_anterior.empty else 0.0
    
    # NOVOS KPIS
    kpis['transacoes_mes'] = df_mes.shape[0] if not df_mes.empty else 0 
    kpis['ticket_medio_mes'] = kpis['total_mes'] / kpis['transacoes_mes'] if kpis['transacoes_mes'] > 0 else 0.0

    # INSIGHTS
    if not df_mes.empty and COLUNA_ITEM_VENDIDO in df_mes.columns:
        try:
             # Modificado para usar o explode para contagem precisa do item campeão
             kpis['item_campeao_mes'] = df_mes[COLUNA_ITEM_VENDIDO].str.split(',').explode().str.strip().mode().iloc[0] 
        except IndexError:
             kpis['item_campeao_mes'] = 'Nenhum item vendido em quantidade'
    else:
        kpis['item_campeao_mes'] = f'N/A (Col. {COLUNA_ITEM_VENDIDO} faltando ou mês vazio)'
        
    if not df_mes.empty and COLUNA_CLIENTE in df_mes.columns:
        melhor_cliente_df = df_mes.groupby(COLUNA_CLIENTE)['Total Limpo'].sum().sort_values(ascending=False)
        kpis['melhor_cliente_mes'] = melhor_cliente_df.index[0] if not melhor_cliente_df.empty else 'N/A'
        kpis['melhor_cliente_gasto'] = melhor_cliente_df.iloc[0] if not melhor_cliente_df.empty else 0.0
    else:
        kpis['melhor_cliente_mes'] = f'N/A (Col. {COLUNA_CLIENTE} faltando ou mês vazio)'
        kpis['melhor_cliente_gasto'] = 0.0

    if not df_dia.empty:
        pico_hora_df = df_dia['Hora'].value_counts()
        pico_hora_str = f"{pico_hora_df.index[0]}h" if not pico_hora_df.empty else 'N/A'
    else:
        pico_hora_str = 'N/A'
        
    kpis['pico_hora_dia'] = pico_hora_str

    return kpis

def calcular_kpis_gastos(df_mes, df_dia, df_anterior): 
    """Calcula KPIs essenciais de GASTOS para o painel clean, incluindo a contagem e comparação diária."""
    kpis = {}
    
    kpis['total_mes'] = df_mes['Total Limpo'].sum() if not df_mes.empty else 0.0
    kpis['contagem_mes'] = df_mes.shape[0]
    kpis['total_dia'] = df_dia['Total Limpo'].sum() if not df_dia.empty else 0.0
    kpis['contagem_dia'] = df_dia.shape[0]

    # KPI de Gasto do Dia Anterior
    kpis['total_anterior'] = df_anterior['Total Limpo'].sum() if not df_anterior.empty else 0.0
    kpis['contagem_anterior'] = df_anterior.shape[0]

    if not df_mes.empty and COLUNA_ITEM_GASTO in df_mes.columns:
        gasto_por_item = df_mes.groupby(COLUNA_ITEM_GASTO)['Total Limpo'].sum().sort_values(ascending=False)
        kpis['item_principal_gasto_mes'] = gasto_por_item.index[0] if not gasto_por_item.empty else 'N/A'
        kpis['gasto_principal_valor'] = gasto_por_item.iloc[0] if not gasto_por_item.empty else 0.0
    else:
        kpis['item_principal_gasto_mes'] = f'N/A (Col. {COLUNA_ITEM_GASTO} faltando ou mês vazio)'
        kpis['gasto_principal_valor'] = 0.0
        
    return kpis

# --- FUNÇÃO ISOLADA: ADICIONA PREVISÃO DE VENDAS COM PROPHET (SÓ ELA BUSCA O HISTÓRICO) ---
def adicionar_previsao_vendas(df_vendas_atual):
    """
    Roda um modelo Prophet para prever a quantidade de vendas dos top itens no dia seguinte.
    A função carrega o histórico separadamente e o junta ao df_vendas_atual (somente se necessário).
    """
    st.divider()
    st.header("🔮 Puxadinho da IA: Previsão de Demanda para Amanhã")
    
    # --- 1. CARREGAR E UNIFICAR DADOS HISTÓRICOS (SÓ AQUI DENTRO!) ---
    df_vendas = df_vendas_atual.copy() # Começa com os dados atuais
    
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])

        if SPREADSHEET_ID_HISTORICO != SPREADSHEET_ID_UNIFICADO:
             try:
                # *** ATENÇÃO AQUI: USA A CONSTANTE MAIÚSCULA AGORA ***
                sh_hist = gc.open_by_key(SPREADSHEET_ID_HISTORICO)
                df_vendas_historico = pd.DataFrame(sh_hist.worksheet(ABA_VENDAS_HISTORICO).get_all_records()) 
                
                # Limpeza e Processamento do Histórico antes de concatenar
                df_vendas_historico = limpar_coluna_valor(df_vendas_historico, COLUNA_VALOR_VENDA) 
                df_vendas_historico = processar_data(df_vendas_historico, COLUNA_DATA_HORA)
                
                # Concatena (Histórico + Atual) - Para o Prophet
                df_vendas = pd.concat([df_vendas_historico, df_vendas_atual], ignore_index=True)
                st.success("✅ Histórico de vendas (passado) carregado e unificado para o Analista Sênior Vidente.")
             except Exception as e:
                 st.warning(f"⚠️ Planilha histórica não encontrada ou inválida para a IA. Aba esperada: '{ABA_VENDAS_HISTORICO}'. Usando apenas dados atuais. Detalhe: {e}")
                 # df_vendas permanece apenas com df_vendas_atual.
        else:
             st.caption("⚠️ Planilha Histórica e Atual são as mesmas. A previsão só terá o histórico atual. O Vidente pode estar 'míope'.")
         
    except Exception as e:
        st.error(f"ERRO DE CONEXÃO DO PUXADINHO: O Vidente falhou ao buscar o histórico (Secret ou ID errado?). Detalhe: {e}")
        return # Para a função de previsão se o carregamento falhar
        
    # --- 2. PREPARAR DADOS E RODAR O PROPHET ---
    
    try:
        # Contagem de ocorrências de cada item em todas as transações (histórico completo)
        itens_contagem = df_vendas[COLUNA_ITEM_VENDIDO].str.split(',').explode().str.strip().value_counts()
        
        # Filtra os 3 itens mais vendidos 
        top_itens = itens_contagem.head(3).index.tolist()
        
    except Exception:
        st.info("Não foi possível identificar itens vendidos no histórico para iniciar a previsão.")
        return

    # O Prophet precisa de pelo menos 14 dias para uma sazonalidade semanal confiável
    if not top_itens or len(df_vendas['Data'].unique()) < 14:
        st.info("Histórico de dados insuficiente (precisamos de pelo menos 14 dias). Alimente a planilha histórica ou a atual por mais tempo!")
        return

    st.caption("Projeção baseada na sazonalidade (dia da semana) e tendência. Focando nos Top 3 itens.")
    
    cols = st.columns(3)
    
    for i, item in enumerate(top_itens):
        
        # Preparar dados para o Prophet (ds, y)
        df_item = df_vendas[
            df_vendas[COLUNA_ITEM_VENDIDO].str.contains(item, case=False, na=False)
        ].copy()
        
        # Agrupar por dia (ds) e contar a ocorrência (y)
        df_item_daily = df_item.groupby('Data').size().reset_index(name='y')
        
        # Formato Prophet
        df_item_daily['ds'] = pd.to_datetime(df_item_daily['Data'])
        df_item_prophet = df_item_daily[['ds', 'y']]
        
        # 3. Treinar e Prever
        if len(df_item_prophet) < 7: 
             cols[i].warning(f"Ainda sem histórico semanal para prever **{item}**.")
             continue
             
        try:
            m = Prophet()
            m.fit(df_item_prophet)
            
            # Previsão para 1 período (o próximo dia)
            future = m.make_future_dataframe(periods=1, include_history=False) 
            forecast = m.predict(future)
            
            previsao_unidades = max(0, forecast.iloc[0]['yhat']) # Não aceita previsão negativa
            
            data_previsao_obj = future.iloc[0]['ds'].date()
            data_previsao_str = data_previsao_obj.strftime('%d/%m')
            
            # 4. Exibir no Streamlit
            cols[i].metric(
                label=f"Demanda Estimada - {item}",
                value=f"{previsao_unidades:.0f} Unidades",
                delta=f"Para {data_previsao_str} ({DIA_SEMANA_MAP[data_previsao_obj.weekday()]})", 
                delta_color="off",
                help=f"Projeção de demanda para o item '{item}' com base no histórico diário e semanal."
            )
            
        except Exception as e:
            cols[i].error(f"Erro ao prever {item}. Detalhes: {e}")

# [ ... Funções adicionar_graficos e montar_dashboard (mantidas) ... ]
def adicionar_graficos(df_vendas_mes, df_vendas_dia, df_gastos_mes):

    st.divider()
    st.header("📈 Visualização Detalhada")

    # 1. GRÁFICO ÚNICO: PRODUTIVIDADE E RESULTADO DIÁRIO (UNIFICADO)
    if not df_vendas_mes.empty or not df_gastos_mes.empty:
        
        # --- PREPARAÇÃO DE DADOS (Unificado) ---
        df_vendas_temp = df_vendas_mes.copy()
        df_vendas_temp['Data'] = pd.to_datetime(df_vendas_temp['Data'])
        
        df_vendas_agregado = df_vendas_temp.groupby('Data').agg(
            Valor=('Total Limpo', 'sum'),
            Quantidade_Itens=('SABORES', lambda x: x.fillna('').astype(str).str.split(',').apply(len).sum())
        ).reset_index()
        
        df_gastos_temp = df_gastos_mes.copy()
        df_gastos_temp['Data'] = pd.to_datetime(df_gastos_temp['Data'])
        
        df_gastos_agregado = df_gastos_temp.groupby('Data')['Total Limpo'].sum().reset_index()
        df_gastos_agregado.rename(columns={'Total Limpo': 'Custo'}, inplace=True)
        
        df_unificado = pd.merge(df_vendas_agregado, df_gastos_agregado, on='Data', how='outer').fillna(0)
        df_unificado['Custo Negativo'] = -df_unificado['Custo']
        
        # --- CRIAÇÃO DO GRÁFICO (Eixo Duplo para Valor e Quantidade) ---

        fig_unificado = make_subplots(specs=[[{"secondary_y": True}]])

        fig_unificado.add_trace(
            go.Bar(x=df_unificado['Data'], y=df_unificado['Valor'], name='R$ Vendas', marker_color='#4CAF50', hovertemplate="<b>Vendas:</b> %{y:$.2f}<br>"),
            secondary_y=False,
        )

        fig_unificado.add_trace(
            go.Bar(x=df_unificado['Data'], y=df_unificado['Custo Negativo'], name='R$ Custos', marker_color='#F44336', hovertemplate="<b>Custos:</b> R$ %{y:,.2f}<br>"),
            secondary_y=False,
        )
        
        fig_unificado.add_trace(
            go.Scatter(x=df_unificado['Data'], y=df_unificado['Quantidade_Itens'], mode='lines+markers', name='Nº Itens Vendidos', line=dict(color='#FFC107', width=3), hovertemplate="<b>Itens Vendidos:</b> %{y}"),
            secondary_y=True,
        )

        fig_unificado.update_layout(
            title_text="Produtividade e Resultado Diário (Vendas, Custos e Itens Vendidos)",
            barmode='overlay', 
            hovermode="x unified",
            xaxis_title='Dia do Mês'
        )

        fig_unificado.update_yaxes(
            title_text="<b>R$ Valor (Vendas Positivo | Custos Negativo)</b>", 
            secondary_y=False,
            tickprefix='R$',
            tickformat=",.2f"
        )

        fig_unificado.update_yaxes(
            title_text="<b>Nº Itens Vendidos (Linha)</b>", 
            secondary_y=True,
            tickformat=",d" 
        )
        
        st.plotly_chart(fig_unificado, use_container_width=True)

    else:
        st.info("Sem dados de vendas ou gastos suficientes para gerar o gráfico unificado de Produtividade/Resultado.")
        
    st.divider()

    # --- 2. GRÁFICOS DE PIZZA DE COMPOSIÇÃO (VENDAS E CLIENTES) ---
    col_vazia, col_grafico_b, col_grafico_c = st.columns([0.1, 1, 1]) 

    # 2.1 GRÁFICO TOP 5 ITENS VENDIDOS (MÊS) - FOCO EM PRODUTO
    if not df_vendas_mes.empty and COLUNA_ITEM_VENDIDO in df_vendas_mes.columns:
        # Usa explode e value_counts para contagem precisa de itens
        top_sabores = df_vendas_mes[COLUNA_ITEM_VENDIDO].str.split(',').explode().str.strip().value_counts().head(5).reset_index()
        top_sabores.columns = ['Sabor', 'Contagem de Transações']
        
        top_sabores['Legenda'] = top_sabores['Sabor'] + ' (' + top_sabores['Contagem de Transações'].astype(str) + ' unid.)'
        
        fig_top = px.pie(
            top_sabores, 
            values='Contagem de Transações', 
            names='Legenda', 
            title='Top 5 Itens Mais Vendidos (Contagem)',
            hole=.3 
        )
        fig_top.update_traces(hovertemplate="Sabor: %{label}<br>Contagem: %{value}<br>Percentual: %{percent}")
        
        col_grafico_b.plotly_chart(fig_top, use_container_width=True)
    else:
        col_grafico_b.info("Sem dados de itens vendidos para gerar o gráfico Top 5.")

    # 2.2 GRÁFICO TOP 5 CLIENTES MAIS FIÉIS (MÊS) - FOCO EM FIDELIDADE
    if not df_vendas_mes.empty and COLUNA_CLIENTE in df_vendas_mes.columns:
        
        top_clientes_valor = df_vendas_mes.groupby(COLUNA_CLIENTE)['Total Limpo'].sum().sort_values(ascending=False).head(5).reset_index()
        top_clientes_valor.columns = ['Cliente', 'Valor Gasto']
        
        top_clientes_valor['Legenda'] = top_clientes_valor['Cliente'] + ' (' + top_clientes_valor['Valor Gasto'].apply(lambda x: f"R$ {x:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')) + ')'
        
        fig_clientes = px.pie(
            top_clientes_valor, 
            values='Valor Gasto', 
            names='Legenda', 
            title='Top 5 Clientes Mais Fiéis (por R$ Gasto)',
            hole=.3 
        )
        fig_clientes.update_traces(hovertemplate="Cliente: %{label}<br>Valor Total: %{value:$.2f}<br>Percentual: %{percent}")
        
        col_grafico_c.plotly_chart(fig_clientes, use_container_width=True)
    else:
        col_grafico_c.info("Sem dados de clientes para gerar o gráfico de fidelidade.")

    # --- 3. NOVA SEÇÃO: DETALHAMENTO DE CUSTOS E PRODUTIVIDADE SEMANAL ---
    st.divider()
    st.header("💸 Detalhamento de Custos e Produtividade Semanal") 

    col_vazia_2, col_gasto_a, col_gasto_b = st.columns([0.1, 1, 1])

    # 3.1 GRÁFICO TOP 5 ITENS DE MAIOR CUSTO (MÊS)
    if not df_gastos_mes.empty and COLUNA_ITEM_GASTO in df_gastos_mes.columns:
        
        top_gastos_valor = df_gastos_mes.groupby(COLUNA_ITEM_GASTO)['Total Limpo'].sum().sort_values(ascending=False).head(5).reset_index()
        top_gastos_valor.columns = ['Item Gasto', 'Valor Gasto']
        
        top_gastos_valor['Legenda'] = top_gastos_valor['Item Gasto'] + ' (' + top_gastos_valor['Valor Gasto'].apply(lambda x: f"R$ {x:,.2f}".replace('.', 'X').replace(',', '.').replace('X', ',')) + ')'
        
        fig_gastos = px.pie(
            top_gastos_valor, 
            values='Valor Gasto', 
            names='Legenda', 
            title='Top 5 Itens de Maior Custo (por R$ Gasto)',
            hole=.3 
        )
        fig_gastos.update_traces(hovertemplate="Item Gasto: %{label}<br>Valor Total: %{value:$.2f}<br>Percentual: %{percent}")
        
        col_gasto_a.plotly_chart(fig_gastos, use_container_width=True)
    else:
        col_gasto_a.info("Sem dados de gastos para gerar o gráfico Top 5 Custos.")

    
    # 3.2 NOVO GRÁFICO: VENDAS POR DIA DA SEMANA (MÊS)
    if not df_vendas_mes.empty:
        
        # 1. Extrair o dia da semana (0=Segunda, 6=Domingo)
        df_vendas_mes['Dia_Semana_Num'] = df_vendas_mes['Data/Hora'].dt.dayofweek
        
        # 2. Mapear para nome em Português
        df_vendas_mes['Dia_Semana'] = df_vendas_mes['Dia_Semana_Num'].map(DIA_SEMANA_MAP) 
        
        # 3. Agrupar e Somar o valor total vendido
        vendas_por_dia = df_vendas_mes.groupby(['Dia_Semana_Num', 'Dia_Semana'])['Total Limpo'].sum().reset_index()
        vendas_por_dia.rename(columns={'Total Limpo': 'R$ Total Vendido'}, inplace=True)
        
        # 4. Criação do gráfico de colunas
        fig_dia_semana = px.bar(
            vendas_por_dia,
            x='Dia_Semana',
            y='R$ Total Vendido',
            title='Total de Vendas por Dia da Semana (Mês)',
            # Garante que o Plotly use a ordem de 'Segunda' a 'Domingo'
            category_orders={"Dia_Semana": DIA_SEMANA_ORDEM}, 
            color='R$ Total Vendido', 
            color_continuous_scale=px.colors.sequential.Plotly3 
        )
        
        # Formatação
        fig_dia_semana.update_layout(xaxis_title="Dia da Semana", yaxis_title="R$ Total Vendido")
        fig_dia_semana.update_yaxes(tickprefix='R$', tickformat=",.2f")
        
        col_gasto_b.plotly_chart(fig_dia_semana, use_container_width=True)
    else:
        col_gasto_b.info("Sem dados de vendas para gerar o gráfico de Produtividade Semanal.")


# --- FUNÇÃO PRINCIPAL DE MONTAGEM DO DASHBOARD STREAMLIT ---
def montar_dashboard(df_vendas_atual, df_vendas_mes, df_vendas_dia, df_gastos_mes, kpis_vendas, kpis_gastos):
    
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    agora_brasilia = datetime.now(fuso_brasilia)
    hora_atualizacao = agora_brasilia.strftime('%d/%m/%Y %H:%M:%S')
    mes_titulo = agora_brasilia.strftime('%B/%Y').upper()
    
    if st.button("🔴 CLIQUE AQUI PARA ATUALIZAR DADOS AGORA (FORÇAR RECARGA)", type="primary"):
        st.rerun() 
    
    st.title(f"🎂 Painel de Confeitaria: Mês de {mes_titulo}")
    
    st.caption(f"Última atualização de dados da planilha: **{hora_atualizacao}**")
    
    st.divider() 
    
    # --- 1. RESULTADO LÍQUIDO DO MÊS E TICKET MÉDIO (KPI CHAVE) ---
    st.header("🎯 Resultados Chave do Mês Vigente")
    
    total_vendas_mes = kpis_vendas['total_mes']
    total_gastos_mes = kpis_gastos['total_mes']
    resultado_liquido = total_vendas_mes - total_gastos_mes
    
    transacoes_mes = df_vendas_mes.shape[0] if not df_vendas_mes.empty else 0
    ticket_medio = total_vendas_mes / transacoes_mes if transacoes_mes > 0 else 0.0
    
    cor_resultado = "normal" if resultado_liquido >= 0 else "inverse" 

    col_res_a, col_res_b, col_res_c = st.columns([2, 1, 1])
    
    col_res_a.metric(
        label="LUCRO / PREJUÍZO (MÊS)", 
        value=format_brl(resultado_liquido),
        delta=f"Vendas: {format_brl(total_vendas_mes)} | Gastos: {format_brl(total_gastos_mes)}",
        delta_color=cor_resultado
    )
    
    col_res_b.metric(
        label="TICKET MÉDIO (MÊS)",
        value=format_brl(ticket_medio),
        help=f"Valor médio gasto por cada transação (baseado em {transacoes_mes} transações)."
    )

    if total_vendas_mes > 0:
        custo_percentual = (total_gastos_mes / total_vendas_mes) * 100
        col_res_c.metric(
            label="% CUSTO/RECEITA",
            value=f"{custo_percentual:.1f}%",
            help="O custo operacional representa esta porcentagem da receita total."
        )

    st.divider()

    # --- 2. KPIS DE VENDAS E GASTOS (LINHA PRINCIPAL) ---
    st.header("💰 Vendas x Despesas (Valores e Quantidades)")
    
    # Variáveis numéricas para a diferença
    diferenca_valor = kpis_vendas['total_dia'] - kpis_vendas['total_anterior']
    diferenca_itens = kpis_vendas['contagem_dia'] - kpis_vendas['contagem_anterior'] 
    diferenca_gasto_valor = kpis_gastos['total_dia'] - kpis_gastos['total_anterior'] 
    
    cor_neutra = "off" 
    
    # Lógica para evitar seta ↑ em Delta zero (Vendas - Valor)
    if diferenca_valor == 0:
        delta_venda_valor = "Estável"
    else:
        delta_venda_valor = diferenca_valor

    # Lógica para evitar seta ↑ em Delta zero (Vendas - Itens)
    if diferenca_itens == 0:
        delta_venda_itens = "Estável"
    else:
        delta_venda_itens = diferenca_itens
        
    # Lógica para evitar seta ↑ em Delta zero (Gastos - Valor)
    if diferenca_gasto_valor == 0:
        delta_gasto_valor = "Estável"
    else:
        delta_gasto_valor = diferenca_gasto_valor

    
    col1, col_comp_valor, col_comp_und, col2, col3, col4 = st.columns([1, 1, 1, 1, 1, 1]) 
    
    col1.metric(
        label="R$ VENDAS HOJE", 
        value=format_brl(kpis_vendas['total_dia']),
        delta=f"{kpis_vendas['contagem_dia']} itens vendidos", 
        delta_color="off" 
    )
    
    col_comp_valor.metric(
        label="R$ DIF. (HOJE vs. ONTEM)",
        value=format_brl(diferenca_valor),
        # Passa o valor numérico ou "Estável" para o delta
        delta=delta_venda_valor if isinstance(delta_venda_valor, str) else format_brl(delta_venda_valor), 
        delta_color=cor_neutra, 
        help=f"Comparação com o total de R$ {kpis_vendas['total_anterior']:,.2f} vendido ontem."
    )

    col_comp_und.metric(
        label="ITENS DIF. (HOJE vs. ONTEM)", 
        value=f"{diferenca_itens:.0f} itens",
        # Passa o valor numérico ou "Estável" para o delta
        delta=delta_venda_itens if isinstance(delta_venda_itens, str) else f"{delta_venda_itens:.0f}", 
        delta_color=cor_neutra, 
        help=f"Variação no número de ITENS vendidos. Ontem: {kpis_vendas['contagem_anterior']:.0f} itens."
    )
    
    col2.metric(
        label="R$ VENDAS MÊS", 
        value=format_brl(kpis_vendas['total_mes']), 
        delta=f"{kpis_vendas['contagem_mes']} itens vendidos",
        delta_color="off"
    )
    
    col3.metric(
        label="R$ GASTOS HOJE (vs. Ontem)", 
        value=format_brl(kpis_gastos['total_dia']),
        # Passa o valor numérico ou "Estável" para o delta
        delta=delta_gasto_valor if isinstance(delta_gasto_valor, str) else format_brl(delta_gasto_valor), 
        delta_color=cor_neutra, 
        help=f"Comparação com o total de R$ {kpis_gastos['total_anterior']:,.2f} gasto ontem."
    )
    
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
    
    col_detalhe_a.info(
        f"**Sabor Mais Vendido (Mês):** {kpis_vendas['item_campeao_mes']}"
    )
    
    cliente_valor = format_brl(kpis_vendas['melhor_cliente_gasto'])
    col_detalhe_b.info(
        f"**Melhor Cliente (Mês):** {kpis_vendas['melhor_cliente_mes']} ({cliente_valor})."
    )
    
    col_detalhe_c.info(
        f"**Pico de Vendas (Hoje):** {kpis_vendas['pico_hora_dia']}. Prepare-se para este horário!"
    )

    gasto_valor = format_brl(kpis_gastos['gasto_principal_valor'])
    col_detalhe_d.warning(
        f"**Item de Maior Gasto (Mês):** {kpis_gastos['item_principal_gasto_mes']} ({gasto_valor}). Revise este custo!"
    )
    
    # --- 4. GRÁFICOS (CHAMADA DA FUNÇÃO) ---
    adicionar_graficos(df_vendas_mes, df_vendas_dia, df_gastos_mes)

    # --- 5. PUXADINHO DA INTELIGÊNCIA PREDITIVA ---
    # Agora passa o df_vendas_atual e deixa a função carregar o histórico sozinha
    adicionar_previsao_vendas(df_vendas_atual) 


# --- EXECUÇÃO PRINCIPAL STREAMLIT ---
if __name__ == "__main__":
    
    with st.spinner('Assando os dados, limpando e unificando Vendas e Gastos... E treinando a IA com a sabedoria do passado...'):
        
        try:
            # df_vendas_atual é o DataFrame de Vendas do ano/mês vigente
            df_vendas_atual, df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia, df_vendas_anterior, df_gastos_anterior = carregar_e_limpar_dados()
            
            if not df_vendas_mes.empty or not df_gastos_mes.empty:
                
                kpis_vendas = calcular_kpis_vendas(df_vendas_mes, df_vendas_dia, df_vendas_anterior) 
                # Agora passa df_gastos_anterior para ter a comparação de gastos com o dia anterior
                kpis_gastos = calcular_kpis_gastos(df_gastos_mes, df_gastos_dia, df_gastos_anterior) 
                
                # df_vendas_atual é passado para a função de montagem
                montar_dashboard(df_vendas_atual, df_vendas_mes, df_vendas_dia, df_gastos_mes, kpis_vendas, kpis_gastos)
                
            else:
                 # Esta mensagem só aparece se a planilha ATUAL estiver vazia
                 st.info("⚠️ Aguardando dados para análise! O mês parece estar de folga. Adicione Vendas ou Gastos para começar a trabalhar.")

        except Exception as e:
            # O erro mais crítico é capturado aqui
            st.exception(f"Ocorreu um erro INESPERADO. Algo deu errado na sua receita de código! Detalhes: {e}")
