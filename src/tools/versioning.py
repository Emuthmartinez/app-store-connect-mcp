"""Version transition and experimentation-oriented App Store Connect tools."""

from __future__ import annotations

from typing import Any

from errors import ConfigurationError, ResourceNotFoundError
from tooling import ToolDefinition
from tools.shared import log_mutation


RELEASE_TYPES = {"AFTER_APPROVAL", "MANUAL", "SCHEDULED"}


def _normalize_release_type(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    if normalized not in RELEASE_TYPES:
        raise ConfigurationError(
            "release_type must be one of AFTER_APPROVAL, MANUAL, or SCHEDULED",
            details={"release_type": value},
        )
    return normalized


def _serialize_version(version: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": version.get("id"),
        **version.get("attributes", {}),
    }


def _serialize_build(build: dict[str, Any] | None) -> dict[str, Any] | None:
    if not build:
        return None
    return {
        "id": build.get("id"),
        **build.get("attributes", {}),
    }


def _serialize_experiment(experiment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": experiment.get("id"),
        **experiment.get("attributes", {}),
    }


def _serialize_treatment(treatment: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": treatment.get("id"),
        **treatment.get("attributes", {}),
    }


def _get_version_snapshot(runtime: Any, version_id: str) -> dict[str, Any]:
    version = runtime.asc.get_version_by_id(version_id)
    build: dict[str, Any] | None = None
    try:
        build = runtime.asc.get_version_build(version_id)
    except ResourceNotFoundError:
        build = None

    return {
        "version": _serialize_version(version),
        "build": _serialize_build(build),
    }


def _get_experiment_snapshot(runtime: Any, experiment_id: str, *, include_treatments: bool = True) -> dict[str, Any]:
    experiment = runtime.asc.get_product_page_optimization_experiment(experiment_id)
    snapshot = {
        "experiment": _serialize_experiment(experiment),
    }
    if include_treatments:
        snapshot["treatments"] = [
            _serialize_treatment(treatment)
            for treatment in runtime.asc.get_product_page_optimization_treatments(experiment_id, limit=50)
        ]
    return snapshot


def get_version_transition_state(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    version_id = str(arguments.get("version_id") or "").strip()
    version = runtime.asc.get_current_version() if not version_id else runtime.asc.get_version_by_id(version_id)
    snapshot = _get_version_snapshot(runtime, version["id"])
    return {
        "ok": True,
        "current": not version_id,
        **snapshot,
    }


def list_build_candidates(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    limit = int(arguments.get("limit") or 20)
    version_string = str(arguments.get("version_string") or "").strip() or None
    build_number = str(arguments.get("build_number") or "").strip() or None
    processing_state = str(arguments.get("processing_state") or "").strip() or None
    builds = runtime.asc.list_builds(
        version_string=version_string,
        build_number=build_number,
        processing_state=processing_state,
        limit=limit,
    )
    return {
        "ok": True,
        "builds": [
            {
                "id": build.get("id"),
                **build.get("attributes", {}),
            }
            for build in builds
        ],
    }


def get_review_submissions(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    limit = int(arguments.get("limit") or 20)
    include_items = bool(arguments.get("include_items", False))
    payload = runtime.asc.get_review_submissions(limit=limit, include_items=include_items)
    submissions = payload.get("data", [])
    included_by_id = {
        item.get("id"): item
        for item in payload.get("included", []) or []
        if isinstance(item, dict) and item.get("type") == "reviewSubmissionItems"
    }
    return {
        "ok": True,
        "review_submissions": [
            {
                "id": submission.get("id"),
                **submission.get("attributes", {}),
                "items": [
                    {
                        "id": item_ref.get("id"),
                        **included_by_id.get(item_ref.get("id"), {}).get("attributes", {}),
                    }
                    for item_ref in submission.get("relationships", {})
                    .get("items", {})
                    .get("data", [])
                ],
            }
            for submission in submissions
        ],
    }


def create_review_submission(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    before = get_review_submissions(runtime, {"limit": 50, "include_items": True})["review_submissions"]
    created = runtime.asc.create_review_submission()
    review_submission_id = created["data"]["id"]
    after = get_review_submissions(runtime, {"limit": 50, "include_items": True})["review_submissions"]
    log_mutation(
        runtime,
        operation="create_review_submission",
        locale=None,
        target={"resource_type": "reviewSubmission", "id": review_submission_id},
        before={"review_submissions": before},
        after={"review_submissions": after, "created": created},
    )
    return {
        "ok": True,
        "created": created,
        "review_submissions": after,
    }


def get_product_page_optimization_experiments(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    limit = int(arguments.get("limit") or 20)
    version_id = str(arguments.get("version_id") or "").strip() or None
    include_treatments = bool(arguments.get("include_treatments", False))
    experiments = runtime.asc.get_product_page_optimization_experiments(
        version_id=version_id,
        limit=limit,
    )
    return {
        "ok": True,
        "experiments": [
            {
                **_serialize_experiment(experiment),
                **(
                    {
                        "treatments": [
                            _serialize_treatment(treatment)
                            for treatment in runtime.asc.get_product_page_optimization_treatments(
                                experiment["id"],
                                limit=50,
                            )
                        ]
                    }
                    if include_treatments
                    else {}
                ),
            }
            for experiment in experiments
        ],
    }


def get_product_page_optimization_experiment(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    experiment_id = str(arguments.get("experiment_id") or "").strip()
    if not experiment_id:
        raise ConfigurationError("experiment_id is required")
    include_treatments = bool(arguments.get("include_treatments", True))
    return {
        "ok": True,
        "product_page_optimization": _get_experiment_snapshot(
            runtime,
            experiment_id,
            include_treatments=include_treatments,
        ),
    }


def _normalize_platform(value: Any) -> str:
    platform = str(value or "IOS").strip().upper()
    if not platform:
        raise ConfigurationError("platform must be a non-empty string")
    return platform


def _normalize_traffic_proportion(value: Any) -> int:
    try:
        proportion = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError("traffic_proportion must be an integer") from exc
    if proportion < 1 or proportion > 100:
        raise ConfigurationError(
            "traffic_proportion must be between 1 and 100",
            details={"traffic_proportion": value},
        )
    return proportion


def create_product_page_optimization_experiment(
    runtime: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    name = str(arguments.get("name") or "").strip()
    if not name:
        raise ConfigurationError("name must be a non-empty string")

    traffic_proportion = _normalize_traffic_proportion(arguments.get("traffic_proportion"))
    platform = _normalize_platform(arguments.get("platform"))
    before = get_product_page_optimization_experiments(
        runtime,
        {"limit": 50, "include_treatments": False},
    )["experiments"]
    created = runtime.asc.create_product_page_optimization_experiment(
        name=name,
        traffic_proportion=traffic_proportion,
        platform=platform,
    )
    experiment_id = created["data"]["id"]
    after = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    log_mutation(
        runtime,
        operation="create_product_page_optimization_experiment",
        locale=None,
        target={"resource_type": "appStoreVersionExperiment", "id": experiment_id},
        before={"experiments": before},
        after=after,
    )
    return {
        "ok": True,
        "created": created,
        "after": after,
    }


def update_product_page_optimization_experiment(
    runtime: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    experiment_id = str(arguments.get("experiment_id") or "").strip()
    if not experiment_id:
        raise ConfigurationError("experiment_id is required")

    attributes: dict[str, Any] = {}
    if "name" in arguments:
        name = str(arguments.get("name") or "").strip()
        if not name:
            raise ConfigurationError("name must be a non-empty string when provided")
        attributes["name"] = name
    if "traffic_proportion" in arguments:
        attributes["trafficProportion"] = _normalize_traffic_proportion(arguments.get("traffic_proportion"))
    if "started" in arguments:
        attributes["started"] = bool(arguments.get("started"))
    if not attributes:
        raise ConfigurationError("Provide at least one experiment field to update")

    before = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    runtime.asc.update_product_page_optimization_experiment(experiment_id, attributes)
    after = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    log_mutation(
        runtime,
        operation="update_product_page_optimization_experiment",
        locale=None,
        target={"resource_type": "appStoreVersionExperiment", "id": experiment_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "experiment_id": experiment_id,
        "before": before,
        "after": after,
    }


def delete_product_page_optimization_experiment(
    runtime: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    experiment_id = str(arguments.get("experiment_id") or "").strip()
    if not experiment_id:
        raise ConfigurationError("experiment_id is required")

    before = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    runtime.asc.delete_product_page_optimization_experiment(experiment_id)
    after = {"deleted": True, "experiment_id": experiment_id}
    log_mutation(
        runtime,
        operation="delete_product_page_optimization_experiment",
        locale=None,
        target={"resource_type": "appStoreVersionExperiment", "id": experiment_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "experiment_id": experiment_id,
        "deleted": True,
    }


def list_product_page_optimization_treatments(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    experiment_id = str(arguments.get("experiment_id") or "").strip()
    if not experiment_id:
        raise ConfigurationError("experiment_id is required")
    limit = int(arguments.get("limit") or 20)
    treatments = runtime.asc.get_product_page_optimization_treatments(experiment_id, limit=limit)
    return {
        "ok": True,
        "experiment_id": experiment_id,
        "treatments": [_serialize_treatment(treatment) for treatment in treatments],
    }


def get_product_page_optimization_treatment(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    treatment_id = str(arguments.get("treatment_id") or "").strip()
    if not treatment_id:
        raise ConfigurationError("treatment_id is required")
    treatment = runtime.asc.get_product_page_optimization_treatment(treatment_id)
    return {
        "ok": True,
        "treatment": _serialize_treatment(treatment),
    }


def create_product_page_optimization_treatment(
    runtime: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    experiment_id = str(arguments.get("experiment_id") or "").strip()
    name = str(arguments.get("name") or "").strip()
    if not experiment_id:
        raise ConfigurationError("experiment_id is required")
    if not name:
        raise ConfigurationError("name must be a non-empty string")

    app_icon_name = str(arguments.get("app_icon_name") or "").strip() or None
    use_v2_relationship = bool(arguments.get("use_v2_relationship", True))
    before = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    created = runtime.asc.create_product_page_optimization_treatment(
        experiment_id=experiment_id,
        name=name,
        app_icon_name=app_icon_name,
        use_v2_relationship=use_v2_relationship,
    )
    after = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    treatment_id = created["data"]["id"]
    log_mutation(
        runtime,
        operation="create_product_page_optimization_treatment",
        locale=None,
        target={
            "resource_type": "appStoreVersionExperimentTreatment",
            "id": treatment_id,
            "experiment_id": experiment_id,
        },
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "created": created,
        "after": after,
    }


def update_product_page_optimization_treatment(
    runtime: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    treatment_id = str(arguments.get("treatment_id") or "").strip()
    if not treatment_id:
        raise ConfigurationError("treatment_id is required")

    attributes: dict[str, Any] = {}
    if "name" in arguments:
        name = str(arguments.get("name") or "").strip()
        if not name:
            raise ConfigurationError("name must be a non-empty string when provided")
        attributes["name"] = name
    if "app_icon_name" in arguments:
        app_icon_name = arguments.get("app_icon_name")
        attributes["appIconName"] = None if app_icon_name is None else str(app_icon_name).strip() or None
    if not attributes:
        raise ConfigurationError("Provide at least one treatment field to update")

    before_treatment = runtime.asc.get_product_page_optimization_treatment(treatment_id)
    experiment_id = (
        before_treatment.get("relationships", {})
        .get("appStoreVersionExperimentV2", {})
        .get("data", {})
        .get("id")
        or before_treatment.get("relationships", {})
        .get("appStoreVersionExperiment", {})
        .get("data", {})
        .get("id")
    )
    before = {
        "treatment": _serialize_treatment(before_treatment),
    }
    if experiment_id:
        before["experiment"] = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    runtime.asc.update_product_page_optimization_treatment(treatment_id, attributes)
    after_treatment = runtime.asc.get_product_page_optimization_treatment(treatment_id)
    after = {
        "treatment": _serialize_treatment(after_treatment),
    }
    if experiment_id:
        after["experiment"] = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    log_mutation(
        runtime,
        operation="update_product_page_optimization_treatment",
        locale=None,
        target={
            "resource_type": "appStoreVersionExperimentTreatment",
            "id": treatment_id,
            "experiment_id": experiment_id,
        },
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "treatment_id": treatment_id,
        "before": before,
        "after": after,
    }


def delete_product_page_optimization_treatment(
    runtime: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    treatment_id = str(arguments.get("treatment_id") or "").strip()
    if not treatment_id:
        raise ConfigurationError("treatment_id is required")

    treatment = runtime.asc.get_product_page_optimization_treatment(treatment_id)
    experiment_id = (
        treatment.get("relationships", {})
        .get("appStoreVersionExperimentV2", {})
        .get("data", {})
        .get("id")
        or treatment.get("relationships", {})
        .get("appStoreVersionExperiment", {})
        .get("data", {})
        .get("id")
    )
    before = {
        "treatment": _serialize_treatment(treatment),
    }
    if experiment_id:
        before["experiment"] = _get_experiment_snapshot(runtime, experiment_id, include_treatments=True)
    runtime.asc.delete_product_page_optimization_treatment(treatment_id)
    after = {"deleted": True, "treatment_id": treatment_id, "experiment_id": experiment_id}
    log_mutation(
        runtime,
        operation="delete_product_page_optimization_treatment",
        locale=None,
        target={
            "resource_type": "appStoreVersionExperimentTreatment",
            "id": treatment_id,
            "experiment_id": experiment_id,
        },
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "treatment_id": treatment_id,
        "experiment_id": experiment_id,
        "deleted": True,
    }


def create_app_store_version(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    version_string = str(arguments.get("version_string") or "").strip()
    if not version_string:
        raise ConfigurationError("version_string must be a non-empty string")

    platform = str(arguments.get("platform") or "IOS").strip().upper()
    release_type = _normalize_release_type(arguments.get("release_type"))
    earliest_release_date = str(arguments.get("earliest_release_date") or "").strip() or None
    copyright_text = str(arguments.get("copyright") or "").strip() or None

    before = {
        "versions": [
            _serialize_version(version)
            for version in runtime.asc.get_app_versions()
        ]
    }
    created = runtime.asc.create_app_store_version(
        version_string=version_string,
        platform=platform,
        release_type=release_type,
        earliest_release_date=earliest_release_date,
        copyright_text=copyright_text,
    )
    created_id = created["data"]["id"]
    after = _get_version_snapshot(runtime, created_id)
    log_mutation(
        runtime,
        operation="create_app_store_version",
        locale=None,
        target={"resource_type": "appStoreVersion", "id": created_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "created": created,
        "after": after,
    }


def update_app_store_version(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    version_id = str(arguments.get("version_id") or "").strip()
    if not version_id:
        raise ConfigurationError("version_id is required")

    attributes: dict[str, Any] = {}
    release_type = _normalize_release_type(arguments.get("release_type"))
    if release_type is not None:
        attributes["releaseType"] = release_type
    if "earliest_release_date" in arguments:
        earliest_release_date = arguments.get("earliest_release_date")
        attributes["earliestReleaseDate"] = (
            None if earliest_release_date is None else str(earliest_release_date).strip() or None
        )
    if "copyright" in arguments:
        copyright_text = arguments.get("copyright")
        attributes["copyright"] = None if copyright_text is None else str(copyright_text).strip() or None
    if "uses_idfa" in arguments:
        attributes["usesIdfa"] = bool(arguments.get("uses_idfa"))

    if not attributes:
        raise ConfigurationError("Provide at least one updatable field for the version")

    before = _get_version_snapshot(runtime, version_id)
    runtime.asc.update_app_store_version(version_id, attributes)
    after = _get_version_snapshot(runtime, version_id)
    log_mutation(
        runtime,
        operation="update_app_store_version",
        locale=None,
        target={"resource_type": "appStoreVersion", "id": version_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "version_id": version_id,
        "before": before,
        "after": after,
    }


def assign_build_to_version(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    version_id = str(arguments.get("version_id") or "").strip()
    build_id = str(arguments.get("build_id") or "").strip()
    if not version_id or not build_id:
        raise ConfigurationError("version_id and build_id are required")

    before = _get_version_snapshot(runtime, version_id)
    runtime.asc.set_version_build(version_id, build_id)
    after = _get_version_snapshot(runtime, version_id)
    log_mutation(
        runtime,
        operation="assign_build_to_version",
        locale=None,
        target={"resource_type": "appStoreVersion", "id": version_id, "build_id": build_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "version_id": version_id,
        "build_id": build_id,
        "before": before,
        "after": after,
    }


def release_app_store_version(runtime: Any, arguments: dict[str, Any]) -> dict[str, Any]:
    version_id = str(arguments.get("version_id") or "").strip()
    if not version_id:
        raise ConfigurationError("version_id is required")

    before = _get_version_snapshot(runtime, version_id)
    release_request = runtime.asc.release_app_store_version(version_id)
    after = _get_version_snapshot(runtime, version_id)
    log_mutation(
        runtime,
        operation="release_app_store_version",
        locale=None,
        target={"resource_type": "appStoreVersion", "id": version_id},
        before=before,
        after=after,
    )
    return {
        "ok": True,
        "release_request": release_request,
        "before": before,
        "after": after,
    }


def add_custom_product_page_version_to_review_submission(
    runtime: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    review_submission_id = str(arguments.get("review_submission_id") or "").strip()
    page_version_id = str(arguments.get("page_version_id") or "").strip()
    if not review_submission_id or not page_version_id:
        raise ConfigurationError("review_submission_id and page_version_id are required")

    before = get_review_submissions(runtime, {"limit": 50, "include_items": True})["review_submissions"]
    created = runtime.asc.add_custom_product_page_version_to_review_submission(
        review_submission_id=review_submission_id,
        page_version_id=page_version_id,
    )
    after = get_review_submissions(runtime, {"limit": 50, "include_items": True})["review_submissions"]
    log_mutation(
        runtime,
        operation="add_custom_product_page_version_to_review_submission",
        locale=None,
        target={
            "resource_type": "reviewSubmission",
            "id": review_submission_id,
            "page_version_id": page_version_id,
        },
        before={"review_submissions": before},
        after={"review_submissions": after, "created": created},
    )
    return {
        "ok": True,
        "created": created,
        "review_submissions": after,
    }


VERSIONING_TOOLS = [
    ToolDefinition(
        name="get_version_transition_state",
        description="Read the current or specified App Store version, including its assigned build.",
        input_schema={
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler=get_version_transition_state,
    ),
    ToolDefinition(
        name="list_build_candidates",
        description="List App Store eligible builds for the configured app, optionally filtered by version string, build number, or processing state.",
        input_schema={
            "type": "object",
            "properties": {
                "version_string": {"type": "string"},
                "build_number": {"type": "string"},
                "processing_state": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "additionalProperties": False,
        },
        handler=list_build_candidates,
    ),
    ToolDefinition(
        name="get_review_submissions",
        description="List review submissions for the configured app so agents can inspect submission state without using generic endpoints.",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "include_items": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        handler=get_review_submissions,
    ),
    ToolDefinition(
        name="create_review_submission",
        description="Create a new review submission for the configured app using the official reviewSubmissions endpoint.",
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        handler=create_review_submission,
    ),
    ToolDefinition(
        name="get_product_page_optimization_experiments",
        description="List product page optimization experiments for the current or specified App Store version.",
        input_schema={
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                "include_treatments": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        handler=get_product_page_optimization_experiments,
    ),
    ToolDefinition(
        name="get_product_page_optimization_experiment",
        description="Read one product page optimization experiment and, by default, its treatments.",
        input_schema={
            "type": "object",
            "properties": {
                "experiment_id": {"type": "string"},
                "include_treatments": {"type": "boolean"},
            },
            "required": ["experiment_id"],
            "additionalProperties": False,
        },
        handler=get_product_page_optimization_experiment,
    ),
    ToolDefinition(
        name="create_product_page_optimization_experiment",
        description="Create a new product page optimization experiment for the configured app.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "traffic_proportion": {"type": "integer", "minimum": 1, "maximum": 100},
                "platform": {"type": "string"},
            },
            "required": ["name", "traffic_proportion"],
            "additionalProperties": False,
        },
        handler=create_product_page_optimization_experiment,
    ),
    ToolDefinition(
        name="update_product_page_optimization_experiment",
        description="Update a product page optimization experiment's name, traffic allocation, or start state.",
        input_schema={
            "type": "object",
            "properties": {
                "experiment_id": {"type": "string"},
                "name": {"type": "string"},
                "traffic_proportion": {"type": "integer", "minimum": 1, "maximum": 100},
                "started": {"type": "boolean"},
            },
            "required": ["experiment_id"],
            "additionalProperties": False,
        },
        handler=update_product_page_optimization_experiment,
    ),
    ToolDefinition(
        name="delete_product_page_optimization_experiment",
        description="Delete a product page optimization experiment.",
        input_schema={
            "type": "object",
            "properties": {
                "experiment_id": {"type": "string"},
            },
            "required": ["experiment_id"],
            "additionalProperties": False,
        },
        handler=delete_product_page_optimization_experiment,
    ),
    ToolDefinition(
        name="list_product_page_optimization_treatments",
        description="List treatments for a product page optimization experiment.",
        input_schema={
            "type": "object",
            "properties": {
                "experiment_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": ["experiment_id"],
            "additionalProperties": False,
        },
        handler=list_product_page_optimization_treatments,
    ),
    ToolDefinition(
        name="get_product_page_optimization_treatment",
        description="Read one treatment for a product page optimization experiment.",
        input_schema={
            "type": "object",
            "properties": {
                "treatment_id": {"type": "string"},
            },
            "required": ["treatment_id"],
            "additionalProperties": False,
        },
        handler=get_product_page_optimization_treatment,
    ),
    ToolDefinition(
        name="create_product_page_optimization_treatment",
        description="Create a treatment under a product page optimization experiment, optionally targeting the v2 experiment relationship.",
        input_schema={
            "type": "object",
            "properties": {
                "experiment_id": {"type": "string"},
                "name": {"type": "string"},
                "app_icon_name": {"type": "string"},
                "use_v2_relationship": {"type": "boolean"},
            },
            "required": ["experiment_id", "name"],
            "additionalProperties": False,
        },
        handler=create_product_page_optimization_treatment,
    ),
    ToolDefinition(
        name="update_product_page_optimization_treatment",
        description="Update a treatment's name or app icon override.",
        input_schema={
            "type": "object",
            "properties": {
                "treatment_id": {"type": "string"},
                "name": {"type": "string"},
                "app_icon_name": {"type": ["string", "null"]},
            },
            "required": ["treatment_id"],
            "additionalProperties": False,
        },
        handler=update_product_page_optimization_treatment,
    ),
    ToolDefinition(
        name="delete_product_page_optimization_treatment",
        description="Delete a treatment from a product page optimization experiment.",
        input_schema={
            "type": "object",
            "properties": {
                "treatment_id": {"type": "string"},
            },
            "required": ["treatment_id"],
            "additionalProperties": False,
        },
        handler=delete_product_page_optimization_treatment,
    ),
    ToolDefinition(
        name="create_app_store_version",
        description="Create a new App Store version for the configured app.",
        input_schema={
            "type": "object",
            "properties": {
                "version_string": {"type": "string"},
                "platform": {"type": "string"},
                "release_type": {"type": "string"},
                "earliest_release_date": {"type": "string"},
                "copyright": {"type": "string"},
            },
            "required": ["version_string"],
            "additionalProperties": False,
        },
        handler=create_app_store_version,
    ),
    ToolDefinition(
        name="update_app_store_version",
        description="Update release settings on an App Store version, including release type or scheduled release date.",
        input_schema={
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "release_type": {"type": "string"},
                "earliest_release_date": {"type": ["string", "null"]},
                "copyright": {"type": ["string", "null"]},
                "uses_idfa": {"type": "boolean"},
            },
            "required": ["version_id"],
            "additionalProperties": False,
        },
        handler=update_app_store_version,
    ),
    ToolDefinition(
        name="assign_build_to_version",
        description="Assign a processed build to an App Store version.",
        input_schema={
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "build_id": {"type": "string"},
            },
            "required": ["version_id", "build_id"],
            "additionalProperties": False,
        },
        handler=assign_build_to_version,
    ),
    ToolDefinition(
        name="release_app_store_version",
        description="Trigger the manual release request for an approved App Store version.",
        input_schema={
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
            },
            "required": ["version_id"],
            "additionalProperties": False,
        },
        handler=release_app_store_version,
    ),
    ToolDefinition(
        name="add_custom_product_page_version_to_review_submission",
        description="Attach a Custom Product Page version to an existing App Review submission so the experiment can ship without falling back to generic endpoints.",
        input_schema={
            "type": "object",
            "properties": {
                "review_submission_id": {"type": "string"},
                "page_version_id": {"type": "string"},
            },
            "required": ["review_submission_id", "page_version_id"],
            "additionalProperties": False,
        },
        handler=add_custom_product_page_version_to_review_submission,
    ),
]
