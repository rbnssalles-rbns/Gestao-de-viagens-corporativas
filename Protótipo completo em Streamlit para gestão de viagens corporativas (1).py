#!/usr/bin/env python
# coding: utf-8

# In[2]:


#Parte 1: Configurações iniciais e políticas internas
# app.py - Parte 1
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import random
import requests

# =========================================================
# Configurações globais e estado
# =========================================================
st.set_page_config(page_title="Gestão de Viagens Corporativas", layout="wide")

# Estado de solicitações (em memória)
if "solicitacoes" not in st.session_state:
    st.session_state.solicitacoes = []  # lista de dicts

# ---------------------------------------------------------
# Políticas internas parametrizadas
# ---------------------------------------------------------
POLITICAS = {
    "limite_trecho_aereo": {
        "Diretor": 2500,
        "Superintendente": 2000,
        "Gerente": 1800,
        "Coordenador": 1500,
        "Analista": 1200,
        "Outros": 1000,
    },
    "limite_diaria_hotel": {
        "Diretor": 900,
        "Superintendente": 750,
        "Gerente": 650,
        "Coordenador": 550,
        "Analista": 450,
        "Outros": 350,
    },
    "categorias_permitidas_por_cargo": {
        "Diretor": ["Luxo", "Executivo", "Padrão"],
        "Superintendente": ["Executivo", "Padrão"],
        "Gerente": ["Executivo", "Padrão"],
        "Coordenador": ["Padrão"],
        "Analista": ["Padrão"],
        "Outros": ["Padrão"],
    },
    "antecedencia_minima_dias": 10,
}

# Ajuda de custo por hierarquia (valor base por dia)
AJUDA_CUSTO_HIERARQUIA = {
    "Diretor": 500,
    "Superintendente": 400,
    "Gerente": 300,
    "Coordenador": 200,
    "Analista": 150,
    "Outros": 100,
}

def multiplicador_ajuda(dias: int) -> float:
    """Multiplicador da ajuda de custo conforme duração da viagem."""
    if dias <= 1:
        return 1.0
    elif dias <= 3:
        return 1.1
    elif dias <= 5:
        return 1.2
    else:
        return 1.3

# =========================================================
# Integrações reais com APIs (Skyscanner)
# =========================================================
API_KEY_SKYSCANNER = "/apiservices/v3/voos/indicativo/pesquisa"

def buscar_voos_indicative(origem: str, destino: str, data_ida: date, data_volta: date, adultos: int = 1):
    """
    Consulta preços indicativos (cacheados) via Skyscanner:
    POST https://partners.api.skyscanner.net/apiservices/v3/flights/indicative/search
    Retorna lista de voos no formato do app.
    """
    headers = {"x-api-key": API_KEY_SKYSCANNER, "Content-Type": "application/json"}
    payload_ida = {
        "query": {
            "market": "BR",
            "locale": "pt-BR",
            "currency": "BRL",
            "originPlace": {"iata": origem},
            "destinationPlace": {"iata": destino},
            "outboundDate": {"year": data_ida.year, "month": data_ida.month, "day": data_ida.day},
            "adults": adultos
        }
    }
    payload_volta = {
        "query": {
            "market": "BR",
            "locale": "pt-BR",
            "currency": "BRL",
            "originPlace": {"iata": destino},
            "destinationPlace": {"iata": origem},
            "outboundDate": {"year": data_volta.year, "month": data_volta.month, "day": data_volta.day},
            "adults": adultos
        }
    }

    def parse_indicative(resp_json, trecho_desc, data_str):
        voos = []
        carriers = resp_json.get("content", {}).get("results", {}).get("carriers", {})
        agents = resp_json.get("content", {}).get("results", {}).get("agents", {})
        itinerarios = resp_json.get("itineraries", []) or resp_json.get("content", {}).get("results", {}).get("itineraries", [])
        if isinstance(itinerarios, dict):
            itinerarios = list(itinerarios.values())
        for i in itinerarios[:4]:
            preco = None
            cia_nome = "—"
            if isinstance(i, dict):
                preco = i.get("price", {}).get("amount") or i.get("pricingOptions", [{}])[0].get("price", {}).get("amount")
                agent_id = i.get("pricingOptions", [{}])[0].get("agentIds", [None])[0]
                cia_nome = agents.get(agent_id, {}).get("name", "—")
            voos.append({
                "trecho": trecho_desc,
                "data": data_str,
                "partida": "00:00",
                "cia": cia_nome,
                "preco": preco if preco is not None else random.randint(450, 2400)
            })
        if not voos:
            voos = simula_voos(trecho_desc.split(" → ")[0], trecho_desc.split(" → ")[1],
                               date.fromisoformat(data_str), date.fromisoformat(data_str))[0]
        return voos

    try:
        r_ida = requests.post("https://partners.api.skyscanner.net/apiservices/v3/flights/indicative/search",
                              headers=headers, json=payload_ida, timeout=20)
        r_volta = requests.post("https://partners.api.skyscanner.net/apiservices/v3/flights/indicative/search",
                                headers=headers, json=payload_volta, timeout=20)
        ida_voos = parse_indicative(r_ida.json(), f"{origem} → {destino}", str(data_ida))
        volta_voos = parse_indicative(r_volta.json(), f"{destino} → {origem}", str(data_volta))
        return ida_voos, volta_voos
    except Exception as e:
        st.warning(f"Falha na consulta Indicative: {e}. Usando simulação.")
        return simula_voos(origem, destino, data_ida, data_volta)

