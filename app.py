import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Extrator de Responsáveis", layout="wide")

def clean_text(text):
    """Limpa espaços extras."""
    if not text: return ""
    return " ".join(text.split()).strip()

def formatar_nome(text):
    """
    Converte para Title Case (Iniciais Maiúsculas), 
    mantendo preposições (de, da, do...) em minúsculo.
    """
    if not text: return ""
    
    # Lista de preposições que devem ficar minúsculas
    preposicoes = {'de', 'da', 'do', 'dos', 'das', 'e', 'em', 'com', 'por', 'para'}
    
    words = text.split()
    new_words = []
    
    for i, word in enumerate(words):
        word_lower = word.lower()
        # Se for preposição e não for a primeira palavra, mantém minúsculo
        if word_lower in preposicoes and i != 0:
            new_words.append(word_lower)
        # Se for sigla (ex: CPF, CNPJ, SMT, IAG), mantém maiúsculo se tiver até 3 letras
        elif len(word) <= 3 and word.isalpha() and word.isupper():
             new_words.append(word) # Mantém SMT, IAG como está se o original for maiúsculo
        else:
            new_words.append(word_lower.capitalize())
            
    return " ".join(new_words)

def extract_info_from_pdf(pdf_bytes, file_name):
    """
    Extrai dados e aplica formatação de nomes.
    """
    data = []
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Erro ao ler {file_name}: {e}")
        return []

    # --- ETAPA 1: Identificar o Nome do Órgão (Entidade) na Capa ---
    nome_orgao_capa = "Não identificado"
    try:
        page1_text = doc[0].get_text("text")
        lines_p1 = [l.strip() for l in page1_text.split('\n')]
        
        # Estratégia A: Horizontal (CNPJ - Nome)
        for line in lines_p1:
            if "CNPJ" in line and len(line) > 15:
                match = re.search(r'CNPJ[:\s]*[\d\.\/-]+\s*[-–]?\s*(.+)', line, re.IGNORECASE)
                if match:
                    cand = clean_text(match.group(1))
                    if len(cand) > 3 and "DADOS CADASTRAIS" not in cand.upper():
                        nome_orgao_capa = formatar_nome(cand) # Aplica formatação
                        break
        
        # Estratégia B: Vertical (Campo "Nome" seguido do valor)
        if nome_orgao_capa == "Não identificado":
            for i, line in enumerate(lines_p1):
                if line == "Nome" and i + 1 < len(lines_p1):
                    cand = lines_p1[i+1]
                    if len(cand) > 3 and not re.match(r'^[\d\.\/-]+$', cand):
                        nome_orgao_capa = formatar_nome(cand) # Aplica formatação
                        break
    except:
        pass

    # --- ETAPA 2: Extrair os Registros ---
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        lines = [l.strip() for l in text.split('\n')]
        
        found_on_page = False
        
        # MODO 1: Horizontal
        for line in lines:
            match = re.search(r'(Responsável|CNPJ|CPF)?[:\s]*([\d\.\/-]{14,18})\s*-\s*(.+)', line, re.IGNORECASE)
            
            if match:
                rotulo = clean_text(match.group(1)) if match.group(1) else "Indefinido"
                doc_num = match.group(2).strip()
                raw_text = clean_text(match.group(3))
                
                if (len(raw_text) > 3 
                    and not re.match(r'^[\d\.\/-]+$', raw_text) 
                    and not re.search(r'\d{2}/\d{2}/\d{4}', raw_text)):
                    
                    data.append({
                        "Nome do Arquivo": file_name,
                        "Órgão / Entidade (PDF)": nome_orgao_capa,
                        "Página": page_num + 1,
                        "Tipo (Rótulo)": rotulo.capitalize(),
                        "Documento": doc_num,
                        "Nome Extraído": formatar_nome(raw_text) # Aplica formatação
                    })
                    found_on_page = True

        # MODO 2: Vertical (Se falhou o horizontal ou é documento específico)
        if not found_on_page or "IDENTIFICAÇÃO DO CONTRIBUINTE" in text:
            for i, line in enumerate(lines):
                if line == "CNPJ/CPF" or line == "CNPJ":
                    if i + 1 < len(lines):
                        doc_cand = lines[i+1]
                        if re.match(r'^[\d\.\/-]+$', doc_cand):
                            
                            nome_cand = "Não identificado"
                            for j in range(max(0, i-10), min(len(lines), i+10)):
                                if lines[j] == "Nome" and j+1 < len(lines):
                                    nome_cand = lines[j+1]
                                    break
                            
                            if nome_cand == "Não identificado":
                                nome_cand = nome_orgao_capa
                            else:
                                nome_cand = formatar_nome(nome_cand) # Aplica formatação

                            data.append({
                                "Nome do Arquivo": file_name,
                                "Órgão / Entidade (PDF)": nome_orgao_capa,
                                "Página": page_num + 1,
                                "Tipo (Rótulo)": "Contribuinte",
                                "Documento": doc_cand,
                                "Nome Extraído": nome_cand
                            })

    return data

# --- Interface Streamlit ---
st.title("📂 Extrator de Responsáveis (Formatado)")
st.markdown("""
Extrai **Responsáveis** e **Entidades** de relatórios da RFB.
\n**Melhoria:** Nomes formatados com iniciais maiúsculas (Ex: *João da Silva*).
""")

uploaded_files = st.file_uploader("Arraste seus PDFs aqui", type=["pdf"], accept_multiple_files=True)

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
            st.success("Arquivos processados com sucesso!")
        else:
            st.warning("Nenhum dado encontrado.")

# --- Exibição e Refinamento ---
if 'processed' in st.session_state and st.session_state['processed']:
    
    df = st.session_state['df_raw']
    st.write("---")
    
    usar_refinamento = st.checkbox("🔍 Refinar Resultado (Priorizar Responsáveis)", value=True)
    
    if usar_refinamento:
        def calcular_pontos(row):
            pontos = 0
            # Normalizamos para maiúsculo apenas para a lógica de pontuação
            nome = str(row["Nome Extraído"]).upper() 
            tipo = str(row["Tipo (Rótulo)"]).upper()
            
            if "RESPONS" in tipo: pontos += 100
            if "CONTRIBUINTE" in tipo: pontos += 50
            if "PÁGINA" in nome or "PAGE" in nome: pontos -= 50
            if "CNPJ" in nome: pontos -= 20
            
            if "CONTRIBUINTE" not in tipo:
                if "MUNICIPIO" in nome or "PREFEITURA" in nome or "SECRETARIA" in nome: 
                    pontos -= 20
            
            if len(nome) > 10: pontos += 5
            return pontos

        df['Pontos'] = df.apply(calcular_pontos, axis=1)
        
        df_sorted = df.sort_values(by=['Nome do Arquivo', 'Pontos'], ascending=[True, False])
        df_final = df_sorted.drop_duplicates(subset=["Nome do Arquivo"], keep="first").copy()
        
        colunas_ordem = ["Nome do Arquivo", "Órgão / Entidade (PDF)", "Documento", "Nome Extraído"]
        cols_to_show = [c for c in colunas_ordem if c in df_final.columns]
        df_final = df_final[cols_to_show]
        
        st.info("Lista refinada e formatada.")
    else:
        df_final = df
        st.warning("Modo bruto (sem filtros).")
    
    st.dataframe(df_final, use_container_width=True)
    
    csv = df_final.to_csv(index=False, sep=";").encode('utf-8-sig')
    st.download_button("📥 Baixar Tabela (CSV)", data=csv, file_name="extracao_nomes_formatados.csv", mime="text/csv")
