"""Pre-download the optional neural models so the first request is fast.

Safe to run offline: any failure is reported and ignored (models then download on first use).
"""
import os


def main():
    try:
        from transformers import pipeline

        pipeline("question-answering", model=os.environ.get("QA_MODEL", "deepset/tinyroberta-squad2"))
        from keybert import KeyBERT

        KeyBERT()
        if os.environ.get("SUMMARY_BACKEND", "").lower() == "transformer":
            pipeline("summarization", model=os.environ.get("SUMMARY_MODEL", "sshleifer/distilbart-cnn-12-6"))
        print("Models downloaded.")
    except Exception as exc:  # noqa: BLE001
        print(f"Model pre-download skipped: {exc}")


if __name__ == "__main__":
    main()