def buscar_voos_live(origem: str, destino: str, data_ida: date, data_volta: date, adultos: int = 1):
    """
    Consulta voos em tempo real via Skyscanner Live Search:
    - POST /flights/live/search/create
    - POST /flights/live/search/poll/{sessionToken}
    Retorna lista de voos no formato do app.
    """
    headers = {"x-api-key": API_KEY_SKYSCANNER, "Content-Type": "application/json"}
    payload_create_ida = {
        "query": {
            "market": "BR",
            "locale": "pt-BR",
            "currency": "BRL",
            "queryLegs": [
                {
                    "originPlace": {"iata": origem},
                    "destinationPlace": {"iata": destino},
                    "date": {"year": data_ida.year, "month": data_ida.month, "day": data_ida.day}
                }
            ],
            "adults": adultos
        }
    }
    payload_create_volta = {
        "query": {
            "market": "BR",
            "locale": "pt-BR",
            "currency": "BRL",
            "queryLegs": [
                {
                    "originPlace": {"iata": destino},
                    "destinationPlace": {"iata": origem},
                    "date": {"year": data_volta.year, "month": data_volta.month, "day": data_volta.day}
                }
            ],
            "adults": adultos
        }
    }

    def create_and_poll(payload, trecho_desc, data_str):
        voos = []
        try:
            r_create = requests.post("https://partners.api.skyscanner.net/apiservices/v3/flights/live/search/create",
                                     headers=headers, json=payload, timeout=20)
            session_token = r_create.json().get("sessionToken")
            if not session_token:
                raise ValueError("Session token não retornado.")
            poll_url = f"https://partners.api.skyscanner.net/apiservices/v3/flights/live/search/poll/{session_token}"
            r_poll = requests.post(poll_url, headers=headers, timeout=20)
            data_json = r_poll.json()

            carriers = data_json.get("content", {}).get("results", {}).get("carriers", {})
            agents = data_json.get("content", {}).get("results", {}).get("agents", {})
            itinerarios = data_json.get("content", {}).get("results", {}).get("itineraries", {})

            for i in list(itinerarios.values())[:4]:
                preco = i.get("pricingOptions", [{}])[0].get("price", {}).get("amount")
                agent_id = i.get("pricingOptions", [{}])[0].get("agentIds", [None])[0]
                cia_nome = agents.get(agent_id, {}).get("name", "—")
                voos.append({
                    "trecho": trecho_desc,
                    "data": data_str,
                    "partida": "00:00",
                    "cia": cia_nome,
                    "preco": preco if preco is not None else random.randint(450, 2400)
                })
        except Exception as e:
            st.warning(f"Falha no Live Search ({trecho_desc}): {e}. Usando simulação para este trecho.")
            voos = simula_voos(trecho_desc.split(" → ")[0], trecho_desc.split(" → ")[1],
                               date.fromisoformat(data_str), date.fromisoformat(data_str))[0]
        return voos

    ida_voos = create_and_poll(payload_create_ida, f"{origem} → {destino}", str(data_ida))
    volta_voos = create_and_poll(payload_create_volta, f"{destino} → {origem}", str(data_volta))
    return ida_voos, volta_voos

