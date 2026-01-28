import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import tempfile
import time
import markdown
from dotenv import load_dotenv

# 1. 설정 및 디자인
st.set_page_config(page_title="수학 기출 분석기 (Final)", layout="wide")

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

st.title("💯 고등학교 수학 기출 vs 부교재 정밀 분석기")

# 2. API 키 및 모델 설정
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    
    st.divider()
    
    # --- 🔥 [수정] 사용자 목록에 있는 '실제 모델'로만 구성 ---
    st.subheader("🤖 AI 모델 선택")
    model_option = st.radio(
        "상황에 맞춰 선택하세요:",
        ("품질 우선 (2.5 Pro)", "대용량/속도 (2.5 Flash)"),
        index=0,
        help="평소엔 2.5 Pro를 쓰시고, 파일이 커서 에러가 나면 2.5 Flash를 쓰세요."
    )

    # 선택에 따른 실제 모델명 매핑 (사용자 목록 기반)
    if "Pro" in model_option:
        model_name = "gemini-2.5-pro"
    else:
        model_name = "gemini-2.5-flash" # 목록에 있는 모델 사용
    
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        st.success(f"현재 모드: {model_name}")
    else:
        st.warning("API 키를 먼저 입력해주세요.")

# 3. 파일 업로드
col1, col2 = st.columns(2)
with col1:
    st.subheader("📄 학교 기출문제 PDF")
    exam_file = st.file_uploader("기출문제 파일을 업로드하세요", type=['pdf'], key="exam")

with col2:
    st.subheader("📘 부교재 PDF")
    textbook_file = st.file_uploader("부교재 파일을 업로드하세요", type=['pdf'], key="text")

