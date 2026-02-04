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
st.set_page_config(page_title="수학 기출 분석기 (Smart Scan)", layout="wide")
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
    .success-log { color: #2e7d32; font-weight: bold; }
    .info-log { color: #0277bd; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

st.title("💯 수학 기출 분석기 (시험지 구조 자동 인식)")

# 2. 세션 초기화
if 'analysis_history' not in st.session_state:
    st.session_state['analysis_history'] = []
if 'question_list' not in st.session_state:
    st.session_state['question_list'] = [] # 파악된 문항 리스트 저장
if 'last_index' not in st.session_state:
    st.session_state['last_index'] = 0
if 'cache_name' not in st.session_state:
    st.session_state['cache_name'] = None

# 3. API 키
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key", type="password")
    st.divider()
    st.info("🧠 **스마트 스캔:** AI가 시험지를 먼저 읽고, 존재하는 문항 번호(객관식/서답형)를 자동으로 파악한 뒤 분석을 시작합니다.")
    
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

# 🔥 [핵심 기능] 시험지 구조 파악 함수
def scan_exam_structure(model):
    """캐시된 모델을 사용하여 시험지에 있는 문항 번호들을 추출"""
    prompt = """
    이 시험지 PDF를 처음부터 끝까지 훑어보고, 포함된 **모든 문제 번호**를 순서대로 나열해라.
    
    **[추출 규칙]**
    1. 객관식은 숫자만 (예: "1", "2", ... "18")
    2. 주관식/서술형은 **표기된 그대로** (예: "[서답형 1]", "서술형 1번", "<단답형 1>" 등 PDF에 적힌 정확한 텍스트로)
    3. 빠진 번호 없이, 없는 번호는 만들어내지 말고 정확히 리스트로 줘.
    
    **[출력 형식]**
    반드시 Python 리스트 형태의 JSON으로만 출력해라. 다른 말은 쓰지 마라.
    예시: ["1", "2", "3", ... "18", "[서답형 1]", "[서답형 2]", "[서답형 3]"]
    """
    
    try:
        response = model.generate_content(prompt)
        text = response.text
        # JSON 부분만 추출 (혹시 모를 잡설 제거)
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return []
    except Exception as e:
        st.error(f"구조 파악 실패: {e}")
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
    
    # 이어하기 버튼 활성화 조건
    if st.session_state['question_list'] and st.session_state['last_index'] < len(st.session_state['question_list']):
        resume_btn = c2.button("⏯️ 이어하기")

    if start_btn or resume_btn:
        try:
            status = st.empty()
            
            # 1. 캐시 생성 및 모델 연결 (없으면 생성)
            if not st.session_state.get('cache_name') or start_btn:
                # 초기화
                st.session_state['analysis_history'] = []
                st.session_state['question_list'] = []
                st.session_state['last_index'] = 0
                
                # 업로드
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
                    display_name='smart_scan_analysis',
                    system_instruction="너는 수학 분석가다. 반말(해라체)로, 수식은 LaTeX($)로, 표는 정해진 양식대로 작성해라.",
                    contents=all_files,
                    ttl=datetime.timedelta(minutes=60)
                )
                st.session_state['cache_name'] = cache.name
            
            # 모델 로드
            model = genai.GenerativeModel.from_cached_content(cached_content=caching.CachedContent.get(st.session_state['cache_name']))
            
            # 2. 🔥 [구조 파악 단계] 문항 리스트 추출
            if not st.session_state['question_list']:
                status.info("🔍 시험지 구조 스캔 중... (문항 번호 파악)")
                detected_questions = scan_exam_structure(model)
                
                if not detected_questions:
                    st.error("문항 인식 실패. PDF 텍스트를 읽을 수 없거나 형식이 특이합니다.")
                    st.stop()
                
                st.session_state['question_list'] = detected_questions
                st.markdown(f"**✅ 감지된 문항 ({len(detected_questions)}개):** {', '.join(detected_questions)}")
                time.sleep(2) # 사용자가 리스트 확인할 시간

            # 3. 분석 루프 (감지된 리스트 기반)
            q_list = st.session_state['question_list']
            start_idx = st.session_state['last_index']
            p_bar = st.progress(start_idx / len(q_list))
            
            for i in range(start_idx, len(q_list)):
                q_label = q_list[i] # 예: "1", "18", "[서답형 1]"
                
                # 문항 번호 정제 (숫자만 있는 경우 '번' 붙이기)
                display_label = q_label + "번" if q_label.isdigit() else q_label
                
                status.info(f"🔄 분석 중... {display_label} ({i+1}/{len(q_list)})")
                
                # 프롬프트: 정확히 파악된 라벨(q_label)을 타겟팅
                prompt = f"""
                기출문제 PDF에서 정확히 **'{q_label}'** 이라고 표기된 문제를 찾아 분석해라.
                (만약 '{q_label}'이 객관식 번호라면, 해당 번호의 문제 전체를 찾아라.)
                
                **[작성 가이드]**
                1. **말투:** 반말(해라체)로 작성해라. (~임, ~함)
                2. **수식:** `$ ... $` (LaTeX) 필수. 유니코드 문자 금지.
                3. **상세 분석:** '▶ 변형 포인트', '▶ 출제 의도'만 핵심 요약해라. (풀이 과정 금지)
                4. **매칭:** 부교재에서 가장 유사한 문항을 찾아라.
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | {display_label} | **[원본]**<br>(LaTeX 수식)<br><br>**[요약]** | **[원본]**<br>p.xx<br>(LaTeX 수식)<br><br>**[요약]** | **▶ 변형 포인트**<br>• 내용<br><br>**▶ 출제 의도**<br>• 내용 |
                """
                
                # 재시도 및 생성 로직
                success = False
                for attempt in range(3):
                    try:
                        resp = model.generate_content(prompt)
                        if resp.parts:
                            txt = resp.text
                            st.session_state['analysis_history'].append(txt)
                            st.markdown(txt, unsafe_allow_html=True)
                            success = True
                            break
                    except:
                        time.sleep(1)
                
                if not success:
                    st.warning(f"⚠️ {display_label} 분석 실패 (건너뜀)")
                
                st.session_state['last_index'] = i + 1
                p_bar.progress((i + 1) / len(q_list))
            
            status.success("🎉 모든 분석 완료!")
            
        except Exception as e:
            st.error(f"오류 발생: {e}")

    # 결과 다운로드
    if st.session_state['analysis_history']:
        st.divider()
        html = create_html(st.session_state['analysis_history'])
        st.download_button("📥 결과 다운로드 (HTML)", html, "분석결과.html")
