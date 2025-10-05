import streamlit as st
import requests
from datetime import datetime
import json
from pathlib import Path
import streamlit_authenticator as stauth
import yaml
from yaml.loader import SafeLoader

# --- KONFIGURATION ---
API_SERVER_URL = "http://cbotc.ddns.net:8000/chat"
API_KEY = "Trp4-gtA9-7hQ-pWz-3kX"
HISTORY_DIR = Path("chatt_historik")
FEEDBACK_FILE = Path("feedback_log.json")

# --- FUNKTIONER FÖR HISTORIK OCH FEEDBACK ---
def ladda_json(filsökväg):
    if filsökväg.exists():
        with open(filsökväg, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {} if str(filsökväg).endswith('history.json') else []
    return {} if str(filsökväg).endswith('history.json') else []

def spara_json(data, filsökväg):
    with open(filsökväg, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def spara_feedback(feedback_typ, fråga, svarsalternativ, källor, förklaring=None):
    feedback_log = ladda_json(FEEDBACK_FILE)
    ny_post = {
        "timestamp": datetime.now().isoformat(), "feedback": feedback_typ,
        "fråga": fråga, "svarsalternativ": svarsalternativ, "källor": källor
    }
    if förklaring:
        ny_post["användarens_förklaring"] = förklaring
    feedback_log.append(ny_post)
    spara_json(feedback_log, FEEDBACK_FILE)

# --- ANROPSFUNKTION ---
def anropa_ai_server(fråga, chatt_historik):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"question": fråga, "history": chatt_historik}
    try:
        response = requests.post(API_SERVER_URL, json=payload, headers=headers, timeout=120)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"answer": f"FEL: Kunde inte ansluta till AI-servern: {e}", "raw_context": []}

# --- Ladda användardata ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("FEL: `config.yaml`-filen hittades inte.")
    st.stop()

authenticator = stauth.Authenticate(
    config['credentials'], config['credentials']['cookie']['name'],
    config['credentials']['cookie']['key'], config['credentials']['cookie']['expiry_days']
)

# --- STREAMLIT APPLIKATIONSLOGIK ---
st.set_page_config(layout="wide", page_title="Cosmic Databas Chatt")
authenticator.login()

if st.session_state.get("authentication_status"):
    name = st.session_state["name"]
    username = st.session_state["username"]
    HISTORY_FILE = HISTORY_DIR / f"{username}_history.json"
    
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.write(f'Välkommen *{name}*')

    if "chat_history" not in st.session_state: st.session_state.chat_history = ladda_json(HISTORY_FILE)
    if "active_chat_id" not in st.session_state: st.session_state.active_chat_id = None

    def new_chat():
        chat_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.chat_history[chat_id] = []
        st.session_state.active_chat_id = chat_id
        spara_json(st.session_state.chat_history, HISTORY_FILE)

    with st.sidebar:
        st.header("Chatt-historik")
        if st.button("➕ Ny Chatt", use_container_width=True):
            new_chat(); st.rerun()
        sorted_chat_ids = sorted(st.session_state.chat_history.keys(), reverse=True)
        for chat_id in sorted_chat_ids:
            chat_title = st.session_state.chat_history[chat_id][0]['content'][:40] + "..." if st.session_state.chat_history[chat_id] else f"Chatt från {chat_id}"
            if st.button(chat_title, key=chat_id, use_container_width=True):
                st.session_state.active_chat_id = chat_id; st.rerun()
    
    if not st.session_state.active_chat_id and st.session_state.chat_history: st.session_state.active_chat_id = sorted_chat_ids[0]
    elif not st.session_state.chat_history: new_chat()

    st.title("💬 Chattbot för Cosmic Databas")
    active_chat_messages = st.session_state.chat_history.get(st.session_state.active_chat_id, [])

    for i, message in enumerate(active_chat_messages):
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            elif message["role"] == "assistant":
                svarsalternativ = message["content"].split("---SPLIT---")
                for alt_index, alternativ in enumerate(svarsalternativ):
                    st.markdown(alternativ.strip())
                    feedback_key_prefix = f"feedback_{st.session_state.active_chat_id}_{i}_{alt_index}"
                    feedback_status = st.session_state.get(f"{feedback_key_prefix}_status")

                    if not feedback_status:
                        st.write("Fick du lösning på problemet?")
                        col1, col2, _ = st.columns([1, 1, 10])
                        if col1.button("Ja", key=f"{feedback_key_prefix}_ja"):
                            spara_feedback("bra", active_chat_messages[i-1]['content'], alternativ.strip(), message.get('källor', []))
                            st.session_state[f"{feedback_key_prefix}_status"] = "bra"; st.rerun()
                        if col2.button("Nej", key=f"{feedback_key_prefix}_nej"):
                            spara_feedback("dåligt", active_chat_messages[i-1]['content'], alternativ.strip(), message.get('källor', []))
                            st.session_state[f"{feedback_key_prefix}_status"] = "dåligt"; st.rerun()
                    elif feedback_status == "bra":
                        st.success("Tack för din feedback!")
                    elif feedback_status == "dåligt":
                        st.warning("Tack, jag lär mig av detta.")
                        if followup := st.text_input("Beskriv problemet för ett nytt försök:", key=f"{feedback_key_prefix}_followup"):
                            active_chat_messages.append({"role": "user", "content": followup})
                            st.session_state.chat_history[st.session_state.active_chat_id] = active_chat_messages
                            spara_json(st.session_state.chat_history, HISTORY_FILE); st.rerun()
                    if alt_index < len(svarsalternativ) - 1: st.divider()

    if prompt := st.chat_input("Hur kan jag hjälpa dig?"):
        active_chat_messages.append({"role": "user", "content": prompt})
        st.rerun()

    if active_chat_messages and active_chat_messages[-1]["role"] == "user":
        prompt = active_chat_messages[-1]["content"]
        with st.chat_message("assistant"):
            with st.spinner("Tänker..."):
                response_data = anropa_ai_server(prompt, active_chat_messages[:-1])
                response = response_data.get("answer", "Ett fel uppstod.")
                källor = response_data.get("raw_context", [])
                
                assistant_message = {"role": "assistant", "content": response, "källor": källor}
                active_chat_messages.append(assistant_message)
                st.session_state.chat_history[st.session_state.active_chat_id] = active_chat_messages
                spara_json(st.session_state.chat_history, HISTORY_FILE)
                st.rerun()

elif st.session_state.get("authentication_status") is False:
    st.error('Användarnamn/lösenord är felaktigt')
elif st.session_state.get("authentication_status") is None:
    st.warning('Vänligen ange ditt användarnamn och lösenord')
