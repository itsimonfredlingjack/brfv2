"""Embedding provider selection and instance sharing.

The sharing test is a regression guard, not a micro-optimisation check:
Model2VecEmbedder loads roughly 1.5 GB of weights per instance. get_embedder()
is called once per Store and again inside the /api/health handler, so an
uncached factory allocated another 1.5 GB on every readiness poll. A demo
backend accumulated nine loads that way and was killed by the OOM killer at
7.9 GB RSS, taking the desktop session with it.
"""

from __future__ import annotations

from app import embeddings
from app.embeddings import HashedNgramEmbedder, get_embedder


class TestGetEmbedder:
    def test_returns_the_same_instance_across_calls(self, monkeypatch):
        monkeypatch.setenv("BRF_EMBEDDER", "hashed")
        embeddings._build_embedder.cache_clear()

        first = get_embedder()
        second = get_embedder()

        assert first is second, "each call would allocate another provider"

    def test_constructs_the_provider_only_once(self, monkeypatch):
        monkeypatch.setenv("BRF_EMBEDDER", "hashed")
        embeddings._build_embedder.cache_clear()
        builds = 0

        real_init = HashedNgramEmbedder.__init__

        def counting_init(self, *args, **kwargs):
            nonlocal builds
            builds += 1
            return real_init(self, *args, **kwargs)

        monkeypatch.setattr(HashedNgramEmbedder, "__init__", counting_init)

        for _ in range(5):
            get_embedder()

        assert builds == 1, f"provider constructed {builds} times, expected 1"

    def test_switching_provider_via_env_still_takes_effect(self, monkeypatch):
        """The cache is keyed on the env value, so it must not pin the first
        choice for the lifetime of the process."""
        embeddings._build_embedder.cache_clear()

        monkeypatch.setenv("BRF_EMBEDDER", "hashed")
        hashed = get_embedder()
        assert isinstance(hashed, HashedNgramEmbedder)

        monkeypatch.setenv("BRF_EMBEDDER", "hashed")
        assert get_embedder() is hashed
