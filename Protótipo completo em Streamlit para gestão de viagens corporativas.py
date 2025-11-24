#!/usr/bin/env python
# coding: utf-8

# In[1]:


import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
import random
import io

# =========================================================
# Configurações globais e estado
# =========================================================
st.set_page_config(page_title="Gestão de Viagens Corporativas", layout="wide")

if "solicitacoes" not in st.session_state:
    st.session_state.solicitacoes = []  # lista de dicts

# ---------------------------------------------------------
# Políticas internas parametrizadas (ajuste conforme empresa)
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

# Ajuste por quantidade de dias/trechos (multiplicador incremental)
# Ex.: 1 dia -> 1.0x, 2-3 dias -> 1.1x, 4-5 dias -> 1.2x, >5 dias -> 1.3x
def multiplicador_ajuda(dias):
    if dias <= 1:
        return 1.0
    elif dias <= 3:
        return 1.1
    elif dias <= 5:
        return 1.2
    else:
        return 1.3

# =========================================================
# Simulação de "APIs" de voos e hotéis
# =========================================================
def simula_voos(origem, destino, data_ida, data_volta):
    # Gera 4 opções por trecho, com preços e horários variados
    random.seed(hash((origem, destino, data_ida, data_volta)) % (2**32))
    def gerar_opcoes(data, trecho_desc):
        opcoes = []
        for i in range(4):
            partida_hora = random.choice([6, 8, 10, 14, 18, 21])
            duracao = random.choice([90, 120, 150, 180, 240])  # minutos
            preco = random.randint(450, 2400)
            cia = random.choice(["AZ", "LA", "G3", "TP"])
            opcoes.append({
                "trecho": trecho_desc,
                "data": data,
                "partida": f"{partida_hora:02d}:00",
                "duracao_min": duracao,
                "cia": cia,
                "preco": preco,
                "tarifa": random.choice(["Light", "Plus", "Top"]),
                "reembolsavel": random.choice([True, False]),
            })
        return opcoes

    ida = gerar_opcoes(data_ida, f"{origem} → {destino}")
    volta = gerar_opcoes(data_volta, f"{destino} → {origem}")
    return ida, volta

def simula_hoteis(destino, noites, cargo):
    random.seed(hash((destino, noites, cargo)) % (2**32))
    categorias = ["Padrão", "Executivo", "Luxo"]
    hoteis = []
    for i in range(5):
        categoria = random.choice(categorias)
        diaria = random.randint(250, 950)
        hoteis.append({
            "hotel": f"Hotel {destino.upper()} {i+1}",
            "categoria": categoria,
            "avaliacao": round(random.uniform(3.5, 4.9), 1),
            "diaria": diaria,
            "cancelamento_gratis": random.choice([True, False]),
            "cafe_incluso": random.choice([True, False]),
            "noites": noites,
            "custo_total": diaria * noites
        })
    return hoteis

# =========================================================
# Funções de política e classificação
# =========================================================
def dentro_da_politica_voo(opcao_voo, cargo):
    return opcao_voo["preco"] <= POLITICAS["limite_trecho_aereo"][cargo]

def dentro_da_politica_hotel(opcao_hotel, cargo):
    limite = POLITICAS["limite_diaria_hotel"][cargo]
    cat_ok = opcao_hotel["categoria"] in POLITICAS["categorias_permitidas_por_cargo"][cargo]
    return (opcao_hotel["diaria"] <= limite) and cat_ok

def classificar_solicitacao(antecedencia, voos_ida, voos_volta, hotel, cargo):
    alertas = []
    fora_politica = False

    if antecedencia < POLITICAS["antecedencia_minima_dias"]:
        alertas.append("Solicitação com menos de 10 dias de antecedência. Risco de tarifas altas.")
        fora_politica = True

    # Checa ao menos 1 opção de ida e volta dentro da política
    ida_ok = any(dentro_da_politica_voo(v, cargo) for v in voos_ida)
    volta_ok = any(dentro_da_politica_voo(v, cargo) for v in voos_volta)
    hotel_ok = dentro_da_politica_hotel(hotel, cargo)

    if not ida_ok:
        alertas.append("Nenhuma opção de voo de ida dentro da política.")
        fora_politica = True
    if not volta_ok:
        alertas.append("Nenhuma opção de voo de volta dentro da política.")
        fora_politica = True
    if not hotel_ok:
        alertas.append("Hotel selecionado fora da política (categoria/diária).")
        fora_politica = True

    status = "Dentro da política ✅" if not fora_politica else "Fora da política ⚠️"
    return status, alertas

def sugerir_reducao_custos(voos_ida, voos_volta, hoteis, cargo):
    # Sugere alternativa mais barata dentro dos limites, se houver
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

def calcular_ajuda_custo(cargo, dias_viagem):
    base = AJUDA_CUSTO_HIERARQUIA[cargo]
    mult = multiplicador_ajuda(dias_viagem)
    return int(base * dias_viagem * mult)

