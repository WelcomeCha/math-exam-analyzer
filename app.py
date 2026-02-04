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
st.set_page_config(page_title="수학 기출 분석기 (Ultimate Fixed)", layout="wide")

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
    .error-log { color: #d32f2f; font-size: 12px; font-family: monospace; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 고등학교 수학 기출 vs 부교재 분석기 (절댓값 오류 수정판)")

# 2. API 키 설정
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    
    st.divider()
    st.info("🔒 **모델:** Gemini 2.5 Pro")
    st.info("🛡️ **수식 보호:** 절댓값 기호가 표를 깨뜨리지 않도록 LaTeX 처리를 강화했습니다.")
    
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
    st.subheader("📚 부교재 PDF")
    textbook_files = st.file_uploader("부교재들을 한꺼번에 업로드하세요", type=['pdf'], key="textbooks", accept_multiple_files=True)


# --- PDF 자동 분할 및 업로드 함수 ---
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
            progress = min((start_page + chunk_size_pages) / total_pages, 1.0)
            progress_bar.progress(progress)
        except Exception as e:
            st.error(f"업로드 중 오류 발생: {e}")
            return None
            
    status_text.success(f"✅ '{file_label}' 준비 완료!")
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
    st.success("✅ 분석 준비 완료!")

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
        <h1>📊 분석 결과 보고서</h1>
        {html_content}
    </body>
    </html>
    """
    return styled_html

# 4. 분석 로직
if exam_file and textbook_files and api_key:
    if 'full_analysis_result' not in st.session_state:
        st.session_state['full_analysis_result'] = ""

    if st.button("정밀 분석 시작 🚀", use_container_width=True):
        st.session_state['full_analysis_result'] = ""
        
        try:
            # 파일 준비
            exam_ref = upload_single_file(exam_file)
            all_textbook_refs = []
            for t_file in textbook_files:
                refs = split_and_upload_pdf(t_file, t_file.name, chunk_size_pages=30)
                if refs: all_textbook_refs.extend(refs)
            
            if not all_textbook_refs:
                st.error("부교재 처리에 실패했습니다.")
                st.stop()

            all_files_to_wait = [exam_ref] + all_textbook_refs
            wait_for_files_active(all_files_to_wait)

            # 모델 설정
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

            # 문항 리스트
            batches = []
            for i in range(1, 26): batches.append((f"{i}번", f"기출문제의 {i}번 문항만"))
            for i in range(1, 7): batches.append((f"서답형 {i}번", f"기출문제의 서답형 {i}번 문항만"))

            full_accumulated_text = ""
            status_text = st.empty()
            total_progress = st.progress(0)

            for i, (title, range_desc) in enumerate(batches):
                status_text.info(f"🔄 {title} 분석 중... ({i+1}/{len(batches)})")
                
                # --- 🔥 [핵심 수정 1] 절댓값 및 표 깨짐 방지 프롬프트 ---
                prompt_full = f"""
                당신은 수학 분석가입니다.
                첫 번째 PDF는 '기출', 나머지는 '부교재'입니다.
                기출 {range_desc}을 찾아 분석하세요.
                
                **[주의사항 - 엄격 준수]**
                1. **절댓값 기호 주의:** 절댓값 기호('|')는 마크다운 표를 깨뜨립니다. **모든 수식은 반드시 LaTeX($...$) 형식으로 작성**하여 표가 깨지지 않게 하세요. (예: $|x+1|$)
                2. **상세 분석 유지:** '상세 변형 분석' 란은 절대 줄이지 말고, **키워드와 설명**을 풍부하게 작성하세요.
                3. **원문 복원:** 부교재 원문은 수치와 조건을 정확히 복원하여 적으세요. (복사가 안 되면 직접 타이핑하듯 복원)
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {title} | **[원본]**<br>(LaTeX 수식 사용 필수)<br><br>**[요약]**<br>(요약) | **[원본]**<br>(교재명) p.00 000번<br>(LaTeX 수식 사용 필수)<br><br>**[요약]**<br>(요약) | **▶ 변형 포인트**<br>• **키워드**: (상세하게 설명)<br>• **키워드**: (상세하게 설명)<br><br>**▶ 출제 의도**<br>(평가 목표) |
                """

                # --- 🔥 [핵심 수정 2] 재시도 시에도 '상세 분석' 요청 (요약 금지) ---
                prompt_retry = f"""
                위 요청과 동일하게 분석하되, **저작권 필터를 피하기 위해 '문제 원문' 부분만 핵심 조건 위주로 살짝 다듬어서** 적으세요.
                단, **'상세 변형 분석' 내용은 절대 줄이지 말고 길게 작성하세요.**
                
                (절댓값 기호 '|' 사용 시 반드시 $ 기호 안에 넣으세요!)
                """
                
                request_content = [prompt_full, exam_ref] + all_textbook_refs
                
                success = False
                error_log = None
                
                for attempt in range(2):
                    try:
                        # 첫 시도는 정석대로, 실패하면 원문만 살짝 다듬어서(그러나 분석은 길게) 재요청
                        if attempt == 1:
                            request_content[0] = prompt_retry
                        
                        response = model.generate_content(request_content)
                        
                        if response.parts:
                            result_text = response.text
                            # SKIP이면 그냥 넘어감
                            if "SKIP" in result_text:
                                success = True
                                break
                                
                            # 결과 출력
                            if i == 0: st.markdown(f"### 📋 분석 결과")
                            st.markdown(result_text, unsafe_allow_html=True)
                            full_accumulated_text += result_text + "\n\n"
                            success = True
                            break
                        else:
                            finish_reason = response.candidates[0].finish_reason
                            error_log = f"Attempt {attempt+1} Blocked (Reason: {finish_reason})"
                            
                    except Exception as e:
                        error_log = f"Attempt {attempt+1} Error: {str(e)}"
                        time.sleep(1)
                
                if not success:
                    with st.expander(f"⚠️ {title} 분석 실패", expanded=False):
                        st.write("AI가 답변을 생성하지 못했습니다.")
                        st.code(error_log)

                total_progress.progress((i + 1) / len(batches))
                time.sleep(1)

            st.session_state['full_analysis_result'] = full_accumulated_text
            status_text.success("✅ 분석 완료! 절댓값 오류 해결됨.")
            total_progress.empty()

        except Exception as e:
            st.error(f"오류 발생: {e}")

    if st.session_state['full_analysis_result']:
        st.divider()
        html_data = create_html_download(st.session_state['full_analysis_result'])
        st.download_button("📥 HTML 파일로 다운로드", html_data, "수학_정밀_분석_결과.html", "text/html")
