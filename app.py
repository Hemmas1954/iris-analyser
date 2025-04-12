import streamlit as st
import pandas as pd
from typing import Tuple, List, Dict, Optional
from utils import (
    load_data,
    analyze_dataframe_rules,
    analyze_row_with_ai,
    get_chatbot_response,
    save_training_data
)
import io
import base64
import os
import json
import time
from datetime import datetime
from pathlib import Path

# --- Configuration de la page ---
st.set_page_config(
    page_title="IRIS Analyseur",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

@st.cache_data
def load_css(css_file: str) -> Optional[str]:
    """
    Load and cache CSS file content
    """
    try:
        with open(css_file, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        st.warning(f"Impossible de charger le fichier CSS: {e}")
        return None

@st.cache_data
def load_logo(logo_path: str) -> Optional[str]:
    """
    Load and cache logo file content
    """
    try:
        with open(logo_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        st.warning(f"Logo non trouvé: {e}")
        return None

def initialize_session_state():
    """
    Initialize session state variables
    """
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    if 'df_original' not in st.session_state:
        st.session_state.df_original = None
    if 'df_results' not in st.session_state:
        st.session_state.df_results = None
    if 'analysis_done' not in st.session_state:
        st.session_state.analysis_done = False
    if 'column_mapping' not in st.session_state:
        st.session_state.column_mapping = None

def render_header():
    """Render the application header with logo and title"""
    col1, col2 = st.columns([1, 3])
    
    try:
        # Load logo as binary data instead of text
        with open("assets/images/iris_logo.PNG", "rb") as f:
            logo_data = f.read()
        col1.image(logo_data, width=150)
    except Exception as e:
        # Fallback if logo can't be loaded
        col1.error(f"Logo non trouvé: {str(e)}")
    
    col2.markdown("<h1>IRIS Analyseur</h1>", unsafe_allow_html=True)
    col2.markdown("<h3>Outil d'analyse des incohérences logiques dans les rapports de service</h3>", unsafe_allow_html=True)

def handle_chat_interaction():
    """
    Handle chat interactions in the sidebar
    """
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    if prompt := st.chat_input("Posez votre question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Réflexion..."):
                response = get_chatbot_response(prompt, st.session_state.messages)
                st.markdown(response)
        
        st.session_state.messages.append({"role": "assistant", "content": response})

@st.cache_data
def process_training_files(files: List) -> Tuple[int, List[str]]:
    """
    Process training files and return results
    """
    success_count = 0
    errors = []
    
    os.makedirs("training_data", exist_ok=True)
    for file in files:
        try:
            file_path = Path("training_data") / file.name
            file_path.write_bytes(file.getvalue())
            
            df, column_mapping = load_data(file)
            if df is not None:
                save_training_data(df, column_mapping)
                success_count += 1
        except Exception as e:
            errors.append(f"Erreur lors du traitement de {file.name}: {e}")
    
    return success_count, errors

def analyze_data_with_progress(df: pd.DataFrame) -> List[Dict]:
    """
    Analyze data with progress tracking
    """
    progress_bar = st.progress(0)
    status_text = st.empty()
    all_errors = []
    total_rows = len(df)

    # Rule-based analysis
    status_text.text("Étape 1/2: Vérification des règles de base...")
    rule_errors = analyze_dataframe_rules(df)
    all_errors.extend(rule_errors)
    progress_bar.progress(25)

    # AI-based analysis
    status_text.text("Étape 2/2: Analyse avec IA...")
    try:
        from utils import model as gemini_model
        if gemini_model:
            cleaned_columns = df.columns.tolist()
            for batch_start in range(0, total_rows, 10):  # Process in batches of 10
                batch_end = min(batch_start + 10, total_rows)
                batch = df.iloc[batch_start:batch_end]
                
                for index, row in batch.iterrows():
                    ai_result = analyze_row_with_ai(index, row.to_dict(), cleaned_columns)
                    if ai_result:
                        all_errors.append(ai_result)
                
                progress_percentage = 25 + int(75 * batch_end / total_rows)
                progress_bar.progress(progress_percentage)
        else:
            st.warning("Analyse IA désactivée: clé API non configurée")
    except Exception as e:
        st.error(f"Erreur lors de l'analyse IA: {e}")
    
    progress_bar.progress(100)
    status_text.text("Analyse terminée!")
    
    return all_errors

def main():
    """
    Main application logic
    """
    # Initialize session state
    initialize_session_state()

    # Load and apply CSS
    css = load_css("assets/style.css")
    if css:
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

    # Render header
    render_header()

    st.markdown("""
    Téléchargez vos rapports Excel ou CSV pour identifier rapidement les incohérences logiques
    comme les dates incorrectes, les incompatibilités produit-pièce, et les données manquantes.
    """)

    # File upload section
    uploaded_file = st.file_uploader("Téléchargez un fichier Excel ou CSV", type=["xlsx", "xls", "csv"])

    # Sidebar
    with st.sidebar:
        st.header("💬 Assistant IRIS")
        handle_chat_interaction()
        
        st.markdown("---")
        
        st.header("🧠 Entraînement du système")
        st.write("Téléchargez des rapports corrigés pour améliorer les règles d'analyse")
        
        training_files = st.file_uploader(
            "Téléchargez des rapports corrigés",
            type=["xlsx", "xls", "csv"],
            accept_multiple_files=True
        )
        
        if training_files and st.button("📚 Entraîner le système"):
            with st.spinner("Traitement des fichiers d'entraînement..."):
                success_count, errors = process_training_files(training_files)
                if errors:
                    for error in errors:
                        st.error(error)
                st.success(f"{success_count} fichiers traités avec succès!")

    # Main analysis section
    if uploaded_file is not None:
        st.markdown("---")
        st.header("Aperçu des données originales (après nettoyage)")

        with st.spinner("Chargement du fichier..."):
            df_original, column_mapping = load_data(uploaded_file)
            st.session_state.df_original = df_original
            st.session_state.column_mapping = column_mapping

        if st.session_state.df_original is not None:
            st.dataframe(st.session_state.df_original.head())
            st.caption(f"{len(st.session_state.df_original)} lignes chargées avec succès.")

            if st.button("🔍 Analyser les erreurs logiques"):
                st.session_state.analysis_done = False
                st.session_state.df_results = None

                st.header("Résultats de l'analyse")
                with st.spinner("Analyse des données en cours..."):
                    all_errors = analyze_data_with_progress(st.session_state.df_original.copy())

                    if not all_errors:
                        st.success("🎉 Aucune erreur logique évidente n'a été trouvée!")
                        st.session_state.df_results = st.session_state.df_original
                    else:
                        affected_rows = len(set(e['row_index'] for e in all_errors))
                        st.success(f"Analyse terminée! {len(all_errors)} problèmes potentiels trouvés dans {affected_rows} lignes.")
                        
                        df_results = st.session_state.df_original.copy()
                        if "Error Description" not in df_results.columns:
                            df_results["Error Description"] = ""
                        
                        for error in all_errors:
                            row_idx = error['row_index']
                            current_errors = df_results.at[row_idx, "Error Description"]
                            new_error = error['description']
                            df_results.at[row_idx, "Error Description"] = f"{current_errors}; {new_error}" if current_errors else new_error
                        
                        st.session_state.df_results = df_results
                    
                    st.session_state.analysis_done = True

        # Display results
        if st.session_state.analysis_done and st.session_state.df_results is not None:
            st.subheader("📊 Rapport avec erreurs identifiées")
            st.markdown("Le tableau ci-dessous contient les données originales avec une colonne supplémentaire `Error Description`.")
            st.dataframe(st.session_state.df_results)
            
            # Export options
            csv = st.session_state.df_results.to_csv(index=False)
            b64 = base64.b64encode(csv.encode()).decode()
            href = f'<a href="data:file/csv;base64,{b64}" download="rapport_analyse.csv">📥 Télécharger le rapport (CSV)</a>'
            st.markdown(href, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("All rights reserved HEMMAS 2025 ©.")

if __name__ == "__main__":
    main()