"""Tests for dedicated version transition and Custom Product Page tools."""

from __future__ import annotations

from pathlib import Path

from errors import ResourceNotFoundError
from tools.cpp import create_custom_product_page, get_custom_product_page, upload_custom_product_page_screenshot
from tools.versioning import (
    assign_build_to_version,
    create_product_page_optimization_experiment,
    create_product_page_optimization_treatment,
    create_review_submission,
    update_product_page_optimization_treatment,
)


class FakeChangeLogger:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(self, **kwargs) -> None:
        self.records.append(kwargs)


class FakeRevenueCat:
    def get_overview(self):
        return {
            "project_id": "proj",
            "metrics": {"active_subscriptions": 12, "mrr": 64},
        }


class FakeAsc:
    def __init__(self) -> None:
        self.version = {
            "id": "version-1",
            "attributes": {
                "versionString": "1.0.48",
                "appVersionState": "PREPARE_FOR_SUBMISSION",
            },
        }
        self.build: dict | None = None
        self.pages = {
            "cpp-1": {
                "id": "cpp-1",
                "attributes": {
                    "name": "Weekly Autopilot",
                    "visible": False,
                    "url": "https://apps.apple.com/app?ppid=cpp-1",
                },
            }
        }
        self.page_versions = {
            "cpp-1": [
                {
                    "id": "cpp-version-1",
                    "attributes": {"version": "1", "state": "APPROVED", "deepLink": None},
                }
            ]
        }
        self.localizations = {
            "cpp-version-1": [
                {
                    "id": "cpp-loc-1",
                    "attributes": {
                        "locale": "en-US",
                        "promotionalText": "Original text",
                    },
                }
            ]
        }
        self.screenshot_sets = {"cpp-loc-1": []}
        self.screenshots: dict[str, list[dict]] = {}
        self.review_submissions = [
            {
                "id": "review-1",
                "attributes": {"state": "WAITING_FOR_REVIEW"},
                "relationships": {
                    "items": {
                        "data": [],
                    }
                },
            }
        ]
        self.review_submission_items: dict[str, dict] = {}
        self.experiments = {
            "ppo-1": {
                "id": "ppo-1",
                "attributes": {
                    "name": "Weekly Hooks",
                    "trafficProportion": 50,
                    "platform": "IOS",
                },
                "relationships": {},
            }
        }
        self.experiment_treatments = {
            "ppo-1": [
                {
                    "id": "treatment-1",
                    "attributes": {
                        "name": "Control",
                        "appIconName": None,
                    },
                    "relationships": {
                        "appStoreVersionExperimentV2": {
                            "data": {
                                "id": "ppo-1",
                                "type": "appStoreVersionExperiments",
                            }
                        }
                    },
                }
            ]
        }

    def get_version_by_id(self, version_id: str) -> dict:
        assert version_id == "version-1"
        return self.version

    def get_version_build(self, version_id: str) -> dict:
        assert version_id == "version-1"
        if self.build is None:
            raise ResourceNotFoundError("No build assigned")
        return self.build

    def set_version_build(self, version_id: str, build_id: str) -> dict:
        assert version_id == "version-1"
        self.build = {
            "id": build_id,
            "attributes": {"version": "681", "processingState": "VALID"},
        }
        return {"data": {"id": build_id}}

    def get_review_submissions(self, *, limit: int = 50, include_items: bool = False) -> dict:
        del limit
        included = list(self.review_submission_items.values()) if include_items else []
        return {
            "data": [
                {
                    "id": submission["id"],
                    "attributes": submission["attributes"],
                    "relationships": submission["relationships"],
                }
                for submission in self.review_submissions
            ],
            "included": included,
        }

    def create_review_submission(self) -> dict:
        submission = {
            "id": "review-2",
            "attributes": {"state": "READY_FOR_REVIEW"},
            "relationships": {"items": {"data": []}},
        }
        self.review_submissions.insert(0, submission)
        return {"data": {"id": "review-2", "type": "reviewSubmissions"}}

    def get_current_version(self) -> dict:
        return self.version

    def get_product_page_optimization_experiments(
        self,
        *,
        version_id: str | None = None,
        limit: int = 50,
    ) -> list[dict]:
        del version_id, limit
        return list(self.experiments.values())

    def get_product_page_optimization_experiment(self, experiment_id: str) -> dict:
        return self.experiments[experiment_id]

    def create_product_page_optimization_experiment(
        self,
        *,
        name: str,
        traffic_proportion: int,
        platform: str = "IOS",
    ) -> dict:
        experiment = {
            "id": "ppo-2",
            "attributes": {
                "name": name,
                "trafficProportion": traffic_proportion,
                "platform": platform,
            },
            "relationships": {},
        }
        self.experiments["ppo-2"] = experiment
        self.experiment_treatments["ppo-2"] = []
        return {"data": {"id": "ppo-2", "type": "appStoreVersionExperiments"}}

    def get_product_page_optimization_treatments(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
    ) -> list[dict]:
        del limit
        return list(self.experiment_treatments[experiment_id])

    def create_product_page_optimization_treatment(
        self,
        *,
        experiment_id: str,
        name: str,
        app_icon_name: str | None = None,
        use_v2_relationship: bool = True,
    ) -> dict:
        relationship_key = "appStoreVersionExperimentV2" if use_v2_relationship else "appStoreVersionExperiment"
        treatment = {
            "id": "treatment-2",
            "attributes": {
                "name": name,
                "appIconName": app_icon_name,
            },
            "relationships": {
                relationship_key: {
                    "data": {
                        "id": experiment_id,
                        "type": "appStoreVersionExperiments",
                    }
                }
            },
        }
        self.experiment_treatments[experiment_id].append(treatment)
        return {"data": {"id": "treatment-2", "type": "appStoreVersionExperimentTreatments"}}

    def get_product_page_optimization_treatment(self, treatment_id: str) -> dict:
        for treatments in self.experiment_treatments.values():
            for treatment in treatments:
                if treatment["id"] == treatment_id:
                    return treatment
        raise KeyError(treatment_id)

    def update_product_page_optimization_treatment(self, treatment_id: str, attributes: dict) -> dict:
        treatment = self.get_product_page_optimization_treatment(treatment_id)
        treatment["attributes"] = {**treatment["attributes"], **attributes}
        return {"data": {"id": treatment_id, "type": "appStoreVersionExperimentTreatments"}}

    def get_custom_product_pages(self, *, include_versions: bool = False, limit: int = 50) -> dict:
        del include_versions, limit
        return {"data": list(self.pages.values())}

    def get_custom_product_page(self, page_id: str) -> dict:
        return {"data": self.pages[page_id]}

    def get_custom_product_page_versions(self, page_id: str) -> list[dict]:
        return self.page_versions[page_id]

    def get_custom_product_page_version(self, version_id: str) -> dict:
        return self.page_versions["cpp-1"][0]

    def get_custom_product_page_localizations(self, version_id: str) -> list[dict]:
        return self.localizations[version_id]

    def get_custom_product_page_localization(self, localization_id: str) -> dict:
        for localizations in self.localizations.values():
            for localization in localizations:
                if localization["id"] == localization_id:
                    return localization
        raise KeyError(localization_id)

    def create_custom_product_page(
        self,
        *,
        name: str,
        locale: str,
        promotional_text: str | None = None,
        deep_link: str | None = None,
    ) -> dict:
        page = {
            "id": "cpp-2",
            "attributes": {
                "name": name,
                "visible": False,
                "url": "https://apps.apple.com/app?ppid=cpp-2",
            },
        }
        self.pages["cpp-2"] = page
        self.page_versions["cpp-2"] = [
            {
                "id": "cpp-version-2",
                "attributes": {
                    "version": "1",
                    "state": "PREPARE_FOR_SUBMISSION",
                    "deepLink": deep_link,
                },
            }
        ]
        self.localizations["cpp-version-2"] = [
            {
                "id": "cpp-loc-2",
                "attributes": {
                    "locale": locale,
                    "promotionalText": promotional_text,
                },
            }
        ]
        self.screenshot_sets["cpp-loc-2"] = []
        return {"data": page}

    def update_custom_product_page(self, page_id: str, attributes: dict) -> dict:
        self.pages[page_id]["attributes"] = {
            **self.pages[page_id]["attributes"],
            **attributes,
        }
        return {"data": self.pages[page_id]}

    def get_cpp_screenshot_sets(self, localization_id: str) -> list[dict]:
        return self.screenshot_sets[localization_id]

    def get_screenshots(self, screenshot_set_id: str) -> list[dict]:
        return self.screenshots.get(screenshot_set_id, [])

    def create_cpp_screenshot_set(self, localization_id: str, display_type: str) -> dict:
        screenshot_set = {
            "id": "cpp-set-1",
            "attributes": {"screenshotDisplayType": display_type},
        }
        self.screenshot_sets[localization_id].append(screenshot_set)
        self.screenshots.setdefault("cpp-set-1", [])
        return {"data": screenshot_set}

    def create_screenshot_reservation(
        self,
        screenshot_set_id: str,
        *,
        file_name: str,
        file_size: int,
    ) -> dict:
        del screenshot_set_id, file_name, file_size
        return {
            "data": {
                "id": "shot-1",
                "attributes": {
                    "uploadOperations": [{"method": "PUT", "url": "https://upload"}]
                },
            }
        }

    def execute_upload_operations(self, operations: list[dict], file_path: str) -> list[dict]:
        del operations, file_path
        return [{"status_code": 200}]

    def finalize_screenshot_upload(self, screenshot_id: str, file_path: str) -> dict:
        del file_path
        self.screenshots["cpp-set-1"].append(
            {
                "id": screenshot_id,
                "attributes": {
                    "fileName": "shot.png",
                    "assetDeliveryState": {"state": "COMPLETE"},
                },
            }
        )
        return {"data": {"id": screenshot_id}}


