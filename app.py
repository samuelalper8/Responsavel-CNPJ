import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Extrator de Responsáveis", layout="wide")

def clean_text(text):
    """Limpa espaços extras."""
    return " ".join(text.split()).strip()

def extract_info_from_pdf(pdf_bytes, file_name):
    """
    Extrai TODAS as ocorrências de 'CNPJ - Texto' encontradas,
    sem filtrar nada inicialmente.
    """
    data = []
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Erro ao ler {file_name}: {e}")
        return []

    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Filtro básico de existência
            if "CNPJ" in line or "Responsável" in line:
                
                # Regex captura: Documento - Qualquer Coisa
                match = re.search(r'([\d\.\/-]{14,18})\s*-\s*(.+)', line)
                
                if match:
                    doc_num = match.group(1).strip()
                    raw_text = clean_text(match.group(2))
                    
                    # Salva TUDO (incluindo o que pode ser lixo)
                    # Adicionamos o número da página para ajudar na conferência
                    data.append({
                        "Arquivo": file_name,
                        "Página": page_num + 1,
                        "Documento (CNPJ/CPF)": doc_num,
                        "Conteúdo Extraído": raw_text
                    })

    return data

# --- Interface Streamlit ---
st.title("📂 Extrator de Nomes (Pós-CNPJ/CPF)")
st.markdown("Extrai o texto localizado logo após o **CNPJ** ou **CPF** (separado por ` - `).")

uploaded_files = st.file_uploader(
    "Arraste seus PDFs aqui", 
    type=["pdf"], 
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Processar Arquivos"):
        all_results = []
        progress_bar = st.progress(0)
        
        for idx, uploaded_file in enumerate(uploaded_files):
            bytes_data = uploaded_file.read()
            extracted_data = extract_info_from_pdf(bytes_data, uploaded_file.name)
            all_results.extend(extracted_data)
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        progress_bar.empty()

        if all_results:
            df = pd.DataFrame(all_results)
            
            st.write("---")
            
            # --- ÁREA DE REFINAMENTO ---
            # Por padrão vem desmarcado (mantém o lixo), mas o usuário pode ativar
            usar_refinamento = st.checkbox("🔍 Aplicar Refinamento (Remover duplicatas e limpar 'lixo')", value=False)
            
            if usar_refinamento:
                # 1. Filtros de Texto (Remove datas, paginação, nomes muito curtos)
                # Cria uma máscara booleana para filtrar
                mask_lixo = (
                    df["Conteúdo Extraído"].str.len() > 3 & 
                    ~df["Conteúdo Extraído"].str.contains(r'\d{2}/\d{2}/\d{4}', regex=True) & # Não é data
                    ~df["Conteúdo Extraído"].str.contains("Página", case=False) &
                    ~df["Conteúdo Extraído"].str.contains("PAGE", case=False)
                )
                df_refined = df[mask_lixo].copy()
                
                # 2. Remover Duplicatas (Mantém apenas a primeira ocorrência de cada CNPJ por Arquivo)
                df_refined = df_refined.drop_duplicates(subset=["Arquivo", "Documento (CNPJ/CPF)"], keep="first")
                
                st.success(f"Refinamento aplicado! Reduzido de {len(df)} para {len(df_refined)} registros.")
                df_final = df_refined
            else:
                st.info(f"Exibindo todos os {len(df)} registros extraídos (sem filtros).")
                df_final = df
            
            # Exibe Tabela
            st.dataframe(df_final, use_container_width=True)
            
            # Download
            csv = df_final.to_csv(index=False, sep=";").encode('utf-8-sig')
            st.download_button(
                label="📥 Baixar Tabela (CSV)",
                data=csv,
                file_name="extracao_nomes.csv",
                mime="text/csv",
            )
        else:
            st.warning("Nenhum padrão 'Documento - Texto' encontrado.")
