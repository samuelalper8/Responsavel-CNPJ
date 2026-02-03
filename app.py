import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import re
from io import BytesIO

# Configuração da página
st.set_page_config(page_title="Extrator de Responsáveis - RFB", layout="wide")

def clean_text(text):
    """Limpa espaços extras e quebras de linha."""
    if not text:
        return ""
    return " ".join(text.split()).strip()

def extract_info_from_pdf(pdf_bytes, file_name):
    """
    Lê o PDF e tenta extrair pares de CNPJ + Nome do Responsável.
    Baseado na estrutura do Relatorio_Consolidado_GERAL.pdf
    """
    data = []
    
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        st.error(f"Erro ao ler {file_name}: {e}")
        return []

    # Iterar por todas as páginas
    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        lines = text.split('\n')
        
        # Variáveis temporárias para capturar o contexto do bloco atual
        current_cnpj = None
        current_ente = None
        
        # Iterar linhas para buscar padrões
        for i, line in enumerate(lines):
            line = line.strip()
            
            # 1. Captura CNPJ e Nome do Ente (Geralmente na mesma linha ou próxima)
            # Ex: CNPJ: 00.000.000/0000-00 NOME DO MUNICIPIO
            if "CNPJ:" in line:
                cnpj_match = re.search(r'(\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2})', line)
                if cnpj_match:
                    current_cnpj = cnpj_match.group(1)
                    # Tenta pegar o nome do Ente na mesma linha, após o CNPJ
                    parts = line.split(current_cnpj)
                    if len(parts) > 1:
                        possible_name = clean_text(parts[1].replace("-", "").strip())
                        if len(possible_name) > 3:
                            current_ente = possible_name

            # 2. Captura o Responsável
            # Padrão observado: "Responsável: [CPF]" e o nome está logo abaixo ou ao lado
            if "Responsável:" in line:
                # Se tivermos um CNPJ ativo no contexto recente, vinculamos
                if current_cnpj:
                    cpf_match = re.search(r'(\d{3}\.\d{3}\.\d{3}-\d{2})', line)
                    cpf_responsavel = cpf_match.group(1) if cpf_match else "CPF não identificado"
                    
                    # O nome do responsável costuma estar na linha SEGUINTE ou algumas linhas abaixo
                    nome_responsavel = "Não encontrado"
                    
                    # Olhar as próximas 3 linhas para achar o nome (que não seja rótulo)
                    for j in range(1, 4):
                        if i + j < len(lines):
                            next_line = clean_text(lines[i+j])
                            # Ignorar linhas de sistema/rótulos
                            if not next_line or "Situação:" in next_line or "CNPJ:" in next_line or "PAGE" in next_line:
                                continue
                            
                            # Se a linha parecer um nome (apenas letras e espaços, tamanho razoável)
                            if re.search(r'[a-zA-Z]{3,}', next_line):
                                nome_responsavel = next_line
                                break
                    
                    data.append({
                        "Arquivo": file_name,
                        "CNPJ": current_cnpj,
                        "Ente / Razão Social": current_ente if current_ente else "Não identificado",
                        "CPF Responsável": cpf_responsavel,
                        "Nome Responsável": nome_responsavel
                    })
                    
                    # Limpa contexto para evitar duplicar o mesmo responsável para o próximo CNPJ erradamente
                    # (embora em alguns relatórios o CNPJ venha depois, ajuste conforme necessário)
                    # current_cnpj = None 

    return data

# --- Interface Streamlit ---
st.title("📂 Extrator de Responsáveis - Relatórios RFB/PGFN")
st.markdown("""
Esta ferramenta extrai o **Nome do Responsável** e **CPF** vinculados aos CNPJs encontrados nos relatórios de restrições (PDF).
""")

uploaded_files = st.file_uploader(
    "Arraste seus PDFs aqui (suporta múltiplos arquivos)", 
    type=["pdf"], 
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Processar Arquivos"):
        all_results = []
        progress_bar = st.progress(0)
        
        for idx, uploaded_file in enumerate(uploaded_files):
            # Ler bytes do arquivo
            bytes_data = uploaded_file.read()
            # Extrair informações
            extracted_data = extract_info_from_pdf(bytes_data, uploaded_file.name)
            all_results.extend(extracted_data)
            # Atualizar barra
            progress_bar.progress((idx + 1) / len(uploaded_files))
            
        progress_bar.empty()

        if all_results:
            df = pd.DataFrame(all_results)
            
            # Remover duplicatas exatas se houver
            df = df.drop_duplicates()
            
            st.success(f"Sucesso! {len(df)} registros encontrados.")
            
            # Exibir tabela interativa
            st.dataframe(df, use_container_width=True)
            
            # Converter para CSV/Excel para download
            csv = df.to_csv(index=False, sep=";").encode('utf-8-sig')
            
            c1, c2 = st.columns(2)
            with c1:
                st.download_button(
                    label="📥 Baixar como CSV (Excel)",
                    data=csv,
                    file_name="responsaveis_extraidos.csv",
                    mime="text/csv",
                )
        else:
            st.warning("Nenhum responsável foi identificado nos PDFs enviados. Verifique se o formato do arquivo corresponde ao padrão RFB/PGFN.")
