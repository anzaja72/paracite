from paracite.classifier.jev import FallbackClassifier, JevHttpClient
from paracite.classifier.laya import LayaRouterClient, laya_mode_enabled
from paracite.classifier.mock import MockPrecisionClassifier
from paracite.config import Settings
from paracite.retrieval.local_store import LocalBm25Store
from paracite.retrieval.weknora import FallbackRetriever, WeKnoraHttpClient


def build_retriever(settings: Settings):
    # seed ES ([FIXTURE]) y piloto CO, lado a lado. No se mezcla el piloto en seed.json.
    local = LocalBm25Store.from_seed(settings.public_base_url)
    if settings.weknora_url and settings.weknora_api_key and settings.weknora_kb_id:
        remote = WeKnoraHttpClient(
            settings.weknora_url,
            settings.weknora_api_key,
            settings.weknora_kb_id,
            fallback_get=local.get,
        )
        return FallbackRetriever(remote, local), local
    return local, local


def build_laya(settings: Settings) -> LayaRouterClient | None:
    """Router perezoso. No descarga pesos: el primer predict lo haría, no el arranque."""
    if not laya_mode_enabled(settings.laya_mode):
        return None
    return LayaRouterClient()


def build_classifier(settings: Settings):
    mock = MockPrecisionClassifier()
    if settings.jev_api_key:
        live = JevHttpClient(settings.jev_api_key, settings.jev_api_url, settings.jev_model)
        return FallbackClassifier(live, mock)
    return mock
