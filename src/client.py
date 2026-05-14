"""App Store Connect API client."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Iterable
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import requests

from auth import AppStoreJwtProvider
from config import Settings
from errors import AscApiError, ConfigurationError, ResourceNotFoundError

JsonDict = dict[str, Any]

EDITABLE_VERSION_STATES = {
    "PREPARE_FOR_SUBMISSION",
    "DEVELOPER_REJECTED",
    "METADATA_REJECTED",
    "WAITING_FOR_REVIEW",
    "IN_REVIEW",
    "PENDING_DEVELOPER_RELEASE",
    "PROCESSING_FOR_DISTRIBUTION",
}

AppSelector = dict[str, str]
_APP_SELECTOR: ContextVar[AppSelector | None] = ContextVar(
    "app_store_connect_app_selector",
    default=None,
)


class AppStoreConnectClient:
    """Thin client around the App Store Connect REST API."""

    def __init__(
        self,
        settings: Settings,
        token_provider: AppStoreJwtProvider,
        *,
        session: requests.Session | None = None,
        sleep_fn: callable = time.sleep,
    ) -> None:
        self._settings = settings
        self._token_provider = token_provider
        self._session = session or requests.Session()
        self._sleep_fn = sleep_fn
        self._cached_app: JsonDict | None = None
        self._cached_selected_apps: dict[tuple[str, str], JsonDict] = {}

    @contextmanager
    def use_app_selector(self, selector: AppSelector | None):
        """Temporarily target a non-default app for this tool call."""

        if selector is None:
            yield
            return

        token = _APP_SELECTOR.set(selector)
        try:
            yield
        finally:
            _APP_SELECTOR.reset(token)

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: JsonDict | None = None,
        headers: dict[str, str] | None = None,
        use_auth: bool = True,
        timeout: int = 40,
    ) -> JsonDict:
        """Send an App Store Connect API request with retry handling."""

        url = path if path.startswith("http") else f"{self._settings.app_store_base_url}{path}"
        retry_401 = True
        rate_limit_attempts = 0

        while True:
            request_headers = {"Content-Type": "application/json"}
            if headers:
                request_headers.update(headers)
            if use_auth:
                request_headers["Authorization"] = f"Bearer {self._token_provider.get_token(force_refresh=False)}"

            response = self._session.request(
                method=method,
                url=url,
                json=json_body,
                headers=request_headers,
                timeout=timeout,
            )

            if 200 <= response.status_code < 300:
                if not response.content:
                    return {}
                if "application/json" in response.headers.get("Content-Type", ""):
                    return response.json()
                return {"raw": response.text}

            if response.status_code == 401 and retry_401 and use_auth:
                retry_401 = False
                self._token_provider.invalidate()
                continue

            if response.status_code == 429 and rate_limit_attempts < 3:
                rate_limit_attempts += 1
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2 ** (rate_limit_attempts - 1))
                self._sleep_fn(delay)
                continue

            self._raise_api_error(response)

    def get_collection(self, path: str) -> list[JsonDict]:
        """Fetch a paginated collection."""

        payload = self.request("GET", path)
        items = list(payload.get("data", []))
        next_link = payload.get("links", {}).get("next")

        while next_link:
            payload = self.request("GET", next_link)
            items.extend(payload.get("data", []))
            next_link = payload.get("links", {}).get("next")
        return items

    def get_configured_app(self) -> JsonDict:
        """Return the configured app resource, cached in-memory."""

        selector = _APP_SELECTOR.get()
        if selector is not None:
            return self._resolve_selected_app(selector)

        if self._cached_app is not None:
            return self._cached_app

        params = urlencode({"filter[bundleId]": self._settings.app_store_bundle_id, "limit": 2})
        payload = self.request("GET", f"/v1/apps?{params}")
        apps = payload.get("data", [])
        if not apps:
            raise ResourceNotFoundError(
                "No App Store Connect app matched the configured bundle id",
                details={"bundle_id": self._settings.app_store_bundle_id},
            )

        self._cached_app = apps[0]
        return self._cached_app

    def _resolve_selected_app(self, selector: AppSelector) -> JsonDict:
        if "app_id" in selector:
            return self._get_selected_app_by_id(selector["app_id"])
        if "bundle_id" in selector:
            return self._get_selected_app_by_filter(
                cache_key=("bundle_id", selector["bundle_id"]),
                filter_name="filter[bundleId]",
                filter_value=selector["bundle_id"],
                detail_key="bundle_id",
            )
        if "app_name" in selector:
            return self._get_selected_app_by_filter(
                cache_key=("app_name", selector["app_name"]),
                filter_name="filter[name]",
                filter_value=selector["app_name"],
                detail_key="app_name",
            )
        raise ConfigurationError(
            "Unsupported app selector",
            details={"selector": selector},
        )

    def _get_selected_app_by_id(self, app_id: str) -> JsonDict:
        cache_key = ("app_id", app_id)
        cached = self._cached_selected_apps.get(cache_key)
        if cached is not None:
            return cached

        payload = self.request("GET", f"/v1/apps/{app_id}")
        app = payload.get("data")
        if not isinstance(app, dict) or not app:
            raise ResourceNotFoundError(
                "No App Store Connect app matched the requested app id",
                details={"app_id": app_id},
            )

        self._cached_selected_apps[cache_key] = app
        return app

    def _get_selected_app_by_filter(
        self,
        *,
        cache_key: tuple[str, str],
        filter_name: str,
        filter_value: str,
        detail_key: str,
    ) -> JsonDict:
        cached = self._cached_selected_apps.get(cache_key)
        if cached is not None:
            return cached

        params = urlencode({filter_name: filter_value, "limit": 10})
        payload = self.request("GET", f"/v1/apps?{params}")
        apps = payload.get("data", [])
        if not apps:
            raise ResourceNotFoundError(
                "No App Store Connect app matched the requested selector",
                details={detail_key: filter_value},
            )

        app = self._select_unique_app_match(
            apps,
            detail_key=detail_key,
            expected=filter_value,
        )
        self._cached_selected_apps[cache_key] = app
        return app

    @staticmethod
    def _select_unique_app_match(
        apps: list[JsonDict],
        *,
        detail_key: str,
        expected: str,
    ) -> JsonDict:
        if len(apps) == 1:
            return apps[0]

        attribute = "bundleId" if detail_key == "bundle_id" else "name"
        exact_matches = [
            app for app in apps if str(app.get("attributes", {}).get(attribute) or "").casefold() == expected.casefold()
        ]
        if len(exact_matches) == 1:
            return exact_matches[0]

        raise ConfigurationError(
            "App selector matched multiple App Store Connect apps",
            details={
                detail_key: expected,
                "matches": [
                    {
                        "id": app.get("id"),
                        "name": app.get("attributes", {}).get("name"),
                        "bundle_id": app.get("attributes", {}).get("bundleId"),
                    }
                    for app in apps
                ],
            },
        )

    def get_app_info(self) -> JsonDict:
        return self.get_configured_app()

    def get_app_infos(self) -> list[JsonDict]:
        app_id = self.get_configured_app()["id"]
        return self.get_collection(f"/v1/apps/{app_id}/appInfos")

    def get_primary_app_info(self) -> JsonDict:
        app_infos = self.get_app_infos()
        if not app_infos:
            raise ResourceNotFoundError("App Store Connect app has no appInfos")
        return app_infos[0]

    def get_app_info_localizations(self, app_info_id: str) -> list[JsonDict]:
        return self.get_collection(f"/v1/appInfos/{app_info_id}/appInfoLocalizations")

    def get_app_versions(self) -> list[JsonDict]:
        app_id = self.get_configured_app()["id"]
        versions = self.get_collection(f"/v1/apps/{app_id}/appStoreVersions")
        return sorted(
            versions,
            key=lambda item: item.get("attributes", {}).get("createdDate", ""),
            reverse=True,
        )

    def get_current_version(self) -> JsonDict:
        versions = self.get_app_versions()
        if not versions:
            raise ResourceNotFoundError("App Store Connect app has no App Store versions")

        editable = [
            version
            for version in versions
            if version.get("attributes", {}).get("appVersionState") in EDITABLE_VERSION_STATES
        ]
        return editable[0] if editable else versions[0]

    def get_version_localizations(self, version_id: str) -> list[JsonDict]:
        return self.get_collection(f"/v1/appStoreVersions/{version_id}/appStoreVersionLocalizations")

    def get_screenshot_sets(self, version_localization_id: str) -> list[JsonDict]:
        return self.get_collection(f"/v1/appStoreVersionLocalizations/{version_localization_id}/appScreenshotSets")

    def get_screenshots(self, screenshot_set_id: str) -> list[JsonDict]:
        return self.get_collection(f"/v1/appScreenshotSets/{screenshot_set_id}/appScreenshots")

    def get_app_price_schedule(self) -> JsonDict:
        app_id = self.get_configured_app()["id"]
        payload = self.request("GET", f"/v1/apps/{app_id}/appPriceSchedule")
        data = payload.get("data", {})
        relationships = data.get("relationships", {})

        related: dict[str, Any] = {}
        for key in ("baseTerritory", "manualPrices", "automaticPrices"):
            related_link = relationships.get(key, {}).get("links", {}).get("related")
            if related_link:
                related[key] = self.request("GET", related_link)

        return {
            "schedule": data,
            "related": related,
        }

    def get_version_by_id(self, version_id: str) -> JsonDict:
        payload = self.request("GET", f"/v1/appStoreVersions/{version_id}")
        return payload.get("data", {})

    def get_version_build(self, version_id: str) -> JsonDict:
        payload = self.request("GET", f"/v1/appStoreVersions/{version_id}/build")
        return payload.get("data", {})

    def list_builds(
        self,
        *,
        version_string: str | None = None,
        build_number: str | None = None,
        processing_state: str | None = None,
        limit: int = 50,
    ) -> list[JsonDict]:
        app_id = self.get_configured_app()["id"]
        query: dict[str, str | int] = {
            "filter[app]": app_id,
            "limit": max(1, min(limit, 200)),
        }
        if version_string:
            query["filter[preReleaseVersion.version]"] = version_string
        if build_number:
            query["filter[version]"] = build_number
        if processing_state:
            query["filter[processingState]"] = processing_state
        params = urlencode(query)
        return self.get_collection(f"/v1/builds?{params}")

    def create_app_store_version(
        self,
        *,
        version_string: str,
        platform: str,
        release_type: str | None = None,
        earliest_release_date: str | None = None,
        copyright_text: str | None = None,
    ) -> JsonDict:
        attributes: JsonDict = {
            "platform": platform,
            "versionString": version_string,
        }
        if release_type is not None:
            attributes["releaseType"] = release_type
        if earliest_release_date is not None:
            attributes["earliestReleaseDate"] = earliest_release_date
        if copyright_text is not None:
            attributes["copyright"] = copyright_text

        app_id = self.get_configured_app()["id"]
        return self.request(
            "POST",
            "/v1/appStoreVersions",
            json_body={
                "data": {
                    "type": "appStoreVersions",
                    "attributes": attributes,
                    "relationships": {
                        "app": {
                            "data": {
                                "type": "apps",
                                "id": app_id,
                            }
                        }
                    },
                }
            },
        )

    def update_app_store_version(self, version_id: str, attributes: JsonDict) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v1/appStoreVersions/{version_id}",
            json_body={
                "data": {
                    "id": version_id,
                    "type": "appStoreVersions",
                    "attributes": attributes,
                }
            },
        )

    def set_version_build(self, version_id: str, build_id: str) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v1/appStoreVersions/{version_id}/relationships/build",
            json_body={
                "data": {
                    "type": "builds",
                    "id": build_id,
                }
            },
        )

    def release_app_store_version(self, version_id: str) -> JsonDict:
        return self.request(
            "POST",
            "/v1/appStoreVersionReleaseRequests",
            json_body={
                "data": {
                    "type": "appStoreVersionReleaseRequests",
                    "relationships": {
                        "appStoreVersion": {
                            "data": {
                                "type": "appStoreVersions",
                                "id": version_id,
                            }
                        }
                    },
                }
            },
        )

    def get_review_submissions(self, *, limit: int = 50, include_items: bool = False) -> JsonDict:
        app_id = self.get_configured_app()["id"]
        query: dict[str, str | int] = {"limit": max(1, min(limit, 200))}
        if include_items:
            query["include"] = "items"
        params = urlencode(query)
        return self.request("GET", f"/v1/apps/{app_id}/reviewSubmissions?{params}")

    def create_review_submission(self) -> JsonDict:
        app_id = self.get_configured_app()["id"]
        return self.request(
            "POST",
            "/v1/reviewSubmissions",
            json_body={
                "data": {
                    "type": "reviewSubmissions",
                    "relationships": {
                        "app": {
                            "data": {
                                "type": "apps",
                                "id": app_id,
                            }
                        }
                    },
                }
            },
        )

    def add_custom_product_page_version_to_review_submission(
        self,
        *,
        review_submission_id: str,
        page_version_id: str,
    ) -> JsonDict:
        return self.request(
            "POST",
            "/v1/reviewSubmissionItems",
            json_body={
                "data": {
                    "type": "reviewSubmissionItems",
                    "relationships": {
                        "reviewSubmission": {
                            "data": {
                                "type": "reviewSubmissions",
                                "id": review_submission_id,
                            }
                        },
                        "appCustomProductPageVersion": {
                            "data": {
                                "type": "appCustomProductPageVersions",
                                "id": page_version_id,
                            }
                        },
                    },
                }
            },
        )

    def get_product_page_optimization_experiments(
        self,
        *,
        version_id: str | None = None,
        limit: int = 50,
    ) -> list[JsonDict]:
        resolved_version_id = version_id or self.get_current_version()["id"]
        params = urlencode({"limit": max(1, min(limit, 200))})
        return self.get_collection(f"/v1/appStoreVersions/{resolved_version_id}/appStoreVersionExperimentsV2?{params}")

    def get_product_page_optimization_experiment(self, experiment_id: str) -> JsonDict:
        payload = self.request("GET", f"/v2/appStoreVersionExperiments/{experiment_id}")
        return payload.get("data", {})

    def create_product_page_optimization_experiment(
        self,
        *,
        name: str,
        traffic_proportion: int,
        platform: str = "IOS",
    ) -> JsonDict:
        app_id = self.get_configured_app()["id"]
        return self.request(
            "POST",
            "/v2/appStoreVersionExperiments",
            json_body={
                "data": {
                    "type": "appStoreVersionExperiments",
                    "attributes": {
                        "name": name,
                        "platform": platform,
                        "trafficProportion": traffic_proportion,
                    },
                    "relationships": {
                        "app": {
                            "data": {
                                "type": "apps",
                                "id": app_id,
                            }
                        }
                    },
                }
            },
        )

    def update_product_page_optimization_experiment(
        self,
        experiment_id: str,
        attributes: JsonDict,
    ) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v2/appStoreVersionExperiments/{experiment_id}",
            json_body={
                "data": {
                    "id": experiment_id,
                    "type": "appStoreVersionExperiments",
                    "attributes": attributes,
                }
            },
        )

    def delete_product_page_optimization_experiment(self, experiment_id: str) -> JsonDict:
        return self.request("DELETE", f"/v2/appStoreVersionExperiments/{experiment_id}")

    def get_product_page_optimization_treatments(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
    ) -> list[JsonDict]:
        params = urlencode({"limit": max(1, min(limit, 200))})
        return self.get_collection(
            f"/v2/appStoreVersionExperiments/{experiment_id}/appStoreVersionExperimentTreatments?{params}"
        )

    def get_product_page_optimization_treatment(self, treatment_id: str) -> JsonDict:
        payload = self.request("GET", f"/v1/appStoreVersionExperimentTreatments/{treatment_id}")
        return payload.get("data", {})

    def create_product_page_optimization_treatment(
        self,
        *,
        experiment_id: str,
        name: str,
        app_icon_name: str | None = None,
        use_v2_relationship: bool = True,
    ) -> JsonDict:
        attributes: JsonDict = {"name": name}
        if app_icon_name is not None:
            attributes["appIconName"] = app_icon_name

        relationship_key = "appStoreVersionExperimentV2" if use_v2_relationship else "appStoreVersionExperiment"
        return self.request(
            "POST",
            "/v1/appStoreVersionExperimentTreatments",
            json_body={
                "data": {
                    "type": "appStoreVersionExperimentTreatments",
                    "attributes": attributes,
                    "relationships": {
                        relationship_key: {
                            "data": {
                                "type": "appStoreVersionExperiments",
                                "id": experiment_id,
                            }
                        }
                    },
                }
            },
        )

    def update_product_page_optimization_treatment(
        self,
        treatment_id: str,
        attributes: JsonDict,
    ) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v1/appStoreVersionExperimentTreatments/{treatment_id}",
            json_body={
                "data": {
                    "id": treatment_id,
                    "type": "appStoreVersionExperimentTreatments",
                    "attributes": attributes,
                }
            },
        )

    def delete_product_page_optimization_treatment(self, treatment_id: str) -> JsonDict:
        return self.request("DELETE", f"/v1/appStoreVersionExperimentTreatments/{treatment_id}")

    def get_custom_product_pages(self, *, include_versions: bool = False, limit: int = 50) -> JsonDict:
        app_id = self.get_configured_app()["id"]
        query: dict[str, str | int] = {"limit": max(1, min(limit, 200))}
        if include_versions:
            query["include"] = "appCustomProductPageVersions"
        params = urlencode(query)
        return self.request("GET", f"/v1/apps/{app_id}/appCustomProductPages?{params}")

    def get_custom_product_page(self, page_id: str) -> JsonDict:
        return self.request("GET", f"/v1/appCustomProductPages/{page_id}")

    def get_custom_product_page_versions(self, page_id: str) -> list[JsonDict]:
        return self.get_collection(f"/v1/appCustomProductPages/{page_id}/appCustomProductPageVersions")

    def get_custom_product_page_version(self, version_id: str) -> JsonDict:
        payload = self.request("GET", f"/v1/appCustomProductPageVersions/{version_id}")
        return payload.get("data", {})

    def get_custom_product_page_localizations(self, version_id: str) -> list[JsonDict]:
        return self.get_collection(f"/v1/appCustomProductPageVersions/{version_id}/appCustomProductPageLocalizations")

    def get_custom_product_page_localization(self, localization_id: str) -> JsonDict:
        payload = self.request("GET", f"/v1/appCustomProductPageLocalizations/{localization_id}")
        return payload.get("data", {})

    def get_cpp_screenshot_sets(self, localization_id: str) -> list[JsonDict]:
        return self.get_collection(f"/v1/appCustomProductPageLocalizations/{localization_id}/appScreenshotSets")

    def create_custom_product_page(
        self,
        *,
        name: str,
        locale: str,
        promotional_text: str | None = None,
        deep_link: str | None = None,
    ) -> JsonDict:
        app_id = self.get_configured_app()["id"]
        version_inline_id = f"${{{'cppVersion' + uuid4().hex}}}"
        localization_inline_id = f"${{{'cppLocalization' + uuid4().hex}}}"

        version_resource: JsonDict = {
            "id": version_inline_id,
            "type": "appCustomProductPageVersions",
            "relationships": {
                "appCustomProductPageLocalizations": {
                    "data": [
                        {
                            "id": localization_inline_id,
                            "type": "appCustomProductPageLocalizations",
                        }
                    ]
                }
            },
        }
        if deep_link is not None:
            version_resource["attributes"] = {"deepLink": deep_link}

        localization_attributes: JsonDict = {"locale": locale}
        if promotional_text is not None:
            localization_attributes["promotionalText"] = promotional_text

        localization_resource: JsonDict = {
            "id": localization_inline_id,
            "type": "appCustomProductPageLocalizations",
            "attributes": localization_attributes,
        }

        return self.request(
            "POST",
            "/v1/appCustomProductPages",
            json_body={
                "data": {
                    "type": "appCustomProductPages",
                    "attributes": {
                        "name": name,
                    },
                    "relationships": {
                        "app": {
                            "data": {
                                "type": "apps",
                                "id": app_id,
                            }
                        },
                        "appCustomProductPageVersions": {
                            "data": [
                                {
                                    "id": version_inline_id,
                                    "type": "appCustomProductPageVersions",
                                }
                            ]
                        },
                    },
                },
                "included": [
                    version_resource,
                    localization_resource,
                ],
            },
        )

    def update_custom_product_page(self, page_id: str, attributes: JsonDict) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v1/appCustomProductPages/{page_id}",
            json_body={
                "data": {
                    "id": page_id,
                    "type": "appCustomProductPages",
                    "attributes": attributes,
                }
            },
        )

    def delete_custom_product_page(self, page_id: str) -> JsonDict:
        return self.request("DELETE", f"/v1/appCustomProductPages/{page_id}")

    def create_custom_product_page_version(
        self,
        page_id: str,
        *,
        deep_link: str | None = None,
    ) -> JsonDict:
        attributes: JsonDict = {}
        if deep_link is not None:
            attributes["deepLink"] = deep_link

        data: JsonDict = {
            "type": "appCustomProductPageVersions",
            "relationships": {
                "appCustomProductPage": {
                    "data": {
                        "type": "appCustomProductPages",
                        "id": page_id,
                    }
                }
            },
        }
        if attributes:
            data["attributes"] = attributes

        return self.request(
            "POST",
            "/v1/appCustomProductPageVersions",
            json_body={"data": data},
        )

    def update_custom_product_page_version(self, version_id: str, attributes: JsonDict) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v1/appCustomProductPageVersions/{version_id}",
            json_body={
                "data": {
                    "id": version_id,
                    "type": "appCustomProductPageVersions",
                    "attributes": attributes,
                }
            },
        )

    def create_custom_product_page_localization(
        self,
        *,
        version_id: str,
        locale: str,
        promotional_text: str | None = None,
    ) -> JsonDict:
        attributes: JsonDict = {"locale": locale}
        if promotional_text is not None:
            attributes["promotionalText"] = promotional_text

        return self.request(
            "POST",
            "/v1/appCustomProductPageLocalizations",
            json_body={
                "data": {
                    "type": "appCustomProductPageLocalizations",
                    "attributes": attributes,
                    "relationships": {
                        "appCustomProductPageVersion": {
                            "data": {
                                "type": "appCustomProductPageVersions",
                                "id": version_id,
                            }
                        }
                    },
                }
            },
        )

    def update_custom_product_page_localization(
        self,
        localization_id: str,
        attributes: JsonDict,
    ) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v1/appCustomProductPageLocalizations/{localization_id}",
            json_body={
                "data": {
                    "id": localization_id,
                    "type": "appCustomProductPageLocalizations",
                    "attributes": attributes,
                }
            },
        )

    def delete_custom_product_page_localization(self, localization_id: str) -> JsonDict:
        return self.request("DELETE", f"/v1/appCustomProductPageLocalizations/{localization_id}")

    def create_cpp_screenshot_set(self, localization_id: str, display_type: str) -> JsonDict:
        return self.request(
            "POST",
            "/v1/appScreenshotSets",
            json_body={
                "data": {
                    "type": "appScreenshotSets",
                    "attributes": {"screenshotDisplayType": display_type},
                    "relationships": {
                        "appCustomProductPageLocalization": {
                            "data": {
                                "type": "appCustomProductPageLocalizations",
                                "id": localization_id,
                            }
                        }
                    },
                }
            },
        )

    def find_locale(self, resources: Iterable[JsonDict], locale: str) -> JsonDict:
        locale_lower = locale.lower()
        fallback: JsonDict | None = None
        for resource in resources:
            item_locale = str(resource.get("attributes", {}).get("locale", "")).lower()
            if item_locale == locale_lower:
                return resource
            if item_locale.startswith(locale_lower.split("-")[0]):
                fallback = resource
        if fallback is not None:
            return fallback

        raise ResourceNotFoundError(
            "Requested locale is not configured in App Store Connect",
            details={"locale": locale},
        )

    def update_app_info_localization(self, localization_id: str, attributes: JsonDict) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v1/appInfoLocalizations/{localization_id}",
            json_body={
                "data": {
                    "id": localization_id,
                    "type": "appInfoLocalizations",
                    "attributes": attributes,
                }
            },
        )

    def update_version_localization(self, localization_id: str, attributes: JsonDict) -> JsonDict:
        return self.request(
            "PATCH",
            f"/v1/appStoreVersionLocalizations/{localization_id}",
            json_body={
                "data": {
                    "id": localization_id,
                    "type": "appStoreVersionLocalizations",
                    "attributes": attributes,
                }
            },
        )

    def create_screenshot_set(self, localization_id: str, display_type: str) -> JsonDict:
        return self.request(
            "POST",
            "/v1/appScreenshotSets",
            json_body={
                "data": {
                    "type": "appScreenshotSets",
                    "attributes": {"screenshotDisplayType": display_type},
                    "relationships": {
                        "appStoreVersionLocalization": {
                            "data": {
                                "type": "appStoreVersionLocalizations",
                                "id": localization_id,
                            }
                        }
                    },
                }
            },
        )

    def create_screenshot_reservation(
        self,
        screenshot_set_id: str,
        *,
        file_name: str,
        file_size: int,
    ) -> JsonDict:
        return self.request(
            "POST",
            "/v1/appScreenshots",
            json_body={
                "data": {
                    "type": "appScreenshots",
                    "attributes": {
                        "fileName": file_name,
                        "fileSize": file_size,
                    },
                    "relationships": {
                        "appScreenshotSet": {
                            "data": {
                                "type": "appScreenshotSets",
                                "id": screenshot_set_id,
                            }
                        }
                    },
                }
            },
        )

    def finalize_screenshot_upload(self, screenshot_id: str, file_path: str) -> JsonDict:
        checksum = hashlib.md5(Path(file_path).read_bytes()).hexdigest()
        return self.request(
            "PATCH",
            f"/v1/appScreenshots/{screenshot_id}",
            json_body={
                "data": {
                    "id": screenshot_id,
                    "type": "appScreenshots",
                    "attributes": {
                        "sourceFileChecksum": checksum,
                        "uploaded": True,
                    },
                }
            },
        )

    def execute_upload_operations(self, operations: list[JsonDict], file_path: str) -> list[JsonDict]:
        payload = Path(file_path).read_bytes()
        responses: list[JsonDict] = []

        for operation in operations:
            method = operation.get("method", "PUT")
            url = operation.get("url")
            if not url:
                raise AscApiError(
                    "App Store Connect returned an upload operation without a URL",
                    status_code=500,
                    retryable=False,
                    details={"operation": operation},
                )

            offset = int(operation.get("offset", 0) or 0)
            length = int(operation.get("length", len(payload)) or len(payload))
            body = payload[offset : offset + length]

            headers: dict[str, str] = {}
            for header in operation.get("requestHeaders", []) or []:
                name = header.get("name")
                value = header.get("value")
                if name and value is not None:
                    headers[str(name)] = str(value)

            response = self._session.request(
                method=method,
                url=url,
                headers=headers,
                data=body,
                timeout=120,
            )
            if not (200 <= response.status_code < 300):
                raise AscApiError(
                    "Screenshot upload failed during asset transfer",
                    status_code=response.status_code,
                    retryable=response.status_code in {429, 500, 502, 503, 504},
                    details={"body": response.text[:1000]},
                )
            responses.append(
                {
                    "method": method,
                    "url": url,
                    "status_code": response.status_code,
                }
            )

        return responses

    def submit_for_review(self, version_id: str) -> JsonDict:
        return self.request(
            "POST",
            "/v1/appStoreVersionSubmissions",
            json_body={
                "data": {
                    "type": "appStoreVersionSubmissions",
                    "relationships": {
                        "appStoreVersion": {
                            "data": {
                                "type": "appStoreVersions",
                                "id": version_id,
                            }
                        }
                    },
                }
            },
        )

    def _raise_api_error(self, response: requests.Response) -> None:
        details: Any = None
        title = response.reason or "App Store Connect request failed"
        detail_message = response.text[:1000]

        try:
            payload = response.json()
            details = payload
            errors = payload.get("errors") or []
            if errors:
                first = errors[0]
                title = first.get("title") or title
                detail_message = first.get("detail") or detail_message
        except ValueError:
            details = {"body": detail_message}

        hint: str | None = None
        if response.status_code == 403:
            hint = "The App Store Connect API key likely needs App Manager or Admin access for this app."
        elif response.status_code == 409:
            hint = (
                "The target version or localization is in a state that does not accept "
                "this edit. Check get_app_versions and move the change to a "
                "PREPARE_FOR_SUBMISSION version if needed."
            )
        elif response.status_code == 429:
            hint = "Rate limited by App Store Connect after the maximum retry attempts."

        if response.status_code == 404:
            raise ResourceNotFoundError(
                detail_message or title,
                details=details,
            )

        raise AscApiError(
            f"{title}: {detail_message}".strip(),
            status_code=response.status_code,
            retryable=response.status_code in {401, 429, 500, 502, 503, 504},
            details=details,
            hint=hint,
        )
