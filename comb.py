import streamlit as st
import pandas as pd
import re
from typing import Tuple, List
from io import BytesIO
import plotly.express as px
import plotly.graph_objects as go

# Configuration de la page
st.set_page_config(
    page_title="Nettoyage d'Inventaire",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def clean_inventory_data(df: pd.DataFrame, 
                        product_name_col: str, 
                        product_ref_col: str) -> Tuple[pd.DataFrame, pd.DataFrame, List[str]]:
    """
    Nettoie les données d'inventaire et divise en combinaisons uniques et dupliquées.
    """
    # Vérification des colonnes
    if product_name_col not in df.columns:
        raise ValueError(f"Colonne '{product_name_col}' non trouvée dans le DataFrame")
    if product_ref_col not in df.columns:
        raise ValueError(f"Colonne '{product_ref_col}' non trouvée dans le DataFrame")
    
    # Copie et initialisation
    cleaned_df = df.copy()
    warnings = []
    
    # === NETTOYAGE DES NOMS DE PRODUITS ===
    original_names = cleaned_df[product_name_col].copy()
    
    # Convertir en string et gérer les NaN
    cleaned_df[product_name_col] = cleaned_df[product_name_col].astype(str)
    cleaned_df[product_name_col] = cleaned_df[product_name_col].replace('nan', '')
    
    # Nettoyage vectorisé des noms
    cleaned_df[product_name_col] = (cleaned_df[product_name_col]
                                   .str.strip()
                                   .str.replace(r'\s+', ' ', regex=True)
                                   .str.replace(r'[\x00-\x1f\x7f-\x9f]', '', regex=True))
    
    names_changed = (original_names.astype(str) != cleaned_df[product_name_col]).sum()
    
    # === NETTOYAGE DES RÉFÉRENCES ===
    original_refs = cleaned_df[product_ref_col].copy()
    
    # Convertir en string et gérer les NaN
    cleaned_df[product_ref_col] = cleaned_df[product_ref_col].astype(str)
    cleaned_df[product_ref_col] = cleaned_df[product_ref_col].replace('nan', '')
    
    # Nettoyage de base
    cleaned_df[product_ref_col] = (cleaned_df[product_ref_col]
                                  .str.strip()
                                  .str.replace(r'[\x00-\x1f\x7f-\x9f]', '', regex=True))
    
    # Correction intelligente o->0
    mask_has_digits = cleaned_df[product_ref_col].str.contains(r'\d', na=False)
    cleaned_df.loc[mask_has_digits, product_ref_col] = (
        cleaned_df.loc[mask_has_digits, product_ref_col]
        .str.replace(r'(?<=\d)[oO](?=\d)', '0', regex=True)
        .str.replace(r'^[oO](?=\d)', '0', regex=True)
        .str.replace(r'(?<=\d)[oO]$', '0', regex=True)
    )
    
    refs_changed = (original_refs.astype(str) != cleaned_df[product_ref_col]).sum()
    
    # === IDENTIFICATION DES DOUBLONS ===
    cleaned_df['_temp_key'] = (cleaned_df[product_name_col] + '|' + 
                              cleaned_df[product_ref_col])
    
    duplicate_mask = cleaned_df['_temp_key'].duplicated(keep=False)
    
    # Diviser les DataFrames
    unique_df = cleaned_df[~duplicate_mask].drop('_temp_key', axis=1).copy()
    duplicate_df = cleaned_df[duplicate_mask].drop('_temp_key', axis=1).copy()
    
    # === AVERTISSEMENTS ===
    if names_changed > 0:
        warnings.append(f"✏️ {names_changed} noms de produits ont été nettoyés")
    if refs_changed > 0:
        warnings.append(f"🔧 {refs_changed} références ont été corrigées")
    
    # Vérification des valeurs vides
    empty_names_unique = (unique_df[product_name_col].isin(['', 'nan']) | 
                         unique_df[product_name_col].isna()).sum()
    empty_refs_unique = (unique_df[product_ref_col].isin(['', 'nan']) | 
                        unique_df[product_ref_col].isna()).sum()
    
    if empty_names_unique > 0:
        warnings.append(f"⚠️ {empty_names_unique} noms vides dans les données uniques")
    if empty_refs_unique > 0:
        warnings.append(f"⚠️ {empty_refs_unique} références vides dans les données uniques")
    
    if len(duplicate_df) > 0:
        duplicate_groups = duplicate_df.groupby([product_name_col, product_ref_col]).size()
        top_duplicates = duplicate_groups.sort_values(ascending=False).head(5)
        
        warnings.append(f"🔄 {len(duplicate_groups)} groupes de doublons trouvés")
        warnings.append("Top 5 doublons:")
        for (name, ref), count in top_duplicates.items():
            warnings.append(f"  • '{name}' | '{ref}' : {count} occurrences")
    
    return unique_df, duplicate_df, warnings


def to_excel(df):
    """Convertit un DataFrame en fichier Excel téléchargeable"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Données', index=False)
    processed_data = output.getvalue()
    return processed_data


def create_statistics_chart(unique_count, duplicate_count):
    """Crée un graphique des statistiques"""
    fig = go.Figure(data=[
        go.Bar(name='Données', 
               x=['Combinaisons Uniques', 'Lignes Dupliquées'], 
               y=[unique_count, duplicate_count],
               marker_color=['#00cc96', '#ff6692'])
    ])
    
    fig.update_layout(
        title="Répartition des Données après Nettoyage",
        yaxis_title="Nombre de lignes",
        showlegend=False,
        height=400
    )
    return fig


def main():
    # Titre et description
    st.title("📊 Nettoyage et Division d'Inventaire")
    st.markdown("""
    Cette application nettoie vos données d'inventaire et sépare les combinaisons **uniques** des **doublons** 
    basées sur le nom du produit et sa référence.
    """)
    
    # Sidebar pour les paramètres
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # Upload du fichier
        uploaded_file = st.file_uploader(
            "Choisir un fichier Excel/CSV",
            type=['xlsx', 'csv', 'xls'],
            help="Formats supportés: Excel (.xlsx, .xls) et CSV"
        )
        
        if uploaded_file is not None:
            # Lecture du fichier
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                st.success(f"✅ Fichier chargé: {len(df)} lignes")
                
                # Sélection des colonnes
                st.subheader("🏷️ Colonnes à analyser")
                
                columns = df.columns.tolist()
                
                name_col = st.selectbox(
                    "Colonne Nom du Produit:",
                    columns,
                    index=0,
                    help="Colonne contenant les noms des produits"
                )
                
                ref_col = st.selectbox(
                    "Colonne Référence:",
                    columns,
                    index=1 if len(columns) > 1 else 0,
                    help="Colonne contenant les références des produits"
                )
                
                # Options de nettoyage
                st.subheader("🧹 Options de nettoyage")
                st.info("""
                **Nettoyage automatique inclus:**
                - Suppression des espaces inutiles
                - Correction 'o' → '0' dans les références
                - Suppression des caractères de contrôle
                """)
                
            except Exception as e:
                st.error(f"❌ Erreur lors du chargement: {str(e)}")
                return
    
    # Corps principal
    if uploaded_file is not None:
        
        # Aperçu des données originales
        with st.expander("👀 Aperçu des données originales", expanded=False):
            st.dataframe(df.head(10), use_container_width=True)
            st.info(f"Colonnes disponibles: {', '.join(df.columns.tolist())}")
        
        # Bouton de traitement
        if st.button("🚀 Nettoyer et Diviser les Données", type="primary"):
            
            try:
                with st.spinner("Traitement en cours..."):
                    # Appliquer le nettoyage
                    unique_df, duplicate_df, warnings = clean_inventory_data(df, name_col, ref_col)
                
                # Métriques
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("📋 Total Lignes", len(df))
                
                with col2:
                    st.metric("✅ Combinaisons Uniques", len(unique_df))
                
                with col3:
                    st.metric("🔄 Lignes Dupliquées", len(duplicate_df))
                
                with col4:
                    duplicate_rate = (len(duplicate_df) / len(df)) * 100 if len(df) > 0 else 0
                    st.metric("📊 Taux Doublons", f"{duplicate_rate:.1f}%")
                
                # Graphique
                if len(unique_df) > 0 or len(duplicate_df) > 0:
                    fig = create_statistics_chart(len(unique_df), len(duplicate_df))
                    st.plotly_chart(fig, use_container_width=True)
                
                # Avertissements
                if warnings:
                    with st.expander("⚠️ Détails du nettoyage", expanded=True):
                        for warning in warnings:
                            st.write(f"• {warning}")
                
                # Résultats en colonnes
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("✅ Données Uniques")
                    if len(unique_df) > 0:
                        st.dataframe(unique_df, use_container_width=True)
                        
                        # Téléchargement Excel
                        excel_unique = to_excel(unique_df)
                        st.download_button(
                            label="📥 Télécharger Données Uniques (Excel)",
                            data=excel_unique,
                            file_name="unique_PDR_carton.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.info("Aucune donnée unique trouvée")
                
                with col2:
                    st.subheader("🔄 Données Dupliquées")
                    if len(duplicate_df) > 0:
                        st.dataframe(duplicate_df, use_container_width=True)
                        
                        # Téléchargement Excel
                        excel_duplicate = to_excel(duplicate_df)
                        st.download_button(
                            label="📥 Télécharger Données Dupliquées (Excel)",
                            data=excel_duplicate,
                            file_name="duplicate_PDR_carton.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.success("🎉 Aucun doublon trouvé!")
                
                # Analyse détaillée des doublons
                if len(duplicate_df) > 0:
                    with st.expander("🔍 Analyse détaillée des doublons", expanded=False):
                        # Grouper par combinaison nom/référence
                        duplicate_analysis = duplicate_df.groupby([name_col, ref_col]).agg({
                            duplicate_df.columns[0]: 'count'  # Utiliser la première colonne pour compter
                        }).rename(columns={duplicate_df.columns[0]: 'Occurrences'})
                        
                        duplicate_analysis = duplicate_analysis.reset_index()
                        duplicate_analysis = duplicate_analysis.sort_values('Occurrences', ascending=False)
                        
                        st.dataframe(duplicate_analysis, use_container_width=True)
                        
                        # Graphique des top doublons
                        if len(duplicate_analysis) > 0:
                            top_10 = duplicate_analysis.head(10)
                            top_10['Label'] = top_10[name_col] + " | " + top_10[ref_col]
                            
                            fig_duplicates = px.bar(
                                top_10, 
                                x='Occurrences', 
                                y='Label',
                                orientation='h',
                                title="Top 10 des Combinaisons Dupliquées",
                                color='Occurrences',
                                color_continuous_scale='Reds'
                            )
                            fig_duplicates.update_layout(height=400)
                            st.plotly_chart(fig_duplicates, use_container_width=True)
                
            except Exception as e:
                st.error(f"❌ Erreur lors du traitement: {str(e)}")
    
    else:
        # Instructions d'utilisation
        st.info("""
        ### 📖 Instructions d'utilisation:
        
        1. **📁 Chargez votre fichier** Excel ou CSV dans la barre latérale
        2. **🏷️ Sélectionnez les colonnes** contenant le nom et la référence du produit  
        3. **🚀 Cliquez sur "Nettoyer et Diviser"** pour traiter vos données
        4. **📥 Téléchargez les résultats** en Excel (données uniques et doublons séparés)
        
        ### ✨ Fonctionnalités:
        - 🧹 **Nettoyage automatique** des espaces et caractères indésirables
        - 🔧 **Correction intelligente** des erreurs courantes (o → 0)
        - 📊 **Visualisation** des statistiques et doublons
        - 📈 **Analyse détaillée** des combinaisons problématiques
        - 💾 **Export Excel** des résultats séparés
        """)
        
        # Exemple de données
        st.subheader("📋 Format de données attendu:")
        sample_data = pd.DataFrame({
            'designation': ['Produit A', 'Produit B', 'Produit A', 'Produit C'],
            'reference': ['REF001', 'REF002', 'REF001', 'REF003'],
            'quantite': [10, 20, 15, 30],
            'prix': [100, 200, 150, 300]
        })
        st.dataframe(sample_data, use_container_width=True)


if __name__ == "__main__":
    main()
