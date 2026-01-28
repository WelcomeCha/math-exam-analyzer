import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import tempfile
import time
import markdown
import pypdf  # 필수: requirements.txt에 pypdf 추가
from dotenv import load_dotenv

# 1. 설정 및 디자인
st.set_page_config(page_title="수학 기출 분석기 (Pro Only)", layout="wide")

st.markdown("""
    <style>
    div[data-testid="stMarkdownContainer"] p, 
    div[data-testid="stMarkdownContainer"] li, 
    div[data-testid="stMarkdownContainer"] td {
        font-size: 15px !important;
        line-height: 1.7 !important;
        font-family: 'Malgun Gothic', sans-serif !important;
    }
    thead tr th {
        background-color: #f0f2f6 !important;
        font-weight: bold !important;
        font-size: 16px !important;
        text-align: center !important;
        white-space: nowrap;
    }
    td { vertical-align: top !important; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 고등학교 수학 기출 vs 부교재 분석기 (2.5 Pro 전용)")

# 2. API 키 설정 (모델 선택창 제거 -> 2.5 Pro 고정)
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    
    st.divider()
    st.info("🔒 **모델 고정:** Gemini 2.5 Pro")
    st.info("ℹ️ **대용량 지원:** 큰 파일은 자동으로 분할하여 2.5 Pro에게 전달합니다.")
    
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        st.success("API 키 확인 완료!")
    else:
        st.warning("API 키를 먼저 입력해주세요.")

# 3. 파일 업로드
col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 학교 기출문제 PDF")
    exam_file = st.file_uploader("기출문제 파일을 업로드하세요", type=['pdf'], key="exam")

with col2:
    st.subheader("📘 부교재 PDF")
    textbook_file = st.file_uploader("부교재 파일을 업로드하세요", type=['pdf'], key="text")


# --- 🔥 PDF 자동 분할 및 업로드 함수 ---
def split_and_upload_pdf(uploaded_file, chunk_size_pages=30):
    """
    2.5 Pro의 안정적인 처리를 위해 PDF를 30페이지씩 잘라서 업로드합니다.
    """
    pdf_reader = pypdf.PdfReader(uploaded_file)
    total_pages = len(pdf_reader.pages)
    
    # 페이지 수가 적으면 분할 없이 바로 업로드
    if total_pages <= chunk_size_pages:
        return [upload_single_file(uploaded_file)]

    status_text = st.empty()
    progress_bar = st.progress(0)
    status_text.info(f"📚 파일이 큽니다({total_pages}쪽). 2.5 Pro가 잘 읽을 수 있도록 {chunk_size_pages}쪽씩 나누어 업로드합니다...")
    
    uploaded_chunks = []
    
    for start_page in range(0, total_pages, chunk_size_pages):
        end_page = min(start_page + chunk_size_pages, total_pages)
        
        pdf_writer = pypdf.PdfWriter()
        for page_num in range(start_page, end_page):
            pdf_writer.add_page(pdf_reader.pages[page_num])
            
        # 분할된 PDF 저장 및 업로드
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_part_{start_page}.pdf") as tmp:
            pdf_writer.write(tmp)
            tmp_path = tmp.name
            
        try:
            file_ref = genai.upload_file(tmp_path, mime_type="application/pdf")
            uploaded_chunks.append(file_ref)
            
            # 진행률 업데이트
            progress = min((start_page + chunk_size_pages) / total_pages, 1.0)
            progress_bar.progress(progress)
            
        except Exception as e:
            st.error(f"업로드 중 오류 발생: {e}")
            return None
            
    status_text.success(f"✅ {len(uploaded_chunks)}개의 파트로 분할 완료! 2.5 Pro에게 전달합니다.")
    time.sleep(1)
    status_text.empty()
    progress_bar.empty()
    
    return uploaded_chunks

def upload_single_file(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    file_ref = genai.upload_file(tmp_path, mime_type="application/pdf")
    return file_ref

def wait_for_files_active(file_list):
    st.info("📚 AI가 파일을 읽고 있습니다...")
    for i, file_obj in enumerate(file_list):
        current_file = genai.get_file(file_obj.name)
        while current_file.state.name == "PROCESSING":
            time.sleep(2)
            current_file = genai.get_file(file_obj.name)
        
        if current_file.state.name == "FAILED":
            st.error(f"❌ 파일 처리 실패: {current_file.uri}")
            st.stop()
            
    st.success("✅ 분석 준비 완료!")

# HTML 변환 함수
def create_html_download(markdown_text):
    html_content = markdown.markdown(markdown_text, extensions=['tables'])
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <script>
        MathJax = {{ tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']] }}, svg: {{ fontCache: 'global' }} }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; padding: 40px; max-width: 1200px; margin: 0 auto; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; }}
            th, td {{ border: 1px solid #ddd; padding: 15px; text-align: left; vertical-align: top; }}
            th {{ background-color: #007bff; color: white; text-align: center; white-space: nowrap; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h1>📊 수학 기출 vs 부교재 정밀 분석 결과</h1>
        {html_content}
    </body>
    </html>
    """
    return styled_html

# 4. 분석 로직
if exam_file and textbook_file and api_key:
    if 'full_analysis_result' not in st.session_state:
        st.session_state['full_analysis_result'] = ""

    if st.button("분석 시작하기 🚀", use_container_width=True):
        st.session_state['full_analysis_result'] = ""
        
        try:
            # 1. 기출문제 업로드
            exam_ref = upload_single_file(exam_file)
            
            # 2. 부교재 분할 업로드 (30페이지씩)
            textbook_refs = split_and_upload_pdf(textbook_file, chunk_size_pages=30)
            
            if not textbook_refs:
                st.stop()

            # 3. 모든 파일 대기
            all_files = [exam_ref] + textbook_refs
            wait_for_files_active(all_files)

            # 4. 모델 설정 (무조건 2.5 Pro 사용)
            model = genai.GenerativeModel(
                "gemini-2.5-pro",  # 사용자 요청대로 2.5 Pro 고정
                generation_config={"temperature": 0.0, "max_output_tokens": 8192},
                safety_settings={
                    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                }
            )

            # 5. 분석 배치 실행
            batches = [
                ("1번 ~ 3번", "기출문제의 1번부터 3번 문항까지만"),
                ("4번 ~ 6번", "기출문제의 4번부터 6번 문항까지만"),
                ("7번 ~ 9번", "기출문제의 7번부터 9번 문항까지만"),
                ("10번 ~ 12번", "기출문제의 10번부터 12번 문항까지만"),
                ("13번 ~ 15번", "기출문제의 13번부터 15번 문항까지만"),
                ("16번 ~ 18번", "기출문제의 16번부터 18번 문항까지만"),
                ("19번 ~ 21번", "기출문제의 19번부터 21번 문항까지만"),
                ("22번 ~ 마지막", "기출문제의 22번부터 서술형 끝번(마지막) 문항까지")
            ]

            full_accumulated_text = ""
            status_text = st.empty()

            for i, (title, range_desc) in enumerate(batches):
                status_text.info(f"🔄 {title} 분석 중... ({i+1}/{len(batches)})")
                
                if i > 0: st.markdown("---")
                st.markdown(f"### 📋 {title}")
                full_accumulated_text += f"\n\n### 📋 {title}\n\n"
                placeholder = st.empty()
                
                # 프롬프트: 분할된 부교재를 하나로 인식하라고 지시
                prompt = f"""
                당신은 수학 분석 전문가입니다.
                첫 번째 PDF는 '기출문제'이고, 나머지 파일들은 '부교재'를 분할하여 업로드한 것입니다.
                나머지 파일들을 **모두 합쳐서 하나의 부교재**로 인식하고 분석하세요.
                
                두 자료를 비교하여 **{range_desc}** 상세 분석하세요.
                
                **[출력 서식 가이드라인 - 엄격 준수]**
                1. **부교재 문항 표기:** - 첫 줄: **`p.페이지번호 문항번호`** (예: p.80 285번)
                   - 두 번째 줄부터: **[원본]** 태그 아래에 **부교재 문제 원문을 반드시 텍스트로 적으세요.**
                
                2. **변형 포인트 표기:** - 반드시 **글머리 기호(•)**를 사용하고, 키워드는 굵게 처리하세요.
                
                **[필수 테이블 양식]**
                **반드시 표 앞에 빈 줄을 하나 띄우고 표를 작성하세요.**
                
                | 문항 | 기출문제 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | (번호) | **[원본]**<br>(기출 문제 텍스트)<br><br>**[요약]**<br>(핵심 요약) | **[원본]**<br>p.00 000번<br>(부교재 문제 원문 텍스트 필수 기재)<br><br>**[요약]**<br>(내용 요약) | **▶ 변형 포인트**<br>• **키워드**: 설명<br>• **키워드**: 설명<br><br>**▶ 출제 의도**<br>(평가 목표) |
                """
                
                # 🔥 [핵심] 2.5 Pro에게 모든 파일 조각을 다 던져줌
                request_content = [prompt, exam_ref] + textbook_refs
                
                chunk_text = ""
                try:
                    stream = model.generate_content(request_content, stream=True)
                    for chunk in stream:
                        if chunk.text:
                            chunk_text += chunk.text
                            placeholder.markdown(chunk_text, unsafe_allow_html=True)
                except Exception as e:
                    # 400 에러 처리 (2.5 Pro 용량 초과 시)
                    if "400" in str(e):
                        st.error("🚨 2.5 Pro 모델의 처리 한도를 초과했습니다.")
                        st.warning("분석 범위를 더 좁히거나(예: 2문제씩), 부교재 파일의 페이지를 조금 더 줄여야 할 수 있습니다.")
                        st.stop()
                    else:
                        st.error(f"오류 발생: {e}")
                
                full_accumulated_text += chunk_text + "\n\n"

            st.session_state['full_analysis_result'] = full_accumulated_text
            status_text.success("✅ 분석 완료! 아래 버튼을 눌러 저장하세요.")

        except Exception as e:
            st.error(f"초기화 중 오류 발생: {e}")

    # 다운로드 버튼
    if st.session_state['full_analysis_result']:
        st.divider()
        html_data = create_html_download(st.session_state['full_analysis_result'])
        st.download_button("📥 HTML 파일로 다운로드", html_data, "수학_기출_분석_결과.html", "text/html")
