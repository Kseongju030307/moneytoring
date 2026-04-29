from pathlib import Path
from typing import List
import re

import fitz  # PyMuPDF
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import FAISS

from app.llm_client import generate_with_image, embed_texts


BASE_DIR = Path(__file__).resolve().parent.parent
PDF_DIR = BASE_DIR / "data" / "pdfs"

FAISS_DIR = BASE_DIR / "data" / "faiss_index"
PAGE_IMAGE_DIR = BASE_DIR / "data" / "page_images"
PAGE_SUMMARY_DIR = BASE_DIR / "data" / "page_summaries"


class GeminiEmbeddings(Embeddings):
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return embed_texts(texts)

    def embed_query(self, text: str) -> List[float]:
        return embed_texts([text])[0]


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ensure_dirs() -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    FAISS_DIR.mkdir(parents=True, exist_ok=True)
    PAGE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    PAGE_SUMMARY_DIR.mkdir(parents=True, exist_ok=True)


def save_page_image(doc: fitz.Document, pdf_path: Path, page_index: int) -> Path:
    page = doc.load_page(page_index)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))

    out_dir = PAGE_IMAGE_DIR / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    image_path = out_dir / f"page_{page_index + 1:03d}.png"
    pix.save(str(image_path))
    return image_path


def get_page_summary_cache_path(pdf_path: Path, page_index: int) -> Path:
    out_dir = PAGE_SUMMARY_DIR / pdf_path.stem
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"page_{page_index + 1:03d}.txt"


def generate_page_summary(page_text: str, image_path: Path) -> str:
    prompt = f"""
You are generating a retrieval-friendly summary for a document page.

Instructions:
- Write the summary in Korean.
- Summarize what this page mainly contains.
- Mention the main topic or page type if possible, such as a summary page, table, chart, business section, financial section, technical explanation, report section, or appendix.
- Mention important entities, keywords, metrics, categories, or topics that are clearly visible on the page.
- If the page includes structured information such as a table, chart, or list, briefly mention that.
- Keep it concise, about 2 to 4 sentences.
- Do not copy the whole page text.
- Do not use markdown or bullet points.
- This summary will be used for retrieval, so it should be descriptive and searchable.

Page text:
{page_text[:2000]}
""".strip()

    return generate_with_image(
        prompt=prompt,
        image_path=image_path,
        temperature=0,
    )


def load_or_create_page_summary(
    pdf_path: Path,
    page_index: int,
    page_text: str,
    image_path: Path,
) -> str:
    cache_path = get_page_summary_cache_path(pdf_path, page_index)

    if cache_path.exists():
        summary = cache_path.read_text(encoding="utf-8", errors="ignore").strip()
        if summary:
            return summary

    summary = generate_page_summary(page_text, image_path)
    summary = clean_text(summary)

    cache_path.write_text(summary, encoding="utf-8")
    return summary


def extract_documents_from_pdf(pdf_path: Path) -> List[Document]:
    documents: List[Document] = []

    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            text = clean_text(page.get_text("text").strip())

            if not text:
                continue

            image_path = save_page_image(doc, pdf_path, page_index)

            page_summary = load_or_create_page_summary(
                pdf_path=pdf_path,
                page_index=page_index,
                page_text=text,
                image_path=image_path,
            )

            if not page_summary:
                page_summary = text[:500]

            documents.append(
                Document(
                    page_content=page_summary,
                    metadata={
                        "file_name": pdf_path.name,
                        "page": page_index + 1,
                        "source": f"{pdf_path.name}#page={page_index + 1}",
                        "file_type": "pdf",
                        "page_text": text,
                        "page_summary": page_summary,
                    },
                )
            )
    finally:
        doc.close()

    return documents


def build_pdf_vectorstore(pdf_path: Path) -> int:
    documents = extract_documents_from_pdf(pdf_path)
    if not documents:
        raise ValueError(f"임베딩할 문서가 없습니다: {pdf_path.name}")

    embeddings = GeminiEmbeddings()
    vectorstore = FAISS.from_documents(documents, embeddings)

    index_dir = FAISS_DIR / pdf_path.stem
    index_dir.mkdir(parents=True, exist_ok=True)
    vectorstore.save_local(str(index_dir))

    return len(documents)


def load_pdf_vectorstore(pdf_path: Path) -> FAISS:
    embeddings = GeminiEmbeddings()
    index_dir = FAISS_DIR / pdf_path.stem

    if not index_dir.exists():
        raise FileNotFoundError(f"FAISS 인덱스가 없습니다: {index_dir}")

    return FAISS.load_local(
        str(index_dir),
        embeddings,
        allow_dangerous_deserialization=True,
    )


def list_pdf_files() -> List[Path]:
    ensure_dirs()
    return sorted(PDF_DIR.glob("*.pdf"))


def build_all_pdf_vectorstores() -> int:
    ensure_dirs()

    pdf_files = list_pdf_files()
    total_docs = 0

    for pdf_file in pdf_files:
        doc_count = build_pdf_vectorstore(pdf_file)
        total_docs += doc_count
        print(f"[완료] {pdf_file.name} | 문서 수: {doc_count}")

    return total_docs


def main() -> None:
    ensure_dirs()

    print("BASE_DIR:", BASE_DIR)
    print("PDF_DIR:", PDF_DIR, PDF_DIR.exists())

    pdf_files = list_pdf_files()
    print(f"[PDF 파일 수] {len(pdf_files)}")

    total_docs = build_all_pdf_vectorstores()
    print(f"[전체 문서 수] {total_docs}")

    print("=== ingest 완료 ===")


if __name__ == "__main__":
    main()