import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
import os
import tempfile
import time
import markdown # html 변환용 라이브러리 (pip install markdown)
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

st.title("💯 고등학교 수학 기출 vs 부교재 정밀 분석기 (저장 기능 추가)")

# 2. API 키 입력
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("Google API Key를 입력하세요", type="password")
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        genai.configure(api_key=api_key)
        st.success("API 키 확인 완료!")
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

def wait_for_files_active(files):
    st.info("📚 파일 처리를 기다리는 중입니다...")
    bar = st.progress(0)
    for i, name in enumerate(file.name for file in files):
        file = genai.get_file(name)
        while file.state.name == "PROCESSING":
            time.sleep(2)
            file = genai.get_file(name)
        bar.progress((i + 1) / len(files))
    st.success("✅ 파일 준비 완료! 정밀 분석을 시작합니다.")

# --- HTML 변환 함수 ---
def create_html_download(markdown_text):
    html = markdown.markdown(markdown_text, extensions=['tables'])
    # 예쁜 스타일(CSS) 추가
    styled_html = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: 'Malgun Gothic', sans-serif; line-height: 1.6; padding: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; vertical-align: top; }}
            th {{ background-color: #f2f2f2; font-weight: bold; text-align: center; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            h3 {{ border-bottom: 2px solid #333; padding-bottom: 10px; margin-top: 30px; }}
            .keyword {{ font-weight: bold; color: #d32f2f; }}
        </style>
    </head>
    <body>
        <h1>📊 수학 기출 vs 부교재 정밀 분석 결과</h1>
        {html}
    </body>
    </html>
    """
    return styled_html

# 4. 분석 로직
if exam_file and textbook_file and api_key:
    # 세션 상태 초기화 (결과 저장용)
    if 'full_analysis_result' not in st.session_state:
        st.session_state['full_analysis_result'] = ""

    if st.button("서식 통일 분석 시작하기 🚀", use_container_width=True):
        status_text = st.empty()
        st.session_state['full_analysis_result'] = "" # 초기화
        
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

            model = genai.GenerativeModel(
                "gemini-2.5-pro",
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

            full_accumulated_text = "" # 전체 결과 모으기용

            for i, (title, range_desc) in enumerate(batches):
                status_text.info(f"🔄 {title} 정밀 분석 중... ({i+1}/{len(batches)})")
                
                # 화면 출력
                if i > 0:
                    st.markdown("---")
                st.markdown(f"### 📋 {title}")
                
                # 저장용 텍스트에도 제목 추가
                batch_header = f"\n\n### 📋 {title}\n\n"
                full_accumulated_text += batch_header
                
                placeholder = st.empty()
                
                prompt = f"""
                당신은 수학 분석 전문가입니다. 
                두 PDF를 비교하여 **{range_desc}** 상세 분석하세요.
                
                **[출력 서식 가이드라인 - 엄격 준수]**
                모든 문항에 대해 아래 표기법을 토씨 하나 틀리지 말고 따르세요.
                
                1. **부교재 문항 표기:** 반드시 **`p.페이지번호 문항번호`** 형태로만 적으세요. (예: p.80 285번)
                2. **변형 포인트 표기:** 반드시 **글머리 기호(•)**를 사용하고, 키워드는 굵게 처리하세요. (예: • **숫자 변형**: 설명)
                
                **[필수 테이블 양식]**
                | 문항 | 기출문제 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | (번호) | **[원본]**<br>(텍스트 기재, 그림 묘사 금지)<br><br>**[요약]**<br>(내용 요약) | **[원본]**<br>p.00 000번<br><br>**[요약]**<br>(내용 요약) | **▶ 변형 포인트**<br>• **키워드**: 설명<br>• **키워드**: 설명<br><br>**▶ 출제 의도**<br>(평가 목표) |
                
                **[주의사항]**
                - '[원본]' 작성 시 그래프나 도형 묘사는 생략하세요.
                - 해당 문제가 없으면 "해당 없음"만 적으세요.
                """
                
                chunk_text = ""
                stream = model.generate_content([prompt, exam_ref, textbook_ref], stream=True)
                
                try:
                    for chunk in stream:
                        if chunk.text:
                            chunk_text += chunk.text
                            placeholder.markdown(chunk_text, unsafe_allow_html=True)
                except Exception as e:
                    pass
                
                # 배치 끝날 때마다 전체 텍스트에 추가
                full_accumulated_text += chunk_text

            # 모든 루프가 끝나면 세션에 저장
            st.session_state['full_analysis_result'] = full_accumulated_text
            status_text.success("✅ 모든 문항의 상세 분석이 완료되었습니다! 아래 버튼을 눌러 저장하세요.")

        except Exception as e:
            st.error(f"오류 발생: {e}")

    # --- 다운로드 버튼 (분석 결과가 있을 때만 표시) ---
    if st.session_state['full_analysis_result']:
        st.divider()
        st.subheader("💾 분석 결과 저장")
        
        # HTML로 변환
        html_data = create_html_download(st.session_state['full_analysis_result'])
        
        col_d1, col_d2 = st.columns([1, 4])
        with col_d1:
            st.download_button(
                label="📥 HTML 파일로 다운로드",
                data=html_data,
                file_name="수학_기출_분석_결과.html",
                mime="text/html"
            )
        with col_d2:
            st.info("💡 **팁:** 다운로드 받은 HTML 파일을 열고, **[Ctrl + P]**를 눌러 **'PDF로 저장'**을 선택하면 깔끔한 PDF 문서를 만들 수 있습니다.")
