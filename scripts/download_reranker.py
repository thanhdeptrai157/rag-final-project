from __future__ import annotations

import os

from sentence_transformers import CrossEncoder

from app.core.config import Config


def main() -> None:
    os.makedirs(Config.RERANKER_CACHE_DIR, exist_ok=True)
    os.environ.setdefault("HF_HOME", Config.RERANKER_CACHE_DIR)
    os.environ.setdefault("TRANSFORMERS_CACHE", Config.RERANKER_CACHE_DIR)

    print(f"[RERANKER] Downloading model: {Config.RERANKER_MODEL}")
    print(f"[RERANKER] Cache dir: {Config.RERANKER_CACHE_DIR}")

    kwargs = {
        "max_length": Config.RERANKER_MAX_LENGTH,
        "device": os.getenv("RERANKER_DEVICE", "cpu"),
    }

    try:
        CrossEncoder(
            Config.RERANKER_MODEL,
            **kwargs,
            tokenizer_args={
                "cache_dir": Config.RERANKER_CACHE_DIR,
                "local_files_only": False,
            },
            automodel_args={
                "cache_dir": Config.RERANKER_CACHE_DIR,
                "local_files_only": False,
            },
            config_args={
                "cache_dir": Config.RERANKER_CACHE_DIR,
                "local_files_only": False,
            },
        )
    except TypeError:
        CrossEncoder(Config.RERANKER_MODEL, **kwargs)

    print("[RERANKER] Model is ready.")


if __name__ == "__main__":
    main()
