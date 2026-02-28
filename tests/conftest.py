import sys
import uuid
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import chromadb
from chromadb.config import Settings

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import server


class TestEmbeddingFunction:
    default_space = "cosine"

    def __call__(self, input):
        embeddings = []
        for text in input:
            base = float(len(text or ""))
            vec = [
                base,
                base + 1.0,
                base + 2.0,
                base + 3.0,
                base + 4.0,
                base + 5.0,
                base + 6.0,
                base + 7.0,
            ]
            embeddings.append(vec)
        return embeddings

    def embed_documents(self, input):
        return self.__call__(input)

    def embed_query(self, input):
        return self.__call__(input)

    def name(self):
        return "test"

    def is_legacy(self):
        return False

    def get_config(self):
        return {}


@pytest.fixture
def test_collection():
    client = chromadb.Client(settings=Settings(anonymized_telemetry=False))
    collection = client.get_or_create_collection(
        name=f"test_memory_{uuid.uuid4()}",
        embedding_function=TestEmbeddingFunction(),
    )
    return collection


@pytest.fixture
def client(test_collection):
    server._collection = test_collection
    with TestClient(server.app) as test_client:
        yield test_client
    server._collection = None
