import streamlit as st
import requests
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import uuid

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Plataforma de Voos Premium", page_icon="✈️", layout="wide")

# =================================================================
# 🔑 RECUPERAÇÃO SEGURA DE CHAVES E CONEXÃO COM O GOOGLE
# =================================================================
try:
    MINHA_CHAVE_SERPAPI = st.secrets["SERPAPI_KEY"]
    MEU_TOKEN_TELEGRAM = st.secrets["TELEGRAM_TOKEN"]
    MEU_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
    
    # Conectando ao Google Sheets
    cred_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
    escopo = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    credenciais = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, escopo)
    cliente_google = gspread.authorize(credenciais)
    
    # Abre a planilha pelo nome exato (precisa estar compartilhada com o email do robô)
    planilha = cliente_google.open("Alertas_Voos").worksheet("alertas")
    
except Exception as e:
    st.error(f"Erro ao conectar com as chaves (Secrets): {e}")
    st.stop()
# =================================================================

st.sidebar.title("📌 Menu")
pagina = st.sidebar.radio("Ir para:", ["🔍 Buscar e Criar Alertas", "🗂️ Gerenciar Alertas Ativos"])

if pagina == "🔍 Buscar e Criar Alertas":
    st.title("✈️ Buscador de Voos & Gerador de Alertas")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        origem = st.text_input("Aeroporto(s) ORIGEM (Ex: VCP,GRU):", value="VCP,GRU")
    with col2:
        destino = st.text_input("Aeroporto(s) DESTINO (Ex: MIA,FLL,MCO):", value="MIA,FLL,MCO")
    with col3:
        classe_nome = st.selectbox("Classe de Voo:", ["Econômica", "Executiva"])
        classe_voo = "1" if classe_nome == "Econômica" else "3"

    st.subheader("🗓️ Escolha o Intervalo de Datas para IDA")
    col_data1, col_data2, col_data3 = st.columns(3)
    with col_data1:
        data_ida_inicio = st.date_input("A partir do dia:", datetime.date(2026, 10, 10))
    with col_data2:
        data_ida_fim = st.date_input("Até o dia (Range de Ida):", datetime.date(2026, 10, 12))
    with col_data3:
        duracao_viagem = st.number_input("Duração (0 = Bate e Volta):", value=14, min_value=0)

    st.subheader("👥 Filtros Adicionais & Alerta de Preço")
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
        salvar_alerta = st.button("🔔 Salvar este Alerta")

    # SALVAR NO GOOGLE SHEETS
    if salvar_alerta:
        valor_direto_bd = 1 if somente_diretos else 0
        id_unico = str(uuid.uuid4())[:8] # Cria um ID curto aleatório
        nova_linha = [
            id_unico, origem, destino, data_ida_inicio.strftime("%Y-%m-%d"), 
            data_ida_fim.strftime("%Y-%m-%d"), int(duracao_viagem), classe_voo, 
            int(qtd_adultos), int(qtd_criancas), float(preco_alvo), "Ativo", valor_direto_bd
        ]
        planilha.append_row(nova_linha)
        st.success(f"✅ Alerta salvo na Planilha do Google com sucesso para {destino}!")

    if buscar:
        if data_ida_inicio > data_ida_fim:
            st.error("A data inicial não pode ser maior que a data final.")
        else:
            dias_para_pesquisar = []
            data_atual = data_ida_inicio
            while data_atual <= data_ida_fim:
                dias_para_pesquisar.append(data_atual)
                data_atual += datetime.timedelta(days=1)
            
            todos_os_voos_acumulados = []
            with st.spinner(f"Varrendo {len(dias_para_pesquisar)} datas no Google Flights..."):
                for data_ida_loop in dias_para_pesquisar:
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
                todos_os_voos_acumulados = sorted(todos_os_voos_acumulados, key=lambda x: x.get("price", 999999))[:10]
                st.success("✅ Resultados encontrados:")
                msg_tel = f"🚨 *BUSCA MANUAL ABAIXO DE R$ {preco_alvo}!* 🚨\n\n"
                achou_promocao = False

                for index, voo in enumerate(todos_os_voos_acumulados, 1):
                    p_total = voo.get("price", 0)
                    trechos = voo.get("flights", [])
                    if not trechos: continue
                    
                    comp = trechos[0].get("airline", "N/A")
                    orig_r = trechos[0].get("departure_airport", {}).get("id", "N/A")
                    dest_r = trechos[-1].get("arrival_airport", {}).get("id", "N/A")
                    saida = trechos[0].get("departure_airport", {}).get("time", "N/A")[11:16]
                    
                    escalas = "Voo Direto" if len(trechos)-1 == 0 else f"{len(trechos)-1} Parada(s)"
                    dur_m = voo.get("total_duration", 0)
                    dur_txt = f"{dur_m//60}h {dur_m%60}m"
                    
                    with st.container():
                        st.markdown(f"### #{index} | {comp} — **R$ {p_total}**")
                        c1, c2, c3 = st.columns(3)
                        c1.write(f"📅 **Ida:** {voo['data_ida_pesquisada']} às {saida}\n📅 **Volta:** {voo['data_volta_pesquisada']}")
                        c2.write(f"_Rota:_ {orig_r} ➔ {dest_r}\n⏱️ _Conexões:_ {escalas}")
                        c3.write(f"⏳ _Duração:_ {dur_txt}")
                        st.markdown("---")
                        
                    if p_total <= preco_alvo:
                        achou_promocao = True
                        msg_tel += f"✈️ *{comp}* | 💰 *R$ {p_total}*\n📅 {voo['data_ida_pesquisada']} ➔ {voo['data_volta_pesquisada']}\n"
                        if somente_diretos: msg_tel += f"✅ APENAS DIRETOS\n"
                        msg_tel += "➖➖➖➖➖➖➖➖➖➖\n"
                        
                if achou_promocao:
                    requests.post(f"https://api.telegram.org/bot{MEU_TOKEN_TELEGRAM}/sendMessage", data={"chat_id": MEU_CHAT_ID, "text": msg_tel, "parse_mode": "Markdown"})
            else:
                st.error("Nenhum voo encontrado.")

