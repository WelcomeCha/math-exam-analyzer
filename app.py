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
st.set_page_config(page_title="수학 기출 분석기 (Zombie Mode)", layout="wide")

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
    .stButton>button { width: 100%; border-radius: 5px; font-weight: bold; }
    .success-log { color: #2e7d32; font-size: 12px; }
    .error-log { color: #d32f2f; font-size: 12px; font-family: monospace; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 고등학교 수학 기출 vs 부교재 분석기 (이어하기 기능)")

# 2. 세션 상태 초기화 (자동 저장을 위해 필수)
if 'analysis_history' not in st.session_state:
    st.session_state['analysis_history'] = [] # 분석된 텍스트 조각들을 저장하는 리스트
if 'last_index' not in st.session_state:
    st.session_state['last_index'] = 0 # 마지막으로 분석한 문항 번호

# 3. API 키 설정
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    
    st.divider()
    st.info("🔒 **모델:** Gemini 2.5 Pro")
    st.info("💾 **자동 저장:** 한 문제 끝날 때마다 저장됩니다.")
    st.info("⏯️ **이어하기:** 중간에 멈추면 '이어하기' 버튼이 나타납니다.")
    
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        st.success("API 키 확인 완료!")
    else:
        st.warning("API 키를 먼저 입력해주세요.")

# 4. 파일 업로드
col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 학교 기출문제 PDF")
    exam_file = st.file_uploader("기출문제 파일을 업로드하세요", type=['pdf'], key="exam")

with col2:
    st.subheader("📚 부교재 PDF")
    textbook_files = st.file_uploader("부교재들을 한꺼번에 업로드하세요", type=['pdf'], key="textbooks", accept_multiple_files=True)


# --- 함수 정의 ---
def upload_single_file(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    file_ref = genai.upload_file(tmp_path, mime_type="application/pdf")
    return file_ref

def split_and_upload_pdf(uploaded_file, file_label, chunk_size_pages=30):
    pdf_reader = pypdf.PdfReader(uploaded_file)
    total_pages = len(pdf_reader.pages)
    
    if total_pages <= chunk_size_pages:
        return [upload_single_file(uploaded_file)]

    status_text = st.empty()
    progress_bar = st.progress(0)
    status_text.info(f"📖 '{file_label}' 분할 업로드 중... ({total_pages}쪽)")
    
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
            progress_bar.progress(min((start_page + chunk_size_pages) / total_pages, 1.0))
        except Exception as e:
            st.error(f"업로드 오류: {e}")
            return None
    status_text.empty()
    progress_bar.empty()
    return uploaded_chunks

def wait_for_files_active(file_list):
    st.info("📚 AI가 자료를 읽고 있습니다...")
    my_bar = st.progress(0)
    for i, file_obj in enumerate(file_list):
        current_file = genai.get_file(file_obj.name)
        while current_file.state.name == "PROCESSING":
            time.sleep(1)
            current_file = genai.get_file(file_obj.name)
        if current_file.state.name == "FAILED":
            st.error(f"❌ 파일 처리 실패: {current_file.uri}")
            st.stop()
        my_bar.progress((i + 1) / len(file_list))
    st.success("✅ 준비 완료!")
    time.sleep(1)
    st.empty() # 메시지 지우기

def create_html_download(text_list):
    full_text = "\n\n".join(text_list)
    html_content = markdown.markdown(full_text, extensions=['tables'])
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
        <h1>📊 분석 결과 보고서</h1>
        {html_content}
    </body>
    </html>
    """
    return styled_html

# 5. 분석 로직 제어
if exam_file and textbook_files and api_key:
    
    # 문항 리스트 생성
    batches = []
    for i in range(1, 26): batches.append((f"{i}번", f"기출문제의 {i}번 문항만"))
    for i in range(1, 7): batches.append((f"서답형 {i}번", f"기출문제의 서답형 {i}번 문항만"))
    
    # --- 🔥 버튼 영역 (이어하기 기능) ---
    col_btn1, col_btn2 = st.columns(2)
    
    start_new = col_btn1.button("🚀 처음부터 시작")
    resume = False
    
    # 이미 분석한 내용이 있으면 '이어하기' 버튼 활성화
    if st.session_state['last_index'] > 0 and st.session_state['last_index'] < len(batches):
        resume = col_btn2.button(f"⏯️ {batches[st.session_state['last_index']][0]}부터 이어하기")

    # 실행 플래그
    run_analysis = False
    start_index = 0

    if start_new:
        st.session_state['analysis_history'] = []
        st.session_state['last_index'] = 0
        run_analysis = True
        start_index = 0
    elif resume:
        run_analysis = True
        start_index = st.session_state['last_index']
    
    # --- 분석 시작 ---
    if run_analysis:
        try:
            # 파일 준비 (이미 준비됐으면 생략하면 좋겠지만, Streamlit 특성상 매번 객체는 다시 만들어야 함)
            # 단, 시간 절약을 위해 메시지는 최소화
            exam_ref = upload_single_file(exam_file)
            all_textbook_refs = []
            for t_file in textbook_files:
                refs = split_and_upload_pdf(t_file, t_file.name, chunk_size_pages=30)
                if refs: all_textbook_refs.extend(refs)
            
            wait_for_files_active([exam_ref] + all_textbook_refs)

            model = genai.GenerativeModel(
                "gemini-2.5-pro",
                generation_config={"temperature": 0.0, "max_output_tokens": 8192},
                safety_settings={HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE}
            )

            status_text = st.empty()
            total_progress = st.progress(start_index / len(batches))
            
            # --- 🔥 분석 루프 (이어하기 지점부터 시작) ---
            for i in range(start_index, len(batches)):
                title, range_desc = batches[i]
                status_text.info(f"🔄 {title} 분석 중... ({i+1}/{len(batches)})")
                
                # 프롬프트 (절댓값 깨짐 방지 포함)
                prompt = f"""
                당신은 수학 분석가입니다.
                기출 {range_desc}을 찾아 부교재와 비교 분석하세요.
                
                **[절대 준수]**
                1. **절댓값 기호(|) 사용 금지**: 표가 깨집니다. 반드시 LaTeX 명령어 **`\\lvert`**, **`\\rvert`**를 사용하세요.
                2. **부교재 원문 복원**: 저작권 문제 없이 핵심 수치와 조건 위주로 원문을 복원하여 적으세요.
                3. **문제 없음**: "SKIP" 출력.
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {title} | **[원본]**<br>(LaTeX 수식 필수)<br><br>**[요약]**<br>(요약) | **[원본]**<br>p.00 000번<br>(LaTeX 수식 필수)<br><br>**[요약]**<br>(요약) | **▶ 변형 포인트**<br>• **키워드**: 설명 |
                """
                
                request_content = [prompt, exam_ref] + all_textbook_refs
                
                success = False
                for attempt in range(2):
                    try:
                        response = model.generate_content(request_content)
                        if response.text:
                            result_text = response.text
                            if "SKIP" in result_text:
                                success = True
                                break
                            
                            # --- 🔥 [핵심] 결과가 나오자마자 세션에 저장 ---
                            st.session_state['analysis_history'].append(result_text)
                            st.session_state['last_index'] = i + 1 # 다음 번호 저장
                            success = True
                            break
                    except Exception:
                        time.sleep(1)
                
                if not success:
                    st.warning(f"⚠️ {title} 분석 실패 (건너뜀)")
                    st.session_state['last_index'] = i + 1 # 실패해도 다음으로 넘어가게 저장

                total_progress.progress((i + 1) / len(batches))
                time.sleep(1) # 과부하 방지

            status_text.success("✅ 모든 분석이 완료되었습니다!")
            total_progress.empty()

        except Exception as e:
            st.error(f"오류 발생: {e}")

    # --- 결과 표시 및 다운로드 (항상 표시) ---
    if st.session_state['analysis_history']:
        st.divider()
        st.subheader(f"📊 분석 결과 ({len(st.session_state['analysis_history'])}건)")
        
        # 지금까지 저장된 결과 보여주기
        for res in st.session_state['analysis_history']:
            st.markdown(res, unsafe_allow_html=True)
            st.markdown("---")
            
        # 다운로드 버튼
        html_data = create_html_download(st.session_state['analysis_history'])
        st.download_button("📥 HTML 파일로 다운로드", html_data, "수학_정밀_분석_결과.html", "text/html")
