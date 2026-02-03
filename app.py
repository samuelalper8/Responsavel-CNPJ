import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Extrator de Responsáveis", layout="wide")

def clean_text(text):
    """Limpa espaços extras e normaliza o texto."""
    return " ".join(text.split()).strip()

def extract_info_from_pdf(pdf_bytes, file_name):
    """
    Extrai TODAS as ocorrências de 'CNPJ/CPF - Texto', capturando também o Rótulo (Contexto).
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
            
            # Regex ajustada para capturar o prefixo (Rótulo) se existir
            # Grupo 1: O rótulo (Ex: Responsável, CNPJ, ou vazio)
            # Grupo 2: O Número (CNPJ/CPF)
            # Grupo 3: O Nome (Texto após o traço)
            
            # Procura por: (Inicio ou espaço) + (Rótulo opcional) + (Numero) + ( - ) + (Nome)
            match = re.search(r'(Responsável|CNPJ|CPF)?[:\s]*([\d\.\/-]{14,18})\s*-\s*(.+)', line, re.IGNORECASE)
            
            if match:
                rotulo = clean_text(match.group(1)) if match.group(1) else "Indefinido"
                doc_num = match.group(2).strip()
                raw_text = clean_text(match.group(3))
                
                # Filtro imediato de segurança (ignora se o nome for só números ou muito curto)
                if len(raw_text) > 3 and not raw_text.replace('/','').replace('-','').isdigit():
                    data.append({
                        "Arquivo": file_name,
                        "Página": page_num + 1,
                        "Tipo (Rótulo)": rotulo.capitalize(), # Ex: Responsável, Cnpj
                        "Documento": doc_num,
                        "Nome Extraído": raw_text
                    })

    return data

# --- Interface Streamlit ---
st.title("📂 Extrator de Responsáveis Inteligente")
st.markdown("Extrai nomes vinculados a **CNPJ** ou **CPF** e seleciona a melhor ocorrência.")

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
            st.session_state['df_raw'] = pd.DataFrame(all_results)
            st.session_state['processed'] = True
            st.success("Arquivos processados! Veja o resultado abaixo.")
        else:
            st.warning("Nenhum padrão 'Documento - Nome' encontrado.")

# --- ÁREA DE EXIBIÇÃO E REFINAMENTO ---
if 'processed' in st.session_state and st.session_state['processed']:
    
    df = st.session_state['df_raw']
    st.write("---")
    
    # Checkbox de Refinamento
    usar_refinamento = st.checkbox("🔍 Refinar (Selecionar o nome mais provável para cada CNPJ)", value=True)
    
    if usar_refinamento:
        # --- LÓGICA DE PONTUAÇÃO (RANKING) ---
        # Criamos uma coluna temporária de 'Pontos' para decidir qual linha é a correta
        
        def calcular_pontos(row):
            pontos = 0
            nome = row["Nome Extraído"].upper()
            tipo = row["Tipo (Rótulo)"]
            
            # 1. Prioridade Máxima: Se o rótulo for "Responsável", é quase certeza que é o correto
            if "RESPONS" in tipo.upper():
                pontos += 100
                
            # 2. Penalidade para "Lixo" comum (Datas, Página)
            if re.search(r'\d{2}/\d{2}/\d{4}', nome): pontos -= 50
            if "PÁGINA" in nome or "PAGE" in nome: pontos -= 50
            
            # 3. Penalidade para Nomes de Órgãos (se queremos o CPF/Nome da Pessoa)
            # Se você quer extrair o Prefeito, não quer extrair "MUNICIPIO DE..."
            if "MUNICIPIO" in nome or "PREFEITURA" in nome or "SECRETARIA" in nome:
                pontos -= 20
            
            # 4. Bonificação por tamanho (nomes completos costumam ser maiores que siglas)
            if len(nome) > 10: pontos += 5
            
            return pontos

        # Aplica a pontuação
        df['Pontos'] = df.apply(calcular_pontos, axis=1)
        
        # ORDENA: Do maior ponto para o menor
        df_sorted = df.sort_values(by=['Arquivo', 'Documento', 'Pontos'], ascending=[True, True, False])
        
        # REMOVE DUPLICATAS: Mantém apenas o primeiro (que agora é o de maior pontuação)
        df_final = df_sorted.drop_duplicates(subset=["Arquivo", "Documento"], keep="first").copy()
        
        # Remove a coluna de pontos para não poluir a saída
        df_final = df_final.drop(columns=['Pontos'])
        
        st.info(f"Refinamento Inteligente: Selecionadas as linhas mais relevantes para cada CNPJ.")
        
    else:
        df_final = df
        st.warning("Modo Bruto: Exibindo todas as ocorrências encontradas.")
    
    # Mostra a Tabela
    st.dataframe(df_final, use_container_width=True)
    
    # Download
    csv = df_final.to_csv(index=False, sep=";").encode('utf-8-sig')
    st.download_button(
        label="📥 Baixar Tabela (CSV)",
        data=csv,
        file_name="responsaveis_refinados.csv",
        mime="text/csv",
    )
