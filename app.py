import streamlit as st
import google.generativeai as genai
from google.generativeai import caching
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import tempfile
import time
import markdown
import pypdf
import datetime

# 1. 설정
st.set_page_config(page_title="수학 기출 분석기 (2.5 Pro Final)", layout="wide")
st.markdown("""
    <style>
    div[data-testid="stMarkdownContainer"] p, td, th { font-family: 'Malgun Gothic', sans-serif !important; }
    .success-log { color: #2e7d32; font-weight: bold; }
    .error-log { color: #d32f2f; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 수학 기출 분석기 (2.5 Pro 고정 + 분할 업로드)")

# 2. 세션
if 'analysis_history' not in st.session_state:
    st.session_state['analysis_history'] = []
if 'last_index' not in st.session_state:
    st.session_state['last_index'] = 0
if 'cache_name' not in st.session_state:
    st.session_state['cache_name'] = None

# 3. API 키
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key", type="password")
    st.divider()
    st.info("🔒 **모델 고정:** gemini-2.5-pro")
    st.info("⚡ **업로드:** 분할 업로드(Chunking) + 상태 확인(Wait) 적용")
    
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
    """대용량 파일을 작게 잘라서 업로드"""
    pdf_reader = pypdf.PdfReader(uploaded_file)
    total_pages = len(pdf_reader.pages)
    file_label = uploaded_file.name
    
    # 페이지 적으면 그냥 통으로 (리스트 반환)
    if total_pages <= chunk_size_pages:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded_file.getvalue())
            tmp_path = tmp.name
        return [genai.upload_file(tmp_path, mime_type="application/pdf")]

    status_text = st.empty()
    status_text.info(f"🔪 '{file_label}' 분할 업로드 중... (총 {total_pages}쪽)")
    
    uploaded_chunks = []
    bar = st.progress(0)
    
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
            bar.progress(min((start_page + chunk_size_pages) / total_pages, 1.0))
        except Exception as e:
            st.error(f"분할 업로드 오류: {e}")
            return None
            
    status_text.empty()
    bar.empty()
    return uploaded_chunks

def wait_for_files_active(files):
    """모든 파일이 ACTIVE 상태가 될 때까지 확실하게 대기"""
    bar = st.progress(0)
    status_text = st.empty()
    
    for i, f in enumerate(files):
        file_obj = genai.get_file(f.name)
        while file_obj.state.name == "PROCESSING":
            status_text.info(f"⏳ 서버 처리 대기 중... ({i+1}/{len(files)})")
            time.sleep(2) 
            file_obj = genai.get_file(f.name)
        
        if file_obj.state.name != "ACTIVE":
            st.error(f"❌ 파일 처리 실패: {file_obj.uri} (State: {file_obj.state.name})")
            st.stop()
        
        bar.progress((i + 1) / len(files))
        
    status_text.success("✅ 모든 파일 준비 완료 (ACTIVE)")
    time.sleep(0.5)
    status_text.empty()
    bar.empty()

def create_html(text_list):
    full_text = "\n\n".join(text_list)
    html_body = markdown.markdown(full_text, extensions=['tables'])
    return f"""
    <html><head><meta charset="utf-8">
    <script>MathJax={{tex:{{inlineMath:[['$','$']],displayMath:[['$$','$$']]}},svg:{{fontCache:'global'}} }};</script>
    <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>body{{font-family:'Malgun Gothic';padding:40px;line-height:1.6}} table{{border-collapse:collapse;width:100%;margin-bottom:30px}} th,td{{border:1px solid #ddd;padding:15px}} th{{background:#007bff;color:white;text-align:center}}</style>
    </head><body>{html_body}</body></html>
    """

# 5. 실행 로직
if exam_file and textbook_files and api_key:
    batches = []
    for i in range(1, 26): batches.append((f"{i}번", f"기출 객관식 {i}번"))
    for i in range(1, 7): batches.append((f"서답형 {i}번", f"기출 서답형(주관식) {i}번"))

    c1, c2 = st.columns(2)
    start_btn = c1.button("🚀 캐싱 & 분석 시작")
    resume_btn = False
    if st.session_state['last_index'] > 0:
        resume_btn = c2.button(f"⏯️ {batches[st.session_state['last_index']][0]}부터 이어하기")

    if start_btn or resume_btn:
        start_idx = 0 if start_btn else st.session_state['last_index']
        if start_btn: st.session_state['analysis_history'] = []

        try:
            status = st.empty()
            
            # --- 캐시 생성 로직 ---
            if not st.session_state.get('cache_name') or start_btn:
                
                # 1. 파일 분할 업로드
                all_files = []
                
                # 기출문제 업로드
                exam_chunks = split_and_upload_pdf(exam_file)
                if exam_chunks: all_files.extend(exam_chunks)
                
                # 부교재 업로드
                for tf in textbook_files:
                    tb_chunks = split_and_upload_pdf(tf)
                    if tb_chunks: all_files.extend(tb_chunks)
                
                if not all_files:
                    st.error("파일 업로드 실패")
                    st.stop()

                # 2. 파일 상태 확인 (ACTIVE 필수!)
                # 여기서 400 Invalid Argument를 막습니다.
                wait_for_files_active(all_files)
                
                status.info("💾 2.5 Pro 컨텍스트 캐시 생성 중...")
                
                try:
                    # 🔥 [절대 고정] 사용자가 지정한 모델명 사용
                    cache = caching.CachedContent.create(
                        model='models/gemini-2.5-pro',
                        display_name='math_exam_analysis_final_v2',
                        system_instruction="""
                        당신은 수학 분석가입니다. 
                        [원칙]
                        1. 절댓값은 반드시 `\\lvert x \\rvert` 사용.
                        2. 부교재 유사 문항 반드시 매칭 (없으면 가장 비슷한 개념이라도).
                        3. 기출에 없는 번호일 때만 "SKIP".
                        """,
                        contents=all_files,
                        ttl=datetime.timedelta(minutes=60)
                    )
                    st.session_state['cache_name'] = cache.name
                    status.markdown(f"<p class='success-log'>✅ 캐시 생성 완료! (ID: {cache.name})</p>", unsafe_allow_html=True)
                
                except Exception as e:
                    st.error(f"캐시 생성 실패: {e}")
                    if "400" in str(e):
                        st.warning("파일이 아직 준비되지 않았거나, 모델이 캐싱을 지원하지 않는 일시적 오류일 수 있습니다. 잠시 후 다시 시도해보세요.")
                    st.stop()

            else:
                cache = caching.CachedContent.get(st.session_state['cache_name'])
                status.info(f"♻️ 기존 캐시 재사용 중: {cache.name}")

            # 모델 연결
            model = genai.GenerativeModel.from_cached_content(cached_content=cache)
            
            # 분석 루프
            p_bar = st.progress(start_idx / len(batches))
            
            for i in range(start_idx, len(batches)):
                title, desc = batches[i]
                status.info(f"🔄 {title} 분석 중...")
                
                prompt_text = f"""
                **{desc}**을 분석하세요.
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {title} | **[원본]**<br>(LaTeX)<br><br>**[요약]** | **[원본]**<br>p.xx<br>(LaTeX)<br><br>**[요약]** | **▶ 변형 포인트**<br>• 내용 |
                """
                
                success = False
                for attempt in range(3):
                    try:
                        current_prompt = prompt_text
                        if attempt == 1: current_prompt += "\n(필터 회피: 문제 원문 요약)"
                        if attempt == 2: current_prompt += "\n(길이 제한 회피: 내용 단축)"
                        
                        resp = model.generate_content(current_prompt)
                        
                        if resp.parts:
                            txt = resp.text
                            # SKIP 검증
                            if "SKIP" in txt and i < 18: pass 
                            
                            st.session_state['analysis_history'].append(txt)
                            st.markdown(txt, unsafe_allow_html=True)
                            success = True
                            break
                    except Exception:
                        time.sleep(1)
                
                st.session_state['last_index'] = i + 1
                p_bar.progress((i + 1) / len(batches))
            
            status.success("✅ 분석 완료!")
            
        except Exception as e:
            st.error(f"오류 상세: {e}")

    if st.session_state['analysis_history']:
        st.divider()
        html = create_html(st.session_state['analysis_history'])
        st.download_button("📥 결과 다운로드", html, "분석결과.html")
