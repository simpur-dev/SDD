from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastmcp import FastMCP

from ..adapters.driven.inference import (
    DeterministicEmbedding,
    MiniMaxEmbedding,
    MiniMaxLLM,
    NullLLM,
)
from ..adapters.driven.powercontext import (
    PowerContextClient,
    PowerContextHandoff,
    PowerContextMemory,
)
from ..adapters.driven.powercontext.health import check_powercontext
from ..adapters.driven.seekdb import (
    SeekdbActivityLog,
    SeekdbCatalog,
    SeekdbClient,
    SeekdbHybridSearch,
)
from ..adapters.driven.seekdb.health import check_seekdb
from ..adapters.driven.workspace import GitWorkspace, SubprocessTestRunner
from ..adapters.driving.mcp.server import build_mcp
from ..application.engines.assembly import AssemblyEngine
from ..application.engines.ingestion import IngestionEngine
from ..application.engines.reconciliation import ReconciliationEngine
from ..application.engines.retrieval import (
    GraphExpander,
    QueryPlanner,
    RetrievalEngine,
)
from ..application.engines.validity import (
    ConflictDetector,
    GapDetector,
    LifecycleValidator,
    ProvenanceDetector,
    SuspectDetector,
    ValidityEngine,
)
from ..application.usecases.complete_task import CompleteTask
from ..application.usecases.get_context import GetContext
from ..application.usecases.ingest_project import IngestProject
from ..application.usecases.resume_task import ResumeTask
from .config import Settings
from .telemetry import Telemetry


@dataclass
class SpecWeaverApp:
    settings: Settings
    telemetry: Telemetry
    mcp: FastMCP
    workspace: GitWorkspace
    test_runner: SubprocessTestRunner
    llm: object
    embedding: object
    catalog: object | None = None
    hybrid: object | None = None
    activity: object | None = None
    memory: object | None = None
    handoff: object | None = None
    usecases: dict = field(default_factory=dict)
    bootstrap_errors: dict = field(default_factory=dict)

    async def doctor(self) -> dict:
        result: dict = {}
        try:
            result["seekdb"] = await check_seekdb(self.settings.seekdb)
        except Exception as exc:  # noqa: BLE001
            result["seekdb"] = {"ok": False, "error": str(exc)}
        try:
            result["powercontext"] = await check_powercontext(
                self.settings.powercontext
            )
        except Exception as exc:  # noqa: BLE001
            result["powercontext"] = {"ok": False, "error": str(exc)}
        result["inference"] = {"provider": self.settings.inference.provider}
        if self.bootstrap_errors:
            result["bootstrap_errors"] = self.bootstrap_errors
        return result

    async def aclose(self) -> None:
        if getattr(self, "_pc_client", None) is not None:
            await self._pc_client.close()


@asynccontextmanager
async def run(settings: Settings | None = None):
    resolved = settings or Settings()
    telemetry = Telemetry()
    bootstrap_errors: dict = {}

    # inference (real MiniMax or local fallback)
    if resolved.inference.provider == "minimax":
        llm = MiniMaxLLM(resolved.inference)
        embedding = MiniMaxEmbedding(resolved.inference)
    else:
        llm = NullLLM()
        embedding = DeterministicEmbedding(resolved.inference.dim)
    dimension = resolved.inference.dim

    # seekdb (engineering catalog + hybrid search)
    catalog = hybrid = activity = None
    pc_client = PowerContextClient(resolved.powercontext)
    try:
        seek_client = SeekdbClient(resolved.seekdb, dimension)
        await asyncio.to_thread(seek_client.initialize)
        catalog = SeekdbCatalog(seek_client)
        hybrid = SeekdbHybridSearch(seek_client)
        activity = SeekdbActivityLog(seek_client)
    except Exception as exc:  # noqa: BLE001
        bootstrap_errors["seekdb"] = str(exc)

    # powercontext (memory + handoff)
    pc_client.open()
    memory = PowerContextMemory(pc_client)
    handoff = PowerContextHandoff(pc_client)

    workspace = GitWorkspace(resolved.workspace)
    test_runner = SubprocessTestRunner(resolved.workspace)

    ingestion_engine = IngestionEngine(embedding)

    # retrieval / validity / assembly engines
    context_cfg = resolved.context
    retrieval_engine = RetrievalEngine(
        QueryPlanner(llm),
        embedding,
        hybrid,
        GraphExpander(catalog),
        n_results=context_cfg.n_results,
    )
    validity_engine = ValidityEngine(
        LifecycleValidator(),
        ConflictDetector(),
        GapDetector(catalog),
        SuspectDetector(catalog),
        ProvenanceDetector(),
    )
    assembly_engine = AssemblyEngine(context_cfg.budget_bytes)
    reconciliation_engine = ReconciliationEngine(embedding)

    get_context_usecase = GetContext(
        retrieval_engine,
        validity_engine,
        assembly_engine,
        telemetry,
        workspace,
    )
    usecases = {
        "ingest_project": IngestProject(
            ingestion_engine, catalog, workspace, telemetry, memory
        ),
        "get_context": get_context_usecase,
        "complete_task": CompleteTask(
            reconciliation_engine,
            catalog,
            activity,
            workspace,
            test_runner,
            telemetry,
            memory,
        ),
        "resume_task": ResumeTask(
            catalog,
            handoff,
            workspace,
            get_context_usecase,
            telemetry,
        ),
    }

    mcp = build_mcp(resolved)
    app = SpecWeaverApp(
        settings=resolved,
        telemetry=telemetry,
        mcp=mcp,
        workspace=workspace,
        test_runner=test_runner,
        llm=llm,
        embedding=embedding,
        catalog=catalog,
        hybrid=hybrid,
        activity=activity,
        memory=memory,
        handoff=handoff,
        usecases=usecases,
        bootstrap_errors=bootstrap_errors,
    )
    app._pc_client = pc_client
    try:
        yield app
    finally:
        await app.aclose()