#Parte 3: Funções de política, cálculo e voucher
# app.py - Parte 3

# =========================================================
# Funções de política e classificação
# =========================================================
def dentro_da_politica_voo(opcao_voo: dict, cargo: str) -> bool:
    """Checa se o preço do voo está dentro do limite por trecho para o cargo."""
    return opcao_voo["preco"] <= POLITICAS["limite_trecho_aereo"][cargo]

def dentro_da_politica_hotel(opcao_hotel: dict, cargo: str) -> bool:
    """Checa se a diária e categoria do hotel estão dentro da política."""
    limite = POLITICAS["limite_diaria_hotel"][cargo]
    cat_ok = opcao_hotel["categoria"] in POLITICAS["categorias_permitidas_por_cargo"][cargo]
    return (opcao_hotel["diaria"] <= limite) and cat_ok

def calcular_ajuda_custo(cargo: str, dias_viagem: int) -> int:
    """Calcula ajuda de custo por hierarquia e multiplicador por dias."""
    base = AJUDA_CUSTO_HIERARQUIA[cargo]
    mult = multiplicador_ajuda(dias_viagem)
    return int(base * dias_viagem * mult)

def classificar_solicitacao(antecedencia: int, voo_ida: dict, voo_volta: dict, hotel: dict, cargo: str):
    """Classifica solicitação como dentro/fora da política e gera alertas."""
    alertas = []
    status = "Dentro da política ✅"
    if antecedencia < POLITICAS["antecedencia_minima_dias"]:
        status = "Fora da política ⚠️"
        alertas.append("Solicitação com menos de 10 dias de antecedência. Risco de tarifas altas.")
    if not dentro_da_politica_voo(voo_ida, cargo):
        status = "Fora da política ⚠️"
        alertas.append("Voo de ida acima do limite por trecho.")
    if not dentro_da_politica_voo(voo_volta, cargo):
        status = "Fora da política ⚠️"
        alertas.append("Voo de volta acima do limite por trecho.")
    if not dentro_da_politica_hotel(hotel, cargo):
        status = "Fora da política ⚠️"
        alertas.append("Hotel fora da política (categoria/diária).")
    return status, alertas

def sugerir_reducao_custos(voos_ida: list, voos_volta: list, hoteis: list, cargo: str):
    """Sugere alternativas mais baratas dentro da política."""
    alternativas = {"ida": None, "volta": None, "hotel": None}
    ida_filtrado = [v for v in voos_ida if dentro_da_politica_voo(v, cargo)]
    volta_filtrado = [v for v in voos_volta if dentro_da_politica_voo(v, cargo)]
    hoteis_filtrado = [h for h in hoteis if dentro_da_politica_hotel(h, cargo)]
    if ida_filtrado:
        alternativas["ida"] = sorted(ida_filtrado, key=lambda x: x["preco"])[0]
    if volta_filtrado:
        alternativas["volta"] = sorted(volta_filtrado, key=lambda x: x["preco"])[0]
    if hoteis_filtrado:
        alternativas["hotel"] = sorted(hoteis_filtrado, key=lambda x: x["diaria"])[0]
    return alternativas

# =========================================================
# Exportação de bilhete/voucher (HTML)
# =========================================================
def gerar_voucher_html(solic: dict) -> str:
    """Gera um voucher HTML simples para registro da viagem."""
    html = f"""
    <html>
    <head><meta charset="utf-8"><title>Voucher de Viagem</title></head>
    <body>
      <h2>Voucher de Viagem - {solic['colaborador']}</h2>
      <p><b>Cargo:</b> {solic['cargo']}</p>
      <p><b>Área:</b> {solic['area']}</p>
      <p><b>Origem/Destino:</b> {solic['origem']} → {solic['destino']}</p>
      <p><b>Datas:</b> {solic['data_ida']} a {solic['data_volta']} ({solic['dias_viagem']} dias)</p>
      <hr>
      <h3>Voos</h3>
      <p><b>Ida:</b> {solic['voo_ida']['cia']} {solic['voo_ida']['trecho']} {solic['voo_ida']['data']} {solic['voo_ida']['partida']} — R$ {solic['voo_ida']['preco']}</p>
      <p><b>Volta:</b> {solic['voo_volta']['cia']} {solic['voo_volta']['trecho']} {solic['voo_volta']['data']} {solic['voo_volta']['partida']} — R$ {solic['voo_volta']['preco']}</p>
      <h3>Hotel</h3>
      <p><b>{solic['hotel']['hotel']}</b> ({solic['hotel']['categoria']}) — Diária R$ {solic['hotel']['diaria']} — {solic['hotel']['noites']} noites (Total R$ {solic['hotel']['custo_total']})</p>
      <h3>Custos</h3>
      <p><b>Ajuda de custo:</b> R$ {solic['ajuda_custo']}</p>
      <p><b>Total previsto:</b> R$ {solic['total_previsto']}</p>
      <hr>
      <p><i>Status:</i> {solic['status']}</p>
      <p><i>Motivo da viagem:</i> {solic['motivo']}</p>
      <p><i>Aprovação:</i> {solic.get('aprovacao','Pendente')}</p>
      <p><i>Comentário do gestor:</i> {solic.get('comentario_gestor','')}</p>
    </body>
    </html>
    """
    return html

