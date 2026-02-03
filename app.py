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
    Extrai TODAS as ocorrências de 'CNPJ - Texto'.
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
            
            # Filtro básico
            if "CNPJ" in line or "Responsável" in line:
                
                # Regex captura: Documento - Qualquer Coisa
                match = re.search(r'([\d\.\/-]{14,18})\s*-\s*(.+)', line)
                
                if match:
                    doc_num = match.group(1).strip()
                    raw_text = clean_text(match.group(2))
                    
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

# Botão de processamento
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
            # SALVA NO SESSION STATE (MEMÓRIA)
            st.session_state['df_raw'] = pd.DataFrame(all_results)
            st.session_state['processed'] = True
            st.success("Arquivos processados com sucesso!")
        else:
            st.warning("Nenhum padrão encontrado.")

# --- ÁREA DE EXIBIÇÃO (FORA DO BOTÃO) ---
# Verifica se já existe dados na memória da sessão
if 'processed' in st.session_state and st.session_state['processed']:
    
    df = st.session_state['df_raw']
    
    st.write("---")
    
    # Checkbox de Refinamento
    usar_refinamento = st.checkbox("🔍 Aplicar Refinamento (Remover duplicatas e limpar 'lixo')", value=False)
    
    if usar_refinamento:
        # Lógica de Filtro
        mask_lixo = (
            (df["Conteúdo Extraído"].str.len() > 3) & 
            (~df["Conteúdo Extraído"].str.contains(r'\d{2}/\d{2}/\d{4}', regex=True)) & 
            (~df["Conteúdo Extraído"].str.contains("Página", case=False)) &
            (~df["Conteúdo Extraído"].str.contains("PAGE", case=False))
        )
        df_final = df[mask_lixo].copy()
        # Remove duplicatas mantendo a primeira ocorrência
        df_final = df_final.drop_duplicates(subset=["Arquivo", "Documento (CNPJ/CPF)"], keep="first")
        
        st.info(f"Refinamento Ativo: Exibindo {len(df_final)} registros únicos (de um total de {len(df)} linhas extraídas).")
    else:
        df_final = df
        st.warning(f"Modo Bruto: Exibindo todos os {len(df)} registros (inclui repetições e dados indesejados).")
    
    # Mostra a Tabela (Sempre atualizada)
    st.dataframe(df_final, use_container_width=True)
    
    # Botão de Download (Sempre visível)
    csv = df_final.to_csv(index=False, sep=";").encode('utf-8-sig')
    st.download_button(
        label="📥 Baixar Tabela (CSV)",
        data=csv,
        file_name="extracao_nomes.csv",
        mime="text/csv",
    )
