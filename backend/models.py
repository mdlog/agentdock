from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


TaskState = Literal["created", "payment_pending", "paid", "running", "completed", "failed", "refunded", "manual_resolution"]


class MetricSet(BaseModel):
    success_rate: float
    uptime_pct: float
    latency_sec: int
    task_volume: int
    recency_score: float
    feedback_score: float
    reputation_score: float


class OnchainIdentity(BaseModel):
    chain_id: int = 56
    registry: str
    agent_id: int
    metadata_verified: bool
    endpoint_verified: bool
    source: str = "ERC-8004 registration"


class Agent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    tagline: str
    description: str
    category: str
    capabilities: list[str]
    price_usd: float
    status: Literal["active", "offline"]
    metrics: MetricSet
    identity: OnchainIdentity
    output_schema: list[str]
    updated_at: str


class AgentList(BaseModel):
    items: list[Agent]
    total: int
    categories: list[str]


class CompareRequest(BaseModel):
    agent_ids: list[str] = Field(min_length=2, max_length=3)


class TaskCreate(BaseModel):
    agent_id: str
    objective: str = Field(min_length=12, max_length=1000)
    constraints: str = Field(default="", max_length=600)
    wallet_address: str | None = None


class AuthorizeRequest(BaseModel):
    payer: str


class PayRequest(BaseModel):
    signature: str


class TaskRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    agent_id: str
    agent_name: str
    objective: str
    constraints: str
    wallet_address: str | None
    state: TaskState
    # Unknown until the merchant answers with its 402 terms, so b402 tasks start
    # without one rather than displaying an invented figure.
    estimated_price_usd: float | None = None
    payment_terms: dict[str, Any] | None = None
    settlement: dict[str, Any] | None = None
    result_preview: str | None = None
    failure_reason: str | None = None
    endpoint_kind: str | None = None
    quote_id: str | None = None
    quote_expires_at: str | None = None
    tx_hash: str | None = None
    result: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    task_id: str
    event: str
    detail: str
    created_at: str


class TaskDetail(BaseModel):
    task: TaskRecord
    audit_events: list[AuditEvent]


class QuoteRequest(BaseModel):
    payer: str


class FeedbackRequest(BaseModel):
    useful: bool
    note: str = Field(default="", max_length=500)


class IntegrationReadiness(BaseModel):
    chain_id: int
    registry_configured: bool
    rpc_reachable: bool
    registry_has_code: bool
    b402_ready: bool
    agent_endpoints_ready: bool
    object_storage_ready: bool
    storage_mode: str
    notes: list[str]


class ScanAgent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    chain_id: int
    is_testnet: bool = False
    token_id: int
    name: str
    description: str
    image_url: str | None = None
    has_source_icon: bool = False
    owner_address: str | None = None
    contract_address: str | None = None
    supported_protocols: list[str] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    activatable: bool = False
    endpoint_checked: bool = False
    # live | auth | payment | dead | error | none — the verdict of a real probe,
    # so the card can say why an agent cannot be activated instead of guessing.
    endpoint_status: str | None = None
    endpoint_note: str | None = None
    endpoint_kind: str | None = None
    x402_supported: bool
    is_verified: bool
    total_score: float | None = None
    rank: int | None = None
    health_score: float | None = None
    total_feedbacks: int = 0
    average_score: float | None = None
    created_at: str | None = None
    updated_at: str | None = None
    source: str
    source_label: str
    synced_at: str


class ScanAgentList(BaseModel):
    items: list[ScanAgent]
    total: int
    source: str = "8004scan"
    chain_id: int = 56
    is_testnet: bool = False
    offset: int = 0
    limit: int = 60


class ScanFeedback(BaseModel):
    model_config = ConfigDict(extra="ignore")
    chain_id: int
    is_testnet: bool
    feedback_id: str
    agent_id: str | int | None = None
    score: float | None = None
    comment: str | None = None
    transaction_hash: str | None = None
    block_number: int | None = None
    user_address: str | None = None
    endpoint: str | None = None
    tags: list[str] = Field(default_factory=list)
    is_revoked: bool
    submitted_at: str | None = None
    synced_at: str
    source: str