#Parte 4: Página “Nova solicitação”
# app.py - Parte 4

# =========================================================
# Sidebar: navegação
# =========================================================
st.sidebar.title("Menu")
pagina = st.sidebar.radio("Ir para", ["Nova solicitação", "Workflow de aprovação", "Dashboard gerencial"])

# Fonte de dados (Simulado vs Skyscanner)
st.sidebar.markdown("### Fonte de dados")
fonte_dados = st.sidebar.selectbox("Voos", ["Simulado", "Skyscanner Indicative", "Skyscanner Live"])

# =========================================================
# Página: Nova solicitação
# =========================================================
if pagina == "Nova solicitação":
    st.title("Nova solicitação de viagem")

    cols = st.columns(3)
    with cols[0]:
        colaborador = st.text_input("Nome do colaborador", value="Fulano de Tal")
        area = st.selectbox("Área", ["Operações", "Comercial", "TI", "Financeiro", "RH"])
        cargo = st.selectbox("Cargo", list(AJUDA_CUSTO_HIERARQUIA.keys()))
    with cols[1]:
        origem = st.text_input("Origem (IATA ou cidade)", value="FOR")
        destino = st.text_input("Destino (IATA ou cidade)", value="GRU")
        motivo = st.text_area("Motivo da viagem", value="Reunião com cliente e visita")
    with cols[2]:
        data_ida = st.date_input("Data de ida", value=date.today() + timedelta(days=12))
        data_volta = st.date_input("Data de volta", value=date.today() + timedelta(days=15))

    dias_viagem = (data_volta - data_ida).days + 1
    antecedencia = (data_ida - date.today()).days

    # Alertas de antecedência
    if antecedencia < POLITICAS["antecedencia_minima_dias"]:
        st.warning("⚠️ Solicitação com menos de 10 dias de antecedência. Risco de tarifas altas.")

    # Consulta de voos conforme fonte
    if fonte_dados == "Simulado":
        voos_ida, voos_volta = simula_voos(origem, destino, data_ida, data_volta)
    elif fonte_dados == "Skyscanner Indicative":
        voos_ida, voos_volta = buscar_voos_indicative(origem, destino, data_ida, data_volta, adultos=1)
    else:
        voos_ida, voos_volta = buscar_voos_live(origem, destino, data_ida, data_volta, adultos=1)

    # Hotéis (mantém simulado; você pode integrar uma API de hotéis depois)
    hoteis = simula_hoteis(destino, dias_viagem, cargo)

    st.subheader("Opções de voo - Ida")
    df_ida = pd.DataFrame(voos_ida)
    st.dataframe(df_ida, use_container_width=True)

    st.subheader("Opções de voo - Volta")
    df_volta = pd.DataFrame(voos_volta)
    st.dataframe(df_volta, use_container_width=True)

    st.subheader("Opções de hospedagem")
    df_hot = pd.DataFrame(hoteis)
    st.dataframe(df_hot, use_container_width=True)

    st.markdown("#### Selecione suas opções")
    idx_ida = st.number_input("Índice da opção de ida (0-3)", min_value=0, max_value=max(0, len(voos_ida)-1), value=0)
    idx_volta = st.number_input("Índice da opção de volta (0-3)", min_value=0, max_value=max(0, len(voos_volta)-1), value=0)
    idx_hotel = st.number_input("Índice do hotel (0-4)", min_value=0, max_value=max(0, len(hoteis)-1), value=0)

    voo_ida = voos_ida[idx_ida]
    voo_volta = voos_volta[idx_volta]
    hotel = hoteis[idx_hotel]

    ajuda_custo = calcular_ajuda_custo(cargo, dias_viagem)
    total_previsto = (voo_ida.get("preco") or 0) + (voo_volta.get("preco") or 0) + hotel["custo_total"] + ajuda_custo

    status, alertas = classificar_solicitacao(antecedencia, voo_ida, voo_volta, hotel, cargo)
    alternativas = sugerir_reducao_custos(voos_ida, voos_volta, hoteis, cargo)

    st.markdown("### Resumo e política")
    colr = st.columns(2)
    with colr[0]:
        st.write(f"**Status:** {status}")
        st.write(f"**Dias de viagem:** {dias_viagem}")
        st.write(f"**Ajuda de custo ({cargo}):** R$ {ajuda_custo}")
        st.write(f"**Total previsto:** R$ {total_previsto}")
        st.write(f"**Limite por trecho aéreo ({cargo}):** R$ {POLITICAS['limite_trecho_aereo'][cargo]}")
        st.write(f"**Limite diária hotel ({cargo}):** R$ {POLITICAS['limite_diaria_hotel'][cargo]}")
        st.write(f"**Categorias permitidas:** {', '.join(POLITICAS['categorias_permitidas_por_cargo'][cargo])}")
    with colr[1]:
        if alertas:
            st.error("Alertas de política:")
            for a in alertas:
                st.write(f"- {a}")
        else:
            st.success("Sem alertas. Dentro da política.")

    st.markdown("### Sugestões de redução de custos")
    sug_msgs = []
    alt = alternativas
    if alt["ida"] and alt["ida"] != voo_ida:
        sug_msgs.append(f"**Ida:** considerar {alt['ida']['cia']} às {alt['ida']['partida']} por R$ {alt['ida']['preco']}.")
    if alt["volta"] and alt["volta"] != voo_volta:
        sug_msgs.append(f"**Volta:** considerar {alt['volta']['cia']} às {alt['volta']['partida']} por R$ {alt['volta']['preco']}.")
    if alt["hotel"] and alt["hotel"] != hotel:
        sug_msgs.append(f"**Hotel:** considerar {alt['hotel']['hotel']} ({alt['hotel']['categoria']}) por diária R$ {alt['hotel']['diaria']}.")

    if sug_msgs:
        for m in sug_msgs:
            st.info(m)
    else:
        st.write("Nenhuma alternativa mais barata dentro da política encontrada para os itens escolhidos.")

    # Fluxo financeiro e comunicações
    st.markdown("### Fluxo financeiro e comunicações")
    if antecedencia == 2:
        st.info("🔔 Alerta ao Financeiro e ao Solicitante: programação de depósito em D-2 e confirmação de dados bancários.")
    if antecedencia == 0:
        st.success("📲 Notificação no celular do viajante: depósito confirmado na conta.")

    # Enviar para aprovação
    if st.button("Enviar para aprovação"):
        registro = {
            "id": len(st.session_state.solicitacoes) + 1,
            "colaborador": colaborador,
            "area": area,
            "cargo": cargo,
            "origem": origem,
            "destino": destino,
            "data_ida": str(data_ida),
            "data_volta": str(data_volta),
            "dias_viagem": dias_viagem,
            "motivo": motivo,
            "voo_ida": voo_ida,
            "voo_volta": voo_volta,
            "hotel": hotel,
            "ajuda_custo": ajuda_custo,
            "total_previsto": total_previsto,
            "status": status,
            "alertas": alertas,
            "aprovacao": "Pendente",
            "comentario_gestor": "",
            "criado_em": datetime.now().isoformat(timespec="seconds"),
            # Campos auxiliares para análises
            "custo_voos": (voo_ida.get("preco") or 0) + (voo_volta.get("preco") or 0),
            "custo_hotel": hotel["custo_total"],
            "trecho_ida": voo_ida["trecho"],
            "trecho_volta": voo_volta["trecho"],
        }
        st.session_state.solicitacoes.append(registro)
        st.success(f"Solicitação #{registro['id']} enviada para aprovação.")

    # Voucher rápido da última solicitação
    if st.session_state.solicitacoes:
        st.markdown("### Exportação de voucher")
        ult = st.session_state.solicitacoes[-1]
        html = gerar_voucher_html(ult)
        st.download_button("Baixar voucher HTML", data=html, file_name=f"voucher_{ult['id']}.html", mime="text/html")

