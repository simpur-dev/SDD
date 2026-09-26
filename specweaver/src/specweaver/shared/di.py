from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from fastmcp import FastMCP

from ..adapters.driven.inference import (
    DeterministicEmbedding,
    MiniMaxEmbedding,
    NullLLM,
    OpenAIChatLLM,
    OpenAIEmbedding,
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
from ..application.usecases.create_handoff import CreateHandoff
from ..application.usecases.explain_source import ExplainSource
from ..application.usecases.get_context import GetContext
from ..application.usecases.ingest_project import IngestProject
from ..application.usecases.record_decision import RecordDecision
from ..application.usecases.report_progress import ReportProgress
from ..application.usecases.resume_task import ResumeTask
from ..application.usecases.verify_state import VerifyState
from ..domain.ports.activity import ActivityLogPort
from ..domain.ports.catalog import CatalogPort, HybridSearchPort
from ..domain.ports.handoff import HandoffPort
from ..domain.ports.inference import (
    EmbeddingGatewayPort,
    LLMGatewayPort,
)
from ..domain.ports.memory import MemoryPort
from .config import Settings
from .telemetry import Telemetry


@dataclass
class SpecWeaverApp:
    settings: Settings
    telemetry: Telemetry
    workspace: GitWorkspace
    test_runner: SubprocessTestRunner
    llm: LLMGatewayPort
    embedding: EmbeddingGatewayPort
    pc_client: PowerContextClient
    mcp: FastMCP | None = None
    catalog: CatalogPort | None = None
    hybrid: HybridSearchPort | None = None
    activity: ActivityLogPort | None = None
    memory: MemoryPort | None = None
    handoff: HandoffPort | None = None
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

    async def ensure_scope(self, project_id: str, scope_id: str = "") -> str:
        """Return the given scope id, resolving the project's PowerContext scope."""
        if scope_id:
            return scope_id
        return await self.memory.resolve_scope(project_id)

    async def aclose(self) -> None:
        await self.pc_client.close()


@dataclass
class InferenceStack:
    llm: LLMGatewayPort
    embedding: EmbeddingGatewayPort
    warning: str | None = None


def build_inference(settings: Settings) -> InferenceStack:
    """Pick the LLM/embedding adapters for the configured provider.

    Chat is OpenAI-compatible across providers; embeddings differ:
    minimax uses its texts/vectors schema, qianwen the standard one, and
    deepseek has no embeddings endpoint (measured 404, docs/02 §7.3) so it
    keeps deterministic vectors.
    """
    inference = settings.inference
    provider = inference.provider
    chat_providers = ("minimax", "deepseek", "qianwen")
    if provider not in chat_providers:
        return InferenceStack(
            NullLLM(), DeterministicEmbedding(inference.dim)
        )
    if not inference.api_key:
        return InferenceStack(
            NullLLM(),
            DeterministicEmbedding(inference.dim),
            warning=(
                f"provider={provider} but no api_key; falling back to "
                "rule mode"
            ),
        )
    if provider == "minimax":
        embedding = MiniMaxEmbedding(inference)
    elif provider == "qianwen":
        embedding = OpenAIEmbedding(inference)
    else:
        embedding = DeterministicEmbedding(inference.dim)
    return InferenceStack(OpenAIChatLLM(inference), embedding)


@asynccontextmanager
async def run(settings: Settings | None = None):
    resolved = settings or Settings()
    telemetry = Telemetry()
    bootstrap_errors: dict = {}

    # inference (provider-backed or rule-mode fallback)
    stack = build_inference(resolved)
    llm, embedding = stack.llm, stack.embedding
    if stack.warning:
        bootstrap_errors["inference"] = stack.warning
    dimension = resolved.inference.dim

    # seekdb (engineering catalog + hybrid search)
    catalog = hybrid = activity = None
    pc_client = PowerContextClient(resolved.powercontext, telemetry=telemetry)
    try:
        seek_client = SeekdbClient(
            resolved.seekdb, dimension, telemetry=telemetry
        )
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
        QueryPlanner(llm, telemetry),
        embedding,
        hybrid,
        GraphExpander(catalog),
        n_results=context_cfg.n_results,
        catalog=catalog,
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
        activity,
    )
    create_handoff_usecase = CreateHandoff(handoff, telemetry)
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
        "create_handoff": create_handoff_usecase,
        "record_decision": RecordDecision(telemetry, memory),
        "report_progress": ReportProgress(
            telemetry, memory, create_handoff_usecase
        ),
        "verify_state": VerifyState(
            catalog, workspace, telemetry, activity, memory, test_runner
        ),
        "explain_source": ExplainSource(catalog, telemetry),
    }

    app = SpecWeaverApp(
        settings=resolved,
        telemetry=telemetry,
        workspace=workspace,
        test_runner=test_runner,
        llm=llm,
        embedding=embedding,
        pc_client=pc_client,
        catalog=catalog,
        hybrid=hybrid,
        activity=activity,
        memory=memory,
        handoff=handoff,
        usecases=usecases,
        bootstrap_errors=bootstrap_errors,
    )
    app.mcp = build_mcp(app)
    try:
        yield app
    finally:
        await app.aclose()
