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
st.set_page_config(page_title="수학 기출 분석기 (Context Caching)", layout="wide")
st.markdown("""
    <style>
    div[data-testid="stMarkdownContainer"] p, td, th { font-family: 'Malgun Gothic', sans-serif !important; }
    .success-log { color: #2e7d32; font-weight: bold; }
    .info-log { color: #0277bd; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 수학 기출 분석기 (비용 절약형: 캐싱 적용)")

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
    st.info("💾 **컨텍스트 캐싱:** 대용량 PDF를 한 번만 서버에 저장하고 재사용합니다. 입력 비용이 획기적으로 줄어듭니다.")
    
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
            # --- 🔥 [핵심 1] 캐시 생성 (최초 1회만 수행하거나 파일 바뀌면 수행) ---
            # 스트림릿 특성상 버튼 누를 때마다 실행되지만, 캐싱 API를 호출하여 최적화함
            
            # 1. 파일 업로드 (Gemini File API)
            status = st.empty()
            status.info("📂 파일 서버 업로드 중...")
            
            uploaded_exam = upload_to_gemini(exam_file)
            uploaded_textbooks = [upload_to_gemini(f) for f in textbook_files]
            all_files = [uploaded_exam] + uploaded_textbooks
            
            wait_for_files(all_files)
            
            # 2. 캐시 생성 (Input Once)
            status.info("💾 컨텍스트 캐시 생성 중 (Input Once)...")
            
            # 캐시 만료 시간 설정 (1시간)
            cache = caching.CachedContent.create(
                model='models/gemini-1.5-pro-002', # 최신 1.5 Pro 모델 지정
                display_name='math_exam_analysis',
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
            status.markdown(f"<p class='success-log'>✅ 캐시 생성 완료! (ID: {cache.name}) - 이제부터 입력 비용은 거의 0원입니다.</p>", unsafe_allow_html=True)
            
            # 3. 모델 연결 (캐시된 내용 사용)
            # 이제 파일을 매번 보내지 않고 cache 객체만 연결합니다.
            model = genai.GenerativeModel.from_cached_content(cached_content=cache)
            
            # 4. 분석 루프 (Output만 끊어서 요청)
            p_bar = st.progress(start_idx / len(batches))
            
            for i in range(start_idx, len(batches)):
                title, desc = batches[i]
                status.info(f"🔄 {title} 분석 중... (캐시 사용)")
                
                # 프롬프트에는 이제 파일이 필요 없습니다! (이미 캐시에 있음)
                prompt_text = f"""
                **{desc}**을 분석하세요.
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {title} | **[원본]**<br>(LaTeX)<br><br>**[요약]** | **[원본]**<br>p.xx<br>(LaTeX)<br><br>**[요약]** | **▶ 변형 포인트**<br>• 내용 |
                """
                
                # 재시도 로직 (필터/오류 대응)
                success = False
                for attempt in range(3):
                    try:
                        # 요약/단축 모드 프롬프트 변경
                        current_prompt = prompt_text
                        if attempt == 1: current_prompt += "\n(저작권 필터 회피: 문제 원문은 핵심 수치만 요약하세요.)"
                        if attempt == 2: current_prompt += "\n(길이 제한 회피: 내용을 아주 간결하게 줄이세요.)"
                        
                        # generate_content에 파일을 넣지 않습니다! (캐시가 알아서 함)
                        resp = model.generate_content(current_prompt)
                        
                        if resp.parts:
                            txt = resp.text
                            if "SKIP" in txt and i < 18: pass # 객관식 SKIP 의심 시 재시도 로직 등 추가 가능
                            
                            st.session_state['analysis_history'].append(txt)
                            st.markdown(txt, unsafe_allow_html=True)
                            success = True
                            break
                    except Exception:
                        time.sleep(1)
                
                st.session_state['last_index'] = i + 1
                p_bar.progress((i + 1) / len(batches))
            
            status.success("✅ 분석 완료!")
            
            # (선택) 분석 끝나면 캐시 삭제해서 저장 공간 확보 (비용 절약)
            # cache.delete() 
            
        except Exception as e:
            st.error(f"오류: {e}")

    if st.session_state['analysis_history']:
        st.divider()
        html = create_html(st.session_state['analysis_history'])
        st.download_button("📥 결과 다운로드", html, "분석결과.html")
