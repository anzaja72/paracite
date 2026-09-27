from pathlib import Path

from paracite.classifier.jev import FallbackClassifier, JevHttpClient
from paracite.classifier.mock import MockPrecisionClassifier
from paracite.config import Settings
from paracite.retrieval.local_store import LocalBm25Store
from paracite.retrieval.weknora import FallbackRetriever, WeKnoraHttpClient


def build_retriever(settings: Settings):
    local = LocalBm25Store.from_seed(settings.public_base_url, corpus_dir=Path(settings.corpus_dir))
    if settings.weknora_url and settings.weknora_api_key and settings.weknora_kb_id:
        remote = WeKnoraHttpClient(
            settings.weknora_url,
            settings.weknora_api_key,
            settings.weknora_kb_id,
            fallback_get=local.get,
        )
        return FallbackRetriever(remote, local), local
    return local, local


def build_classifier(settings: Settings):
    mock = MockPrecisionClassifier()
    if settings.jev_api_key:
        live = JevHttpClient(settings.jev_api_key, settings.jev_api_url, settings.jev_model)
        return FallbackClassifier(live, mock)
    return mock
