import json

from app.rag import ask_rag


def main() -> None:
    question = "2025년 1분기 매출총이익 알려줘"
    result = ask_rag(question, k=4)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()