class Runtime:
    def __init__(self) -> None:
        self.asc = FakeAsc()
        self.change_logger = FakeChangeLogger()
        self.revenuecat = FakeRevenueCat()


def test_assign_build_to_version_logs_before_after() -> None:
    runtime = Runtime()

    payload = assign_build_to_version(
        runtime,
        {"version_id": "version-1", "build_id": "build-1"},
    )

    assert payload["after"]["build"]["id"] == "build-1"
    assert runtime.change_logger.records[0]["operation"] == "assign_build_to_version"
    assert runtime.change_logger.records[0]["before"]["build"] is None


def test_create_custom_product_page_returns_snapshot_and_logs() -> None:
    runtime = Runtime()

    payload = create_custom_product_page(
        runtime,
        {
            "name": "Cold Weather Hooks",
            "locale": "en-US",
            "promotional_text": "Weekly outfit planning.",
            "deep_link": "example://cold-weather-hooks",
            "visible": False,
        },
    )

    assert payload["after"]["page"]["name"] == "Cold Weather Hooks"
    assert payload["after"]["versions"][0]["deepLink"] == "example://cold-weather-hooks"
    assert payload["after"]["versions"][0]["localizations"][0]["locale"] == "en-US"
    assert runtime.change_logger.records[0]["operation"] == "create_custom_product_page"


