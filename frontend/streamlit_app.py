import uuid
from datetime import datetime
from typing import Dict, List, Any, Optional

import requests
import streamlit as st

API_BASE_URL = "http://127.0.0.1:8000"

st.set_page_config(
    page_title="Moneytoring",
    page_icon="💬",
    layout="wide",
)


# ── Auth helpers ──────────────────────────────────────────────────────────────

def get_auth_headers() -> dict:
    token = st.session_state.get("auth_token")
    return {"Authorization": f"Bearer {token}"} if token else {}


def login_api(username: str, password: str) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/auth/login",
        data={"username": username, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def register_api(username: str, email: str, password: str) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/auth/register",
        json={"username": username, "email": email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def render_auth_page() -> None:
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        st.title("Moneytoring")
        st.markdown("---")

        tab_login, tab_register = st.tabs(["로그인", "회원가입"])

        with tab_login:
            st.subheader("로그인")
            username = st.text_input("아이디", key="login_username")
            password = st.text_input("비밀번호", type="password", key="login_password")

            if st.button("로그인", use_container_width=True, type="primary"):
                if not username or not password:
                    st.error("아이디와 비밀번호를 입력하세요.")
                else:
                    try:
                        result = login_api(username, password)
                        st.session_state.auth_token = result["access_token"]
                        st.session_state.auth_username = result["username"]
                        st.session_state.chats_loaded = False
                        st.rerun()
                    except requests.HTTPError as e:
                        try:
                            detail = e.response.json().get("detail", "로그인 실패")
                        except Exception:
                            detail = "로그인 실패"
                        st.error(detail)
                    except Exception as e:
                        st.error(f"서버 연결 오류: {e}")

        with tab_register:
            st.subheader("회원가입")
            reg_username = st.text_input("아이디", key="reg_username")
            reg_email = st.text_input("이메일", key="reg_email")
            reg_password = st.text_input("비밀번호", type="password", key="reg_password")
            reg_password2 = st.text_input("비밀번호 확인", type="password", key="reg_password2")

            if st.button("회원가입", use_container_width=True, type="primary"):
                if not reg_username or not reg_email or not reg_password:
                    st.error("모든 항목을 입력하세요.")
                elif reg_password != reg_password2:
                    st.error("비밀번호가 일치하지 않습니다.")
                elif len(reg_password) < 6:
                    st.error("비밀번호는 6자 이상이어야 합니다.")
                else:
                    try:
                        register_api(reg_username, reg_email, reg_password)
                        st.success("회원가입이 완료되었습니다. 로그인 탭에서 로그인하세요.")
                    except requests.HTTPError as e:
                        try:
                            detail = e.response.json().get("detail", "회원가입 실패")
                        except Exception:
                            detail = "회원가입 실패"
                        st.error(detail)
                    except Exception as e:
                        st.error(f"서버 연결 오류: {e}")


# ── Chat DB API ───────────────────────────────────────────────────────────────

def api_load_chats() -> dict:
    response = requests.get(
        f"{API_BASE_URL}/chats",
        headers=get_auth_headers(),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def api_create_chat(chat_id: str, title: str) -> None:
    response = requests.post(
        f"{API_BASE_URL}/chats",
        json={"chat_id": chat_id, "title": title},
        headers=get_auth_headers(),
        timeout=30,
    )
    response.raise_for_status()


def api_update_chat_title(chat_id: str, title: str) -> None:
    response = requests.put(
        f"{API_BASE_URL}/chats/{chat_id}",
        json={"title": title},
        headers=get_auth_headers(),
        timeout=30,
    )
    response.raise_for_status()


def api_delete_chat(chat_id: str) -> None:
    response = requests.delete(
        f"{API_BASE_URL}/chats/{chat_id}",
        headers=get_auth_headers(),
        timeout=30,
    )
    response.raise_for_status()


# ── Document API ──────────────────────────────────────────────────────────────

def delete_document_api(file_name: str) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/documents/delete",
        json={"file_name": file_name},
        headers=get_auth_headers(),
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def request_chat_response(user_input: str, history: list[dict], chat_id: Optional[str] = None) -> dict:
    response = requests.post(
        f"{API_BASE_URL}/chat",
        json={"question": user_input, "k": 8, "history": history, "chat_id": chat_id},
        headers=get_auth_headers(),
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


# ── Utilities ─────────────────────────────────────────────────────────────────

def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")




def generate_chat_id() -> str:
    return str(uuid.uuid4())


def build_empty_chat(title: str = "새 채팅") -> Dict[str, Any]:
    now = now_str()
    return {"title": title, "messages": [], "created_at": now, "updated_at": now}


def create_new_chat(title: Optional[str] = None) -> str:
    clean_title = (title or "").strip() or "새 채팅"
    chat_id = generate_chat_id()
    st.session_state.chats[chat_id] = build_empty_chat(clean_title)
    st.session_state.current_chat_id = chat_id
    try:
        api_create_chat(chat_id, clean_title)
    except Exception:
        pass
    return chat_id


def delete_chat(chat_id: str) -> None:
    if chat_id not in st.session_state.chats:
        return
    was_current = st.session_state.current_chat_id == chat_id
    del st.session_state.chats[chat_id]
    try:
        api_delete_chat(chat_id)
    except Exception:
        pass
    if not st.session_state.chats:
        st.session_state.current_chat_id = None
        return
    if was_current:
        st.session_state.current_chat_id = next(iter(st.session_state.chats))


def delete_current_chat() -> None:
    if st.session_state.current_chat_id:
        delete_chat(st.session_state.current_chat_id)


def ensure_session_state() -> None:
    defaults = {
        "auth_token": None,
        "auth_username": None,
        "chats": {},
        "current_chat_id": None,
        "pending_user_input": None,
        "is_waiting_response": False,
        "chat_search_keyword": "",
        "chats_loaded": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    if (
        st.session_state.current_chat_id is not None
        and st.session_state.current_chat_id not in st.session_state.chats
    ):
        st.session_state.current_chat_id = None


def load_chats_from_db() -> None:
    if st.session_state.chats_loaded:
        return
    try:
        result = api_load_chats()
        chats: Dict[str, Any] = {}
        for c in result.get("chats", []):
            chats[c["id"]] = {
                "title": c["title"],
                "created_at": c["created_at"],
                "updated_at": c["updated_at"],
                "messages": c.get("messages", []),
            }
        st.session_state.chats = chats
        if chats and st.session_state.current_chat_id not in chats:
            st.session_state.current_chat_id = next(iter(chats))
    except Exception:
        pass
    st.session_state.chats_loaded = True


def get_current_chat() -> Dict[str, Any] | None:
    chat_id = st.session_state.current_chat_id
    if not chat_id:
        return None
    return st.session_state.chats.get(chat_id)


def update_chat_title_if_needed(chat: Dict[str, Any], chat_id: str, user_input: str) -> None:
    if chat["title"] == "새 채팅" and user_input.strip():
        title = user_input.strip().replace("\n", " ")
        new_title = title[:24] + ("..." if len(title) > 24 else "")
        chat["title"] = new_title
        try:
            api_update_chat_title(chat_id, new_title)
        except Exception:
            pass


def add_message(
    chat_id: str,
    role: str,
    content: str,
    sources: Optional[List[Dict[str, Any]]] = None,
    parsed_query: Optional[Dict[str, Any]] = None,
) -> None:
    st.session_state.chats[chat_id]["messages"].append(
        {
            "role": role,
            "content": content,
            "sources": sources or [],
            "parsed_query": parsed_query,
            "timestamp": now_str(),
        }
    )
    st.session_state.chats[chat_id]["updated_at"] = now_str()


def render_sources(sources: List[Dict[str, Any]]) -> None:
    if not sources:
        return
    grouped: Dict[str, List[int]] = {}
    for source in sources:
        file_name = source.get("file_name", "unknown")
        page = source.get("page")
        grouped.setdefault(file_name, [])
        if isinstance(page, int):
            grouped[file_name].append(page)

    st.markdown("**출처**")
    for file_name, pages in grouped.items():
        pages = sorted(set(pages))
        page_str = ",".join(str(p) for p in pages) if pages else "-"
        with st.container(border=True):
            st.markdown(f"**{file_name}** / p.{page_str}")


def search_chats(keyword: str) -> List[tuple[str, Dict[str, Any]]]:
    keyword = keyword.strip().lower()
    chats_items = list(st.session_state.chats.items())
    if not keyword:
        return chats_items

    results: List[tuple[str, Dict[str, Any]]] = []
    for chat_id, chat in chats_items:
        matched = keyword in chat.get("title", "").lower()
        if not matched:
            for msg in chat.get("messages", []):
                if keyword in msg.get("content", "").lower():
                    matched = True
                    break
        if matched:
            results.append((chat_id, chat))
    return results


# ── Sidebar ───────────────────────────────────────────────────────────────────

def render_sidebar() -> None:
    with st.sidebar:
        st.title("Moneytoring")

        username = st.session_state.get("auth_username", "")
        col1, col2 = st.columns([2, 1])
        with col1:
            st.caption(f"로그인: {username}")
        with col2:
            if st.button("로그아웃", key="logout_btn"):
                st.session_state.auth_token = None
                st.session_state.auth_username = None
                st.session_state.chats = {}
                st.session_state.current_chat_id = None
                st.session_state.chats_loaded = False
                st.rerun()

        st.markdown("---")

        with st.popover("+ 새 채팅", use_container_width=True):
            st.markdown("### 새 채팅 만들기")
            new_chat_title = st.text_input(
                "채팅 이름",
                placeholder="예: 2025년 1분기 실적 질문",
                key="new_chat_title_input",
            )
            if st.button("생성", use_container_width=True):
                create_new_chat(new_chat_title)
                st.rerun()

        st.markdown("---")
        st.subheader("채팅 목록")

        search_keyword = st.text_input(
            "채팅 검색",
            placeholder="제목 또는 대화 내용 검색",
            key="chat_search_keyword",
        )

        if search_keyword.strip():
            matched_chats = search_chats(search_keyword)
            if matched_chats:
                with st.container(border=True):
                    st.caption("검색 결과")
                    for chat_id, chat in matched_chats:
                        if st.button(
                            chat['title'],
                            key=f"search_result_{chat_id}",
                            use_container_width=True,
                        ):
                            st.session_state.current_chat_id = chat_id
                            st.rerun()
            else:
                with st.container(border=True):
                    st.caption("검색 결과가 없습니다.")

        st.markdown("---")

        chats_items = list(st.session_state.chats.items())
        chats_items.sort(key=lambda x: x[1]["updated_at"], reverse=True)

        if not chats_items:
            st.caption("아직 채팅이 없습니다.")

        for chat_id, chat in chats_items:
            is_current = chat_id == st.session_state.current_chat_id
            title = chat["title"]
            label = f"👉 {title}" if is_current else title
            if st.button(label, key=f"chat_btn_{chat_id}", use_container_width=True):
                st.session_state.current_chat_id = chat_id
                st.rerun()

        st.markdown("---")
        if st.button("채팅 지우기", use_container_width=True, type="secondary"):
            delete_current_chat()
            st.rerun()


# ── Chat rendering ─────────────────────────────────────────────────────────────

def render_chat_messages(chat: Dict[str, Any]) -> None:
    if not chat["messages"]:
        st.info("질문을 입력하면 여기에서 대화가 시작됩니다.")
        return
    for msg in chat["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                render_sources(msg.get("sources", []))


def submit_user_input(user_input: str) -> None:
    if st.session_state.current_chat_id is None:
        return
    chat_id = st.session_state.current_chat_id
    chat = st.session_state.chats[chat_id]
    update_chat_title_if_needed(chat, chat_id, user_input)
    add_message(chat_id, "user", user_input)
    st.session_state.pending_user_input = user_input
    st.session_state.is_waiting_response = True


def process_pending_response() -> None:
    if not st.session_state.is_waiting_response:
        return

    user_input = st.session_state.pending_user_input
    if not user_input:
        st.session_state.is_waiting_response = False
        return

    chat_id = st.session_state.current_chat_id
    if chat_id is None:
        st.session_state.pending_user_input = None
        st.session_state.is_waiting_response = False
        return

    chat = st.session_state.chats[chat_id]
    recent_history = [
        {"role": m["role"], "content": m["content"], "parsed_query": m.get("parsed_query")}
        for m in chat["messages"][-6:]
    ]

    with st.chat_message("assistant"):
        with st.spinner("생각 중..."):
            try:
                api_result = request_chat_response(user_input, recent_history, chat_id=chat_id)
                answer = api_result.get("answer", "")
                sources = api_result.get("sources", [])
                parsed_query = api_result.get("parsed_query", None)
            except requests.HTTPError as e:
                if e.response.status_code == 401:
                    answer = "세션이 만료되었습니다. 다시 로그인해주세요."
                    st.session_state.auth_token = None
                else:
                    answer = f"API 오류가 발생했습니다: {e}"
                sources = []
                parsed_query = None
            except Exception as e:
                answer = f"오류가 발생했습니다: {e}"
                sources = []
                parsed_query = None

        st.markdown(answer)
        render_sources(sources)

    add_message(chat_id, "assistant", answer, sources=sources, parsed_query=parsed_query)
    st.session_state.pending_user_input = None
    st.session_state.is_waiting_response = False
    st.rerun()


def handle_user_input() -> None:
    if st.session_state.current_chat_id is None:
        return
    user_input = st.chat_input("삼성전자 최근 실적에 대해 질문해보세요.")
    if not user_input:
        return
    submit_user_input(user_input)
    st.rerun()


def render_empty_main() -> None:
    st.title("RAG Chatbot")
    st.markdown("---")
    st.info("왼쪽의 + 새 채팅 버튼을 눌러 대화를 시작하세요.")


# ── Document manager ──────────────────────────────────────────────────────────

def request_documents() -> dict:
    response = requests.get(
        f"{API_BASE_URL}/documents",
        headers=get_auth_headers(),
        timeout=120,
    )
    response.raise_for_status()
    return response.json()


def upload_document_api(uploaded_file) -> dict:
    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
    response = requests.post(
        f"{API_BASE_URL}/documents/upload",
        files=files,
        headers=get_auth_headers(),
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def render_document_manager() -> None:
    st.subheader("문서 관리")
    st.markdown("### PDF 업로드")
    uploaded_file = st.file_uploader("PDF 파일 선택", type=["pdf"], key="document_upload")

    if uploaded_file is not None:
        if st.button("업로드 및 반영", use_container_width=True):
            with st.spinner("PDF 업로드 및 지식베이스 반영 중..."):
                try:
                    result = upload_document_api(uploaded_file)
                    st.success(result.get("message", "업로드 완료"))
                    st.rerun()
                except Exception as e:
                    st.error(f"업로드 실패: {e}")

    st.markdown("---")
    st.markdown("### 등록된 PDF")

    try:
        documents = request_documents().get("documents", [])
    except Exception as e:
        st.error(f"문서 목록 조회 실패: {e}")
        return

    if not documents:
        st.info("등록된 PDF가 없습니다.")
        return

    for doc in documents:
        file_name = doc.get("file_name", "unknown")
        file_type = doc.get("file_type", "pdf")
        with st.container(border=True):
            col1, col2 = st.columns([6, 1])
            with col1:
                st.markdown(f"**{file_name}** ({file_type})")
            with col2:
                if st.button("삭제", key=f"delete_{file_name}", type="secondary"):
                    with st.spinner("PDF 및 인덱스 삭제 중..."):
                        try:
                            result = delete_document_api(file_name)
                            st.success(result.get("message", "삭제 완료"))
                            st.rerun()
                        except Exception as e:
                            st.error(f"삭제 실패: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ensure_session_state()

    if not st.session_state.auth_token:
        render_auth_page()
        return

    load_chats_from_db()

    render_sidebar()

    current_chat = get_current_chat()
    tab_chat, tab_docs = st.tabs(["채팅", "문서 관리"])

    with tab_chat:
        if current_chat is None:
            render_empty_main()
        else:
            col1, col2 = st.columns([8, 2])
            with col1:
                st.title(current_chat["title"])
            with col2:
                pass
            st.markdown("---")
            render_chat_messages(current_chat)
            process_pending_response()
            handle_user_input()

    with tab_docs:
        render_document_manager()


if __name__ == "__main__":
    main()
