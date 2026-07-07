import streamlit as st
import requests
import datetime
import sqlite3

# =================================================================
# 1. CONFIGURAÇÃO DO BANCO DE DADOS (SQLite) E ATUALIZAÇÃO SEGURA
# =================================================================
conn = sqlite3.connect("alertas_voos.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origem TEXT,
    destino TEXT,
    data_ida_inicio TEXT,
    data_ida_fim TEXT,
    duracao_viagem INTEGER,
    classe TEXT,
    qtd_adultos INTEGER,
    qtd_criancas INTEGER,
    preco_alvo REAL,
    status TEXT DEFAULT 'Ativo'
)
""")

# Tenta adicionar a nova coluna de "voos diretos" caso o banco de dados já exista na versão antiga
try:
    cursor.execute("ALTER TABLE alertas ADD COLUMN somente_diretos INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass # A coluna já existe, segue o jogo.

conn.commit()

# CONFIGURAÇÃO DA PÁGINA
st.set_page_config(page_title="Plataforma de Voos Premium", page_icon="✈️", layout="wide")

# =================================================================
# 🔑 RECUPERAÇÃO SEGURA DE CHAVES (DA NUVEM)
# =================================================================
try:
    MINHA_CHAVE_SERPAPI = st.secrets["SERPAPI_KEY"]
    MEU_TOKEN_TELEGRAM = st.secrets["TELEGRAM_TOKEN"]
    MEU_CHAT_ID = st.secrets["TELEGRAM_CHAT_ID"]
except Exception:
    st.error("Configuração de chaves (Secrets) não encontrada no Streamlit Cloud.")
    st.stop()
# =================================================================

# MENU LATERAL DE NAVEGAÇÃO
st.sidebar.title("📌 Menu")
pagina = st.sidebar.radio("Ir para:", ["🔍 Buscar e Criar Alertas", "🗂️ Gerenciar Alertas Ativos"])

# =================================================================
# PÁGINA 1: BUSCAR E CRIAR ALERTAS
# =================================================================
if pagina == "🔍 Buscar e Criar Alertas":
    st.title("✈️ Buscador de Voos & Gerador de Alertas")
    
    # LINHA 1: DESTINOS E CLASSE
    col1, col2, col3 = st.columns(3)
    with col1:
        origem = st.text_input("Aeroporto(s) de ORIGEM (Separe por vírgula):", value="VCP,GRU")
    with col2:
        destino = st.text_input("Aeroporto(s) de DESTINO (Separe por vírgula):", value="MIA,FLL,MCO")
    with col3:
        classe_nome = st.selectbox("Classe de Voo:", ["Econômica", "Executiva"])
        classe_voo = "1" if classe_nome == "Econômica" else "3"

    # LINHA 2: DATAS FLEXÍVEIS (INTERVALO DE IDA E DURAÇÃO COM OPÇÃO 0)
    st.subheader("🗓️ Escolha o Intervalo de Datas para IDA")
    col_data1, col_data2, col_data3 = st.columns(3)
    with col_data1:
        data_ida_inicio = st.date_input("A partir do dia:", datetime.date(2026, 10, 10))
    with col_data2:
        data_ida_fim = st.date_input("Até o dia (Range de Ida):", datetime.date(2026, 10, 12))
    with col_data3:
        # Ajuste feito: min_value=0 permite viagens bate-e-volta no mesmo dia
        duracao_viagem = st.number_input("Duração (0 = Bate e Volta no mesmo dia):", value=14, min_value=0)

    # LINHA 3: PASSAGEIROS, FILTRO DE PARADAS E ALERTA
    st.subheader("👥 Filtros Adicionais & Alerta de Preço")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        qtd_adultos = st.number_input("Adultos:", value=1, min_value=1, step=1)
    with col_p2:
        qtd_criancas = st.number_input("Crianças (2 a 11 anos):", value=0, min_value=0, step=1)
    with col_p3:
        preco_alvo = st.number_input("Preço Alvo TOTAL para Alerta (R$):", value=4500, step=100)

    # Nova opção visual para buscar apenas voos diretos
    somente_diretos = st.checkbox("🛑 Exibir APENAS voos diretos (sem escalas)")

    st.markdown("---")
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        buscar = st.button("🔍 Iniciar Varredura de Voos")
    with col_btn2:
        salvar_alerta = st.button("🔔 Salvar este Alerta de Monitoramento")

    # Salva no Banco de Dados mantendo os ranges flexíveis, passageiros e filtro de direto cadastrados
    if salvar_alerta:
        valor_direto_bd = 1 if somente_diretos else 0
        cursor.execute("""
            INSERT INTO alertas (origem, destino, data_ida_inicio, data_ida_fim, duracao_viagem, classe, qtd_adultos, qtd_criancas, preco_alvo, somente_diretos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (origem, destino, data_ida_inicio.strftime("%Y-%m-%d"), data_ida_fim.strftime("%Y-%m-%d"), int(duracao_viagem), classe_voo, int(qtd_adultos), int(qtd_criancas), preco_alvo, valor_direto_bd))
        conn.commit()
        st.success(f"✅ Alerta dinâmico salvo com sucesso para {destino}! O sistema passará a monitorar este range.")

    # Lógica de busca acumulada e corrigida
    if buscar:
        if data_ida_inicio > data_ida_fim:
            st.error("Erro: A data inicial de ida não pode ser maior que a data final.")
        else:
            dias_para_pesquisar = []
            data_atual = data_ida_inicio
            while data_atual <= data_ida_fim:
                dias_para_pesquisar.append(data_atual)
                data_atual += datetime.timedelta(days=1)
            
            st.info(f"O sistema fará {len(dias_para_pesquisar)} pesquisas para cobrir o seu range de datas.")
            todos_os_voos_acumulados = []
            
            with st.spinner("Varrendo o Google Flights de forma flexível..."):
                for data_ida_loop in dias_para_pesquisar:
                    data_volta_loop = data_ida_loop + datetime.timedelta(days=int(duracao_viagem))
                    
                    url_da_api = "https://serpapi.com/search"
                    parametros = {
                        "engine": "google_flights", "departure_id": origem, "arrival_id": destino,
                        "outbound_date": data_ida_loop.strftime("%Y-%m-%d"), "return_date": data_volta_loop.strftime("%Y-%m-%d"),
                        "travel_class": classe_voo, "adults": int(qtd_adultos), "children": int(qtd_criancas),
                        "currency": "BRL", "api_key": MINHA_CHAVE_SERPAPI
                    }
                    
                    # Se o usuário marcou apenas diretos, injeta o filtro na API
                    if somente_diretos:
                        parametros["stops"] = "0"

                    resposta = requests.get(url_da_api, params=parametros)
                    dados_dos_voos = resposta.json()

                    if "error" not in dados_dos_voos:
                        melhores = dados_dos_voos.get("best_flights", [])
                        outros = dados_dos_voos.get("other_flights", [])
                        for v in (melhores + outros):
                            v['data_ida_pesquisada'] = data_ida_loop.strftime("%d/%m/%Y")
                            v['data_volta_pesquisada'] = data_volta_loop.strftime("%d/%m/%Y")
                            todos_os_voos_acumulados.append(v)

            if len(todos_os_voos_acumulados) > 0:
                todos_os_voos_acumulados = sorted(todos_os_voos_acumulados, key=lambda x: x.get("price", 999999))
                top_10_voos = todos_os_voos_acumulados[:10]
                
                st.success(f"✅ Varredura concluída! Aqui estão as melhores opções encontradas:")
                
                mensagem_telegram = f"🚨 *PROMOÇÃO MULTI-DATAS ABAIXO DE R$ {preco_alvo}!* 🚨\n\n"
                encontrou_promocao = False

                for index, voo in enumerate(top_10_voos, 1):
                    preco_total_viagem = voo.get("price", 0)
                    trechos = voo.get("flights", [])
                    if not trechos:
                        continue
                    
                    primeiro_trecho = trechos[0]
                    ultimo_trecho = trechos[-1]
                    companhia = primeiro_trecho.get("airline")
                    origem_real = primeiro_trecho.get("departure_airport", {}).get("id", "N/A")
                    destino_real = ultimo_trecho.get("arrival_airport", {}).get("id", "N/A")
                    
                    horario_saida = primeiro_trecho.get("departure_airport", {}).get("time", "N/A")
                    if len(horario_saida) > 11:
                        horario_saida = horario_saida[11:16]
                    
                    qtd_escalas = len(trechos) - 1
                    texto_escalas = "Voo Direto" if qtd_escalas == 0 else f"{qtd_escalas} Parada(s)"
                    
                    duracao_min = voo.get("total_duration", 0)
                    texto_duracao = f"{duracao_min // 60}h {duracao_min % 60}m" if duracao_min > 0 else "N/A"

                    # CARD VISUAL NA TELA COM OS DETALHES RECUPERADOS
                    with st.container():
                        st.markdown(f"### #{index} | {companhia} — **R$ {preco_total_viagem}** (Total para o Grupo)")
                        col_c1, col_c2, col_c3 = st.columns(3)
                        with col_c1:
                            st.write(f"📅 **Ida:** {voo['data_ida_pesquisada']} às {horario_saida}")
                            st.write(f"📅 **Volta:** {voo['data_volta_pesquisada']}")
                        with col_c2:
                            st.write(f"_Rota:_ {origem_real} ➔ {destino_real}")
                            st.write(f"⏱️ _Conexões:_ {texto_escalas}")
                        with col_c3:
                            st.write(f"⏳ _Duração Total:_ {texto_duracao}")
                        st.markdown("---")

                    if preco_total_viagem <= preco_alvo:
                        encontrou_promocao = True
                        mensagem_telegram += f"✈️ *{companhia}* | 💰 *R$ {preco_total_viagem}*\n"
                        mensagem_telegram += f"📅 Ida: {voo['data_ida_pesquisada']} | Volta: {voo['data_volta_pesquisada']}\n"
                        mensagem_telegram += f"🛫 Rota: {origem_real} ➔ {destino_real} | ⏳ {texto_duracao}\n"
                        if somente_diretos:
                            mensagem_telegram += f"✅ APENAS VOOS DIRETOS\n"
                        mensagem_telegram += "➖➖➖➖➖➖➖➖➖➖\n"

                if encontrou_promocao:
                    url_telegram = f"https://api.telegram.org/bot{MEU_TOKEN_TELEGRAM}/sendMessage"
                    requests.post(url_telegram, data={"chat_id": MEU_CHAT_ID, "text": mensagem_telegram, "parse_mode": "Markdown"})
                    st.success("📲 Voos detectados abaixo da meta! Alerta enviado ao Telegram.")
            else:
                st.error("Nenhum voo encontrado no intervalo e filtros selecionados.")

