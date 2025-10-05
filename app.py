import streamlit as st
import torch
from sentence_transformers import SentenceTransformer
import chromadb
import requests
import re
from datetime import datetime
import json
from pathlib import Path

# --- KONFIGURATION ---
DB_PATH = "C:/cbotC/cosmic_db"
COLLECTION_NAME = "cosmic_documents_embedded_v2" 
EMBEDDING_MODEL_NAME = 'KBLab/sentence-bert-swedish-cased'
OLLAMA_MODEL_NAME = 'mistral'
OLLAMA_API_URL = "http://localhost:11434/api/generate"
HISTORY_FILE = Path("C:/cbotC/chat_history.json")
FEEDBACK_FILE = Path("C:/cbotC/feedback_log.json")

# --- FUNKTIONER FÖR HISTORIK OCH FEEDBACK ---
def ladda_json(filsökväg):
    if filsökväg.exists():
        with open(filsökväg, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {} if filsökväg == HISTORY_FILE else []
    return {} if filsökväg == HISTORY_FILE else []

def spara_json(data, filsökväg):
    with open(filsökväg, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def spara_feedback(feedback_typ, fråga, svar, källor, förklaring=None):
    feedback_log = ladda_json(FEEDBACK_FILE)
    ny_post = {
        "timestamp": datetime.now().isoformat(), "feedback": feedback_typ,
        "fråga": fråga, "svar": svar, "källor": källor
    }
    if förklaring:
        ny_post["användarens_förklaring"] = förklaring
    feedback_log.append(ny_post)
    spara_json(feedback_log, FEEDBACK_FILE)

# --- CACHADE FUNKTIONER ---
@st.cache_resource
def ladda_embedding_modell():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(EMBEDDING_MODEL_NAME, device=device)

@st.cache_resource
def anslut_till_db():
    client = chromadb.PersistentClient(path=DB_PATH)
    return client.get_collection(name=COLLECTION_NAME)

# --- KÄRNFUNKTIONER ---
def hämta_kontext(fråga, model, collection):
    query_embedding = model.encode(fråga).tolist()
    results = collection.query(query_embeddings=[query_embedding], n_results=10, include=["documents", "metadatas"])
    return results.get('documents', [[]])[0], results.get('metadatas', [[]])[0]

def generera_svar(fråga, kontext_chunks, kontext_meta, chatt_historik):
    kontext_text = "\n\n".join([f"## Utdrag från '{meta.get('titel', 'Okänd')}':\n{chunk}" for chunk, meta in zip(kontext_chunks, kontext_meta)])
    historik_text = "\n".join([f"{'Användare' if msg['role'] == 'user' else 'Assistent'}: {msg['content']}" for msg in chatt_historik])
    prompt = f"""SYSTEMINSTRUKTION: Du är en noggrann AI-expert på IT-systemet Cosmic.
DITT UPPDRAG: Svara på SENASTE ANVÄNDARFRÅGAN genom att följa dessa regler:
1. Analysera Kontexten Kritiskt: Om du ser instruktioner från olika dokument som beskriver OLIKA processer, välj ENDAST den process som bäst besvarar frågan. Blanda ALDRIG ihop steg från olika processer.
2. Formulera Svaret: Skriv en tydlig guide i punktform.
3. Ange Källa: Avsluta med att ange dokumentets namn under rubriken "KÄLLA:".
4. Om information saknas: Svara "Jag hittar inte information om detta i mina källor.".
---
KONTEXT: {kontext_text}
---
TIDIGARE KONVERSATION:
{historik_text}
---
SENASTE ANVÄNDARFRÅGAN: {fråga}
SVAR:"""
    try:
        payload = {"model": OLLAMA_MODEL_NAME, "prompt": prompt, "stream": False, "options": {"temperature": 0.0}}
        response = requests.post(OLLAMA_API_URL, json=payload, timeout=90)
        return response.json().get("response", "").strip()
    except Exception as e: return f"Ett fel uppstod: {e}"

# --- STREAMLIT APPLIKATIONSLOGIK ---
st.set_page_config(layout="wide", page_title="Cosmic Databas Chatt")
embedding_model, collection = ladda_embedding_modell(), anslut_till_db()

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
        st.markdown(message["content"])
        
        if message["role"] == "assistant":
            feedback_key_prefix = f"feedback_{st.session_state.active_chat_id}_{i}"
            feedback_status = st.session_state.get(f"{feedback_key_prefix}_status", None)

            if not feedback_status:
                st.write("Fick du lösning på problemet?")
                col1, col2, _ = st.columns([1, 1, 10])
                
                if col1.button("Ja", key=f"{feedback_key_prefix}_ja"):
                    fråga = active_chat_messages[i-1]['content']
                    källor = message.get('källor', [])
                    spara_feedback("bra", fråga, message["content"], källor)
                    st.session_state[f"{feedback_key_prefix}_status"] = "bra"
                    st.rerun()

                if col2.button("Nej", key=f"{feedback_key_prefix}_nej"):
                    fråga = active_chat_messages[i-1]['content']
                    källor = message.get('källor', [])
                    spara_feedback("dåligt", fråga, message["content"], källor)
                    st.session_state[f"{feedback_key_prefix}_status"] = "dåligt"
                    st.rerun()
            
            elif feedback_status == "bra":
                st.success("Tack för din feedback!")
            
            elif feedback_status == "dåligt":
                st.warning("Tack, jag lär mig av detta.")
                if followup_prompt := st.text_input("Kan du beskriva problemet med några fler ord? Jag gör ett nytt försök.", key=f"{feedback_key_prefix}_followup"):
                    active_chat_messages.append({"role": "user", "content": followup_prompt})
                    st.session_state.chat_history[st.session_state.active_chat_id] = active_chat_messages
                    spara_json(st.session_state.chat_history, HISTORY_FILE)
                    st.rerun()

if prompt := st.chat_input("Hur kan jag hjälpa dig?"):
    active_chat_messages.append({"role": "user", "content": prompt})
    st.rerun()

if active_chat_messages and active_chat_messages[-1]["role"] == "user":
    prompt = active_chat_messages[-1]["content"]
    with st.chat_message("assistant"):
        with st.spinner("Tänker..."):
            kontext_chunks, kontext_meta = hämta_kontext(prompt, embedding_model, collection)
            response = ""
            if kontext_chunks:
                response = generera_svar(prompt, kontext_chunks, kontext_meta, active_chat_messages[:-1])
            else:
                response = "Jag hittade tyvärr ingen information alls som matchade din fråga."
            
            st.markdown(response)
            
            assistant_message = {"role": "assistant", "content": response, "källor": list(zip(kontext_chunks, kontext_meta))}
            active_chat_messages.append(assistant_message)
            st.session_state.chat_history[st.session_state.active_chat_id] = active_chat_messages
            spara_json(st.session_state.chat_history, HISTORY_FILE)
            st.rerun()
