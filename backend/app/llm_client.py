# backend/app/llm_client.py

from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Iterable, List

from google import genai
from google.genai import types


GEMINI_API_KEY = "Gogle-GenAI-API-Key" #구글 제미니 API 키를 환경 변수로 설정하거나 직접 입력하세요.

TEXT_MODEL = "gemini-2.5-flash"
VISION_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client

    if _client is None:
        if not GEMINI_API_KEY:
            raise EnvironmentError("GEMINI_API_KEY가 설정되지 않았습니다.")
        _client = genai.Client(api_key=GEMINI_API_KEY)

    return _client


def _clean_response_text(text: str | None) -> str:
    return (text or "").strip()


def _image_part_from_path(image_path: str | Path) -> types.Part:
    image_path = Path(image_path)

    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일이 없습니다: {image_path}")

    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = "image/png"

    with open(image_path, "rb") as f:
        image_bytes = f.read()

    return types.Part.from_bytes(
        data=image_bytes,
        mime_type=mime_type,
    )


def generate_text(
    prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0,
) -> str:
    client = get_client()

    response = client.models.generate_content(
        model=model or TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=temperature,
        ),
    )

    return _clean_response_text(response.text)


def generate_with_image(
    prompt: str,
    image_path: str | Path,
    *,
    model: str | None = None,
    temperature: float = 0,
) -> str:
    client = get_client()

    response = client.models.generate_content(
        model=model or VISION_MODEL,
        contents=[
            _image_part_from_path(image_path),
            prompt,
        ],
        config=types.GenerateContentConfig(
            temperature=temperature,
        ),
    )

    return _clean_response_text(response.text)


def generate_with_images(
    prompt: str,
    image_paths,
    *,
    model: str | None = None,
    temperature: float = 0,
) -> str:
    client = get_client()

    parts = []
    for image_path in image_paths:
        parts.append(_image_part_from_path(image_path))
    parts.append(prompt)

    response = client.models.generate_content(
        model=model or VISION_MODEL,
        contents=parts,
        config=types.GenerateContentConfig(
            temperature=temperature,
        ),
    )

    return _clean_response_text(response.text)


def embed_text(text: str, *, model: str | None = None) -> List[float]:
    client = get_client()

    response = client.models.embed_content(
        model=model or EMBEDDING_MODEL,
        contents=text,
    )

    return list(response.embeddings[0].values)


def embed_texts(texts: Iterable[str], *, model: str | None = None) -> List[List[float]]:
    text_list = list(texts)
    if not text_list:
        return []

    client = get_client()

    response = client.models.embed_content(
        model=model or EMBEDDING_MODEL,
        contents=text_list,
    )

    return [list(item.values) for item in response.embeddings]