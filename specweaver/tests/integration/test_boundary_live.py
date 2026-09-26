"""Live-backend boundary pins (M4 audit). Skipped when containers are down."""
from __future__ import annotations

import pytest
from contract.suites import vec

from specweaver.domain.ports.catalog import HybridQuery
from specweaver.shared.errors import SWError

pytestmark = pytest.mark.integration


async def test_empty_text_hybrid_search_raises_swerror(
    seekdb_adapters,
) -> None:
    _catalog, hybrid = seekdb_adapters
    with pytest.raises(SWError):
        await hybrid.hybrid_search(
            HybridQuery(
                project_id="p",
                text="",
                query_embedding=vec(3),
                n_results=5,
            )
        )
