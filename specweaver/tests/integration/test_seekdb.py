from __future__ import annotations

import pytest
from contract.suites import (
    activity_suite,
    catalog_isolation_suite,
    catalog_suite,
    hybrid_suite,
)

pytestmark = pytest.mark.integration


async def test_seekdb_catalog_and_hybrid(seekdb_adapters) -> None:
    catalog, hybrid = seekdb_adapters
    await catalog_suite(catalog)
    await hybrid_suite(hybrid)
    await catalog_isolation_suite(catalog)


async def test_seekdb_activity_log(seekdb_activity) -> None:
    activity, project = seekdb_activity
    await activity_suite(activity, project)
