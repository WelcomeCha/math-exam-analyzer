import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import tempfile
import time
import markdown
import pypdf
from dotenv import load_dotenv

# 1. 설정 및 디자인
st.set_page_config(page_title="수학 기출 분석기 (Multi-Source)", layout="wide")

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

st.title("💯 고등학교 수학 기출 vs N권의 부교재 통합 분석기")

# 2. API 키 설정
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    
    st.divider()
    st.info("🔒 **모델:** Gemini 2.5 Pro")
    st.info("📚 **다중 분석:** 여러 권의 부교재를 한 번에 업로드하여 분석할 수 있습니다.")
    
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
    st.subheader("📚 부교재 PDF (여러 개 선택 가능)")
    # accept_multiple_files=True 설정으로 여러 파일 업로드 가능
    textbook_files = st.file_uploader("부교재들을 한꺼번에 업로드하세요", type=['pdf'], key="textbooks", accept_multiple_files=True)


# --- 🔥 PDF 자동 분할 및 업로드 함수 ---
def split_and_upload_pdf(uploaded_file, file_label, chunk_size_pages=30):
    """
    PDF를 30페이지씩 잘라서 업로드합니다.
    """
    pdf_reader = pypdf.PdfReader(uploaded_file)
    total_pages = len(pdf_reader.pages)
    
    # 페이지 수가 적으면 분할 없이 바로 업로드
    if total_pages <= chunk_size_pages:
        return [upload_single_file(uploaded_file)]

    status_text = st.empty()
    progress_bar = st.progress(0)
    status_text.info(f"📖 '{file_label}' 파일이 큽니다({total_pages}쪽). 분할 업로드 중...")
    
    uploaded_chunks = []
    
    for start_page in range(0, total_pages, chunk_size_pages):
        end_page = min(start_page + chunk_size_pages, total_pages)
        
        pdf_writer = pypdf.PdfWriter()
        for page_num in range(start_page, end_page):
            pdf_writer.add_page(pdf_reader.pages[page_num])
            
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_part_{start_page}.pdf") as tmp:
            pdf_writer.write(tmp)
            tmp_path = tmp.name
            
        try:
            file_ref = genai.upload_file(tmp_path, mime_type="application/pdf")
            uploaded_chunks.append(file_ref)
            
            progress = min((start_page + chunk_size_pages) / total_pages, 1.0)
            progress_bar.progress(progress)
            
        except Exception as e:
            st.error(f"업로드 중 오류 발생: {e}")
            return None
            
    status_text.success(f"✅ '{file_label}' 업로드 완료!")
    time.sleep(0.5)
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
    st.info("📚 AI가 모든 자료를 학습하고 있습니다... (잠시만 기다려주세요)")
    my_bar = st.progress(0)
    for i, file_obj in enumerate(file_list):
        current_file = genai.get_file(file_obj.name)
        while current_file.state.name == "PROCESSING":
            time.sleep(2)
            current_file = genai.get_file(file_obj.name)
        
        if current_file.state.name == "FAILED":
            st.error(f"❌ 파일 처리 실패: {current_file.uri}")
            st.stop()
        my_bar.progress((i + 1) / len(file_list))
            
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
        <h1>📊 수학 기출 vs 부교재 통합 정밀 분석 결과</h1>
        {html_content}
    </body>
    </html>
    """
    return styled_html

# 4. 분석 로직
if exam_file and textbook_files and api_key:
    if 'full_analysis_result' not in st.session_state:
        st.session_state['full_analysis_result'] = ""

    # 버튼 클릭 시 분석 시작
    if st.button("통합 분석 시작하기 🚀", use_container_width=True):
        st.session_state['full_analysis_result'] = ""
        
        try:
            # 1. 기출문제 업로드
            exam_ref = upload_single_file(exam_file)
            
            # 2. 여러 부교재 파일 순차적으로 처리
            all_textbook_refs = []
            
            # 업로드된 파일 리스트를 하나씩 돌면서 처리
            for t_file in textbook_files:
                # 각 파일을 자동 분할해서 업로드 (파일명도 인자로 전달)
                refs = split_and_upload_pdf(t_file, t_file.name, chunk_size_pages=30)
                if refs:
                    all_textbook_refs.extend(refs)
            
            if not all_textbook_refs:
                st.error("부교재 처리에 실패했습니다.")
                st.stop()

            # 3. 모든 파일 대기 (기출 + 모든 부교재 조각들)
            all_files_to_wait = [exam_ref] + all_textbook_refs
            wait_for_files_active(all_files_to_wait)

            # 4. 모델 설정 (2.5 Pro)
            model = genai.GenerativeModel(
                "gemini-2.5-pro",
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
                
                # 프롬프트: 여러 권의 부교재임을 명시
                prompt = f"""
                당신은 수학 분석 전문가입니다.
                첫 번째 PDF는 '학교 기출문제'입니다.
                나머지 모든 PDF 파일들은 **여러 권의 부교재(교과서, EBS, 프린트물 등)를 합친 자료**입니다.
                
                기출문제의 **{range_desc}** 분석하여, 업로드된 부교재 자료들 중 가장 유사한 문항을 찾아 비교하세요.
                
                **[출력 서식 가이드라인 - 엄격 준수]**
                1. **부교재 문항 표기:** - 첫 줄: **`p.페이지번호 문항번호`** (어떤 교재인지 알 수 있다면 교재명도 간단히 적으세요. 예: 올림포스 p.80 285번)
                   - 두 번째 줄: **[원본]** 태그 아래에 **문제 원문을 반드시 텍스트로 적으세요.**
                
                2. **변형 포인트 표기:** - 반드시 **글머리 기호(•)**를 사용하고, 키워드는 굵게 처리하세요.
                
                **[필수 테이블 양식]**
                **반드시 표 앞에 빈 줄을 하나 띄우고 표를 작성하세요.**
                
                | 문항 | 기출문제 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | (번호) | **[원본]**<br>(문제 텍스트)<br><br>**[요약]**<br>(요약) | **[원본]**<br>(교재명) p.00 000번<br>(원문 텍스트)<br><br>**[요약]**<br>(요약) | **▶ 변형 포인트**<br>• **키워드**: 설명<br>• **키워드**: 설명<br><br>**▶ 출제 의도**<br>(평가 목표) |
                """
                
                # 🔥 [핵심] 기출문제 + 모든 부교재 파일 리스트 전송
                request_content = [prompt, exam_ref] + all_textbook_refs
                
                chunk_text = ""
                try:
                    stream = model.generate_content(request_content, stream=True)
                    for chunk in stream:
                        if chunk.text:
                            chunk_text += chunk.text
                            placeholder.markdown(chunk_text, unsafe_allow_html=True)
                except Exception as e:
                    if "400" in str(e):
                        st.error("🚨 2.5 Pro 모델 처리 용량 초과. 파일이 너무 많거나 큽니다.")
                        st.stop()
                    else:
                        st.error(f"오류 발생: {e}")
                
                full_accumulated_text += chunk_text + "\n\n"

            st.session_state['full_analysis_result'] = full_accumulated_text
            status_text.success("✅ 통합 분석 완료! 아래 버튼을 눌러 저장하세요.")

        except Exception as e:
            st.error(f"초기화 중 오류 발생: {e}")

    # 다운로드 버튼
    if st.session_state['full_analysis_result']:
        st.divider()
        html_data = create_html_download(st.session_state['full_analysis_result'])
        st.download_button("📥 HTML 파일로 다운로드", html_data, "수학_통합_분석_결과.html", "text/html")
