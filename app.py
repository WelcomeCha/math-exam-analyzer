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

# 1. 설정 및 스타일링 (표 너비 고정 CSS 포함)
st.set_page_config(page_title="수학 기출 분석기 (Final Layout)", layout="wide")
st.markdown("""
    <style>
    /* 폰트 및 기본 설정 */
    div[data-testid="stMarkdownContainer"] p, td, th { 
        font-family: 'Malgun Gothic', sans-serif !important; 
        font-size: 15px !important;
        line-height: 1.6 !important;
    }
    
    /* 표 스타일 강제 고정 */
    table {
        width: 100% !important;
        table-layout: fixed !important; /* 열 너비 고정 */
        border-collapse: collapse !important;
    }
    th, td {
        border: 1px solid #ddd !important;
        padding: 12px !important;
        vertical-align: top !important;
        word-wrap: break-word !important; /* 긴 수식 줄바꿈 */
    }
    
    /* 열 너비 비율 설정 (8:30:31:31) */
    th:nth-child(1) { width: 8% !important; }
    th:nth-child(2) { width: 30% !important; }
    th:nth-child(3) { width: 31% !important; }
    th:nth-child(4) { width: 31% !important; }
    
    /* 헤더 스타일 */
    th {
        background-color: #f0f2f6 !important;
        font-weight: bold !important;
        text-align: center !important;
    }
    
    .success-log { color: #2e7d32; font-weight: bold; }
    .error-log { color: #d32f2f; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 수학 기출 분석기 (양식 고정 + LaTeX 완벽 적용)")

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
    st.info("🎨 **양식:** 표 너비 고정, LaTeX 필수, 풀이 생략")
    
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
    file_label = uploaded_file.name
    
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
    bar = st.progress(0)
    status_text = st.empty()
    
    for i, f in enumerate(files):
        file_obj = genai.get_file(f.name)
        while file_obj.state.name == "PROCESSING":
            status_text.info(f"⏳ 서버 처리 대기 중... ({i+1}/{len(files)})")
            time.sleep(2) 
            file_obj = genai.get_file(f.name)
        
        if file_obj.state.name != "ACTIVE":
            st.error(f"❌ 파일 처리 실패: {file_obj.uri}")
            st.stop()
        
        bar.progress((i + 1) / len(files))
        
    status_text.success("✅ 모든 파일 준비 완료 (ACTIVE)")
    time.sleep(0.5)
    status_text.empty()
    bar.empty()

def create_html(text_list):
    full_text = "\n\n".join(text_list)
    html_body = markdown.markdown(full_text, extensions=['tables'])
    # HTML 파일 다운로드 시에도 표 너비 고정 스타일 적용
    return f"""
    <html><head><meta charset="utf-8">
    <script>
    MathJax = {{
      tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']], displayMath: [['$$', '$$']] }},
      svg: {{ fontCache: 'global' }} 
    }};
    </script>
    <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        body {{ font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; padding: 40px; max-width: 1400px; margin: 0 auto; }}
        table {{ border-collapse: collapse; width: 100%; table-layout: fixed; margin-bottom: 30px; }}
        th, td {{ border: 1px solid #ddd; padding: 15px; text-align: left; vertical-align: top; word-wrap: break-word; }}
        th {{ background-color: #007bff; color: white; text-align: center; }}
        th:nth-child(1) {{ width: 8%; }}
        th:nth-child(2) {{ width: 30%; }}
        th:nth-child(3) {{ width: 31%; }}
        th:nth-child(4) {{ width: 31%; }}
        tr:nth-child(even) {{ background-color: #f2f2f2; }}
    </style>
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
            
            # --- 캐시 생성 ---
            if not st.session_state.get('cache_name') or start_btn:
                all_files = []
                # 분할 업로드
                exam_chunks = split_and_upload_pdf(exam_file)
                if exam_chunks: all_files.extend(exam_chunks)
                for tf in textbook_files:
                    tb_chunks = split_and_upload_pdf(tf)
                    if tb_chunks: all_files.extend(tb_chunks)
                
                if not all_files:
                    st.error("파일 업로드 실패")
                    st.stop()

                wait_for_files_active(all_files)
                
                status.info("💾 2.5 Pro 컨텍스트 캐시 생성 중...")
                
                try:
                    cache = caching.CachedContent.create(
                        model='models/gemini-2.5-pro',
                        display_name='math_exam_fixed_layout',
                        system_instruction="""
                        당신은 수학 분석가입니다. 
                        
                        **[절대 원칙 - 위반 시 오작동]**
                        1. **모든 수식은 LaTeX로:** $x^2$, $a_n$ 처럼 반드시 달러 기호($)를 사용하세요. 
                           - 절대 `x²`이나 `a₁` 같은 유니코드 문자를 쓰지 마세요.
                        2. **절댓값:** 반드시 `\\lvert x \\rvert`를 사용하세요.
                        3. **부교재 매칭:** 가장 유사한 문항을 반드시 찾으세요. (기출 문항 자체가 없을 때만 SKIP)
                        """,
                        contents=all_files,
                        ttl=datetime.timedelta(minutes=60)
                    )
                    st.session_state['cache_name'] = cache.name
                    status.markdown(f"<p class='success-log'>✅ 캐시 생성 완료! (ID: {cache.name})</p>", unsafe_allow_html=True)
                
                except Exception as e:
                    st.error(f"캐시 생성 실패: {e}")
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
                
                # 프롬프트: '상세 변형 분석' 란의 내용을 엄격하게 제한
                prompt_text = f"""
                **{desc}**을 분석하세요.
                
                **[작성 가이드]**
                1. '상세 변형 분석' 란에는 **'▶ 변형 포인트'**와 **'▶ 출제 의도'**만 적으세요.
                2. **[금지]** '풀이 과정', '정답 구하기' 등의 내용은 절대 적지 마세요. 분석 칸이 너무 길어지지 않게 하세요.
                3. 모든 수식은 `$ ... $` (LaTeX) 형식을 사용하세요.
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {title} | **[원본]**<br>(LaTeX 수식)<br><br>**[요약]** | **[원본]**<br>p.xx<br>(LaTeX 수식)<br><br>**[요약]** | **▶ 변형 포인트**<br>• (핵심 차이점만 서술)<br><br>**▶ 출제 의도**<br>(평가 요소 서술) |
                """
                
                success = False
                for attempt in range(3):
                    try:
                        current_prompt = prompt_text
                        if attempt == 1: current_prompt += "\n(주의: 문제 원문은 핵심 수치만 요약하세요.)"
                        if attempt == 2: current_prompt += "\n(주의: 내용을 아주 간결하게 줄이세요.)"
                        
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