# =================================================================
# PÁGINA 2: GERENCIAR ALERTAS ATIVOS E MONITORAR
# =================================================================
elif pagina == "🗂️ Gerenciar Alertas Ativos":
    st.title("🗂️ Seus Alertas de Monitoramento")
    st.write("Abaixo você gerencia ou executa os rastreamentos multi-datas salvos no banco de dados.")

    # 🔄 BOTÃO MÁGICO DO MONITORAMENTO AUTOMÁTICO
    if st.button("🔄 Executar Monitoramento Agora (Processar todos os ranges ativos)"):
        with st.spinner("Processando todos os intervalos de monitoramento..."):
            cursor.execute("SELECT origem, destino, data_ida_inicio, data_ida_fim, duracao_viagem, classe, qtd_adultos, qtd_criancas, preco_alvo, somente_diretos FROM alertas WHERE status = 'Ativo'")
            alertas_ativos = cursor.fetchall()
            
            if not alertas_ativos:
                st.warning("Nenhum alerta ativo configurado para monitoramento.")
            else:
                for art in alertas_ativos:
                    orig_a, dest_a, ida_ini_a, ida_fim_a, dur_a, cl_a, ad_a, cr_a, alvo_a, diretos_a = art
                    
                    d_ini = datetime.datetime.strptime(ida_ini_a, "%Y-%m-%d").date()
                    d_fim = datetime.datetime.strptime(ida_fim_a, "%Y-%m-%d").date()
                    
                    dias_varredura = []
                    curr_d = d_ini
                    while curr_d <= d_fim:
                        dias_varredura.append(curr_d)
                        curr_d += datetime.timedelta(days=1)
                        
                    msg_tel = f"🚨 *ALERTA DA MONITORIA AUTOMÁTICA:* 🚨\n\nRota: {orig_a} ➔ {dest_a} (Alvo: R$ {alvo_a})\n"
                    disparar_mensagem = False
                    
                    for d_ida_v in dias_varredura:
                        d_volta_v = d_ida_v + datetime.timedelta(days=dur_a)
                        url_da_api = "https://serpapi.com/search"
                        params = {
                            "engine": "google_flights", "departure_id": orig_a, "arrival_id": dest_a,
                            "outbound_date": d_ida_v.strftime("%Y-%m-%d"), "return_date": d_volta_v.strftime("%Y-%m-%d"),
                            "travel_class": cl_a, "adults": int(ad_a), "children": int(cr_a),
                            "currency": "BRL", "api_key": MINHA_CHAVE_SERPAPI
                        }
                        
                        if diretos_a == 1:
                            params["stops"] = "0"
                            
                        res = requests.get(url_da_api, params=params).json()
                        
                        if "error" not in res:
                            opcoes = (res.get("best_flights", []) + res.get("other_flights", []))[:3]
                            for op in opcoes:
                                p_total = op.get("price", 99999)
                                if p_total <= alvo_a:
                                    disparar_mensagem = True
                                    comp = op["flights"][0].get("airline", "N/A")
                                    dur_v = op.get("total_duration", 0)
                                    msg_tel += f"✈️ *{comp}* | 💰 *R$ {p_total}*\n"
                                    msg_tel += f"📅 Ida: {d_ida_v.strftime('%d/%m/%Y')} | Volta: {d_volta_v.strftime('%d/%m/%Y')} | ⏳ {dur_v//60}h {dur_v%60}m\n"
                                    msg_tel += "➖➖➖➖➖➖➖➖➖➖\n"
                                    
                    if disparar_mensagem:
                        url_t = f"https://api.telegram.org/bot{MEU_TOKEN_TELEGRAM}/sendMessage"
                        requests.post(url_t, data={"chat_id": MEU_CHAT_ID, "text": msg_tel, "parse_mode": "Markdown"})
                st.success("✅ Monitoramento de rotas e ranges concluído com sucesso!")

    st.markdown("---")
    
    # LISTAGEM E CONTROLE DOS CARDS SALVOS
    cursor.execute("SELECT id, origem, destino, data_ida_inicio, data_ida_fim, duracao_viagem, preco_alvo, status, somente_diretos FROM alertas")
    alertas_salvos = cursor.fetchall()

    if not alertas_salvos:
        st.info("Você ainda não tem nenhum alerta criado.")
    else:
        for alerta in alertas_salvos:
            id_alerta, orig, dest, ida_i, ida_f, dur, alvo, status, diretos = alerta
            
            # Ajuste na formatação do card para mostrar se é apenas voo direto
            badge_direto = " | 🛑 Apenas Diretos" if diretos == 1 else ""
            
            with st.expander(f"✈️ Rota: {orig} ➔ {dest} | Meta Grupo: R$ {alvo} | Estado: **{status}** {badge_direto}"):
                st.write(f"📅 **Intervalo de Ida:** {ida_i} até {ida_f} | ⏳ **Duração:** {dur} dias")
                col_card1, col_card2 = st.columns(2)
                with col_card1:
                    if status == "Ativo":
                        if st.button("⏸️ Pausar Rastreio", key=f"p_{id_alerta}"):
                            cursor.execute("UPDATE alertas SET status = 'Pausado' WHERE id = ?", (id_alerta,))
                            conn.commit()
                            st.rerun()
                    else:
                        if st.button("▶️ Ativar Rastreio", key=f"a_{id_alerta}"):
                            cursor.execute("UPDATE alertas SET status = 'Ativo' WHERE id = ?", (id_alerta,))
                            conn.commit()
                            st.rerun()
                with col_card2:
                    if st.button("🗑️ Deletar Definitivamente", key=f"d_{id_alerta}"):
                        cursor.execute("DELETE FROM alertas WHERE id = ?", (id_alerta,))
                        conn.commit()
                        st.rerun()
