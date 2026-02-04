import streamlit as st
import google.generativeai as genai
from google.generativeai import caching
import os
import tempfile
import time
import markdown
import pypdf
import datetime
import json
import re

# 1. 설정 및 스타일링
st.set_page_config(page_title="수학 기출 분석기 (Auto Sort)", layout="wide")
st.markdown("""
    <style>
    div[data-testid="stMarkdownContainer"] p, td, th { 
        font-family: 'Malgun Gothic', sans-serif !important; 
        font-size: 15px !important;
        line-height: 1.6 !important;
    }
    table {
        width: 100% !important;
        table-layout: fixed !important;
        border-collapse: collapse !important;
    }
    th, td {
        border: 1px solid #ddd !important;
        padding: 12px !important;
        vertical-align: top !important;
        word-wrap: break-word !important;
    }
    th:nth-child(1) { width: 8% !important; }
    th:nth-child(2) { width: 30% !important; }
    th:nth-child(3) { width: 31% !important; }
    th:nth-child(4) { width: 31% !important; }
    th { background-color: #007bff !important; color: white !important; text-align: center !important; }
    
    .token-info {
        font-size: 12px;
        color: #666;
        background-color: #f8f9fa;
        padding: 5px 10px;
        border-radius: 5px;
        border: 1px solid #eee;
        margin-bottom: 10px;
    }
    .token-cached { color: #2e7d32; font-weight: bold; }
    .token-new { color: #d32f2f; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 수학 기출 분석기 (번호 자동 정렬)")

# 2. 세션 초기화
if 'analysis_history' not in st.session_state:
    st.session_state['analysis_history'] = []
if 'question_list' not in st.session_state:
    st.session_state['question_list'] = [] 
if 'last_index' not in st.session_state:
    st.session_state['last_index'] = 0
if 'cache_name' not in st.session_state:
    st.session_state['cache_name'] = None

# 3. API 키
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key", type="password")
    st.divider()
    st.info("🔒 **모델:** gemini-2.5-pro")
    st.info("🔢 **정렬:** 문항 번호를 인식하여 자동으로 오름차순(1->2->서답1) 정렬합니다.")
    
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)

# 4. 파일 업로드
col1, col2 = st.columns(2)
with col1:
    exam_file = st.file_uploader("기출 PDF", type=['pdf'])
with col2:
    textbook_files = st.file_uploader("부교재 PDF (다중)", type=['pdf'], accept_multiple_files=True)

# --- 함수 정의 ---

def split_and_upload_pdf(uploaded_file, chunk_size_pages=30):
    pdf_reader = pypdf.PdfReader(uploaded_file)
    total_pages = len(pdf_reader.pages)
    
    if total_pages <= chunk_size_pages:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        return [genai.upload_file(tmp_path, mime_type="application/pdf")]

    status = st.empty()
    status.info(f"🔪 분할 업로드 중... ({uploaded_file.name})")
    
    uploaded_chunks = []
    for start in range(0, total_pages, chunk_size_pages):
        end = min(start + chunk_size_pages, total_pages)
        pdf_writer = pypdf.PdfWriter()
        for p in range(start, end):
            pdf_writer.add_page(pdf_reader.pages[p])
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_part_{start}.pdf") as tmp:
            pdf_writer.write(tmp)
            tmp_path = tmp.name
        try:
            uploaded_chunks.append(genai.upload_file(tmp_path, mime_type="application/pdf"))
        except Exception as e:
            st.error(f"업로드 오류: {e}")
            return None
    status.empty()
    return uploaded_chunks

def wait_for_files_active(files):
    status = st.empty()
    for f in files:
        file_obj = genai.get_file(f.name)
        while file_obj.state.name == "PROCESSING":
            status.info(f"⏳ 서버 처리 대기 중... {file_obj.display_name}")
            time.sleep(2)
            file_obj = genai.get_file(f.name)
        if file_obj.state.name != "ACTIVE":
            st.error("파일 처리 실패. 다시 시도해주세요.")
            st.stop()
    status.empty()

# 🔥 [핵심 기능] 문항 리스트 강제 정렬 함수
def sort_question_list(q_list):
    def sort_key(x):
        # 1. 숫자만 있는 경우 (객관식) -> 우선순위 0
        if str(x).isdigit():
            return (0, int(x))
        
        # 2. 텍스트가 섞인 경우 (서답형 등) -> 우선순위 1
        # 정규식으로 숫자만 추출해서 서브 정렬
        num_match = re.search(r'\d+', str(x))
        num = int(num_match.group()) if num_match else 999
        return (1, num)
    
    return sorted(q_list, key=sort_key)

def scan_exam_structure(model):
    """시험지 문항 번호 자동 파악"""
    prompt = """
    이 시험지 PDF 전체를 훑어보고 **모든 문제 번호**를 빠짐없이 리스트로 뽑아라.
    
    **[규칙]**
    1. 객관식은 숫자만 (예: "1", "2", ... "18")
    2. 서술형은 표기 그대로 (예: "[서답형 1]", "주관식 1")
    **[출력]** Python List JSON 형식만 (예: ["1", "2", "[서답형 1]"])
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            raw_list = json.loads(json_match.group())
            # 🔥 여기서 강제 정렬 실행
            return sort_question_list(raw_list)
        else:
            return []
    except:
        return []

def create_html(text_list):
    full_text = "\n\n".join(text_list)
    html_body = markdown.markdown(full_text, extensions=['tables'])
    return f"""
    <html><head><meta charset="utf-8">
    <script>MathJax={{tex:{{inlineMath:[['$','$']],displayMath:[['$$','$$']]}},svg:{{fontCache:'global'}} }};</script>
    <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        body {{ font-family: 'Malgun Gothic', sans-serif; padding: 40px; line-height: 1.6; max-width: 1400px; margin: 0 auto; }}
        table {{ border-collapse: collapse; width: 100%; table-layout: fixed; margin-bottom: 30px; }}
        th, td {{ border: 1px solid #ddd; padding: 15px; vertical-align: top; word-wrap: break-word; }}
        th {{ background: #007bff; color: white; text-align: center; }}
        th:nth-child(1) {{ width: 8%; }} th:nth-child(2) {{ width: 30%; }}
        th:nth-child(3) {{ width: 31%; }} th:nth-child(4) {{ width: 31%; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
    </style></head><body>{html_body}</body></html>
    """

# 5. 메인 로직
if exam_file and textbook_files and api_key:
    c1, c2 = st.columns(2)
    start_btn = c1.button("🚀 구조 파악 & 분석 시작")
    resume_btn = False
    
    if st.session_state['question_list'] and st.session_state['last_index'] < len(st.session_state['question_list']):
        resume_btn = c2.button("⏯️ 이어하기")

    if start_btn or resume_btn:
        try:
            status = st.empty()
            
            # 1. 캐시 생성
            if not st.session_state.get('cache_name') or start_btn:
                st.session_state['analysis_history'] = []
                st.session_state['question_list'] = []
                st.session_state['last_index'] = 0
                
                all_files = []
                exam_chunks = split_and_upload_pdf(exam_file)
                if exam_chunks: all_files.extend(exam_chunks)
                for tf in textbook_files:
                    tb_chunks = split_and_upload_pdf(tf)
                    if tb_chunks: all_files.extend(tb_chunks)
                
                if not all_files: st.stop()
                wait_for_files_active(all_files)
                
                status.info("💾 캐시 생성 중...")
                cache = caching.CachedContent.create(
                    model='models/gemini-2.5-pro',
                    display_name='sorted_scan_analysis',
                    system_instruction="너는 수학 분석가다. 반말(해라체), LaTeX($) 필수, 표 양식 준수.",
                    contents=all_files,
                    ttl=datetime.timedelta(minutes=60)
                )
                st.session_state['cache_name'] = cache.name
            
            model = genai.GenerativeModel.from_cached_content(cached_content=caching.CachedContent.get(st.session_state['cache_name']))
            
            # 2. 구조 파악 및 정렬
            if not st.session_state['question_list']:
                status.info("🔍 시험지 스캔 및 번호 정렬 중...")
                detected_questions = scan_exam_structure(model)
                if not detected_questions:
                    st.error("문항 인식 실패")
                    st.stop()
                st.session_state['question_list'] = detected_questions
                
                # 정렬된 리스트 보여주기
                st.success(f"✅ 정렬된 문항 리스트: {', '.join(detected_questions)}")
                time.sleep(2)

            q_list = st.session_state['question_list']
            start_idx = st.session_state['last_index']
            p_bar = st.progress(start_idx / len(q_list))
            
            for i in range(start_idx, len(q_list)):
                q_label = q_list[i]
                display_label = q_label + "번" if q_label.isdigit() else q_label
                
                status.info(f"🔄 분석 중... {display_label} (캐시 활용 중)")
                
                prompt = f"""
                기출문제 PDF에서 정확히 **'{q_label}'** 문항을 찾아 분석해라.
                
                **[작성 가이드 - 엄격 준수]**
                1. **출처 표기:** [원본] 첫 줄은 반드시 **`[교재명] p.00 00번`** 양식.
                2. **말투:** 무조건 반말(해라체).
                3. **수식:** `$ ... $` (LaTeX) 필수.
                4. **상세 분석:** '▶ 변형 포인트', '▶ 출제 의도'만 핵심 요약. (풀이 과정 X)
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {display_label} | **[원본]**<br>(LaTeX)<br><br>**[요약]** | **[원본]**<br>[교재명] p.xx xx번<br>(LaTeX)<br><br>**[요약]** | **▶ 변형 포인트**<br>• 내용<br><br>**▶ 출제 의도**<br>• 내용 |
                """
                
                success = False
                for attempt in range(3):
                    try:
                        resp = model.generate_content(prompt)
                        if resp.parts:
                            txt = resp.text
                            usage = resp.usage_metadata
                            total = usage.prompt_token_count
                            
                            token_info = f"<div class='token-info'>📊 토큰: 전체 {total:,} (캐시됨) + 신규 약 300</div>"
                            st.markdown(token_info, unsafe_allow_html=True)
                            
                            st.session_state['analysis_history'].append(txt)
                            st.markdown(txt, unsafe_allow_html=True)
                            success = True
                            break
                    except:
                        time.sleep(1)
                
                if not success:
                    st.warning(f"⚠️ {display_label} 실패 (건너뜀)")
                
                st.session_state['last_index'] = i + 1
                p_bar.progress((i + 1) / len(q_list))
            
            status.success("🎉 정렬 분석 완료!")
            
        except Exception as e:
            st.error(f"오류: {e}")

    if st.session_state['analysis_history']:
        st.divider()
        html = create_html(st.session_state['analysis_history'])
        st.download_button("📥 결과 다운로드", html, "분석결과.html")
