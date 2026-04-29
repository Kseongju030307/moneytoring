from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import json
import re

from langchain_community.vectorstores import FAISS
from langchain_core.embeddings import Embeddings

from app.llm_client import embed_texts, generate_text, generate_with_images
from app.query_parser import parse_query
from app.prompts import build_chat_prompt, build_finance_prompt

BASE_DIR = Path(__file__).resolve().parent.parent
FAISS_DIR = BASE_DIR / "data" / "faiss_index"
PAGE_IMAGE_DIR = BASE_DIR / "data" / "page_images"


class GeminiEmbeddings(Embeddings):
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return embed_texts(texts)

    def embed_query(self, text: str) -> List[float]:
        return embed_texts([text])[0]


def print_selected_docs(question: str, docs) -> None:
    print("\n[QUESTION]")
    print(question)

    print("\n[SELECTED DOCS]")
    if not docs:
        print("(no docs)")
        return

    for i, doc in enumerate(docs, start=1):
        file_name = doc.metadata.get("file_name", "unknown")
        page = doc.metadata.get("page", None)
        preview = doc.page_content[:300].replace("\n", " ").strip()

        print(f"{i}. {file_name} / p.{page}")
        print(f"   summary: {preview}")


def normalize_to_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def get_embeddings() -> GeminiEmbeddings:
    return GeminiEmbeddings()


def load_vectorstore(index_dir: Path) -> FAISS:
    if not index_dir.exists():
        raise FileNotFoundError(f"FAISS 인덱스 폴더가 없습니다: {index_dir}")

    index_file = index_dir / "index.faiss"
    pkl_file = index_dir / "index.pkl"

    if not index_file.exists() or not pkl_file.exists():
        raise FileNotFoundError(f"FAISS 인덱스 파일이 없습니다: {index_dir}")

    embeddings = get_embeddings()

    vectorstore = FAISS.load_local(
        str(index_dir),
        embeddings,
        allow_dangerous_deserialization=True,
    )
    return vectorstore


def quarter_to_index_dir(quarter: str) -> Optional[Path]:
    """
    예:
    2025_Q3 -> backend/data/faiss_index/2025_3Q_conference_kor
    """
    match = re.fullmatch(r"(\d{4})_Q([1-4])", quarter.strip())
    if not match:
        return None

    year, q = match.groups()
    folder_name = f"{year}_{q}Q_conference_kor"
    folder_path = FAISS_DIR / folder_name

    if folder_path.exists():
        return folder_path
    return None


def list_all_index_dirs() -> List[Path]:
    if not FAISS_DIR.exists():
        return []

    results = []
    for child in FAISS_DIR.iterdir():
        if not child.is_dir():
            continue

        if (child / "index.faiss").exists() and (child / "index.pkl").exists():
            results.append(child)

    results.sort()
    return results


def resolve_target_index_dirs(quarters: List[str]) -> List[Path]:
    dirs = []

    for q in quarters:
        index_dir = quarter_to_index_dir(q)
        if index_dir is not None:
            dirs.append(index_dir)

    return dirs


def build_search_query(parsed: Dict[str, Any], original_question: str) -> str:
    parts: List[str] = [original_question]

    quarters = normalize_to_list(parsed.get("quarters", []))
    metrics = normalize_to_list(parsed.get("metrics", []))
    business_units = normalize_to_list(parsed.get("business_units", []))

    for quarter in quarters:
        parts.append(quarter)

        quarter_aliases = {
            "2024_Q1": "2024년 1분기 1Q'24 1Q24",
            "2024_Q2": "2024년 2분기 2Q'24 2Q24",
            "2024_Q3": "2024년 3분기 3Q'24 3Q24",
            "2024_Q4": "2024년 4분기 4Q'24 4Q24",
            "2025_Q1": "2025년 1분기 1Q'25 1Q25",
            "2025_Q2": "2025년 2분기 2Q'25 2Q25",
            "2025_Q3": "2025년 3분기 3Q'25 3Q25",
            "2025_Q4": "2025년 4분기 4Q'25 4Q25",
        }
        if quarter in quarter_aliases:
            parts.append(quarter_aliases[quarter])

    for metric in metrics:
        parts.append(metric)

    for unit in business_units:
        parts.append(unit)

    deduped = []
    seen = set()
    for part in parts:
        part = str(part).strip()
        if part and part not in seen:
            seen.add(part)
            deduped.append(part)

    return " ".join(deduped).strip()


