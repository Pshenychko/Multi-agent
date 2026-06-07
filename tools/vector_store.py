"""FAISS vector store for transaction pattern memory — uses Gemini embedding API."""
import os, json, pickle, requests
import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

from dotenv import load_dotenv
load_dotenv()

INDEX_PATH = "faiss_index"
DIM = 768
API_KEY = os.getenv("GOOGLE_API_KEY")


def _get_embedding(text: str) -> np.ndarray:
    """Get embedding via Gemini REST API."""
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent?key={API_KEY}",
        json={"content": {"parts": [{"text": text}]}},
        timeout=15,
    )
    resp.raise_for_status()
    values = resp.json()["embedding"]["values"]
    return np.array(values, dtype=np.float32)


def build_index(documents: list[dict]):
    """Build FAISS index from documents [{text, metadata}]."""
    if not faiss:
        print("faiss-cpu not installed")
        return
    os.makedirs(INDEX_PATH, exist_ok=True)
    embeddings = []
    for doc in documents:
        emb = _get_embedding(doc["text"])
        embeddings.append(emb)

    matrix = np.vstack(embeddings)
    index = faiss.IndexFlatL2(DIM)
    index.add(matrix)
    faiss.write_index(index, f"{INDEX_PATH}/index.faiss")
    with open(f"{INDEX_PATH}/docs.pkl", "wb") as f:
        pickle.dump(documents, f)
    print(f"Built FAISS index with {len(documents)} documents")


def search(query: str, k: int = 3) -> list[dict]:
    """Search FAISS index."""
    if not faiss or not os.path.exists(f"{INDEX_PATH}/index.faiss"):
        return []
    index = faiss.read_index(f"{INDEX_PATH}/index.faiss")
    with open(f"{INDEX_PATH}/docs.pkl", "rb") as f:
        docs = pickle.load(f)
    emb = _get_embedding(query).reshape(1, -1)
    distances, indices = index.search(emb, k)
    return [{"text": docs[i]["text"], "metadata": docs[i].get("metadata", {}),
             "score": float(distances[0][j])} for j, i in enumerate(indices[0]) if i < len(docs)]


def build_patterns_index():
    """Pre-build index with known spending patterns."""
    import pandas as pd
    df = pd.read_csv("data/transactions.csv", parse_dates=["date"])

    patterns = []
    for cat in df[df["amount"] < 0]["category"].unique():
        cat_data = df[df["category"] == cat]
        monthly = cat_data.groupby(cat_data["date"].dt.to_period("M"))["amount"].sum().abs()
        patterns.append({
            "text": f"Category {cat}: avg monthly ${monthly.mean():.0f}, range ${monthly.min():.0f}-${monthly.max():.0f}, {len(cat_data)} total transactions",
            "metadata": {"type": "category_summary", "category": cat},
        })

    for merchant in df["merchant"].value_counts().head(15).index:
        m_data = df[df["merchant"] == merchant]
        patterns.append({
            "text": f"Merchant {merchant}: {len(m_data)} transactions, total ${abs(m_data['amount'].sum()):.0f}, category {m_data['category'].iloc[0]}",
            "metadata": {"type": "merchant_summary", "merchant": merchant},
        })

    build_index(patterns)


if __name__ == "__main__":
    build_patterns_index()
