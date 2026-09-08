"""Pure, persistence-independent storage accounting and allocation rules."""
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import Mapping, Sequence
from uuid import UUID


ACCOUNT_QUOTA_BYTES = 100_000_000
LOGICAL_ACCOUNTING_VERSION = 1
LOGICAL_RECORD_OVERHEAD_BYTES = 64


class StorageRuleViolation(ValueError):
    pass


class InsufficientSharedCapacity(StorageRuleViolation):
    """The requested shared state cannot fit without identifying an Owner."""


def _json_value(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (UUID, date, datetime, Decimal, Enum)):
        return str(value.value if isinstance(value, Enum) else value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise StorageRuleViolation(f"Unsupported logical value type: {type(value).__name__}")


def logical_record_bytes(record_type: str, payload: object) -> int:
    """Return stable v1 logical bytes, independent from PostgreSQL internals."""
    kind = record_type.strip()
    if not kind:
        raise StorageRuleViolation("A logical record type is required.")
    canonical = json.dumps(
        _json_value(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return LOGICAL_RECORD_OVERHEAD_BYTES + len(kind.encode("utf-8")) + len(canonical)


def logical_collection_bytes(
    records: Sequence[tuple[str, object]], *, object_bytes: Sequence[int] = ()
) -> int:
    if any(size < 0 for size in object_bytes):
        raise StorageRuleViolation("Stored object sizes cannot be negative.")
    return sum(logical_record_bytes(kind, payload) for kind, payload in records) + sum(object_bytes)


@dataclass(frozen=True, slots=True)
class AccountCapacity:
    user_id: UUID
    entitlement_bytes: int = ACCOUNT_QUOTA_BYTES
    account_data_bytes: int = 0


@dataclass(frozen=True, slots=True)
class LibraryDemand:
    library_id: UUID
    logical_size_bytes: int
    owner_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class StorageAllocation:
    library_id: UUID
    user_id: UUID
    allocated_bytes: int


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    allocations: tuple[StorageAllocation, ...]
    account_used_bytes: Mapping[UUID, int]


@dataclass(slots=True)
class _Edge:
    to: int
    reverse: int
    capacity: int
    cost: int
    original: int


def allocate_storage(
    accounts: Sequence[AccountCapacity],
    libraries: Sequence[LibraryDemand],
    previous: Mapping[tuple[UUID, UUID], int] | None = None,
) -> AllocationPlan:
    """Find a global feasible allocation, preferring retained and balanced shares."""
    previous = previous or {}
    account_by_id = {item.user_id: item for item in accounts}
    if len(account_by_id) != len(accounts):
        raise StorageRuleViolation("Account IDs must be unique.")
    for account in accounts:
        if account.entitlement_bytes < 0 or account.account_data_bytes < 0:
            raise StorageRuleViolation("Account byte values cannot be negative.")
        if account.account_data_bytes > account.entitlement_bytes:
            raise InsufficientSharedCapacity("Shared storage capacity is insufficient.")
    library_by_id = {item.library_id: item for item in libraries}
    if len(library_by_id) != len(libraries):
        raise StorageRuleViolation("Library IDs must be unique.")
    for library in libraries:
        if library.logical_size_bytes < 0 or not library.owner_ids:
            raise StorageRuleViolation("Every library needs non-negative size and an Owner.")
        if len(set(library.owner_ids)) != len(library.owner_ids):
            raise StorageRuleViolation("Library Owner IDs must be unique.")
        if any(owner not in account_by_id for owner in library.owner_ids):
            raise StorageRuleViolation("Every Owner needs an account capacity.")
    total = sum(item.logical_size_bytes for item in libraries)
    source = 0
    library_node = {item.library_id: index + 1 for index, item in enumerate(libraries)}
    owner_start = 1 + len(libraries)
    owner_node = {item.user_id: owner_start + index for index, item in enumerate(accounts)}
    sink = owner_start + len(accounts)
    graph: list[list[_Edge]] = [[] for _ in range(sink + 1)]

    def add_edge(start: int, end: int, capacity: int, cost: int) -> _Edge:
        forward = _Edge(end, len(graph[end]), capacity, cost, capacity)
        backward = _Edge(start, len(graph[start]), 0, -cost, 0)
        graph[start].append(forward); graph[end].append(backward)
        return forward

    references: list[tuple[UUID, UUID, _Edge]] = []
    retention_reward = total + 1
    for library in sorted(libraries, key=lambda item: str(item.library_id)):
        add_edge(source, library_node[library.library_id], library.logical_size_bytes, 0)
        fair_ceiling = (library.logical_size_bytes + len(library.owner_ids) - 1) // len(library.owner_ids)
        for owner in sorted(library.owner_ids, key=str):
            retained = min(library.logical_size_bytes, max(0, previous.get((library.library_id, owner), 0)))
            boundaries = sorted({0, retained, fair_ceiling, library.logical_size_bytes})
            for start, end in zip(boundaries, boundaries[1:]):
                if end <= start:
                    continue
                cost = (-retention_reward if start < retained else 0) + (1 if start >= fair_ceiling else 0)
                edge = add_edge(library_node[library.library_id], owner_node[owner], end - start, cost)
                references.append((library.library_id, owner, edge))
    for account in sorted(accounts, key=lambda item: str(item.user_id)):
        free = account.entitlement_bytes - account.account_data_bytes
        add_edge(owner_node[account.user_id], sink, free, 0)

    flow = 0
    while flow < total:
        distance = [None] * len(graph); distance[source] = 0
        parent: list[tuple[int, int] | None] = [None] * len(graph)
        changed = True
        for _ in range(len(graph)):
            if not changed: break
            changed = False
            for node, edges in enumerate(graph):
                if distance[node] is None: continue
                for index, edge in enumerate(edges):
                    candidate = distance[node] + edge.cost
                    if edge.capacity and (distance[edge.to] is None or candidate < distance[edge.to]):
                        distance[edge.to] = candidate; parent[edge.to] = (node, index); changed = True
        if parent[sink] is None:
            raise InsufficientSharedCapacity("Shared storage capacity is insufficient.")
        amount = total - flow; node = sink
        while node != source:
            prior, index = parent[node]  # type: ignore[misc]
            amount = min(amount, graph[prior][index].capacity); node = prior
        node = sink
        while node != source:
            prior, index = parent[node]  # type: ignore[misc]
            edge = graph[prior][index]; edge.capacity -= amount
            graph[node][edge.reverse].capacity += amount; node = prior
        flow += amount

    combined: dict[tuple[UUID, UUID], int] = {}
    for library_id, user_id, edge in references:
        combined[(library_id, user_id)] = combined.get((library_id, user_id), 0) + edge.original - edge.capacity
    allocations = tuple(StorageAllocation(library, owner, size) for (library, owner), size in sorted(combined.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))) if size)
    used = {account.user_id: account.account_data_bytes for account in accounts}
    for item in allocations: used[item.user_id] += item.allocated_bytes
    return AllocationPlan(allocations, used)
