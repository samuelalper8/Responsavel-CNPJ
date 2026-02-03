import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Extrator de Responsáveis", layout="wide")

def clean_text(text):
    """Limpa espaços extras e normaliza o texto."""
    if not text: return ""
    return " ".join(text.split()).strip()

def extract_info_from_pdf(pdf_bytes, file_name):
    """
    Extrai o Responsável e tenta identificar o Nome do Órgão/Entidade na capa.
    """
    data = []
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Erro ao ler {file_name}: {e}")
        return []

    # --- ETAPA 1: Identificar o Nome do Órgão (Entidade) na Página 1 ---
    # Geralmente é a primeira linha com CNPJ ou logo abaixo do cabeçalho
    nome_orgao = "Não identificado"
    try:
        page1_text = doc[0].get_text("text")
        lines_p1 = page1_text.split('\n')
        
        for line in lines_p1:
            line = line.strip()
            # Procura por "CNPJ: 00... NOME DO ORGAO" (com ou sem traço)
            # Pega o primeiro que aparecer (geralmente é o titular do relatório)
            if "CNPJ" in line and len(line) > 15:
                # Regex para pegar o texto após o número do CNPJ
                match_orgao = re.search(r'CNPJ[:\s]*[\d\.\/-]+\s*[-–]?\s*(.+)', line, re.IGNORECASE)
                if match_orgao:
                    candidato = clean_text(match_orgao.group(1))
                    # Filtra se capturou lixo ou "Dados Cadastrais"
                    if len(candidato) > 3 and "DADOS CADASTRAIS" not in candidato.upper():
                        nome_orgao = candidato
                        break # Achou o primeiro, para.
    except:
        pass # Se der erro na identificação, segue como "Não identificado"

    # --- ETAPA 2: Extrair os Responsáveis (Varredura Completa) ---
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Regex principal para capturar CPF/CNPJ - Nome
            match = re.search(r'(Responsável|CNPJ|CPF)?[:\s]*([\d\.\/-]{14,18})\s*-\s*(.+)', line, re.IGNORECASE)
            
            if match:
                rotulo = clean_text(match.group(1)) if match.group(1) else "Indefinido"
                doc_num = match.group(2).strip()
                raw_text = clean_text(match.group(3))
                
                # Filtros de qualidade
                if (len(raw_text) > 3 
                    and not re.match(r'^[\d\.\/-]+$', raw_text) # Não é só número
                    and not re.search(r'\d{2}/\d{2}/\d{4}', raw_text)): # Não é data
                    
                    data.append({
                        "Nome do Arquivo": file_name,
                        "Órgão / Entidade (PDF)": nome_orgao, # Nova Coluna
                        "Página": page_num + 1,
                        "Tipo (Rótulo)": rotulo.capitalize(),
                        "Documento": doc_num,
                        "Nome Extraído": raw_text
                    })

    return data

# --- Interface Streamlit ---
st.title("📂 Extrator de Responsáveis Inteligente")
st.markdown("""
Esta ferramenta extrai o **Nome do Responsável** e identifica o **Nome do Órgão** dentro do PDF.
Útil mesmo quando os nomes dos arquivos estão truncados (ex: `GO~1.PDF`).
""")

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
            st.session_state['df_raw'] = pd.DataFrame(all_results)
            st.session_state['processed'] = True
            st.success("Arquivos processados!")
        else:
            st.warning("Nenhum dado encontrado.")

# --- Exibição ---
if 'processed' in st.session_state and st.session_state['processed']:
    
    df = st.session_state['df_raw']
    st.write("---")
    
    usar_refinamento = st.checkbox("🔍 Refinar (Selecionar Responsável + Identificar Órgão)", value=True)
    
    if usar_refinamento:
        # 1. Calcular Pontos para achar o RESPONSÁVEL
        def calcular_pontos(row):
            pontos = 0
            nome = row["Nome Extraído"].upper()
            tipo = row["Tipo (Rótulo)"]
            
            if "RESPONS" in tipo.upper(): pontos += 100
            if "PÁGINA" in nome or "PAGE" in nome: pontos -= 50
            if "CNPJ" in nome: pontos -= 20
            # Penaliza se o nome extraído for igual ao nome do órgão (queremos a pessoa)
            if row["Órgão / Entidade (PDF)"] != "Não identificado" and row["Órgão / Entidade (PDF)"] in nome:
                pontos -= 10
            if "MUNICIPIO" in nome or "PREFEITURA" in nome or "SECRETARIA" in nome: pontos -= 20
            if len(nome) > 10: pontos += 5
            return pontos

        df['Pontos'] = df.apply(calcular_pontos, axis=1)
        
        # Ordena para o Responsável ficar no topo
        df_sorted = df.sort_values(by=['Nome do Arquivo', 'Pontos'], ascending=[True, False])
        
        # Remove duplicatas por arquivo (Pega o melhor candidato a Responsável de cada PDF)
        # Atenção: Aqui assumimos 1 Responsável principal por arquivo PDF
        df_final = df_sorted.drop_duplicates(subset=["Nome do Arquivo"], keep="first").copy()
        
        # Reorganiza as colunas para ficar bonito
        colunas_ordem = ["Nome do Arquivo", "Órgão / Entidade (PDF)", "Documento", "Nome Extraído"]
        # Garante que as colunas existem (caso falte alguma)
        cols_to_show = [c for c in colunas_ordem if c in df_final.columns]
        df_final = df_final[cols_to_show]
        
        st.info("Refinamento Ativo: Identificamos o Órgão e o Responsável de cada arquivo.")
    else:
        df_final = df
        st.warning("Modo Bruto.")
    
    st.dataframe(df_final, use_container_width=True)
    
    csv = df_final.to_csv(index=False, sep=";").encode('utf-8-sig')
    st.download_button("📥 Baixar Tabela (CSV)", data=csv, file_name="responsaveis_identificados.csv", mime="text/csv")
