from typing import Union, List
import re
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2"


def get_chunks(texts: Union[str, List[str]], max_chars: int = 800, overlap: int = 100) -> List[str]:
    if isinstance(texts, str):
        texts = [texts]

    chunks: List[str] = []

    for text in texts:
        text = (text or "").strip()
        if not text:
            continue

        sentences = re.split(r"(?<=[.!?])\s+", text)
        sentences = [s.strip() for s in sentences if s and s.strip()]

        current = ""
        for s in sentences:
            if not current:
                current = s
                continue

            candidate = current + " " + s
            if len(candidate) <= max_chars:
                current = candidate
            else:
                chunks.append(current)
                if overlap > 0 and len(current) > overlap:
                    tail = current[-overlap:]
                    current = tail + " " + s
                else:
                    current = s

        if current:
            chunks.append(current)

    return chunks


def get_embeddings(chunks: List[str], model_name: str = MODEL_NAME, normalize: bool = True) -> np.ndarray:
    if not chunks:
        return np.zeros((0, 0), dtype=np.float32)

    model = SentenceTransformer(model_name)
    embeddings = model.encode(
        chunks,
        convert_to_numpy=True,
        normalize_embeddings=normalize,
        show_progress_bar=False
    )
    return embeddings


def cos_compare(v: np.ndarray, w: np.ndarray) -> float:
    v = np.asarray(v).reshape(1, -1)
    w = np.asarray(w).reshape(1, -1)

    return float(cosine_similarity(v, w)[0][0])
