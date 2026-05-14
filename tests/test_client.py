"""Tests for App Store Connect client retry and error handling."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from client import AppStoreConnectClient
from config import Settings
from errors import AscApiError, ConfigurationError


class FakeTokenProvider:
    def __init__(self) -> None:
        self.invalidations = 0

    def get_token(self, *, force_refresh: bool = False) -> str:
        del force_refresh
        return "token"

    def invalidate(self) -> None:
        self.invalidations += 1


class FakeResponse:
    def __init__(
        self,
        status_code: int,
        *,
        json_body: dict | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
        reason: str = "ERR",
    ) -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = text
        self.headers = headers or {"Content-Type": "application/json"}
        self.reason = reason
        self.content = json.dumps(json_body).encode("utf-8") if json_body is not None else text.encode("utf-8")

    def json(self) -> dict:
        if self._json_body is None:
            raise ValueError("no json")
        return self._json_body


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


def _settings() -> Settings:
    return Settings(
        app_store_key_id="KEY1234567",
        app_store_issuer_id="issuer-id",
        app_store_private_key="-----BEGIN PRIVATE KEY-----\nABC\n-----END PRIVATE KEY-----",
        app_store_bundle_id="example.bundle",
        app_store_sku="example.bundle",
        app_store_apple_id="123456789",
        app_store_name="Example",
        revenuecat_api_key=None,
        revenuecat_project_id=None,
        change_log_path=Path("/tmp/changes.jsonl"),
    )


def test_request_retries_once_after_401() -> None:
    session = FakeSession(
        [
            FakeResponse(401, json_body={"errors": [{"title": "Unauthorized", "detail": "expired"}]}),
            FakeResponse(200, json_body={"data": {"id": "ok"}}),
        ]
    )
    token_provider = FakeTokenProvider()
    client = AppStoreConnectClient(_settings(), token_provider, session=session)

    payload = client.request("GET", "/v1/apps")

    assert payload == {"data": {"id": "ok"}}
    assert token_provider.invalidations == 1
    assert len(session.calls) == 2


def test_request_retries_after_rate_limit() -> None:
    sleeps: list[float] = []
    session = FakeSession(
        [
            FakeResponse(429, json_body={"errors": [{"title": "Rate Limited", "detail": "slow down"}]}),
            FakeResponse(200, json_body={"data": {"id": "ok"}}),
        ]
    )
    client = AppStoreConnectClient(
        _settings(),
        FakeTokenProvider(),
        session=session,
        sleep_fn=sleeps.append,
    )

    payload = client.request("GET", "/v1/apps")

    assert payload["data"]["id"] == "ok"
    assert sleeps == [1.0]


def test_request_raises_structured_conflict_error() -> None:
    session = FakeSession(
        [
            FakeResponse(
                409,
                json_body={
                    "errors": [
                        {
                            "title": "Conflict",
                            "detail": "Version is not editable",
                        }
                    ]
                },
            )
        ]
    )
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)

    with pytest.raises(AscApiError) as exc_info:
        client.request("PATCH", "/v1/appStoreVersionLocalizations/example")

    assert exc_info.value.status_code == 409
    assert exc_info.value.hint is not None


def test_create_app_store_version_uses_app_relationship() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": {"id": "version-1"}})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)
    client._cached_app = {"id": "app-1", "attributes": {"bundleId": "example.bundle"}}  # noqa: SLF001

    payload = client.create_app_store_version(
        version_string="1.0.49",
        platform="IOS",
        release_type="AFTER_APPROVAL",
        earliest_release_date=None,
        copyright_text=None,
    )

    assert payload["data"]["id"] == "version-1"
    body = session.calls[0]["json"]
    assert body["data"]["type"] == "appStoreVersions"
    assert body["data"]["relationships"]["app"]["data"]["id"] == "app-1"
    assert body["data"]["attributes"]["versionString"] == "1.0.49"


def test_app_id_selector_overrides_default_only_inside_context() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                json_body={
                    "data": {
                        "id": "app-2",
                        "attributes": {
                            "bundleId": "other.bundle",
                            "name": "Other App",
                        },
                    }
                },
            ),
            FakeResponse(
                200,
                json_body={
                    "data": [
                        {
                            "id": "app-1",
                            "attributes": {
                                "bundleId": "example.bundle",
                                "name": "Example App",
                            },
                        }
                    ]
                },
            ),
        ]
    )
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)

    with client.use_app_selector({"app_id": "app-2"}):
        assert client.get_configured_app()["id"] == "app-2"

    assert client.get_configured_app()["id"] == "app-1"
    assert session.calls[0]["url"].endswith("/v1/apps/app-2")
    assert "filter%5BbundleId%5D=example.bundle" in session.calls[1]["url"]


def test_bundle_selector_feeds_dedicated_tool_app_relationships_and_caches() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                json_body={
                    "data": [
                        {
                            "id": "app-2",
                            "attributes": {
                                "bundleId": "other.bundle",
                                "name": "Other App",
                            },
                        }
                    ]
                },
            ),
            FakeResponse(200, json_body={"data": []}),
        ]
    )
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)

    with client.use_app_selector({"bundle_id": "other.bundle"}):
        assert client.get_app_versions() == []

    assert len(session.calls) == 2
    assert "filter%5BbundleId%5D=other.bundle" in session.calls[0]["url"]
    assert session.calls[1]["url"].endswith("/v1/apps/app-2/appStoreVersions")


def test_name_selector_requires_a_unique_app_match() -> None:
    session = FakeSession(
        [
            FakeResponse(
                200,
                json_body={
                    "data": [
                        {
                            "id": "app-1",
                            "attributes": {
                                "bundleId": "example.one",
                                "name": "Example",
                            },
                        },
                        {
                            "id": "app-2",
                            "attributes": {
                                "bundleId": "example.two",
                                "name": "Example",
                            },
                        },
                    ]
                },
            )
        ]
    )
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)

    with pytest.raises(ConfigurationError) as exc_info, client.use_app_selector({"app_name": "Example"}):
        client.get_configured_app()

    assert exc_info.value.details["app_name"] == "Example"
    assert len(exc_info.value.details["matches"]) == 2


def test_set_version_build_patches_relationship() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": {"id": "build-1"}})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)

    client.set_version_build("version-1", "build-1")

    assert session.calls[0]["url"].endswith("/v1/appStoreVersions/version-1/relationships/build")
    assert session.calls[0]["json"]["data"] == {"type": "builds", "id": "build-1"}


def test_create_custom_product_page_localization_uses_version_relationship() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": {"id": "cpp-loc-1"}})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)

    payload = client.create_custom_product_page_localization(
        version_id="cpp-version-1",
        locale="en-US",
        promotional_text="Weekly outfit planning.",
    )

    assert payload["data"]["id"] == "cpp-loc-1"
    body = session.calls[0]["json"]
    assert body["data"]["type"] == "appCustomProductPageLocalizations"
    assert body["data"]["relationships"]["appCustomProductPageVersion"]["data"]["id"] == "cpp-version-1"
    assert body["data"]["attributes"]["locale"] == "en-US"


def test_create_custom_product_page_uses_inline_version_and_localization() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": {"id": "cpp-1"}})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)
    client._cached_app = {"id": "app-1", "attributes": {"bundleId": "example.bundle"}}  # noqa: SLF001

    payload = client.create_custom_product_page(
        name="Winter Hooks",
        locale="en-US",
        promotional_text="Weekly outfit planning.",
        deep_link="example://winter-hooks",
    )

    assert payload["data"]["id"] == "cpp-1"
    body = session.calls[0]["json"]
    assert body["data"]["type"] == "appCustomProductPages"
    assert body["data"]["relationships"]["app"]["data"]["id"] == "app-1"
    assert body["data"]["attributes"]["name"] == "Winter Hooks"
    version_link = body["data"]["relationships"]["appCustomProductPageVersions"]["data"][0]
    version_resource = next(item for item in body["included"] if item["type"] == "appCustomProductPageVersions")
    localization_resource = next(
        item for item in body["included"] if item["type"] == "appCustomProductPageLocalizations"
    )
    assert version_link["id"].startswith("${cppVersion")
    assert version_link["id"].endswith("}")
    assert localization_resource["id"].startswith("${cppLocalization")
    assert localization_resource["id"].endswith("}")
    assert version_link["id"] == version_resource["id"]
    assert version_resource["attributes"]["deepLink"] == "example://winter-hooks"
    assert version_resource["relationships"]["appCustomProductPageLocalizations"]["data"] == [
        {
            "id": localization_resource["id"],
            "type": "appCustomProductPageLocalizations",
        }
    ]
    assert localization_resource["attributes"] == {
        "locale": "en-US",
        "promotionalText": "Weekly outfit planning.",
    }
    assert "relationships" not in localization_resource


def test_add_custom_product_page_version_to_review_submission_uses_relationships() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": {"id": "item-1"}})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)

    payload = client.add_custom_product_page_version_to_review_submission(
        review_submission_id="review-1",
        page_version_id="cpp-version-1",
    )

    assert payload["data"]["id"] == "item-1"
    body = session.calls[0]["json"]
    assert body["data"]["type"] == "reviewSubmissionItems"
    assert body["data"]["relationships"]["reviewSubmission"]["data"]["id"] == "review-1"
    assert body["data"]["relationships"]["appCustomProductPageVersion"]["data"]["id"] == "cpp-version-1"


def test_create_review_submission_uses_app_relationship() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": {"id": "review-1"}})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)
    client._cached_app = {"id": "app-1", "attributes": {"bundleId": "example.bundle"}}  # noqa: SLF001

    payload = client.create_review_submission()

    assert payload["data"]["id"] == "review-1"
    body = session.calls[0]["json"]
    assert body["data"]["type"] == "reviewSubmissions"
    assert body["data"]["relationships"]["app"]["data"] == {"type": "apps", "id": "app-1"}


def test_get_product_page_optimization_experiments_uses_version_path() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": [{"id": "ppo-1"}]})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)
    client.get_current_version = lambda: {"id": "version-1"}  # type: ignore[method-assign]

    payload = client.get_product_page_optimization_experiments(limit=5)

    assert payload == [{"id": "ppo-1"}]
    assert session.calls[0]["url"].endswith("/v1/appStoreVersions/version-1/appStoreVersionExperimentsV2?limit=5")


def test_create_product_page_optimization_experiment_uses_v2_endpoint() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": {"id": "ppo-1"}})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)
    client._cached_app = {"id": "app-1", "attributes": {"bundleId": "example.bundle"}}  # noqa: SLF001

    payload = client.create_product_page_optimization_experiment(
        name="Hooks Test",
        traffic_proportion=66,
        platform="IOS",
    )

    assert payload["data"]["id"] == "ppo-1"
    assert session.calls[0]["url"].endswith("/v2/appStoreVersionExperiments")
    body = session.calls[0]["json"]
    assert body["data"]["type"] == "appStoreVersionExperiments"
    assert body["data"]["attributes"]["name"] == "Hooks Test"
    assert body["data"]["attributes"]["trafficProportion"] == 66
    assert body["data"]["relationships"]["app"]["data"]["id"] == "app-1"


def test_create_product_page_optimization_treatment_uses_v2_relationship() -> None:
    session = FakeSession([FakeResponse(200, json_body={"data": {"id": "treatment-1"}})])
    client = AppStoreConnectClient(_settings(), FakeTokenProvider(), session=session)

    payload = client.create_product_page_optimization_treatment(
        experiment_id="ppo-1",
        name="Variant A",
        app_icon_name="VariantAIcon",
        use_v2_relationship=True,
    )

    assert payload["data"]["id"] == "treatment-1"
    body = session.calls[0]["json"]
    assert body["data"]["type"] == "appStoreVersionExperimentTreatments"
    assert body["data"]["attributes"]["appIconName"] == "VariantAIcon"
    assert body["data"]["relationships"]["appStoreVersionExperimentV2"]["data"] == {
        "type": "appStoreVersionExperiments",
        "id": "ppo-1",
    }
