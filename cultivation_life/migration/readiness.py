from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = frozenset({"pass", "partial", "missing", "retired"})
READY_STATUSES = frozenset({"pass"})


class FeatureMatrixError(ValueError):
    pass


class CutoverBlockedError(RuntimeError):
    pass


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise FeatureMatrixError(f"功能矩阵存在重复JSON键：{key}")
        result[key] = value
    return result


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except FileNotFoundError as error:
        raise FeatureMatrixError(f"文件不存在：{path}") from error
    except json.JSONDecodeError as error:
        raise FeatureMatrixError(f"JSON损坏：{path}: {error.msg}") from error
    if not isinstance(value, dict):
        raise FeatureMatrixError(f"JSON根节点必须是对象：{path}")
    return value


@dataclass(frozen=True, slots=True)
class FeatureEntry:
    id: str
    domain: str
    status: str
    required_for_cutover: bool
    v1_operations: tuple[str, ...]
    evidence: tuple[str, ...]
    notes: str
    retirement_decision: str | None = None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    matrix_path: str
    baseline_path: str
    baseline_commit: str
    operation_count: int
    covered_operation_count: int
    feature_count: int
    status_counts: dict[str, int]
    domain_counts: dict[str, dict[str, int]]
    structural_errors: tuple[str, ...]
    blockers: tuple[dict[str, str], ...]

    @property
    def ready(self) -> bool:
        return not self.structural_errors and not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {"ready": self.ready, **asdict(self)}

    def require_ready(self) -> None:
        if self.ready:
            return
        counts: dict[str, int] = {}
        for blocker in self.blockers:
            status = blocker["status"]
            counts[status] = counts.get(status, 0) + 1
        summary = ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        if self.structural_errors:
            summary = f"结构错误={len(self.structural_errors)}" + (f", {summary}" if summary else "")
        raise CutoverBlockedError(f"V2尚未满足切换条件：{summary or '未知阻断'}")


