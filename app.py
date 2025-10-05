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

# --- Ladda användardata från config.yaml ---
try:
    with open('config.yaml') as file:
        config = yaml.load(file, Loader=SafeLoader)
except FileNotFoundError:
    st.error("FEL: `config.yaml`-filen hittades inte.")
    st.stop()

# --- KORRIGERAD INITIERING AV AUTHENTICATOR ---
# Den sista 'preauthorized'-parametern är borttagen för att matcha den nya versionen.
authenticator = stauth.Authenticate(
    config['credentials'],
    config['credentials']['cookie']['name'],
    config['credentials']['cookie']['key'],
    config['credentials']['cookie']['expiry_days']
)

# --- FUNKTIONER ---
def get_history_filepath(username):
    HISTORY_DIR.mkdir(exist_ok=True)
    return HISTORY_DIR / f"{username}_history.json"

def ladda_chatt_historik(username):
    filepath = get_history_filepath(username)
    if filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}
    return {}

def spara_chatt_historik(username, historik):
    filepath = get_history_filepath(username)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(historik, f, indent=4, ensure_ascii=False)

def anropa_ai_server(fråga, chatt_historik):
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    payload = {"question": fråga, "history": chatt_historik}
    try:
        response = requests.post(API_SERVER_URL, json=payload, headers=headers, timeout=90)
        response.raise_for_status()
        data = response.json()
        return data.get('answer', 'Fick ett felaktigt svar från servern.')
    except Exception as e:
        return f"Kunde inte ansluta till AI-servern: {e}"

# --- STREAMLIT APPLIKATIONSLOGIK ---
st.set_page_config(layout="wide", page_title="Cosmic Databas Chatt")

name, authentication_status, username = authenticator.login()

if st.session_state["authentication_status"]:
    # --- KOD KÖRS ENDAST OM ANVÄNDAREN ÄR INLOGGAD ---
    authenticator.logout('Logout', 'sidebar')
    st.sidebar.write(f'Välkommen *{name}*')

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = ladda_chatt_historik(username)
    if "active_chat_id" not in st.session_state:
        st.session_state.active_chat_id = None
    
    def new_chat():
        chat_id = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        st.session_state.chat_history[chat_id] = []
        st.session_state.active_chat_id = chat_id
        spara_chatt_historik(username, st.session_state.chat_history)
    
    with st.sidebar:
        st.header("Chatt-historik")
        if st.button("➕ Ny Chatt", use_container_width=True):
            new_chat(); st.rerun()
        sorted_chat_ids = sorted(st.session_state.chat_history.keys(), reverse=True)
        for chat_id in sorted_chat_ids:
            chat_title = st.session_state.chat_history[chat_id][0]['content'][:40] + "..." if st.session_state.chat_history[chat_id] else f"Chatt från {chat_id}"
            if st.button(chat_title, key=chat_id, use_container_width=True):
                st.session_state.active_chat_id = chat_id; st.rerun()
    
    if not st.session_state.active_chat_id and st.session_state.chat_history:
        st.session_state.active_chat_id = sorted_chat_ids[0]
    elif not st.session_state.chat_history:
        new_chat()

    st.title("💬 Chattbot för Cosmic Databas")
    active_chat_messages = st.session_state.chat_history.get(st.session_state.active_chat_id, [])

    for message in active_chat_messages:
        with st.chat_message(message["role"]): st.markdown(message["content"])

    if prompt := st.chat_input("Hur kan jag hjälpa dig?"):
        active_chat_messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Skickar fråga till AI-servern..."):
                response = anropa_ai_server(prompt, active_chat_messages[:-1])
                st.markdown(response)
                active_chat_messages.append({"role": "assistant", "content": response})
        st.session_state.chat_history[st.session_state.active_chat_id] = active_chat_messages
        spara_chatt_historik(username, st.session_state.chat_history)
        st.rerun()

elif st.session_state["authentication_status"] is False:
    st.error('Användarnamn/lösenord är felaktigt')
elif st.session_state["authentication_status"] is None:
    st.warning('Vänligen ange ditt användarnamn och lösenord')
