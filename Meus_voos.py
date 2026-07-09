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

# Inicializa as gavetas de memória (Session State) para evitar que os dados somam ao clicar em botões
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
        data_ida_inicio = st.date_input("Ida a partir de:", datetime.date(2026, 10, 10))
    with col_d2:
        data_ida_fim = st.date_input("Ida até (Range):", datetime.date(2026, 10, 12))
    
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
        nova_linha = [
            id_unico, origem, destino, data_ida_inicio.strftime("%Y-%m-%d"), 
            data_ida_fim.strftime("%Y-%m-%d"), duracao_calc, classe_voo, 
            int(qtd_adultos), int(qtd_criancas), float(preco_alvo), "Ativo", valor_direto_bd
        ]
        
        plan_al_direta = obter_conexao_direta("alertas")
        plan_al_direta.append_row(nova_linha)
        st.cache_data.clear()
        st.success("✅ Alerta salvo na Planilha do Google com sucesso!")

    # Executa a busca real e salva na gaveta (Session State)
    if buscar:
        if data_ida_inicio > data_ida_fim:
            st.error("A data inicial não pode ser maior que a data final.")
        elif data_volta_fixa and data_volta_fixa < data_ida_fim:
            st.error("A data de volta não pode ser anterior à data final de ida.")
        else:
            dias_para_pesquisar = []
            data_atual = data_ida_inicio
            while data_atual <= data_ida_fim:
                dias_para_pesquisar.append(data_atual)
                data_atual += datetime.timedelta(days=1)
            
            todos_os_voos_acumulados = []
            with st.spinner(f"Varrendo as datas no Google Flights..."):
                for data_ida_loop in dias_para_pesquisar:
                    if data_volta_fixa:
                        data_volta_loop = data_volta_fixa
                    else:
                        data_volta_loop = data_ida_loop + datetime.timedelta(days=int(duracao_viagem))
                        
                    params = {
                        "engine": "google_flights", "departure_id": origem, "arrival_id": destino,
                        "outbound_date": data_ida_loop.strftime("%Y-%m-%d"), "return_date": data_volta_loop.strftime("%Y-%m-%d"),
                        "travel_class": classe_voo, "adults": int(qtd_adultos), "children": int(qtd_criancas),
                        "currency": "BRL", "api_key": MINHA_CHAVE_SERPAPI
                    }
                    if somente_diretos:
                        params["stops"] = "1"
                    
                    res = requests.get("https://serpapi.com/search", params=params).json()
                    if "error" not in res:
                        for v in (res.get("best_flights", []) + res.get("other_flights", [])):
                            v['data_ida_pesquisada'] = data_ida_loop.strftime("%d/%m/%Y")
                            v['data_volta_pesquisada'] = data_volta_loop.strftime("%d/%m/%Y")
                            todos_os_voos_acumulados.append(v)

            if todos_os_voos_acumulados:
                # Armazena os resultados e os filtros de forma fixa na sessão segura
                st.session_state.resultados_voos = sorted(todos_os_voos_acumulados, key=lambda x: x.get("price", 999999))[:10]
                st.session_state.filtros_pesquisa = {"origem": origem, "destino": destino, "preco_alvo": preco_alvo, "somente_diretos": somente_diretos}
            else:
                st.session_state.resultados_voos = []
                st.error("Nenhum voo encontrado com esses critérios.")

    # Renderiza os cards e botões adicionais se houver dados salvos na gaveta (Session State)
    if st.session_state.resultados_voos:
        st.success("✅ Resultados encontrados!")
        
        # --- BLOCO DE CONTROLE DO HISTÓRICO FIXADO ---
        melhor_voo_historico = st.session_state.resultados_voos[0]
        detalhes_historico = extrair_detalhes_completos(melhor_voo_historico, melhor_voo_historico['data_ida_pesquisada'], melhor_voo_historico['data_volta_pesquisada'])
        
        if st.button("💾 Salvar Melhor Resultado no Histórico"):
            with st.spinner("Gravando no Google Sheets..."):
                hoje = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
                rota_str = f"{st.session_state.filtros_pesquisa['origem']} -> {st.session_state.filtros_pesquisa['destino']}"
                datas_str = f"{melhor_voo_historico['data_ida_pesquisada']} a {melhor_voo_historico['data_volta_pesquisada']}"
                preco_str = f"R$ {melhor_voo_historico.get('price', 0)}"
                
                plan_hist_direta = obter_conexao_direta("historico")
                plan_hist_direta.append_row([hoje, rota_str, datas_str, preco_str, detalhes_historico])
                st.cache_data.clear() # Limpa o cache para forçar a atualização imediata na outra aba
                st.success("🔥 Sucesso! O melhor voo deste grupo foi gravado no seu histórico permanente.")

        # --- EXIBIÇÃO DOS DETALHES ---
        msg_tel = f"🚨 *BUSCA MANUAL ABAIXO DE R$ {st.session_state.filtros_pesquisa['preco_alvo']}!* 🚨\n\n"
        achou_promocao = False

        for index, voo in enumerate(st.session_state.resultados_voos, 1):
            p_total = voo.get("price", 0)
            ida_str = voo['data_ida_pesquisada']
            volta_str = voo['data_volta_pesquisada']
            
            texto_detalhado = extrair_detalhes_completos(voo, ida_str, volta_str)
            
            with st.expander(f"#{index} | R$ {p_total} | Ida: {ida_str} - Volta: {volta_str}", expanded=(index==1)):
                st.markdown(texto_detalhado.replace('\n', '  \n')) 
                
                texto_wpp = f"Olha essa passagem que achei! 😱\n\n*Preço Total:* R$ {p_total}\n{texto_detalhado}"
                link_wpp = f"https://api.whatsapp.com/send?text={urllib.parse.quote(texto_wpp)}"
                
                col_w1, col_w2 = st.columns(2)
                with col_w1:
                    st.markdown(f"[📲 Compartilhar no WhatsApp]({link_wpp})", unsafe_allow_html=True)
                with col_w2:
                    st.download_button(label="📄 Baixar Resumo (TXT)", data=texto_wpp, file_name=f"Voo_{p_total}.txt", mime="text/plain", key=f"dl_{index}")
            
            if p_total <= st.session_state.filtros_pesquisa['preco_alvo']:
                achou_promocao = True
                msg_tel += f"💰 *R$ {p_total}*\n{texto_detalhado}\n"
                msg_tel += "➖➖➖➖➖➖➖➖➖➖\n"

        # Disparo do Telegram se houver promoção dentro dos dados fixados
        if achou_promocao and buscar: # Só envia o Telegram na hora exata do clique de busca para evitar loops de envio
            requests.post(f"https://api.telegram.org/bot{MEU_TOKEN_TELEGRAM}/sendMessage", data={"chat_id": MEU_CHAT_ID, "text": msg_tel, "parse_mode": "Markdown"})
            st.success("📲 A busca atingiu o preço alvo! Alerta detalhado enviado ao seu Telegram.")