elif pagina == "🗂️ Gerenciar Alertas Ativos":
    st.title("🗂️ Seus Alertas de Monitoramento")
    st.write("Lendo os dados direto do seu Google Sheets...")

    # Pega todos os registros pulando o cabeçalho
    try:
        alertas_salvos = planilha.get_all_records()
    except Exception as e:
        st.error("A planilha está vazia ou com o cabeçalho incorreto. Crie um alerta primeiro.")
        alertas_salvos = []

    if not alertas_salvos:
        st.info("Nenhum alerta encontrado na planilha.")
    else:
        for indice_linha, alerta in enumerate(alertas_salvos, start=2): # Start=2 porque a linha 1 é o cabeçalho
            id_a = alerta.get("id", "")
            orig, dest = alerta.get("origem", ""), alerta.get("destino", "")
            ida_i, ida_f, dur = alerta.get("data_ida_inicio", ""), alerta.get("data_ida_fim", ""), alerta.get("duracao_viagem", "")
            alvo, status, diretos = alerta.get("preco_alvo", 0), alerta.get("status", ""), alerta.get("somente_diretos", 0)
            
            badge_direto = " | 🛑 Apenas Diretos" if diretos == 1 else ""
            
            with st.expander(f"✈️ {orig} ➔ {dest} | Meta: R$ {alvo} | Estado: **{status}** {badge_direto}"):
                st.write(f"📅 **Intervalo:** {ida_i} a {ida_f} | ⏳ **Duração:** {dur} dias")
                col_c1, col_c2 = st.columns(2)
                
                with col_c1:
                    if status == "Ativo":
                        if st.button("⏸️ Pausar", key=f"p_{id_a}"):
                            planilha.update_cell(indice_linha, 11, 'Pausado') # Atualiza a coluna 11 (status)
                            st.rerun()
                    else:
                        if st.button("▶️ Ativar", key=f"a_{id_a}"):
                            planilha.update_cell(indice_linha, 11, 'Ativo')
                            st.rerun()
                with col_c2:
                    if st.button("🗑️ Deletar", key=f"d_{id_a}"):
                        planilha.delete_rows(indice_linha)
                        st.rerun()
