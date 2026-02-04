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
st.set_page_config(page_title="수학 기출 분석기 (2.5 Pro Caching)", layout="wide")
st.markdown("""
    <style>
    div[data-testid="stMarkdownContainer"] p, td, th { font-family: 'Malgun Gothic', sans-serif !important; }
    .success-log { color: #2e7d32; font-weight: bold; }
    .info-log { color: #0277bd; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 수학 기출 분석기 (2.5 Pro 고정 + 캐싱)")

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
    st.info("🔒 **모델 고정:** Gemini 2.5 Pro")
    st.info("💾 **기능:** 2.5 Pro 모델에 캐싱을 적용하여 비용을 절감합니다.")
    
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)

# 4. 파일 업로드
col1, col2 = st.columns(2)
with col1:
    exam_file = st.file_uploader("기출 PDF", type=['pdf'])
with col2:
    textbook_files = st.file_uploader("부교재 PDF (다중)", type=['pdf'], accept_multiple_files=True)

# 함수들
def upload_to_gemini(file_obj):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(file_obj.getvalue())
        tmp_path = tmp.name
    return genai.upload_file(tmp_path, mime_type="application/pdf")

def wait_for_files(files):
    with st.spinner("파일 처리 중..."):
        for f in files:
            while genai.get_file(f.name).state.name == "PROCESSING":
                time.sleep(1)

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
            # 1. 파일 업로드
            status = st.empty()
            
            # 캐시가 없거나 처음 시작이면 새로 생성
            if not st.session_state.get('cache_name') or start_btn:
                status.info("📂 파일 서버 업로드 중...")
                uploaded_exam = upload_to_gemini(exam_file)
                uploaded_textbooks = [upload_to_gemini(f) for f in textbook_files]
                all_files = [uploaded_exam] + uploaded_textbooks
                
                wait_for_files(all_files)
                
                status.info("💾 2.5 Pro 컨텍스트 캐시 생성 중...")
                
                # --- 🔥 [수정 완료] 모델명을 2.5 Pro로 확실하게 고정 ---
                cache = caching.CachedContent.create(
                    model='models/gemini-2.5-pro', # 1.5 Pro 삭제 -> 2.5 Pro 적용
                    display_name='math_exam_analysis_v2',
                    system_instruction="""
                    당신은 수학 분석가입니다. 
                    [원칙]
                    1. 절댓값은 반드시 `\\lvert x \\rvert` 사용.
                    2. 부교재 유사 문항 반드시 매칭.
                    3. 없는 경우에만 "SKIP".
                    """,
                    contents=all_files,
                    ttl=datetime.timedelta(minutes=60)
                )
                st.session_state['cache_name'] = cache.name
                status.markdown(f"<p class='success-log'>✅ 캐시 생성 완료! (ID: {cache.name})</p>", unsafe_allow_html=True)
            else:
                # 이미 캐시가 있으면 재사용 (이름으로 가져옴)
                cache = caching.CachedContent.get(st.session_state['cache_name'])
                status.info(f"♻️ 기존 캐시 재사용 중: {cache.name}")

            # 2. 모델 연결 (2.5 Pro 캐시 사용)
            model = genai.GenerativeModel.from_cached_content(cached_content=cache)
            
            # 3. 분석 루프
            p_bar = st.progress(start_idx / len(batches))
            
            for i in range(start_idx, len(batches)):
                title, desc = batches[i]
                status.info(f"🔄 {title} 분석 중... (2.5 Pro)")
                
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
                        if attempt == 1: current_prompt += "\n(저작권 필터 회피: 문제 원문은 핵심 수치만 요약하세요.)"
                        if attempt == 2: current_prompt += "\n(길이 제한 회피: 내용을 아주 간결하게 줄이세요.)"
                        
                        resp = model.generate_content(current_prompt)
                        
                        if resp.parts:
                            txt = resp.text
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
            st.error(f"오류: {e}")

    if st.session_state['analysis_history']:
        st.divider()
        html = create_html(st.session_state['analysis_history'])
        st.download_button("📥 결과 다운로드", html, "분석결과.html")
