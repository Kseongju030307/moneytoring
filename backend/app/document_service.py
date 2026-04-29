from pathlib import Path
import shutil

from fastapi import HTTPException, UploadFile

from app.ingest import (
    PDF_DIR,
    FAISS_DIR,
    PAGE_IMAGE_DIR,
    PAGE_SUMMARY_DIR,
    ensure_dirs,
    build_pdf_vectorstore,
)


def list_documents() -> list[dict]:
    ensure_dirs()

    files: list[dict] = []
    for pdf_file in sorted(PDF_DIR.glob("*.pdf")):
        files.append(
            {
                "file_name": pdf_file.name,
                "size": pdf_file.stat().st_size,
                "file_type": "pdf",
            }
        )

    return files


def save_uploaded_pdf(file: UploadFile) -> Path:
    ensure_dirs()

    if not file.filename:
        raise HTTPException(status_code=400, detail="파일 이름이 없습니다.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    save_path = PDF_DIR / file.filename

    if save_path.exists():
        raise HTTPException(status_code=400, detail="같은 이름의 PDF가 이미 존재합니다.")

    try:
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        if save_path.exists():
            save_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"파일 저장 중 오류가 발생했습니다: {e}")

    return save_path


def upload_pdf(file: UploadFile) -> dict:
    save_path = save_uploaded_pdf(file)

    try:
        added_docs = build_pdf_vectorstore(save_path)

        return {
            "message": "PDF 업로드 및 인덱스 생성이 완료되었습니다.",
            "file_name": save_path.name,
            "added_docs": added_docs,
        }

    except Exception as e:
        # 업로드는 됐는데 ingest/인덱스 생성 실패한 경우 롤백
        if save_path.exists():
            save_path.unlink(missing_ok=True)

        page_image_dir = PAGE_IMAGE_DIR / save_path.stem
        page_summary_dir = PAGE_SUMMARY_DIR / save_path.stem
        faiss_dir = FAISS_DIR / save_path.stem

        if page_image_dir.exists():
            shutil.rmtree(page_image_dir, ignore_errors=True)
        if page_summary_dir.exists():
            shutil.rmtree(page_summary_dir, ignore_errors=True)
        if faiss_dir.exists():
            shutil.rmtree(faiss_dir, ignore_errors=True)

        raise HTTPException(status_code=500, detail=f"PDF 처리 중 오류가 발생했습니다: {e}")


def delete_pdf(file_name: str) -> dict:
    ensure_dirs()

    pdf_path = PDF_DIR / file_name
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="삭제할 PDF를 찾을 수 없습니다.")

    stem = pdf_path.stem
    page_image_dir = PAGE_IMAGE_DIR / stem
    page_summary_dir = PAGE_SUMMARY_DIR / stem
    faiss_dir = FAISS_DIR / stem

    try:
        pdf_path.unlink()

        if page_image_dir.exists():
            shutil.rmtree(page_image_dir, ignore_errors=True)

        if page_summary_dir.exists():
            shutil.rmtree(page_summary_dir, ignore_errors=True)

        if faiss_dir.exists():
            shutil.rmtree(faiss_dir, ignore_errors=True)

        return {
            "message": "PDF 및 관련 인덱스 삭제가 완료되었습니다.",
            "file_name": file_name,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"삭제 중 오류가 발생했습니다: {e}")