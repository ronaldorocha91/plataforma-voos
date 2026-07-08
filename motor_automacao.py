import requests
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# 1. PUXA AS CHAVES ESCONDIDAS DO GITHUB
MINHA_CHAVE_SERPAPI = os.environ.get("SERPAPI_KEY")
MEU_TOKEN_TELEGRAM = os.environ.get("TELEGRAM_TOKEN")
MEU_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
cred_dict = json.loads(os.environ.get("GOOGLE_CREDENTIALS_JSON"))

print("🤖 Iniciando Motor de Varredura Automática...")

# 2. CONECTA NA PLANILHA DO GOOGLE
escopo = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
credenciais = ServiceAccountCredentials.from_json_keyfile_dict(cred_dict, escopo)
cliente_google = gspread.authorize(credenciais)
planilha = cliente_google.open("Alertas_Voos").worksheet("alertas")

alertas_salvos = planilha.get_all_records()
alertas_ativos = [a for a in alertas_salvos if a.get("status") == "Ativo"]

if not alertas_ativos:
    print("😴 Nenhum alerta ativo encontrado. Encerrando.")
else:
    for art in alertas_ativos:
        orig_a = art["origem"]
        dest_a = art["destino"]
        ida_ini_a = art["data_ida_inicio"]
        ida_fim_a = art["data_ida_fim"]
        dur_a = int(art["duracao_viagem"])
        cl_a = str(art["classe"])
        ad_a = int(art["qtd_adultos"])
        cr_a = int(art["qtd_criancas"])
        alvo_a = float(art["preco_alvo"])
        diretos_a = int(art.get("somente_diretos", 0))
        
        d_ini = datetime.datetime.strptime(ida_ini_a, "%Y-%m-%d").date()
        d_fim = datetime.datetime.strptime(ida_fim_a, "%Y-%m-%d").date()
        
        dias_varredura = []
        curr_d = d_ini
        while curr_d <= d_fim:
            dias_varredura.append(curr_d)
            curr_d += datetime.timedelta(days=1)
            
        msg_tel = f"🚨 *ALERTA DA MONITORIA AUTOMÁTICA:* 🚨\n\nRota: {orig_a} ➔ {dest_a} (Alvo: R$ {alvo_a})\n"
        disparar_mensagem = False
        
        print(f"🔎 Pesquisando rota {orig_a} -> {dest_a} (Range: {ida_ini_a} a {ida_fim_a})")
        
        for d_ida_v in dias_varredura:
            d_volta_v = d_ida_v + datetime.timedelta(days=dur_a)
            url_da_api = "https://serpapi.com/search"
            params = {
                "engine": "google_flights", "departure_id": orig_a, "arrival_id": dest_a,
                "outbound_date": d_ida_v.strftime("%Y-%m-%d"), "return_date": d_volta_v.strftime("%Y-%m-%d"),
                "travel_class": cl_a, "adults": ad_a, "children": cr_a,
                "currency": "BRL", "api_key": MINHA_CHAVE_SERPAPI
            }
            
            if diretos_a == 1:
                params["stops"] = "1"
                
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
            print("🔥 Preço atingido! Enviando Telegram...")
            url_t = f"https://api.telegram.org/bot{MEU_TOKEN_TELEGRAM}/sendMessage"
            requests.post(url_t, data={"chat_id": MEU_CHAT_ID, "text": msg_tel, "parse_mode": "Markdown"})

print("✅ Rotina automática finalizada com sucesso.")
