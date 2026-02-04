import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import tempfile
import time
import markdown
import pypdf

# 1. 설정
st.set_page_config(page_title="수학 기출 분석기 (LaTeX Fix)", layout="wide")
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

st.title("💯 고등학교 수학 기출 vs 부교재 분석기 (수식 렌더링 복구)")

# 2. 세션
if 'analysis_history' not in st.session_state:
    st.session_state['analysis_history'] = []
if 'last_index' not in st.session_state:
    st.session_state['last_index'] = 0

# 3. API 키
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    
    st.divider()
    st.info("🔒 **모델:** Gemini 2.5 Pro")
    st.info("💲 **LaTeX 강제:** 회색 코드박스 대신 깔끔한 수식으로 출력되도록 수정했습니다.")
    
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        st.success("API 키 확인 완료!")
    else:
        st.warning("API 키를 먼저 입력해주세요.")

# 4. 파일 업로드
col1, col2 = st.columns(2)
with col1:
    exam_file = st.file_uploader("기출문제 PDF", type=['pdf'], key="exam")
with col2:
    textbook_files = st.file_uploader("부교재 PDF (다중 선택)", type=['pdf'], key="textbooks", accept_multiple_files=True)

# 함수들
def upload_single_file(uploaded_file):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = tmp.name
    return genai.upload_file(tmp_path, mime_type="application/pdf")

def split_and_upload_pdf(uploaded_file):
    pdf_reader = pypdf.PdfReader(uploaded_file)
    total_pages = len(pdf_reader.pages)
    chunk_size = 30
    
    if total_pages <= chunk_size:
        return [upload_single_file(uploaded_file)]

    uploaded_chunks = []
    for start in range(0, total_pages, chunk_size):
        end = min(start + chunk_size, total_pages)
        pdf_writer = pypdf.PdfWriter()
        for p in range(start, end):
            pdf_writer.add_page(pdf_reader.pages[p])
        with tempfile.NamedTemporaryFile(delete=False, suffix=f"_part_{start}.pdf") as tmp:
            pdf_writer.write(tmp)
            tmp_path = tmp.name
        try:
            uploaded_chunks.append(genai.upload_file(tmp_path, mime_type="application/pdf"))
        except:
            pass
    return uploaded_chunks

def wait_for_files(files):
    with st.spinner("파일 처리 중..."):
        for f in files:
            while genai.get_file(f.name).state.name == "PROCESSING":
                time.sleep(1)

def create_html(text_list):
    full_text = "\n\n".join(text_list)
    html_body = markdown.markdown(full_text, extensions=['tables'])
    # MathJax 설정: $...$ 및 $$...$$ 인식 강화
    return f"""
    <html><head><meta charset="utf-8">
    <script>
    MathJax = {{
      tex: {{
        inlineMath: [['$', '$']],
        displayMath: [['$$', '$$']]
      }},
      svg: {{ fontCache: 'global' }}
    }};
    </script>
    <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>body{{font-family:'Malgun Gothic';padding:40px;line-height:1.6}} table{{border-collapse:collapse;width:100%;margin-bottom:30px}} th,td{{border:1px solid #ddd;padding:15px}} th{{background:#007bff;color:white;text-align:center}}</style>
    </head><body>{html_body}</body></html>
    """

# 5. 실행 로직
if exam_file and textbook_files and api_key:
    batches = []
    # 1~18번 (객관식)
    for i in range(1, 19): 
        batches.append((f"{i}번", f"기출 객관식 {i}번"))
    
    # 서답형 인식 범위 (1~6)
    for i in range(1, 7): 
        desc = f"기출 서답형(주관식/단답형/서술형) {i}번째 문항"
        batches.append((f"주관식 {i}번", desc))

    c1, c2 = st.columns(2)
    start_btn = c1.button("🚀 처음부터 시작")
    resume_btn = False
    if st.session_state['last_index'] > 0:
        resume_btn = c2.button(f"⏯️ {batches[st.session_state['last_index']][0]}부터 이어하기")

    if start_btn or resume_btn:
        start_idx = 0 if start_btn else st.session_state['last_index']
        if start_btn: st.session_state['analysis_history'] = []

        try:
            exam_ref = upload_single_file(exam_file)
            tb_refs = []
            for t in textbook_files:
                refs = split_and_upload_pdf(t)
                if refs: tb_refs.extend(refs)
            
            wait_for_files([exam_ref] + tb_refs)
            
            model = genai.GenerativeModel("gemini-2.5-pro", safety_settings={HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE})
            
            p_bar = st.progress(0)
            status = st.empty()

            for i in range(start_idx, len(batches)):
                title, desc = batches[i]
                status.info(f"🔄 {title} 분석 중... ({i+1}/{len(batches)})")
                
                # --- 🔥 [핵심 수정] LaTeX 강제 프롬프트 ---
                # 백틱(`) 사용 금지 명령 추가
                prompt_common_rules = """
                **[출력 형식 절대 준수]**
                1. **수식 표기:** 모든 수식은 반드시 **`$ 수식 $`** 형태로 작성하세요.
                   - (오답) `x^2`, `x^2` (회색 박스 금지)
                   - (정답) $x^2$
                2. **절댓값:** 표 깨짐 방지를 위해 `|x|` 대신 반드시 **`$\\lvert x \\rvert$`**를 사용하세요.
                3. **코드 블록 금지:** 답변에 코드 블록(```)이나 인라인 코드(`)를 절대 사용하지 마세요.
                """
                
                prompt_forced = f"""
                당신은 수학 분석가입니다.
                기출문제 PDF에서 **{desc}**을 찾아 부교재와 비교하세요.
                
                {prompt_common_rules}
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {title} | **[원본]**<br>(수식은 $...$ 필수)<br><br>**[요약]** | **[원본]**<br>p.xx<br>(수식은 $...$ 필수)<br><br>**[요약]** | **▶ 변형 포인트**<br>• 내용 |
                """
                
                prompt_bypass = f"""
                위와 동일하게 하되, 저작권 보호를 위해 **'문제 원문'을 그대로 적지 말고 핵심 수치와 조건만 요약**하세요.
                {prompt_common_rules}
                """

                prompt_simple = f"""
                위와 동일하게 하되, **내용을 아주 짧고 간결하게** 줄여서 적으세요.
                {prompt_common_rules}
                """

                req = [prompt_forced, exam_ref] + tb_refs
                success = False
                
                for attempt in range(3):
                    try:
                        if attempt == 1: req[0] = prompt_bypass
                        if attempt == 2: req[0] = prompt_simple
                        
                        resp = model.generate_content(req)
                        
                        if resp.parts:
                            txt = resp.text
                            # SKIP 검증
                            if "SKIP" in txt:
                                if i < 18: pass 
                            
                            st.session_state['analysis_history'].append(txt)
                            st.markdown(txt, unsafe_allow_html=True)
                            success = True
                            break
                    except:
                        time.sleep(1)
                
                st.session_state['last_index'] = i + 1
                p_bar.progress((i + 1) / len(batches))
            
            status.success("완료")
            
        except Exception as e:
            st.error(f"오류: {e}")

    if st.session_state['analysis_history']:
        st.divider()
        html = create_html(st.session_state['analysis_history'])
        st.download_button("📥 결과 다운로드", html, "분석결과.html")
