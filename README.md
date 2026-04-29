
# Moneytoring

Moneytoring은 기업 실적 발표 PDF를 기반으로 사용자의 재무 질문에 답변하는 RAG 기반 재무 분석 챗봇입니다.

단순 키워드 검색이 아니라 질문에서 분기, 재무 지표, 사업부 등 주요 메타데이터를 추출하고, 이를 기반으로 관련 문서를 검색한 뒤 답변을 생성합니다. 또한 표와 수치가 많은 PDF 문서의 특성을 고려하여 문서 텍스트와 페이지 정보를 함께 활용하며, 답변에는 참고한 출처 페이지를 함께 제공합니다.

## 주요 기능

- 기업 실적 발표 PDF 기반 질의응답
- 분기, 재무 지표, 사업부 등 메타데이터 기반 검색
- RAG 기반 문서 검색 및 답변 생성
- 답변 출처 페이지 제공
- PDF 문서 업로드 및 지식 베이스 확장
- Streamlit 기반 사용자 인터페이스 제공
- FastAPI 기반 백엔드 API 서버 구성

## 실행 전 준비

본 프로젝트는 LLM API를 사용하므로 실행 전 API 키를 입력해야 합니다.

`backend/app/llm_client.py` 파일을 열고, 아래 부분에 본인의 API 키를 입력합니다.

```python
API_KEY = "YOUR_API_KEY"
```

## 실행 방법

### 1. 가상환경 생성

#### Windows
```bash
python -m venv venv
venv\Scripts\activate
```

#### Linux / macOS
```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. 패키지 설치

#### Windows
```bash
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
```

#### Linux / macOS
```bash
python3 -m pip install --upgrade pip
pip3 install -r requirements.txt
```

### 3. API 키 입력

실행 전 `backend/app/llm_client.py` 파일을 열고 API 키를 입력합니다.

```python
API_KEY = "YOUR_API_KEY"
```

### 4. 백엔드 서버 실행

프로젝트 루트 폴더에서 백엔드 폴더로 이동합니다.

```bash
cd backend
```

FastAPI 서버를 실행합니다.

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

백엔드 서버가 정상적으로 실행되면 아래 주소에서 확인할 수 있습니다.

```text
http://localhost:8000
```

### 5. 프론트엔드 실행

새 터미널을 열고 프로젝트 루트 폴더로 이동합니다.

```bash
cd moneytoring
```

가상환경을 실행합니다.

#### Windows
```bash
venv\Scripts\activate
```

#### Linux / macOS
```bash
source venv/bin/activate
```

Streamlit 프론트엔드를 실행합니다.

```bash
streamlit run frontend/streamlit_app.py --server.port 8501
```

### 6. 접속 방법

실행 후 브라우저에서 아래 주소로 접속합니다.

```text
http://localhost:8501
```