def filter_docs(parsed: Dict[str, Any], docs) -> list:
    filtered = docs

    # 1,2,3 페이지 제외
    non_cover_docs = [
        doc for doc in filtered
        if doc.metadata.get("page") not in [0, 1, 2, 3]
    ]
    if non_cover_docs:
        filtered = non_cover_docs

    return filtered


def limit_one_per_file(docs) -> list:
    result = []
    seen_files = set()

    for doc in docs:
        file_name = doc.metadata.get("file_name", "unknown")
        if file_name in seen_files:
            continue
        seen_files.add(file_name)
        result.append(doc)

    return result


def limit_per_file(docs, max_per_file: int = 3) -> list:
    result = []
    counts = {}

    for doc in docs:
        file_name = doc.metadata.get("file_name", "unknown")
        counts.setdefault(file_name, 0)

        if counts[file_name] >= max_per_file:
            continue

        counts[file_name] += 1
        result.append(doc)

    return result


def similarity_search_from_dirs(
    index_dirs: List[Path],
    search_query: str,
    k_per_dir: int = 10,
) -> List:
    """
    여러 분기 폴더의 FAISS를 각각 검색한 뒤 score 기준으로 합쳐서 반환
    score는 낮을수록 유사
    """
    scored_results: List[Tuple[Any, float]] = []

    for index_dir in index_dirs:
        try:
            vectorstore = load_vectorstore(index_dir)
            results = vectorstore.similarity_search_with_score(search_query, k=k_per_dir)

            for doc, score in results:
                if doc.metadata.get("page") in [0, 1]:
                    continue
                scored_results.append((doc, float(score)))

        except Exception as e:
            print(f"[INDEX SEARCH ERROR] {index_dir} -> {repr(e)}")

    scored_results.sort(key=lambda x: x[1])

    unique_results = []
    seen = set()

    for doc, score in scored_results:
        key = (
            doc.metadata.get("file_name", ""),
            doc.metadata.get("page", None),
            doc.page_content[:200],
        )
        if key in seen:
            continue
        seen.add(key)
        unique_results.append(doc)

    return unique_results


def get_relevant_docs(question: str, parsed: dict, k: int = 5):
    quarters = normalize_to_list(parsed.get("quarters", []))
    search_query = build_search_query(parsed, question)

    # 1. 분기가 있으면 해당 분기 폴더만 검색
    if quarters:
        target_index_dirs = resolve_target_index_dirs(quarters)

        # 요청한 분기 폴더가 하나도 없으면 바로 종료
        if not target_index_dirs:
            return [], parsed, True

        docs = similarity_search_from_dirs(
            target_index_dirs,
            search_query,
            k_per_dir=10,
        )

        docs = filter_docs(parsed, docs)

        if len(target_index_dirs) >= 2:
            docs = limit_one_per_file(docs)
            final_k = min(len(target_index_dirs), len(docs))
        else:
            docs = limit_per_file(docs, max_per_file=3)
            final_k = min(3, len(docs))

        return docs[:final_k], parsed, False

    # 2. 분기 없는 일반 검색이면 전체 인덱스 폴더 대상으로 검색
    all_index_dirs = list_all_index_dirs()
    if not all_index_dirs:
        return [], parsed, False

    docs = similarity_search_from_dirs(
        all_index_dirs,
        search_query,
        k_per_dir=5,
    )
    docs = filter_docs(parsed, docs)

    final_k = min(k, len(docs))
    return docs[:final_k], parsed, False


def docs_to_sources(docs) -> List[Dict[str, Any]]:
    sources = []

    for doc in docs:
        sources.append(
            {
                "file_name": doc.metadata.get("file_name", "unknown"),
                "page": doc.metadata.get("page", None),
            }
        )

    return sources


def get_page_image_path(file_name: str, page: int) -> Optional[str]:
    stem = Path(file_name).stem
    image_path = PAGE_IMAGE_DIR / stem / f"page_{page:03d}.png"
    if image_path.exists():
        return str(image_path)
    return None