class FeatureMatrix:
    def __init__(
        self,
        *,
        matrix_path: Path,
        project_root: Path,
        baseline_path: Path,
        baseline_commit: str,
        baseline_operations: tuple[str, ...],
        features: tuple[FeatureEntry, ...],
        parse_errors: tuple[str, ...] = (),
    ):
        self.matrix_path = matrix_path
        self.project_root = project_root
        self.baseline_path = baseline_path
        self.baseline_commit = baseline_commit
        self.baseline_operations = baseline_operations
        self.features = features
        self.parse_errors = parse_errors

    @classmethod
    def load(cls, matrix_path: Path, *, project_root: Path) -> FeatureMatrix:
        root = Path(project_root).resolve()
        path = Path(matrix_path).resolve()
        document = _load_json(path)
        if int(document.get("schema_version", 0)) != 1:
            raise FeatureMatrixError("不支持的功能矩阵版本")
        baseline_value = str(document.get("baseline_inventory", "")).strip()
        if not baseline_value:
            raise FeatureMatrixError("功能矩阵缺少baseline_inventory")
        baseline_path = (root / baseline_value).resolve()
        try:
            baseline_path.relative_to(root)
        except ValueError as error:
            raise FeatureMatrixError("baseline_inventory必须位于项目目录内") from error
        baseline = _load_json(baseline_path)
        operations_value = baseline.get("public_operations")
        if not isinstance(operations_value, list) or not all(
            isinstance(operation, str) and operation for operation in operations_value
        ):
            raise FeatureMatrixError("V1行为清单的public_operations非法")
        feature_rows = document.get("features")
        if not isinstance(feature_rows, list):
            raise FeatureMatrixError("功能矩阵缺少features数组")
        features: list[FeatureEntry] = []
        parse_errors: list[str] = []
        for index, row in enumerate(feature_rows):
            if not isinstance(row, dict):
                parse_errors.append(f"features[{index}]必须是对象")
                continue
            operations = row.get("v1_operations", [])
            evidence = row.get("evidence", [])
            if not isinstance(operations, list) or not all(isinstance(value, str) for value in operations):
                parse_errors.append(f"features[{index}].v1_operations必须是字符串数组")
                operations = []
            if not isinstance(evidence, list) or not all(isinstance(value, str) for value in evidence):
                parse_errors.append(f"features[{index}].evidence必须是字符串数组")
                evidence = []
            features.append(FeatureEntry(
                id=str(row.get("id", "")).strip(),
                domain=str(row.get("domain", "")).strip(),
                status=str(row.get("status", "")).strip(),
                required_for_cutover=bool(row.get("required_for_cutover", True)),
                v1_operations=tuple(operations),
                evidence=tuple(evidence),
                notes=str(row.get("notes", "")).strip(),
                retirement_decision=(
                    str(row["retirement_decision"]).strip()
                    if row.get("retirement_decision") is not None else None
                ),
            ))
        return cls(
            matrix_path=path,
            project_root=root,
            baseline_path=baseline_path,
            baseline_commit=str(baseline.get("baseline_commit", "")),
            baseline_operations=tuple(operations_value),
            features=tuple(features),
            parse_errors=tuple(parse_errors),
        )

    def assess(self) -> ReadinessReport:
        errors = list(self.parse_errors)
        feature_ids: set[str] = set()
        assignments: dict[str, list[str]] = {}
        status_counts: dict[str, int] = {}
        domain_counts: dict[str, dict[str, int]] = {}
        baseline = set(self.baseline_operations)
        if len(baseline) != len(self.baseline_operations):
            errors.append("V1行为清单自身包含重复操作")
        for feature in self.features:
            label = feature.id or "<empty>"
            if not feature.id:
                errors.append("功能项ID不能为空")
            elif feature.id in feature_ids:
                errors.append(f"功能项ID重复：{feature.id}")
            feature_ids.add(feature.id)
            if not feature.domain:
                errors.append(f"功能项缺少domain：{label}")
            if feature.status not in ALLOWED_STATUSES:
                errors.append(f"功能项状态非法：{label}={feature.status}")
            if not feature.notes:
                errors.append(f"功能项缺少说明：{label}")
            if len(feature.v1_operations) != len(set(feature.v1_operations)):
                errors.append(f"功能项内操作重复：{label}")
            for operation in feature.v1_operations:
                assignments.setdefault(operation, []).append(label)
            if feature.status == "pass" and not feature.evidence:
                errors.append(f"已通过功能缺少证据：{label}")
            if feature.status == "retired" and not feature.retirement_decision:
                errors.append(f"废弃功能缺少决策记录：{label}")
            if feature.status == "retired" and feature.required_for_cutover:
                errors.append(f"废弃功能必须显式移出切换必需项：{label}")
            for evidence in feature.evidence:
                evidence_path = evidence.split("::", 1)[0]
                target = (self.project_root / evidence_path).resolve()
                try:
                    target.relative_to(self.project_root)
                except ValueError:
                    errors.append(f"证据路径越出项目目录：{label}: {evidence}")
                    continue
                if not target.is_file():
                    errors.append(f"证据文件不存在：{label}: {evidence}")
            status_counts[feature.status] = status_counts.get(feature.status, 0) + 1
            per_domain = domain_counts.setdefault(feature.domain, {})
            per_domain[feature.status] = per_domain.get(feature.status, 0) + 1
        missing = sorted(baseline - set(assignments))
        unknown = sorted(set(assignments) - baseline)
        duplicated = sorted(operation for operation, owners in assignments.items() if len(owners) > 1)
        if missing:
            errors.append(f"矩阵遗漏V1公开操作：{missing}")
        if unknown:
            errors.append(f"矩阵包含未知V1公开操作：{unknown}")
        if duplicated:
            detail = {operation: assignments[operation] for operation in duplicated}
            errors.append(f"V1公开操作被重复归属：{detail}")
        blockers = tuple(
            {
                "id": feature.id,
                "domain": feature.domain,
                "status": feature.status,
                "notes": feature.notes,
            }
            for feature in self.features
            if feature.required_for_cutover and feature.status not in READY_STATUSES
        )
        covered = len(baseline & set(assignments))
        return ReadinessReport(
            matrix_path=str(self.matrix_path),
            baseline_path=str(self.baseline_path),
            baseline_commit=self.baseline_commit,
            operation_count=len(baseline),
            covered_operation_count=covered,
            feature_count=len(self.features),
            status_counts=dict(sorted(status_counts.items())),
            domain_counts={
                domain: dict(sorted(counts.items()))
                for domain, counts in sorted(domain_counts.items())
            },
            structural_errors=tuple(errors),
            blockers=blockers,
        )


def assess_default_matrix(project_root: Path) -> ReadinessReport:
    root = Path(project_root).resolve()
    matrix = FeatureMatrix.load(root / "docs" / "v2" / "feature_matrix.json", project_root=root)
    return matrix.assess()


def assert_ready_for_cutover(project_root: Path) -> ReadinessReport:
    report = assess_default_matrix(project_root)
    report.require_ready()
    return report