# =========================================================
# Exportação de bilhete/voucher (HTML)
# =========================================================
def gerar_voucher_html(solic):
    html = f"""
    <html>
    <head><meta charset="utf-8"><title>Voucher de Viagem</title></head>
    <body>
      <h2>Voucher de Viagem - {solic['colaborador']}</h2>
      <p><b>Cargo:</b> {solic['cargo']}</p>
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
    </body>
    </html>
    """
    return html

# =========================================================
# Sidebar: navegação
# =========================================================
st.sidebar.title("Menu")
pagina = st.sidebar.radio("Ir para", ["Nova solicitação", "Workflow de aprovação", "Dashboard gerencial"])

# =========================================================
# Página: Nova solicitação
# =========================================================
if pagina == "Nova solicitação":
    st.title("Nova solicitação de viagem")

    # --- Formulário principal ---
    cols = st.columns(3)
    with cols[0]:
        colaborador = st.text_input("Nome do colaborador", value="Fulano de Tal")
        area = st.selectbox("Área", ["Operações", "Comercial", "TI", "Financeiro", "RH"])
        cargo = st.selectbox("Cargo", list(AJUDA_CUSTO_HIERARQUIA.keys()))
    with cols[1]:
        origem = st.text_input("Origem (IATA ou cidade)", value="FOR")
        destino = st.text_input("Destino (IATA ou cidade)", value="GRU")
        motivo = st.text_area("Motivo da viagem", value="Reunião com cliente e visita a unidade")
    with cols[2]:
        data_ida = st.date_input("Data de ida", value=date.today() + timedelta(days=12))
        data_volta = st.date_input("Data de volta", value=date.today() + timedelta(days=15))

    dias_viagem = (data_volta - data_ida).days + 1
    antecedencia = (data_ida - date.today()).days

    # --- Alertas de antecedência ---
    if antecedencia < POLITICAS["antecedencia_minima_dias"]:
        st.warning("⚠️ Solicitação com menos de 10 dias de antecedência. Risco de tarifas altas e possível fora da política.")

    # --- Consulta a "APIs" (simuladas) ---
    voos_ida, voos_volta = simula_voos(origem, destino, data_ida, data_volta)
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

    # --- Seleção do usuário ---
    st.markdown("#### Selecione suas opções")
    idx_ida = st.number_input("Índice da opção de ida (0-3)", min_value=0, max_value=len(voos_ida)-1, value=0)
    idx_volta = st.number_input("Índice da opção de volta (0-3)", min_value=0, max_value=len(voos_volta)-1, value=0)
    idx_hotel = st.number_input("Índice do hotel (0-4)", min_value=0, max_value=len(hoteis)-1, value=0)

    voo_ida = voos_ida[idx_ida]
    voo_volta = voos_volta[idx_volta]
    hotel = hoteis[idx_hotel]

    ajuda_custo = calcular_ajuda_custo(cargo, dias_viagem)
    total_previsto = voo_ida["preco"] + voo_volta["preco"] + hotel["custo_total"] + ajuda_custo

    status, alertas = classificar_solicitacao(antecedencia, voos_ida, voos_volta, hotel, cargo)
    alternativas = sugerir_reducao_custos(voos_ida, voos_volta, hoteis, cargo)

    # --- Resumo ---
    st.markdown("### Resumo e política")
    cols2 = st.columns(2)
    with cols2[0]:
        st.write(f"**Status:** {status}")
        st.write(f"**Dias de viagem:** {dias_viagem}")
        st.write(f"**Ajuda de custo ({cargo}):** R$ {ajuda_custo}")
        st.write(f"**Total previsto:** R$ {total_previsto}")
        st.write(f"**Limite por trecho aéreo ({cargo}):** R$ {POLITICAS['limite_trecho_aereo'][cargo]}")
        st.write(f"**Limite diária hotel ({cargo}):** R$ {POLITICAS['limite_diaria_hotel'][cargo]}")
        st.write(f"**Categorias permitidas:** {', '.join(POLITICAS['categorias_permitidas_por_cargo'][cargo])}")
    with cols2[1]:
        if alertas:
            st.error("Alertas de política:")
            for a in alertas:
                st.write(f"- {a}")
        else:
            st.success("Sem alertas. Dentro da política.")

    # --- Sugestões de redução de custo ---
    st.markdown("### Sugestões de redução de custos")
    sug_msgs = []
    if alternativas["ida"] and alternativas["ida"] != voo_ida:
        sug_msgs.append(f"**Ida:** considerar {alternativas['ida']['cia']} às {alternativas['ida']['partida']} por R$ {alternativas['ida']['preco']}.")
    if alternativas["volta"] and alternativas["volta"] != voo_volta:
        sug_msgs.append(f"**Volta:** considerar {alternativas['volta']['cia']} às {alternativas['volta']['partida']} por R$ {alternativas['volta']['preco']}.")
    if alternativas["hotel"] and alternativas["hotel"] != hotel:
        sug_msgs.append(f"**Hotel:** considerar {alternativas['hotel']['hotel']} ({alternativas['hotel']['categoria']}) por diária R$ {alternativas['hotel']['diaria']}.")

    if sug_msgs:
        for m in sug_msgs:
            st.info(m)
    else:
        st.write("Nenhuma alternativa mais barata dentro da política encontrada para os itens escolhidos.")

    # --- Fluxo financeiro (alertas D-2 e depósito/SMS simulado) ---
    st.markdown("### Fluxo financeiro e comunicações")
    if antecedencia == 2:
        st.info("🔔 Alerta ao Financeiro e ao Solicitante: programação de depósito em D-2 e confirmação de dados bancários.")
    if antecedencia == 0:
        st.success("📲 Notificação no celular do viajante: depósito confirmado na conta.")

    # --- Cadastrar solicitação ---
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
            "criado_em": datetime.now().isoformat(timespec="seconds"),
        }
        st.session_state.solicitacoes.append(registro)
        st.success(f"Solicitação #{registro['id']} enviada para aprovação.")

    # --- Voucher/Comprovante ---
    if st.session_state.solicitacoes:
        st.markdown("### Exportação de voucher")
        ult = st.session_state.solicitacoes[-1]
        html = gerar_voucher_html(ult)
        st.download_button("Baixar voucher HTML", data=html, file_name=f"voucher_{ult['id']}.html", mime="text/html")

