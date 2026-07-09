import streamlit as st
import requests
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import uuid
import urllib.parse
import time

# =================================================================
# CONFIGURAÇÃO DA PÁGINA E BANCO DE DADOS NA NUVEM
# =================================================================
st.set_page_config(page_title="Plataforma de Voos Premium", page_icon="✈️", layout="wide")

# Inicializa as gavetas de memória (Session State) para evitar que os dados sumam ao clicar em botões
if "resultados_voos" not in st.session_state:
    st.session_state.resultados_voos = None
if "filtros_pesquisa" not in st.session_state:
    st.session_state.filtros_pesquisa = {}

@st.cache_data(ttl=5) # Cache curto apenas para evitar duplo clique acidental travar a cota do Sheets
def buscar_dados_planilha(nome_aba):
    cred_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
    escopo = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credenciais = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, escopo)
    cliente_google = gspread.authorize(credenciais)
    return cliente_google.open("Alertas_Voos").worksheet(nome_aba).get_all_records()

def obter_conexao_direta(nome_aba):
    cred_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
    escopo = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credenciais = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, escopo)
    cliente_google = gspread.authorize(credenciais)
    return cliente_google.open("Alertas_Voos").worksheet(nome_aba)

try:
    MINHA_CHAVE_SERPAPI = st.secrets["SERPAPI_KEY"]
    MEU_TOKEN_TELEGRAM = st.secrets["TELEGRAM_TOKEN"]
    MEU_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except Exception as e:
    st.error(f"Erro ao conectar com as chaves (Secrets): {e}")
    st.stop()

# =================================================================
# MENU LATERAL
# =================================================================
st.sidebar.title("📌 Menu")
pagina = st.sidebar.radio("Navegação:", ["🔍 Buscar Voos", "🗂️ Gerenciar Alertas", "📜 Histórico de Pesquisas"])

# =================================================================
# FUNÇÃO: EXTRAIR DETALHES RICOS DO VOO
# =================================================================
def extrair_detalhes_completos(voo, data_ida_str, data_volta_str):
    trechos = voo.get("flights", [])
    layovers = voo.get("layovers", [])
    
    if not trechos:
        return "Detalhes indisponíveis."

    comp_principal = trechos[0].get("airline", "N/A")
    origem_final = trechos[0].get("departure_airport", {}).get("id", "N/A")
    destino_final = trechos[-1].get("arrival_airport", {}).get("id", "N/A")
    duracao_total = voo.get("total_duration", 0)
    
    texto = f"✈️ *Companhia:* {comp_principal}\n"
    texto += f"📅 *Ida:* {data_ida_str} | *Volta:* {data_volta_str}\n"
    texto += f"⏳ *Duração Total da Viagem:* {duracao_total//60}h {duracao_total%60}m\n\n"
    texto += "*--- DETALHAMENTO DOS TRECHOS ---*\n"

    for j, trecho in enumerate(trechos):
        saida = trecho.get("departure_airport", {}).get("time", "")[11:16]
        chegada = trecho.get("arrival_airport", {}).get("time", "")[11:16]
        orig_t = trecho.get("departure_airport", {}).get("id", "N/A")
        dest_t = trecho.get("arrival_airport", {}).get("id", "N/A")
        dur_t = trecho.get("duration", 0)
        
        texto += f"🛫 {orig_t} ({saida}) ➔ 🛬 {dest_t} ({chegada}) | Voo: {dur_t//60}h {dur_t%60}m\n"
        
        if j < len(layovers):
            espera = layovers[j].get("duration", 0)
            local = layovers[j].get("name", "Conexão")
            texto += f"   🛑 *Espera em {local}:* {espera//60}h {espera%60}m\n"

    return texto

# =================================================================
# PÁGINA 1: BUSCAR VOOS
# =================================================================
if pagina == "🔍 Buscar Voos":
    st.title("✈️ Buscador de Voos Premium")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        origem = st.text_input("Aeroporto(s) ORIGEM (Ex: VCP,GRU):", value="VCP,GRU")
    with col2:
        destino = st.text_input("Aeroporto(s) DESTINO (Ex: MIA,FLL):", value="MIA,FLL,MCO")
    with col3:
        classe_nome = st.selectbox("Classe de Voo:", ["Econômica", "Executiva"])
        classe_voo = "1" if classe_nome == "Econômica" else "3"

    st.subheader("🗓️ Datas da Viagem")
    col_d1, col_d2, col_d3 = st.columns(3)
    with col_d1:
        data_ida_inicio = st.date_input("Ida a partir de:", datetime.date.today() + datetime.timedelta(days=30))
    with col_d2:
        data_ida_fim = st.date_input("Ida até (Range):", data_ida_inicio)
    
    with col_d3:
        tipo_volta = st.radio("Como definir a volta?", ["Opção A (Data Fixa)", "Opção B (Duração em Dias)"])
        if "A" in tipo_volta:
            data_volta_fixa = st.date_input("Data de Volta:", data_ida_fim + datetime.timedelta(days=7))
            duracao_viagem = None
        else:
            duracao_viagem = st.number_input("Duração (0 = Bate e Volta):", value=14, min_value=0)
            data_volta_fixa = None

    st.subheader("👥 Filtros Adicionais & Alerta")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        qtd_adultos = st.number_input("Adultos:", value=1, min_value=1, step=1)
    with col_p2:
        qtd_criancas = st.number_input("Crianças (2 a 11 anos):", value=0, min_value=0, step=1)
    with col_p3:
        preco_alvo = st.number_input("Preço Alvo TOTAL (R$):", value=4500, step=100)

    somente_diretos = st.checkbox("🛑 Exibir APENAS voos diretos")
    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        buscar = st.button("🔍 Iniciar Varredura de Voos")
    with col_btn2:
        salvar_alerta = st.button("🔔 Salvar Rota para Monitoramento (Alerta)")

    if salvar_alerta:
        if data_volta_fixa:
            duracao_calc = (data_volta_fixa - data_ida_inicio).days
        else:
            duracao_calc = int(duracao_viagem)
            
        valor_direto_bd = 1 if somente_diretos else 0
        id_unico = str(uuid.uuid4())[:8]
        nova_linha =
