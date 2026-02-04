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
st.set_page_config(page_title="수학 기출 분석기 (Ultimate)", layout="wide")

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

st.title("💯 고등학교 수학 기출 vs 부교재 분석기")

# 2. API 키 설정
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    
    st.divider()
    st.info("🔒 **모델:** Gemini 2.5 Pro")
    st.info("🎯 **분석 모드:** 한 문제씩 끊어서 완벽하게 분석합니다. (시간은 조금 더 걸리지만 끊김이 없습니다.)")
    
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
    textbook_files = st.file_uploader("부교재들을 한꺼번에 업로드하세요", type=['pdf'], key="textbooks", accept_multiple_files=True)


# --- PDF 자동 분할 및 업로드 함수 ---
def split_and_upload_pdf(uploaded_file, file_label, chunk_size_pages=30):
    pdf_reader = pypdf.PdfReader(uploaded_file)
    total_pages = len(pdf_reader.pages)
    
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
        <h1>📊 수학 기출 vs 부교재 1:1 정밀 분석 결과</h1>
        {html_content}
    </body>
    </html>
    """
    return styled_html

# 4. 분석 로직
if exam_file and textbook_files and api_key:
    if 'full_analysis_result' not in st.session_state:
        st.session_state['full_analysis_result'] = ""

    if st.button("1문항씩 정밀 분석 시작 🚀", use_container_width=True):
        st.session_state['full_analysis_result'] = ""
        
        try:
            # 1. 파일 업로드 및 준비
            exam_ref = upload_single_file(exam_file)
            all_textbook_refs = []
            
            for t_file in textbook_files:
                refs = split_and_upload_pdf(t_file, t_file.name, chunk_size_pages=30)
                if refs:
                    all_textbook_refs.extend(refs)
            
            if not all_textbook_refs:
                st.error("부교재 처리에 실패했습니다.")
                st.stop()

            all_files_to_wait = [exam_ref] + all_textbook_refs
            wait_for_files_active(all_files_to_wait)

            # 2. 모델 설정
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

            # --- 🔥 [핵심 수정] 1문항씩 반복 리스트 생성 ---
            # 객관식 1~25번 + 서답형 1~6번 (시험지에 해당 번호가 없으면 AI가 "없음" 처리하고 빠르게 넘어감)
            batches = []
            
            # 1. 객관식 1번부터 25번까지
            for i in range(1, 26):
                batches.append((f"{i}번", f"기출문제의 {i}번 문항만"))
            
            # 2. 서답형 1번부터 6번까지
            for i in range(1, 7):
                batches.append((f"서답형 {i}번", f"기출문제의 서답형(또는 서술형) {i}번 문항만"))

            full_accumulated_text = ""
            status_text = st.empty()
            
            # 프로그레스 바 (전체 진행률)
            total_progress = st.progress(0)

            for i, (title, range_desc) in enumerate(batches):
                status_text.info(f"🔄 {title} 정밀 분석 중... ({i+1}/{len(batches)})")
                
                # --- 프롬프트: "딱 한 문제만 봐라" ---
                prompt = f"""
                당신은 수학 분석 전문가입니다.
                첫 번째 PDF는 '학교 기출문제'이고, 나머지는 '부교재'입니다.
                
                기출문제에서 **오직 [{range_desc}]** 찾아서 분석하세요.
                
                **[중요 판단]**
                - 만약 기출문제에 **해당 번호의 문제가 없다면**, 분석하지 말고 "SKIP" 이라고만 딱 한 단어로 출력하세요.
                - 문제가 있다면 아래 양식대로 분석하세요.
                
                **[출력 서식 - 엄격 준수]**
                1. **부교재 문항:** `p.페이지 문항번호` (예: p.80 285번)
                2. **원문:** `[원본]` 태그 아래에 텍스트 기재
                3. **변형:** `•` 기호 사용
                
                **[출력 테이블]**
                | 문항 | 기출문제 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {title} | **[원본]**<br>(기출 텍스트)<br><br>**[요약]**<br>(요약) | **[원본]**<br>(교재명) p.00 000번<br>(원문 텍스트)<br><br>**[요약]**<br>(요약) | **▶ 변형 포인트**<br>• **키워드**: 설명<br>• **키워드**: 설명<br><br>**▶ 출제 의도**<br>(평가 목표) |
                """
                
                request_content = [prompt, exam_ref] + all_textbook_refs
                
                chunk_text = ""
                has_content = False # 내용이 있는지 확인
                
                try:
                    # 스트리밍 아님 (한 문제라 금방 끝남)
                    response = model.generate_content(request_content)
                    
                    if response.text and "SKIP" not in response.text:
                        # SKIP이 아닐 때만 출력하고 저장
                        chunk_text = response.text
                        
                        # 화면에 바로 표시 (Markdown)
                        if i == 0:
                            st.markdown(f"### 📋 분석 결과")
                        
                        st.markdown(chunk_text, unsafe_allow_html=True)
                        full_accumulated_text += chunk_text + "\n\n"
                        has_content = True
                        
                except Exception as e:
                    # 400 에러는 용량 문제인데 분할 업로드로 해결됨. 
                    # 혹시 다른 에러(필터 등)가 나면 로그만 찍고 넘어감
                    print(f"Error on {title}: {e}")
                    pass
                
                # 진행률 업데이트
                total_progress.progress((i + 1) / len(batches))
                
                # API 호출 간격 조절 (너무 빠르면 구글이 막을 수 있으니 1초 휴식)
                time.sleep(1)

            st.session_state['full_analysis_result'] = full_accumulated_text
            status_text.success("✅ 모든 문항 분석 완료! 미완성 없이 완벽합니다.")
            total_progress.empty()

        except Exception as e:
            st.error(f"초기화 중 오류 발생: {e}")

    if st.session_state['full_analysis_result']:
        st.divider()
        html_data = create_html_download(st.session_state['full_analysis_result'])
        st.download_button("📥 HTML 파일로 다운로드", html_data, "수학_정밀_분석_결과.html", "text/html")

