import pandas as pd
import gspread
from datetime import datetime, date
import streamlit as st 
import time 
import pytz # NOVO: Importamos o pytz

# --- CONFIGURAÇÕES FIXAS ---
# ... (restante das configurações fixas permanece igual)

# ... (Funções helper, limpeza e cálculo de KPIs permanecem iguais)
# --- FUNÇÕES DE LIMPEZA E CÁLCULO DE KPIS ---

# MUDANÇA: REMOÇÃO TOTAL DO CACHE (@st.cache_data)
def carregar_e_limpar_dados():
    st.set_page_config(layout="wide", page_title="💰 Controle de vendas diário")
    
    # AJUSTE CRÍTICO: Definindo o FUSO HORÁRIO de São Paulo (Brasília)
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    agora_brasilia = datetime.now(fuso_brasilia) # Obtém a data/hora AGORA no fuso de Brasília
    data_atual = agora_brasilia.date() # Apenas a data para o filtro diário

    # ... (o restante da função carregar_e_limpar_dados permanece INALTERADO)

    # ... (A função continua com as autenticações, carregamento e filtragem)
    # ...
    # return df_vendas_mes, df_vendas_dia, df_gastos_mes, df_gastos_dia

# --- FUNÇÃO PRINCIPAL DE MONTAGEM DO DASHBOARD STREAMLIT ---
def montar_dashboard(kpis_vendas, kpis_gastos):
    
    # AJUSTE: Usamos o fuso de Brasília para a hora de atualização
    fuso_brasilia = pytz.timezone('America/Sao_Paulo')
    hora_atualizacao = datetime.now(fuso_brasilia).strftime('%d/%m/%Y %H:%M:%S')

    # MUDANÇA: BOTÃO BEM VISÍVEL NO TOPO
    if st.button("🔴 CLIQUE AQUI PARA ATUALIZAR DADOS AGORA (FORÇAR RECARGA)", type="primary"):
        st.rerun() 
    
    st.title(f"🎂 Painel de Confeitaria: Mês de {datetime.now(fuso_brasilia).strftime('%B/%Y').upper()}") # AJUSTE AQUI TAMBÉM
    
    # MANTEM a última atualização, mas remove a menção ao cache
    st.caption(f"Última atualização de dados da planilha: **{hora_atualizacao}**")
    
    # ... (o restante da função montar_dashboard permanece INALTERADO)
    # ...


# --- EXECUÇÃO PRINCIPAL STREAMLIT ---
if __name__ == "__main__":
    
    # Requer que o import do pytz esteja no topo do arquivo.
    # ... (o restante do código permanece INALTERADO)
