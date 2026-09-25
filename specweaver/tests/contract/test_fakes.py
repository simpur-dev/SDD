from __future__ import annotations

from fakes import (
    InMemoryCatalog,
    InMemoryHandoff,
    InMemoryHybridSearch,
    InMemoryMemory,
)

from .suites import (
    catalog_suite,
    handoff_suite,
    hybrid_suite,
    memory_suite,
)


async def test_catalog_contract() -> None:
    await catalog_suite(InMemoryCatalog())


async def test_hybrid_contract() -> None:
    catalog = InMemoryCatalog()
    await catalog_suite(catalog)
    await hybrid_suite(InMemoryHybridSearch(catalog))


async def test_memory_contract() -> None:
    await memory_suite(InMemoryMemory(), "scope-fake")


async def test_handoff_contract() -> None:
    await handoff_suite(InMemoryHandoff(), "scope-fake", "src-fake-1")
