from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass

from schema_sentry.domain.enums import PipelineCriticality, Severity
from schema_sentry.domain.models import ColumnRef, SchemaChange


@dataclass(frozen=True, slots=True)
class PipelineDefinition:
    key: str
    airflow_dag_id: str
    owner: str
    criticality: PipelineCriticality


@dataclass(frozen=True, slots=True)
class LineageEdge:
    pipeline: PipelineDefinition
    upstream: ColumnRef
    downstream: ColumnRef


@dataclass(frozen=True, slots=True)
class PipelineImpact:
    pipeline: PipelineDefinition
    downstream: ColumnRef
    path: tuple[LineageEdge, ...]


_CRITICALITY_RANK = {
    PipelineCriticality.LOW: 0,
    PipelineCriticality.MEDIUM: 1,
    PipelineCriticality.HIGH: 2,
    PipelineCriticality.CRITICAL: 3,
}


class LineageGraph:
    def __init__(self, edges: Sequence[LineageEdge]) -> None:
        grouped: dict[ColumnRef, list[LineageEdge]] = defaultdict(list)
        for edge in edges:
            grouped[edge.upstream].append(edge)
        self.edges_by_upstream = {
            upstream: tuple(
                sorted(
                    values,
                    key=lambda edge: (
                        edge.pipeline.key,
                        edge.downstream.dataset.schema,
                        edge.downstream.dataset.table,
                        edge.downstream.name,
                    ),
                )
            )
            for upstream, values in grouped.items()
        }

    def impacts(self, changes: Sequence[SchemaChange]) -> tuple[PipelineImpact, ...]:
        queue: deque[tuple[ColumnRef, tuple[LineageEdge, ...]]] = deque(
            (change.ref, ()) for change in changes if change.severity is Severity.BREAKING
        )
        visited: set[tuple[str, ColumnRef]] = set()
        found: dict[tuple[str, ColumnRef], PipelineImpact] = {}
        while queue:
            column, path = queue.popleft()
            for edge in self.edges_by_upstream.get(column, ()):
                key = (edge.pipeline.key, edge.downstream)
                if key in visited:
                    continue
                visited.add(key)
                next_path = (*path, edge)
                found[key] = PipelineImpact(edge.pipeline, edge.downstream, next_path)
                queue.append((edge.downstream, next_path))
        return tuple(
            sorted(
                found.values(),
                key=lambda impact: (
                    -_CRITICALITY_RANK[impact.pipeline.criticality],
                    impact.pipeline.key,
                    impact.downstream.qualified_name,
                ),
            )
        )