# =================================================================
# PÁGINA 2: GERENCIAR ALERTAS ATIVOS
# =================================================================
elif pagina == "🗂️ Gerenciar Alertas":
    st.title("🗂️ Seus Alertas de Monitoramento")
    
    alertas_salvos = buscar_dados_planilha("alertas")

    if not alertas_salvos:
        st.info("Nenhum alerta cadastrado na planilha.")
    else:
        for indice_linha, alerta in enumerate(alertas_salvos, start=2):
            id_a = alerta.get("id", "")
            orig, dest = alerta.get("origem", ""), alerta.get("destino", "")
            alvo, status, diretos = alerta.get("preco_alvo", 0), alerta.get("status", ""), alerta.get("somente_diretos", 0)
            
            badge_direto = " | 🛑 Apenas Diretos" if diretos == 1 else ""
            with st.expander(f"✈️ {orig} ➔ {dest} | Meta: R$ {alvo} | Estado: **{status}** {badge_direto}"):
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    if status == "Ativo":
                        if st.button("⏸️ Pausar", key=f"p_{id_a}"):
                            plan_al_direta = obter_conexao_direta("alertas")
                            plan_al_direta.update_cell(indice_linha, 11, 'Pausado')
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                    else:
                        if st.button("▶️ Ativar", key=f"a_{id_a}"):
                            plan_al_direta = obter_conexao_direta("alertas")
                            plan_al_direta.update_cell(indice_linha, 11, 'Ativo')
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                with col_c2:
                    if st.button("🗑️ Deletar", key=f"d_{id_a}"):
                        plan_al_direta = obter_conexao_direta("alertas")
                        plan_al_direta.delete_rows(indice_linha)
                        st.cache_data.clear()
                        time.sleep(1)
                        st.rerun()

# =================================================================
# PÁGINA 3: HISTÓRICO DE PESQUISAS
# =================================================================
elif pagina == "📜 Histórico de Pesquisas":
    st.title("📜 Seu Histórico de Melhores Voos")
    st.write("Abaixo estão as pesquisas salvas no Google Sheets.")
    
    historico_salvo = buscar_dados_planilha("historico")

    if not historico_salvo:
        st.info("Você ainda não salvou nenhum resultado no histórico. Faça uma busca e clique em 'Salvar Resultado no Histórico'.")
    else:
        for linha, registro in enumerate(reversed(historico_salvo)):
            data_pesq = registro.get("data_pesquisa", "")
            rota = registro.get("rota", "")
            preco = registro.get("melhor_preco", "")
            detalhes = registro.get("detalhes", "")
            
            with st.expander(f"🔍 {data_pesq} | {rota} | {preco}"):
                st.markdown(detalhes.replace('\n', '  \n'))
                link_wpp_hist = f"https://api.whatsapp.com/send?text={urllib.parse.quote('Olha essa pesquisa que deixei salva:\n\n' + detalhes)}"
                st.markdown(f"[📲 Reenviar pelo WhatsApp]({link_wpp_hist})", unsafe_allow_html=True)