def format_docs_for_vlm(docs) -> str:
    chunks = []

    for i, doc in enumerate(docs, start=1):
        file_name = doc.metadata.get("file_name", "unknown")
        page = doc.metadata.get("page", "?")
        text = str(doc.metadata.get("page_text", doc.page_content)).strip()
        summary = str(doc.metadata.get("page_summary", doc.page_content)).strip()

        chunks.append(
            f"[문서 {i}]\n"
            f"파일명: {file_name}\n"
            f"페이지: {page}\n"
            f"페이지 요약:\n{summary}\n\n"
            f"원문 텍스트:\n{text}"
        )

    return "\n\n".join(chunks)


def parse_json_response(text: str) -> Dict[str, Any]:
    text = text.strip()

    if text.startswith("```"):
        text = re.sub(r"^```json\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^```\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        text = match.group(0)

    return json.loads(text)


def call_vlm(question: str, parsed: Dict[str, Any], docs) -> Dict[str, Any]:
    intent = parsed.get("intent", "general")

    if intent == "general":
        prompt = build_chat_prompt(question)
        content = generate_text(
            prompt,
            temperature=0,
        )
    else:
        context = format_docs_for_vlm(docs)
        prompt = build_finance_prompt(question, context)

        image_paths = []
        for doc in docs:
            file_name = doc.metadata.get("file_name", "")
            page = doc.metadata.get("page", None)

            if not file_name or page is None:
                continue

            image_path = get_page_image_path(file_name, page)
            if not image_path:
                continue

            image_paths.append(image_path)

        if not image_paths:
            raise ValueError("전달할 페이지 이미지가 없습니다.")

        content = generate_with_images(
            prompt,
            image_paths,
            temperature=0,
        )

    print("\n[MODEL RAW RESPONSE]\n", content, "\n")

    try:
        parsed_response = parse_json_response(content)
        answer = parsed_response.get("answer", "").strip()
        if not answer:
            answer = content
    except Exception:
        answer = content

    return {
        "answer": answer,
        "raw_response": content,
    }


def quarter_to_korean_text(quarter: str) -> str:
    match = re.fullmatch(r"(\d{4})_Q([1-4])", quarter.strip())
    if not match:
        return quarter
    year, q = match.groups()
    return f"{year}년 {q}분기"


def ask_rag(question: str, parsed: dict | None = None, k: int = 5) -> Dict[str, Any]:
    if parsed is None:
        parsed = parse_query(question)

    if parsed.get("intent") == "general":
        result = call_vlm(question, parsed, docs=[])
        answer = result.get("answer", "").strip() or "안녕! 뭐 도와줄까?"
        return {
            "question": question,
            "parsed_query": parsed,
            "answer": answer,
            "sources": [],
            "raw_response": result.get("raw_response", ""),
            "retrieved_sources": [],
        }

    docs, parsed, missing_requested_quarter = get_relevant_docs(question, parsed=parsed, k=k)

    if missing_requested_quarter:
        quarter_texts = [quarter_to_korean_text(q) for q in normalize_to_list(parsed.get("quarters", []))]
        quarter_text = ", ".join(quarter_texts) if quarter_texts else "요청한 분기"

        return {
            "question": question,
            "parsed_query": parsed,
            "answer": f"제공된 자료에는 {quarter_text}에 해당하는 인덱스가 없습니다.",
            "sources": [],
            "raw_response": "",
            "retrieved_sources": [],
        }

    print_selected_docs(question, docs)
    sources = docs_to_sources(docs)

    if not docs:
        return {
            "question": question,
            "parsed_query": parsed,
            "answer": "관련 문서를 찾지 못했습니다.",
            "sources": [],
            "raw_response": "",
            "retrieved_sources": [],
        }

    try:
        result = call_vlm(question, parsed, docs)
        answer = result.get("answer", "").strip()
        if not answer:
            answer = "제공된 자료를 바탕으로 답변을 생성하지 못했습니다."
    except Exception as e:
        print("[ASK_RAG ERROR]", repr(e))
        answer = "응답 생성 중 오류가 발생했습니다."

    return {
        "question": question,
        "parsed_query": parsed,
        "answer": answer,
        "sources": sources,
        "raw_response": result.get("raw_response", "") if "result" in locals() else "",
        "retrieved_sources": sources,
    }