#Parte 5: Página “Workflow de aprovação” (com comentário do gestor)
# app.py - Parte 5

elif pagina == "Workflow de aprovação":
    st.title("Aprovação de solicitações")

    if not st.session_state.solicitacoes:
        st.info("Nenhuma solicitação cadastrada ainda.")
    else:
        df = pd.DataFrame(st.session_state.solicitacoes)
        st.dataframe(df[["id", "colaborador", "area", "cargo", "origem", "destino",
                         "data_ida", "data_volta", "total_previsto", "status", "aprovacao"]],
                     use_container_width=True)

        sel_id = st.number_input("ID da solicitação para analisar", min_value=1,
                                 max_value=len(st.session_state.solicitacoes), value=1)
        solic = next(s for s in st.session_state.solicitacoes if s["id"] == sel_id)

        st.markdown(f"#### Solicitação #{solic['id']} - {solic['colaborador']}")
        st.write(f"**Status de política:** {solic['status']}")
        if solic["alertas"]:
            st.error("Alertas:")
            for a in solic["alertas"]:
                st.write(f"- {a}")

        cols = st.columns(3)
        with cols[0]:
            st.write("**Voo ida:**", solic["voo_ida"])
        with cols[1]:
            st.write("**Voo volta:**", solic["voo_volta"])
        with cols[2]:
            st.write("**Hotel:**", solic["hotel"])

        st.write(f"**Ajuda de custo:** R$ {solic['ajuda_custo']}")
        st.write(f"**Total previsto:** R$ {solic['total_previsto']}")

        decisao = st.radio("Decisão do gestor", ["Aprovar", "Reprovar"], index=0)
        comentario = st.text_area("Comentário do gestor (opcional)")

        if st.button("Registrar decisão"):
            solic["aprovacao"] = "Aprovado ✅" if decisao == "Aprovar" else "Reprovado ❌"
            solic["comentario_gestor"] = comentario
            st.success(f"Decisão registrada: {solic['aprovacao']}")

        st.markdown("##### Notificações automáticas")
        if solic["aprovacao"] == "Aprovado ✅":
            st.info("🔔 Gestor imediato e Financeiro notificados sobre aprovação e programação de depósito.")
        elif solic["aprovacao"] == "Reprovado ❌":
            st.info("🔔 Solicitante notificado com motivos e possibilidade de reenvio com ajustes.")

        # Voucher pós-decisão
        html = gerar_voucher_html(solic)
        st.download_button("Baixar voucher HTML da solicitação", data=html,
                           file_name=f"voucher_{solic['id']}.html", mime="text/html")