# =========================================================
# Página: Workflow de aprovação
# =========================================================
elif pagina == "Workflow de aprovação":
    st.title("Aprovação de solicitações")
    if not st.session_state.solicitacoes:
        st.info("Nenhuma solicitação cadastrada ainda.")
    else:
        df = pd.DataFrame(st.session_state.solicitacoes)
        st.dataframe(df[["id", "colaborador", "area", "cargo", "origem", "destino", "data_ida", "data_volta", "total_previsto", "status", "aprovacao"]], use_container_width=True)

        sel_id = st.number_input("ID da solicitação para analisar", min_value=1, max_value=len(st.session_state.solicitacoes), value=1)
        solic = next(s for s in st.session_state.solicitacoes if s["id"] == sel_id)

        st.markdown(f"#### Solicitação #{solic['id']} - {solic['colaborador']}")
        st.write(f"**Status de política:** {solic['status']}")
        if solic["alertas"]:
            st.error("Alertas:")
            for a in solic["alertas"]:
                st.write(f"- {a}")

        st.write(f"**Total previsto:** R$ {solic['total_previsto']}")
        st.write(f"**Ajuda de custo:** R$ {solic['ajuda_custo']}")

        cols = st.columns(3)
        with cols[0]:
            st.write("**Voo ida:**", solic["voo_ida"])
        with cols[1]:
            st.write("**Voo volta:**", solic["voo_volta"])
        with cols[2]:
            st.write("**Hotel:**", solic["hotel"])

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

        # Voucher pós-aprovação
        html = gerar_voucher_html(solic)
        st.download_button("Baixar voucher HTML da solicitação", data=html, file_name=f"voucher_{solic['id']}.html", mime="text/html")

# =========================================================
# Página: Dashboard gerencial
# =========================================================
elif pagina == "Dashboard gerencial":
    st.title("Dashboard gerencial")

    if not st.session_state.solicitacoes:
        st.info("Sem dados para o dashboard ainda.")
    else:
        df = pd.DataFrame(st.session_state.solicitacoes)

        # Filtros
        cols = st.columns(4)
        with cols[0]:
            filtro_area = st.multiselect("Filtrar por área", sorted(df["area"].unique()), default=list(sorted(df["area"].unique())))
        with cols[1]:
            filtro_cargo = st.multiselect("Filtrar por cargo", sorted(df["cargo"].unique()), default=list(sorted(df["cargo"].unique())))
        with cols[2]:
            filtro_aprov = st.multiselect("Filtrar por aprovação", sorted(df["aprovacao"].unique()), default=list(sorted(df["aprovacao"].unique())))
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

        # Tabelas e gráficos
        st.subheader("Gastos por área")
        gastos_area = dff.groupby("area")["total_previsto"].sum().reset_index().sort_values("total_previsto", ascending=False)
        st.bar_chart(gastos_area.set_index("area"))

        st.subheader("Gastos por cargo")
        gastos_cargo = dff.groupby("cargo")["total_previsto"].sum().reset_index().sort_values("total_previsto", ascending=False)
        st.bar_chart(gastos_cargo.set_index("cargo"))

        st.subheader("Violações por cargo")
        viol_cargo = dff.groupby("cargo").apply(lambda x: (x["status"] == "Fora da política ⚠️").sum()).reset_index(name="violacoes")
        st.bar_chart(viol_cargo.set_index("cargo"))

        st.subheader("Lista consolidada")
        st.dataframe(dff[["id", "colaborador", "area", "cargo", "origem", "destino", "data_ida", "data_volta", "total_previsto", "status", "aprovacao"]], use_container_width=True)


# In[ ]:




