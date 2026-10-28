"""Cross-encoder reranker that runs inside the container. No clause text leaves the machine.

A cross-encoder reads the clause and one candidate together and says how well they match. That is
more exact than comparing two separate vectors, but too slow to run on the whole library, which is
why it only sees the ~30 candidates left after search. Runs on the CPU through ONNX (fastembed),
so there is no PyTorch in the image. The model downloads once into `cache_dir` on first use.
"""

import math
from functools import cached_property

from app.providers.base import ProviderError


def sigmoid(x: float) -> float:
    """The model returns a raw score on any scale. This squeezes it into 0 to 1."""
    return 1 / (1 + math.exp(-x))


class LocalReranker:
    def __init__(self, model: str, cache_dir: str | None = None):
        self.model = model
        self._cache_dir = cache_dir

    @cached_property
    def _encoder(self):
        import onnxruntime
        from fastembed.rerank.cross_encoder import TextCrossEncoder  # slow import, so loaded late

        onnxruntime.disable_telemetry_events()  # the app makes no outbound calls of its own

        try:
            return TextCrossEncoder(model_name=self.model, cache_dir=self._cache_dir)
        except Exception as e:  # noqa: BLE001 - unknown model, no network for the download, etc.
            raise ProviderError(f"could not load reranker model {self.model}: {e}") from e

    def score(self, query: str, docs: list[str]) -> list[float]:
        if not docs:
            return []
        return [sigmoid(s) for s in self._encoder.rerank(query, docs)]