#Parte 6: Página “Dashboard gerencial” com análises
# app.py - Parte 6

elif pagina == "Dashboard gerencial":
    st.title("Dashboard gerencial")

    if not st.session_state.solicitacoes:
        st.info("Sem dados para o dashboard ainda.")
    else:
        df = pd.DataFrame(st.session_state.solicitacoes)

        # Filtros
        cols = st.columns(4)
        with cols[0]:
            filtro_area = st.multiselect("Filtrar por área", sorted(df["area"].unique()),
                                         default=list(sorted(df["area"].unique())))
        with cols[1]:
            filtro_cargo = st.multiselect("Filtrar por cargo", sorted(df["cargo"].unique()),
                                          default=list(sorted(df["cargo"].unique())))
        with cols[2]:
            filtro_aprov = st.multiselect("Filtrar por aprovação", sorted(df["aprovacao"].unique()),
                                          default=list(sorted(df["aprovacao"].unique())))
        with cols[3]:
            periodo_ini = st.date_input("Período inicial", value=date.today() - timedelta(days=60))
            periodo_fim = st.date_input("Período final", value=date.today() + timedelta(days=1))

        df["data_ida_dt"] = pd.to_datetime(df["data_ida"])
        mask = (
            df["area"].isin(filtro_area)
            & df["cargo"].isin(filtro_cargo)
            & df["aprovacao"].isin(filtro_aprov)
            & (df["data_ida_dt"].dt.date >= periodo_ini)
            & (df["data_ida_dt"].dt.date <= periodo_fim)
        )
        dff = df[mask].copy()

        # KPIs
        colk = st.columns(4)
        with colk[0]:
            st.metric("Total de solicitações", len(dff))
        with colk[1]:
            st.metric("Aprovadas", int((dff["aprovacao"] == "Aprovado ✅").sum()))
        with colk[2]:
            st.metric("Fora da política", int((dff["status"] == "Fora da política ⚠️").sum()))
        with colk[3]:
            st.metric("Gasto previsto (R$)", int(dff["total_previsto"].sum()))

        # Ticket médio: aéreo, hospedagem e total por área
        st.subheader("Ticket médio por área")
        if not dff.empty:
            tm_area = dff.groupby("area")[["custo_voos", "custo_hotel", "total_previsto"]].mean().round(2)
            st.dataframe(tm_area, use_container_width=True)
            st.bar_chart(tm_area["total_previsto"])
        else:
            st.info("Nenhum dado no período filtrado.")

        # Ticket médio por cargo
        st.subheader("Ticket médio por cargo")
        if not dff.empty:
            tm_cargo = dff.groupby("cargo")[["custo_voos", "custo_hotel", "total_previsto"]].mean().round(2)
            st.dataframe(tm_cargo, use_container_width=True)
            st.bar_chart(tm_cargo["total_previsto"])

        # Violações por área e cargo
        st.subheader("Histórico de violações por área e cargo")
        if not dff.empty:
            viol_por_area = dff.groupby("area").apply(lambda x: (x["status"] == "Fora da política ⚠️").sum()).reset_index(name="violacoes")
            viol_por_cargo = dff.groupby("cargo").apply(lambda x: (x["status"] == "Fora da política ⚠️").sum()).reset_index(name="violacoes")
            colv = st.columns(2)
            with colv[0]:
                st.dataframe(viol_por_area.sort_values("violacoes", ascending=False), use_container_width=True)
                st.bar_chart(viol_por_area.set_index("area"))
            with colv[1]:
                st.dataframe(viol_por_cargo.sort_values("violacoes", ascending=False), use_container_width=True)
                st.bar_chart(viol_por_cargo.set_index("cargo"))

        # Comentários dos gestores (qualitativo)
        st.subheader("Comentários dos gestores")
        if "comentario_gestor" in dff.columns:
            comentarios = dff[["id", "colaborador", "area", "cargo", "aprovacao", "comentario_gestor"]].copy()
            comentarios = comentarios[comentarios["comentario_gestor"].str.len() > 0]
            st.dataframe(comentarios, use_container_width=True)
        else:
            st.write("Sem comentários registrados.")

        # Top 5 trechos mais solicitados (considerando ida e volta separadamente)
        st.subheader("Top 5 trechos mais solicitados")
        if not dff.empty:
            trechos = pd.concat([
                dff["trecho_ida"].rename("trecho"),
                dff["trecho_volta"].rename("trecho")
            ], ignore_index=True)
            top_trechos = trechos.value_counts().reset_index()
            top_trechos.columns = ["trecho", "solicitacoes"]
            st.dataframe(top_trechos.head(5), use_container_width=True)
            st.bar_chart(top_trechos.set_index("trecho").head(5))
        else:
            st.write("Sem dados para trechos no período.")

        # Trecho mais caro (pela soma de custo de voos)
        st.subheader("Trecho mais caro (com base no custo de voos)")
        if not dff.empty:
            custos_ida = dff.groupby("trecho_ida")["custo_voos"].mean().reset_index().rename(
                columns={"trecho_ida": "trecho", "custo_voos": "custo_medio_voos"})
            custos_volta = dff.groupby("trecho_volta")["custo_voos"].mean().reset_index().rename(
                columns={"trecho_volta": "trecho", "custo_voos": "custo_medio_voos"})
            custos_trechos = pd.concat([custos_ida, custos_volta]).groupby("trecho")["custo_medio_voos"].mean().reset_index()
            trecho_mais_caro = custos_trechos.sort_values("custo_medio_voos", ascending=False).head(1)
            st.dataframe(trecho_mais_caro, use_container_width=True)
        else:
            st.write("Sem dados para cálculo do trecho mais caro.")


# In[ ]:




