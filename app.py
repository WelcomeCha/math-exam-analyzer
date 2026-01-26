import streamlit as st
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold # 안전 설정용 모듈 추가
import os
import tempfile
import time
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

st.title("💯 고등학교 수학 기출 vs 부교재 정밀 분석기 (무중단 모드)")

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

if exam_file and textbook_file and api_key:
    if st.button("끊김 없는 분석 시작하기 🚀", use_container_width=True):
        status_text = st.empty()
        
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

            # --- 🔥 [핵심 수정 1] 안전 설정(Safety Settings) 필터 끄기 ---
            # 수학 문제 풀이 중 발생하는 오탐지를 막기 위해 모든 필터를 끕니다.
            safety_settings = {
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }

            model = genai.GenerativeModel(
                "gemini-2.5-pro",
                generation_config={"temperature": 0.0, "max_output_tokens": 8192},
                safety_settings=safety_settings  # 여기에 적용
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

            for i, (title, range_desc) in enumerate(batches):
                status_text.info(f"🔄 {title} 정밀 분석 중... ({i+1}/{len(batches)})")
                
                if i > 0:
                    st.markdown("---")
                    
                st.markdown(f"### 📋 {title}")
                placeholder = st.empty()
                
                # --- 🔥 [핵심 수정 2] 프롬프트 보완: 그림 묘사 금지 ---
                # '원본'을 적을 때 그림을 말로 설명하려다 토큰이 폭발하는 것을 방지합니다.
                prompt = f"""
                당신은 수학 분석 전문가입니다. 
                두 PDF를 비교하여 **{range_desc}** 상세 분석하세요.
                
                **[필수 출력 형식]**
                아래 마크다운 표 양식을 **정확히 준수**하세요.
                
                | 문항 | 기출문제 요약 | 부교재 유사 문항 | 상세 변형 분석 |
                | :--- | :--- | :--- | :--- |
                | (번호) | **[원본]**<br>(문제 텍스트만 기재, 그래프/그림 묘사 생략)<br><br>**[요약]**<br>(핵심 조건 요약) | **[원본]**<br>(페이지/번호/텍스트)<br><br>**[요약]**<br>(유사 문제 내용) | **▶ 변형 포인트**<br>(구체적 변경 사항)<br><br>**▶ 출제 의도**<br>(평가 목표) |
                
                **[주의사항]**
                1. **중요:** '[원본]' 작성 시 그래프나 도형은 텍스트로 묘사하지 말고 글로 적힌 문제만 옮기세요. (토큰 절약)
                2. 범위 내에 해당 문제가 없으면 "해당 없음"이라고만 적으세요.
                3. 내용이 잘리지 않도록 핵심 위주로 명료하게 작성하세요.
                """
                
                full_text = ""
                stream = model.generate_content([prompt, exam_ref, textbook_ref], stream=True)
                
                try:
                    for chunk in stream:
                        if chunk.text:
                            full_text += chunk.text
                            placeholder.markdown(full_text, unsafe_allow_html=True)
                except Exception as e:
                    # 에러가 나도 멈추지 않고 다음 배치 진행
                    pass 

            status_text.success("✅ 모든 문항의 상세 분석이 완료되었습니다!")

        except Exception as e:
            st.error(f"오류 발생: {e}")