# 대용량 파일 대기 함수
def wait_for_files_active(files):
    st.info("📚 대용량 파일 처리를 기다리는 중입니다... (1분 이상 소요될 수 있습니다)")
    bar = st.progress(0)
    for i, name in enumerate(file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            time.sleep(5)
            file = genai.get_file(name)
        
        if file.state.name == "FAILED":
            st.error(f"❌ 파일 처리 실패: {file.uri}")
            st.error("구글 서버가 이 PDF를 읽는 데 실패했습니다.")
            st.stop()

        bar.progress((i + 1) / len(files))
    st.success("✅ 파일 준비 완료! 정밀 분석을 시작합니다.")

# HTML 변환 함수
def create_html_download(markdown_text):
    html_content = markdown.markdown(markdown_text, extensions=['tables'])
    styled_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>수학 분석 결과</title>
        <script>
        MathJax = {{
          tex: {{
            inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
            displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
          }},
          svg: {{
            fontCache: 'global'
          }}
        }};
        </script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <style>
            body {{ font-family: 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif; line-height: 1.6; padding: 40px; max-width: 1200px; margin: 0 auto; }}
            h1 {{ text-align: center; border-bottom: 3px solid #333; padding-bottom: 20px; }}
            h3 {{ background-color: #f8f9fa; padding: 10px; border-left: 5px solid #007bff; margin-top: 40px; margin-bottom: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 30px; }}
            th, td {{ border: 1px solid #ddd; padding: 15px; text-align: left; vertical-align: top; }}
            th {{ background-color: #007bff; color: white; font-weight: bold; text-align: center; white-space: nowrap; }}
            tr:nth-child(even) {{ background-color: #f2f2f2; }}
            .keyword {{ font-weight: bold; color: #d32f2f; }}
        </style>
    </head>
    <body>
        <h1>📊 수학 기출 vs 부교재 정밀 분석 결과</h1>
        {html_content}
    </body>
    </html>
    """
    return styled_html

# 4. 분석 로직
if exam_file and textbook_file and api_key:
    if 'full_analysis_result' not in st.session_state:
        st.session_state['full_analysis_result'] = ""

    if st.button("분석 시작하기 🚀", use_container_width=True):
        status_text = st.empty()
        st.session_state['full_analysis_result'] = ""
        
        try:
            def upload_to_gemini(uploaded_file, mime_type="application/pdf"):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                    tmp.write(uploaded_file.getvalue())
                    tmp_path = tmp.name
                file_ref = genai.upload_file(tmp_path, mime_type=mime_type)
                return file_ref

            exam_ref = upload_to_gemini(exam_file)
            textbook_ref = upload_to_gemini(textbook_file)
            
            wait_for_files_active([exam_ref, textbook_ref])

            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            # --- 🔥 검증된 모델 사용 ---
            model = genai.GenerativeModel(
                model_name, # 위에서 선택한 변수 (gemini-2.5-pro 또는 gemini-2.5-flash)
                generation_config={"temperature": 0.0, "max_output_tokens": 8192},
                safety_settings=safety_settings
            )

            batches = [
                ("1번 ~ 3번", "기출문제의 1번부터 3번 문항까지만"),
                ("4번 ~ 6번", "기출문제의 4번부터 6번 문항까지만"),
                ("7번 ~ 9번", "기출문제의 7번부터 9번 문항까지만"),
                ("10번 ~ 12번", "기출문제의 10번부터 12번 문항까지만"),
                ("13번 ~ 15번", "기출문제의 13번부터 15번 문항까지만"),
                ("16번 ~ 18번", "기출문제의 16번부터 18번 문항까지만"),
                ("19번 ~ 21번", "기출문제의 19번부터 21번 문항까지만"),
                ("22번 ~ 마지막", "기출문제의 22번부터 서술형 끝번(마지막) 문항까지")
            ]

            full_accumulated_text = ""

            for i, (title, range_desc) in enumerate(batches):
                status_text.info(f"🔄 {title} 정밀 분석 중... ({i+1}/{len(batches)})")
                
                if i > 0:
                    st.markdown("---")
                st.markdown(f"### 📋 {title}")
                
                batch_header = f"\n\n### 📋 {title}\n\n"
                full_accumulated_text += batch_header
                
                placeholder = st.empty()
                
                prompt = f"""
                당신은 수학 분석 전문가입니다. 
                두 PDF를 비교하여 **{range_desc}** 상세 분석하세요.
                
                **[출력 서식 가이드라인 - 엄격 준수]**
                1. **부교재 문항 표기:** - 첫 줄: **`p.페이지번호 문항번호`** (예: p.80 285번)
                   - 두 번째 줄부터: **[원본]** 태그 아래에 **부교재 문제 원문을 반드시 텍스트로 적으세요.** (그림 묘사 제외)
                
                2. **변형 포인트 표기:** - 반드시 **글머리 기호(•)**를 사용하고, 키워드는 굵게 처리하세요.
                
                **[필수 테이블 양식]**
                **반드시 표 앞에 빈 줄을 하나 띄우고 표를 작성하세요.**
                
                | 문항 | 기출문제 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | (번호) | **[원본]**<br>(기출 문제 텍스트)<br><br>**[요약]**<br>(핵심 요약) | **[원본]**<br>p.00 000번<br>(부교재 문제 원문 텍스트 필수 기재)<br><br>**[요약]**<br>(내용 요약) | **▶ 변형 포인트**<br>• **키워드**: 설명<br>• **키워드**: 설명<br><br>**▶ 출제 의도**<br>(평가 목표) |
                
                **[주의사항]**
                - '[원본]' 작성 시 그래프나 도형 묘사는 생략하고 텍스트만 적으세요.
                - 해당 문제가 없으면 "해당 없음"만 적으세요.
                """
                
                chunk_text = ""
                try:
                    stream = model.generate_content([prompt, exam_ref, textbook_ref], stream=True)
                    for chunk in stream:
                        if chunk.text:
                            chunk_text += chunk.text
                            placeholder.markdown(chunk_text, unsafe_allow_html=True)
                except Exception as e:
                    if "400" in str(e) and "Pro" in model_name:
                        st.error("🚨 2.5 Pro 모델 용량 초과!")
                        st.warning("👈 왼쪽 사이드바에서 **'대용량/속도 (2.5 Flash)'**를 선택하고 다시 시도하세요.")
                        st.stop()
                    else:
                        st.error(f"오류 발생: {e}")
                
                full_accumulated_text += chunk_text + "\n\n"

            st.session_state['full_analysis_result'] = full_accumulated_text
            status_text.success("✅ 모든 문항의 상세 분석이 완료되었습니다! 아래 버튼을 눌러 저장하세요.")

        except Exception as e:
            st.error(f"오류 발생: {e}")

    # --- 다운로드 버튼 ---
    if st.session_state['full_analysis_result']:
        st.divider()
        st.subheader("💾 분석 결과 저장")
        
        html_data = create_html_download(st.session_state['full_analysis_result'])
        
        col_d1, col_d2 = st.columns([1, 4])
        with col_d1:
            st.download_button(
                label="📥 HTML 파일로 다운로드",
                data=html_data,
                file_name="수학_기출_분석_결과(최종).html",
                mime="text/html"
            )
        with col_d2:
            st.info("💡 **팁:** 다운로드 받은 파일을 열고 '인쇄(Ctrl+P) -> PDF로 저장' 하시면 됩니다.")
