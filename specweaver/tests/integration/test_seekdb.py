from __future__ import annotations

import pytest
from contract.suites import catalog_suite, hybrid_suite

pytestmark = pytest.mark.integration


async def test_seekdb_catalog_and_hybrid(seekdb_adapters) -> None:
    catalog, hybrid = seekdb_adapters
    await catalog_suite(catalog)
    await hybrid_suite(hybrid)