def test_get_custom_product_page_includes_localizations_and_screenshots(tmp_path: Path) -> None:
    runtime = Runtime()
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"fake png")

    upload_custom_product_page_screenshot(
        runtime,
        {
            "localization_id": "cpp-loc-1",
            "display_type": "APP_IPHONE_67",
            "file_path": str(shot),
        },
    )
    payload = get_custom_product_page(
        runtime,
        {"page_id": "cpp-1", "include_screenshots": True},
    )

    localization = payload["custom_product_page"]["versions"][0]["localizations"][0]
    assert localization["screenshot_sets"][0]["count"] == 1
    assert runtime.change_logger.records[-1]["operation"] == "upload_custom_product_page_screenshot"


def test_create_review_submission_logs_created_submission() -> None:
    runtime = Runtime()

    payload = create_review_submission(runtime, {})

    assert payload["created"]["data"]["id"] == "review-2"
    assert runtime.change_logger.records[0]["operation"] == "create_review_submission"
    assert runtime.change_logger.records[0]["after"]["review_submissions"][0]["id"] == "review-2"


def test_create_product_page_optimization_experiment_logs_snapshot() -> None:
    runtime = Runtime()

    payload = create_product_page_optimization_experiment(
        runtime,
        {
            "name": "Rainy Day Test",
            "traffic_proportion": 66,
            "platform": "IOS",
        },
    )

    assert payload["after"]["experiment"]["name"] == "Rainy Day Test"
    assert runtime.change_logger.records[0]["operation"] == "create_product_page_optimization_experiment"


def test_create_and_update_product_page_optimization_treatment_log_changes() -> None:
    runtime = Runtime()

    created = create_product_page_optimization_treatment(
        runtime,
        {
            "experiment_id": "ppo-1",
            "name": "Variant A",
            "app_icon_name": "VariantAIcon",
            "use_v2_relationship": True,
        },
    )
    updated = update_product_page_optimization_treatment(
        runtime,
        {
            "treatment_id": "treatment-2",
            "name": "Variant A2",
            "app_icon_name": None,
        },
    )

    assert created["created"]["data"]["id"] == "treatment-2"
    assert updated["after"]["treatment"]["name"] == "Variant A2"
    assert runtime.change_logger.records[0]["operation"] == "create_product_page_optimization_treatment"
    assert runtime.change_logger.records[1]["operation"] == "update_product_page_optimization_treatment"
