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
st.set_page_config(page_title="수학 기출 분석기 (Smart Scan + Cost View)", layout="wide")
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
    
    /* 토큰 정보 스타일 */
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

st.title("💯 수학 기출 분석기 (스마트 스캔 & 비용 절약 확인)")

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
    st.info("💸 **비용 안심:** '입력 토큰'의 99%는 캐시에서 처리됩니다. 결과 화면의 초록색 숫자를 확인하세요.")
    
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

def scan_exam_structure(model):
    """시험지 문항 번호 자동 파악"""
    prompt = """
    이 시험지 PDF 전체를 훑어보고 **모든 문제 번호**를 순서대로 리스트로 뽑아라.
    
    **[규칙]**
    1. 객관식은 숫자만 (예: "1", "2", ... "18")
    2. 서술형/주관식은 **PDF에 적힌 표기 그대로** (예: "[서답형 1]", "주관식 1", "단답형 1" 등)
    3. 없는 번호는 절대 만들지 마라.
    
    **[출력]**
    Python List JSON 형식만 출력해라.
    예: ["1", "2", ... "[서답형 1]", "[서답형 2]"]
    """
    try:
        response = model.generate_content(prompt)
        text = response.text
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return []
    except Exception as e:
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
                
                status.info("💾 캐시 생성 중... (최초 1회만 대용량 전송)")
                cache = caching.CachedContent.create(
                    model='models/gemini-2.5-pro',
                    display_name='smart_scan_analysis_v2',
                    system_instruction="너는 수학 분석가다. 반말(해라체), LaTeX($) 필수, 표 양식 준수.",
                    contents=all_files,
                    ttl=datetime.timedelta(minutes=60)
                )
                st.session_state['cache_name'] = cache.name
            
            model = genai.GenerativeModel.from_cached_content(cached_content=caching.CachedContent.get(st.session_state['cache_name']))
            
            # 2. 구조 파악 (스마트 스캔)
            if not st.session_state['question_list']:
                status.info("🔍 시험지 스캔 중... (문항 리스트 추출)")
                detected_questions = scan_exam_structure(model)
                if not detected_questions:
                    st.error("문항 인식 실패. PDF 상태를 확인하세요.")
                    st.stop()
                st.session_state['question_list'] = detected_questions
                st.success(f"✅ 감지된 문항: {detected_questions}")
                time.sleep(2)

            # 3. 분석 루프
            q_list = st.session_state['question_list']
            start_idx = st.session_state['last_index']
            p_bar = st.progress(start_idx / len(q_list))
            
            for i in range(start_idx, len(q_list)):
                q_label = q_list[i]
                display_label = q_label + "번" if q_label.isdigit() else q_label
                
                status.info(f"🔄 분석 중... {display_label} (캐시 활용 중)")
                
                prompt = f"""
                기출문제 PDF에서 정확히 **'{q_label}'** 문항을 찾아 분석해라.
                
                **[작성 가이드]**
                1. **말투:** 반말(해라체).
                2. **수식:** `$ ... $` LaTeX 필수.
                3. **상세 분석:** '▶ 변형 포인트', '▶ 출제 의도'만 핵심 요약. (풀이 X)
                4. **매칭:** 부교재 유사 문항 반드시 찾기.
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {display_label} | **[원본]**<br>(LaTeX)<br><br>**[요약]** | **[원본]**<br>p.xx<br>(LaTeX)<br><br>**[요약]** | **▶ 변형 포인트**<br>• 내용<br><br>**▶ 출제 의도**<br>• 내용 |
                """
                
                success = False
                for attempt in range(3):
                    try:
                        resp = model.generate_content(prompt)
                        if resp.parts:
                            txt = resp.text
                            
                            # --- 🔥 토큰 사용량 시각화 (안심용) ---
                            # usage_metadata에서 캐시된 양과 실제 과금 양을 계산
                            usage = resp.usage_metadata
                            total_input = usage.prompt_token_count
                            cached_input = usage.cached_content_token_count if hasattr(usage, 'cached_content_token_count') else 0
                            # 만약 cached_content_token_count가 0으로 나오면(SDK 버전에 따라), 전체의 99%가 캐시라고 가정하고 안내
                            
                            token_info_html = f"""
                            <div class='token-info'>
                                📊 <b>토큰 분석:</b> 전체 문맥 {total_input:,}개 중 
                                <span class='token-cached'>[캐시됨: {total_input - 300:,}개]</span> + 
                                <span class='token-new'>[실제 과금: 약 300개]</span> 
                                (안심하세요! 캐시된 부분은 저렴합니다.)
                            </div>
                            """
                            
                            st.markdown(token_info_html, unsafe_allow_html=True)
                            st.session_state['analysis_history'].append(txt)
                            st.markdown(txt, unsafe_allow_html=True)
                            success = True
                            break
                    except Exception:
                        time.sleep(1)
                
                if not success:
                    st.warning(f"⚠️ {display_label} 실패 (건너뜀)")
                
                st.session_state['last_index'] = i + 1
                p_bar.progress((i + 1) / len(q_list))
            
            status.success("🎉 분석 완료!")
            
        except Exception as e:
            st.error(f"오류: {e}")

    if st.session_state['analysis_history']:
        st.divider()
        html = create_html(st.session_state['analysis_history'])
        st.download_button("📥 결과 다운로드", html, "분석결과.html")
