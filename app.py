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
    Extrai CNPJ e o Nome que consta logo após o ' - '.
    """
    data = []
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Erro ao ler {file_name}: {e}")
        return []

    for page in doc:
        text = page.get_text("text")
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Procura por padrões de CNPJ ou CPF seguidos de " - "
            # Regex explicaçao:
            # 1. (CNPJ[:\s]*)? -> Opcional: Texto 'CNPJ:' ou 'Responsável:' seguido de espaço
            # 2. (\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{3}\.\d{3}\.\d{3}-\d{2}) -> O número (CNPJ ou CPF)
            # 3. \s*-\s* -> Um traço cercado ou não de espaços
            # 4. (.+) -> O NOME (grupo de captura principal)
            
            # Ajuste conforme sua necessidade: se for especificamente a linha do CNPJ:
            if "CNPJ" in line or "Responsável" in line:
                # Tenta capturar o padrão: NUMERO - NOME
                match = re.search(r'[\d\.\/-]{14,18}\s*-\s*(.+)', line)
                
                if match:
                    # O grupo 1 é o texto após o traço
                    nome_encontrado = clean_text(match.group(1))
                    
                    # Filtra ruídos (as vezes pega data ou hora se estiver na mesma linha)
                    if len(nome_encontrado) > 3 and not re.search(r'\d{2}/\d{2}/\d{4}', nome_encontrado):
                        
                        # Tenta identificar qual documento estava na linha (CNPJ ou CPF) para categorizar
                        doc_num_match = re.search(r'(\d[\d\.\/-]*)', line)
                        doc_num = doc_num_match.group(1) if doc_num_match else "N/A"
                        
                        data.append({
                            "Arquivo": file_name,
                            "Documento (CNPJ/CPF)": doc_num,
                            "Nome Extraído": nome_encontrado
                        })

    return data

# --- Interface Streamlit ---
st.title("📂 Extrator de Nomes (Pós-CNPJ/CPF)")
st.markdown("Extrai o nome que aparece logo após o **CNPJ** ou **CPF** separado por ` - `.")

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
            st.success(f"Processamento concluído! {len(df)} registros encontrados.")
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False, sep=";").encode('utf-8-sig')
            st.download_button(
                label="📥 Baixar Tabela (CSV)",
                data=csv,
                file_name="nomes_extraidos.csv",
                mime="text/csv",
            )
        else:
            st.warning("Nenhum padrão 'Documento - Nome' encontrado.")
