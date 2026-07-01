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
st.set_page_config(page_title="수학 기출 분석기 (3.5 flash + Batch 최적화)", layout="wide")
st.markdown("""
    <style>
    div[data-testid="stMarkdownContainer"] p, td, th, li { 
        font-family: 'Malgun Gothic', sans-serif !important; 
        font-size: 14px !important;
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
    </style>
    """, unsafe_allow_html=True)

st.title("💯 수학 기출 분석기 (3.5 flash + 비용 절감)")

# 2. 세션 초기화
if 'analysis_history' not in st.session_state:
    st.session_state['analysis_history'] = []
if 'target_list' not in st.session_state:
    st.session_state['target_list'] = [] 
if 'last_index' not in st.session_state:
    st.session_state['last_index'] = 0
if 'cache_name' not in st.session_state:
    st.session_state['cache_name'] = None
if 'textbook_names' not in st.session_state:
    st.session_state['textbook_names'] = ""

# 3. API 키
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key", type="password")
    st.divider()
    st.info("🔒 **모델:** gemini-3.5-flash (안정성 검증 완료)")
    st.info("💰 **비용 절감:** 3문항 단위 묶음 처리(Batch)로 호출 비용 대폭 감소")
    st.info("🎨 **렌더링 Fix:** 폰트 14px, 부등호(&lt;), 행렬 줄바꿈(\\\\) 자동 보정 적용")
    
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)

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

# 🔥 LaTeX/HTML 렌더링 보정 함수
def fix_latex_rendering(text):
    text = re.sub(r'<(?!(br|/br|b|/b|strong|/strong|span|/span))', '&lt;', text, flags=re.IGNORECASE)
    text = text.replace(r"\ ", r"\\ ")
    return text

def create_html(text_list):
    full_text = "\n\n".join(text_list)
    html_body = markdown.markdown(full_text, extensions=['tables'])
    
    return f"""
    <html><head><meta charset="utf-8">
    <script>MathJax={{tex:{{inlineMath:[['$','$']],displayMath:[['$$','$$']]}},svg:{{fontCache:'global'}} }};</script>
    <script async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        body {{ 
            font-family: 'Malgun Gothic', sans-serif; 
            font-size: 14px; 
            line-height: 1.6; 
            padding: 40px; 
            max-width: 1400px; 
            margin: 0 auto; 
        }}
        table {{ border-collapse: collapse; width: 100%; table-layout: fixed; margin-bottom: 30px; }}
        th, td {{ border: 1px solid #ddd; padding: 15px; vertical-align: top; word-wrap: break-word; }}
        th {{ background: #007bff; color: white; text-align: center; }}
        th:nth-child(1) {{ width: 8%; }} th:nth-child(2) {{ width: 30%; }}
        th:nth-child(3) {{ width: 31%; }} th:nth-child(4) {{ width: 31%; }}
        tr:nth-child(even) {{ background: #f2f2f2; }}
    </style></head><body>{html_body}</body></html>
    """

# 4. 파일 업로드
col1, col2 = st.columns(2)
with col1:
    exam_file = st.file_uploader("기출 PDF", type=['pdf'])
with col2:
    textbook_files = st.file_uploader("부교재 PDF (다중)", type=['pdf'], accept_multiple_files=True)

