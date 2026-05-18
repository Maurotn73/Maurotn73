import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_gsheets import GSheetsConnection
from streamlit_js_eval import get_geolocation
import math
from PIL import Image, ImageDraw

# ==========================================
# CONFIGURAZIONE PAGINA E IDENTITÀ VISIVA
# ==========================================
st.set_page_config(page_title="Art Polish - Gestionale V2", page_icon="🧹", layout="centered")

def crea_logo_temporaneo():
    # Crea un banner blu con il nome dell'azienda a titolo esemplificativo
    img = Image.new('RGB', (400, 100), color = '#1E3A8A')
    d = ImageDraw.Draw(img)
    d.text((20, 35), "ART POLISH - Sistema Presenze", fill=(255, 255, 255))
    return img

st.image(crea_logo_temporaneo(), use_container_width=True)

# ==========================================
# FUNZIONE GEOGRAFICA (ANTI-FRODE)
# ==========================================
def calcola_distanza(lat1, lon1, lat2, lon2):
    """Calcola la distanza in metri tra la posizione dello smartphone e il cantiere"""
    R = 6371000 
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# ==========================================
# CREAZIONE DELLE INTERFACCE (TAB)
# ==========================================
tab_timbratura, tab_admin = st.tabs(["📝 Registra Presenza", "📊 Pannello Amministratore"])

# --- SCHEDA DIPENDENTE ---
with tab_timbratura:
    if 'operatore' not in st.session_state:
        st.session_state['operatore'] = ""

    if not st.session_state['operatore']:
        st.subheader("🔒 Configurazione Primo Accesso")
        nome_inserito = st.text_input("Inserisci Nome e Cognome del dipendente:")
        if st.button("Configura Dispositivo"):
            if nome_inserito.strip():
                st.session_state['operatore'] = nome_inserito.strip()
                st.rerun()
            else:
                st.error("Inserisci un nome valido.")
    else:
        st.caption(f"Operatore Attivo: **{st.session_state['operatore']}**")
        
        # Richiesta coordinate GPS
        posizione = get_geolocation()
        
        if posizione:
            lat_utente = posizione['coords']['latitude']
            lon_utente = posizione['coords']['longitude']
            st.success("✅ Segnale GPS attivo.")
            
            tipo_registro = st.radio("Operazione:", ["Entrata", "Uscita"], horizontal=True)
            dati_qr = st.text_input("Dati del QR Code del cantiere:", placeholder="Cantiere Alpha, Via Roma 10, 45.4642, 9.1900")

            if st.button("Invia Timbratura Sicura"):
                if dati_qr:
                    try:
                        # Estrazione dati dal QR Code
                        parti = [x.strip() for x in dati_qr.split(",")]
                        nome_cantiere = parti[0]
                        luogo_cantiere = parti[1]
                        lat_cantiere = float(parti[2])
                        lon_cantiere = float(parti[3])
                        
                        # Controllo Geofencing
                        distanza = calcola_distanza(lat_utente, lon_utente, lat_cantiere, lon_cantiere)
                        SOGLIA_MASSIMA = 50.0  # Parametro modificabile: tolleranza in metri
                        
                        if distanza <= SOGLIA_MASSIMA:
                            ora_attuale_str = datetime.now().strftime("%H:%M:%S")
                            data_attuale_str = datetime.now().strftime("%Y-%m-%d")
                            
                            conn = st.connection("gsheets", type=GSheetsConnection)
                            df_esistente = conn.read()
                            
                            ore_calcolate = ""
                            
                            # SE È UN'USCITA: Calcoliamo le ore lavorate cercando l'entrata corrispondente
                            if tipo_registro == "Uscita" and not df_esistente.empty:
                                # Filtriamo per trovare l'entrata dello stesso giorno, stesso operatore, stesso cantiere
                                riga_entrata = df_esistente[
                                    (df_esistente['Operatore'] == st.session_state['operatore']) & 
                                    (df_esistente['Cantiere'] == nome_cantiere) & 
                                    (df_esistente['Data'] == data_attuale_str) & 
                                    (df_esistente['Tipo Registro'] == 'Entrata')
                                ].last_valid_index()
                                
                                if riga_entrata is not None:
                                    ora_entrata_str = df_esistente.loc[riga_entrata, 'Ora']
                                    t1 = datetime.strptime(f"{data_attuale_str} {ora_entrata_str}", "%Y-%m-%d %H:%M:%S")
                                    t2 = datetime.strptime(f"{data_attuale_str} {ora_attuale_str}", "%Y-%m-%d %H:%M:%S")
                                    diff = t2 - t1
                                    ore_calcolate = round(diff.total_seconds() / 3600, 2)
                            
                            # Creazione riga dati
                            riga = {
                                "ID": len(df_esistente) + 1,
                                "Data": data_attuale_str,
                                "Ora": ora_attuale_str,
                                "Operatore": st.session_state['operatore'],
                                "Cantiere": nome_cantiere,
                                "Luogo": luogo_cantiere,
                                "Tipo Registro": tipo_registro,
                                "Ore Lavorate": ore_calcolate
                            }
                            
                            # Aggiornamento database
                            df_aggiornato = pd.concat([df_esistente, pd.DataFrame([riga])], ignore_index=True)
                            conn.update(data=df_aggiornato)
                            
                            st.success(f"✅ {tipo_registro} registrata con successo presso {nome_cantiere}!")
                            if ore_calcolate != "":
                                st.info(f"⏱️ Ore di lavoro calcolate per questo turno: {ore_calcolate} ore.")
                        else:
                            st.error(f"❌ Blocco Sicurezza: Ti trovi fuori dal cantiere di {distanza:.1f} metri.")
                    except Exception as e:
                        st.error(f"Errore nel formato del QR Code o nella scrittura dei dati: {e}")
        else:
            st.warning("Abilita il GPS sul tuo smartphone per sbloccare la timbratura.")

# --- SCHEDA AMMINISTRATORE (PANNELLO DI CONTROLLO) ---
with tab_admin:
    st.subheader("🔍 Monitoraggio e Filtro Dipendenti")
    
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        df_dati = conn.read()
        
        if not df_dati.empty:
            # Rimozione righe vuote per evitare errori di filtraggio
            df_dati = df_dati.dropna(subset=['Operatore'])
            
            # Elenco univoco dei dipendenti presenti nel file Excel per il filtro
            lista_dipendenti = df_dati['Operatore'].unique().tolist()
            dipendente_selezionato = st.selectbox("Scegli il dipendente da analizzare:", lista_dipendenti)
            
            # Applicazione del filtro Pandas
            df_filtrato = df_dati[df_dati['Operatore'] == dipendente_selezionato]
            
            st.write(f"#### Registro dei movimenti di: **{dipendente_selezionato}**")
            st.dataframe(df_filtrato)
            
            # Sezione calcolo riepilogativo
            st.write("#### 📅 Ore Totali Raggruppate per Cantiere")
            # Convertiamo la colonna in valori numerici per poter fare la somma
            df_filtrato['Ore Lavorate'] = pd.to_numeric(df_filtrato['Ore Lavorate'], errors='coerce')
            
            # Raggruppamento per Data e Cantiere per sommare le ore svolte
            report_ore = df_filtrato.groupby(['Data', 'Cantiere'])['Ore Lavorate'].sum().reset_index()
            st.table(report_ore)
            
        else:
            st.info("Il file Excel è vuoto. Inizia a inserire le presenze per vedere i filtri.")
    except Exception as e:
        st.error(f"Errore nel caricamento del pannello amministratore: {e}")