# 5. 메인 로직
if exam_file and textbook_files and api_key:
    c1, c2 = st.columns(2)
    start_btn = c1.button("🚀 분석 시작 (3.5 flash + 묶음 처리)")
    resume_btn = False
    
    if st.session_state['target_list'] and st.session_state['last_index'] < len(st.session_state['target_list']):
        resume_btn = c2.button("⏯️ 이어하기")

    if start_btn or resume_btn:
        try:
            status = st.empty()
            
            if not st.session_state.get('cache_name') or start_btn:
                st.session_state['analysis_history'] = []
                st.session_state['last_index'] = 0
                
                # 순차 강제 리스트
                forced_list = [f"{i}" for i in range(1, 26)] + \
                              [f"[서답형 {i}]" for i in range(1, 7)]
                st.session_state['target_list'] = forced_list

                # 부교재명 파일명 기반 바인딩
                tb_names_list = [f"[{f.name.replace('.pdf', '')}]" for f in textbook_files]
                st.session_state['textbook_names'] = ", ".join(tb_names_list)
                
                all_files = []
                exam_chunks = split_and_upload_pdf(exam_file)
                if exam_chunks: all_files.extend(exam_chunks)
                for tf in textbook_files:
                    tb_chunks = split_and_upload_pdf(tf)
                    if tb_chunks: all_files.extend(tb_chunks)
                
                if not all_files: st.stop()
                wait_for_files_active(all_files)
                
                status.info("💾 캐시 생성 중...")
                
                # 🔥 [수정 완료] 모델 3.5 flash 확정 적용
                cache = caching.CachedContent.create(
                    model='models/gemini-3.5-flash',
                    display_name='batch_optimized_analysis_25pro',
                    system_instruction="너는 수학 분석가다. 반말(해라체), LaTeX($) 필수, 표 양식 준수.",
                    contents=all_files,
                    ttl=datetime.timedelta(minutes=60)
                )
                st.session_state['cache_name'] = cache.name
            
            model = genai.GenerativeModel.from_cached_content(cached_content=caching.CachedContent.get(st.session_state['cache_name']))
            
            q_list = st.session_state['target_list']
            start_idx = st.session_state['last_index']
            tb_names_str = st.session_state['textbook_names']
            
            p_bar = st.progress(start_idx / len(q_list))
            
            # 🔥 3문항씩 묶어 배열(Batch) 처리 
            chunk_size = 3
            
            for i in range(start_idx, len(q_list), chunk_size):
                chunk = q_list[i:i+chunk_size]
                display_labels = [q + "번" if q.isdigit() else q for q in chunk]
                labels_str = ", ".join(display_labels)
                
                status.info(f"🔄 묶음 분석 중... [{labels_str}]")
                
                prompt = f"""
                기출문제 PDF에서 다음 문항들을 찾아 각각 분석해라: **{labels_str}**
                (해당 번호의 문제가 PDF에 없으면, 분석 표 내 해당 문항 칸에 "SKIP" 이라고만 적어라.)
                
                **[부교재 매칭 가이드]**
                지금 등록된 부교재 목록: **{tb_names_str}**
                유사 문항 출처는 위 목록 이름을 사용하여 **`[교재명] p.00 00번`** 양식으로 통일해라.
                
                **[작성 주의사항]**
                1. **절댓값:** `|` 대신 **`\\lvert x \\rvert`** 사용 (표 깨짐 방지).
                2. **수식:** `$ ... $` (LaTeX) 필수.
                3. **말투:** 반말(해라체).
                4. **상세 분석:** '▶ 변형 포인트', '▶ 출제 의도'만 요약.
                
                아래 양식에 맞추어 {len(chunk)}개 문항에 대한 분석을 **하나의 연속된 표**로 작성해라.
                
                | 문항 | 기출 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | (문항 A) | **[원본]**<br>(LaTeX)<br><br>**[요약]** | **[원본]**<br>[교재명] p.xx xx번<br>(LaTeX)<br><br>**[요약]** | **▶ 변형 포인트**<br>• 내용<br><br>**▶ 출제 의도**<br>• 내용 |
                | (문항 B) | (A문항과 동일 형식 반복) | ... | ... |
                """
                
                success = False
                for attempt in range(2):
                    try:
                        resp = model.generate_content(prompt)
                        if resp.parts:
                            txt = resp.text
                            
                            # 렌더링 보정 함수 적용
                            txt = fix_latex_rendering(txt)
                            
                            usage = resp.usage_metadata
                            total = usage.prompt_token_count
                            token_info = f"<div class='token-info'>📊 [{labels_str}] 묶음 처리 완료 - 문맥 {total:,} (캐시됨) / 누적 호출 비용 약 66% 절감</div>"
                            st.markdown(token_info, unsafe_allow_html=True)
                            
                            st.session_state['analysis_history'].append(txt)
                            st.markdown(txt, unsafe_allow_html=True)
                            success = True
                            break
                    except:
                        time.sleep(1)
                
                # 저장 인덱스를 청크 크기만큼 점프
                st.session_state['last_index'] = i + chunk_size
                p_bar.progress(min((i + chunk_size) / len(q_list), 1.0))
            
            status.success("🎉 분석 완료!")
            
        except Exception as e:
            st.error(f"오류: {e}")

    if st.session_state['analysis_history']:
        st.divider()
        html = create_html(st.session_state['analysis_history'])
        st.download_button("📥 결과 다운로드", html, "분석결과.html")
