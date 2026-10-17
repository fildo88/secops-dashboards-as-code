#! /usr/bin/env python3
# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import logging
import os
import subprocess
from pathlib import Path

from config import SECOPS_CUSTOMER_ID, SECOPS_PROJECT_ID, SECOPS_REGION
import google.oauth2.credentials
from models import DashboardOperation, DashboardType, NativeDashboard
from secops import SecOpsClient
from secops.auth import RetryConfig
from secops.exceptions import APIError
from utils import setup_logging

setup_logging()

LOGGER = logging.getLogger(__name__)


def _resolve_credentials() -> tuple[google.oauth2.credentials.Credentials | None, bool]:
    """Resolves credentials.

    In GitHub Actions (where GOOGLE_APPLICATION_CREDENTIALS points to the WIF
    external_account file created by google-github-actions/auth@v2), returns
    (None, False) so SecOpsClient uses google.auth.default() directly without
    requiring serviceusage.services.use quota-project headers.
    Locally on Cloudtop, falls back to SECOPS_ACCESS_TOKEN or `gcloud auth print-access-token`.
    """
    adc_file = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if adc_file and os.path.exists(adc_file):
        return None, False

    token = os.environ.get("SECOPS_ACCESS_TOKEN")
    if not token:
        try:
            env = os.environ.copy()
            env["CLOUDSDK_METRICS_ENVIRONMENT"] = "datacloud.jetski"
            proc = subprocess.run(
                ["gcloud", "auth", "print-access-token"],
                capture_output=True,
                text=True,
                timeout=5,
                env=env,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                token = proc.stdout.strip()
        except Exception:
            pass
    if token:
        return (
            google.oauth2.credentials.Credentials(
                token=token,
                quota_project_id=SECOPS_PROJECT_ID,
            ),
            True,
        )
    return None, False


class DashboardManager:
    """Manages the lifecycle of SecOps Native Dashboards as Code."""

    def __init__(self):
        if not all([SECOPS_CUSTOMER_ID, SECOPS_PROJECT_ID, SECOPS_REGION]):
            raise APIError(
                "Missing SecOps env vars: SECOPS_CUSTOMER_ID, SECOPS_PROJECT_ID, SECOPS_REGION."
            )
        try:
            retry_config = RetryConfig(
                total=10,
                retry_status_codes=[429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST", "PATCH", "DELETE"],
                backoff_factor=0.5,
            )
            creds, needs_user_project_header = _resolve_credentials()
            self.client = SecOpsClient(
                credentials=creds,
                retry_config=retry_config,
            ).chronicle(
                customer_id=SECOPS_CUSTOMER_ID,
                project_id=SECOPS_PROJECT_ID,
                region=SECOPS_REGION,
            )
            if needs_user_project_header:
                self.client.session.headers["x-goog-user-project"] = SECOPS_PROJECT_ID
            LOGGER.info(
                f"SecOps client initialized successfully for project={SECOPS_PROJECT_ID}, "
                f"region={SECOPS_REGION}, customer_id={SECOPS_CUSTOMER_ID}."
            )
        except Exception as e:
            raise APIError(f"Failed to initialize SecOps client: {e}") from e

    def export_dashboard(self, dashboard_names: list[str]):
        return self.client.export_dashboard(dashboard_names=dashboard_names)

    def list_remote_dashboards(self, include_charts: bool = True) -> dict:
        """
        Fetches all custom dashboards and optionally their charts from the Google SecOps API.

        Returns:
            dict: A dictionary where keys are dashboard displayNames and values are
                  NativeDashboard (if include_charts=False) or dicts containing
                  dashboard details and a list of its charts (if include_charts=True).
        """
        try:
            all_dashboards_raw = self.client.list_dashboards(page_size=1000)
            dashboards = {}

            if "nativeDashboards" not in all_dashboards_raw:
                LOGGER.info("No remote dashboards found.")
                return dashboards

            all_dashboards = [
                NativeDashboard.from_dict(d)
                for d in all_dashboards_raw["nativeDashboards"]
            ]

            for dashboard in all_dashboards:
                if not dashboard.display_name:
                    LOGGER.warning(
                        f"Skipping a dashboard with no displayName: {dashboard.name}"
                    )
                    continue

                if dashboard.type == DashboardType.CURATED:
                    LOGGER.debug(f"Skipping a curated dashboard: {dashboard.name}")
                    continue

                if include_charts:
                    LOGGER.info(
                        f"Fetching full details for dashboard: {dashboard.display_name}"
                    )
                    full_dashboard_dict = self.client.get_dashboard(
                        dashboard.name.split("/")[-1], "FULL"
                    )
                    full_dashboard = NativeDashboard.from_dict(full_dashboard_dict)
                    charts_list = []
                    if full_dashboard.definition and full_dashboard.definition.charts:
                        for chart_ref in full_dashboard.definition.charts:
                            if chart_ref.dashboard_chart:
                                chart_id = chart_ref.dashboard_chart.split("/")[-1]
                                try:
                                    chart_details = self.client.get_chart(chart_id)
                                    charts_list.append(chart_details)
                                except Exception as e:  # noqa: BLE001
                                    LOGGER.error(
                                        f"Failed to fetch chart {chart_id} for dashboard {dashboard.display_name}: {e}"
                                    )

                    dashboards[dashboard.display_name] = {
                        "dashboard": full_dashboard,
                        "dashboardCharts": charts_list,
                    }
                else:
                    dashboards[dashboard.display_name] = dashboard
            return dashboards

        except Exception as e:  # noqa: BLE001
            LOGGER.error(
                "Error: Could not connect to Google SecOps API or list dashboards."
            )
            LOGGER.error(f"Details: {e}")
            raise

    def get_local_dashboards_with_charts(self, path: str = "./dashboards") -> dict:
        dashboard_dir = Path(path)
        if not dashboard_dir.is_dir():
            LOGGER.error(f"Error: Directory '{path}' not found.")
            return {}

        local_dashboards = {}
        for json_file in sorted(dashboard_dir.glob("*.json")):
            try:
                with open(json_file, "r") as f:
                    config = json.load(f)
                    dashboard_def = config["dashboards"][0]
                    dashboard_name = dashboard_def["dashboard"]["displayName"]
                    charts = dashboard_def.get("dashboardCharts", [])
                    queries = dashboard_def.get("dashboardQueries", [])

                    local_dashboards[dashboard_name] = {
                        "dashboard": dashboard_def["dashboard"],
                        "dashboardCharts": charts,
                        "dashboardQueries": queries,
                    }
            except (json.JSONDecodeError, KeyError) as e:
                LOGGER.error(f"Error parsing {json_file.name}: {e}")
            except Exception as e:  # noqa: BLE001
                LOGGER.error(
                    f"An unexpected error occurred with file {json_file.name}: {e}"
                )

        return local_dashboards

    def are_charts_different(self, local_chart: dict, remote_chart: dict) -> bool:
        local_copy = local_chart.copy()
        remote_copy = remote_chart.copy()

        ignore_fields = [
            "name",
            "etag",
            "chartDatasource",
            "chartType",
            "nativeDashboard",
            "createTime",
            "updateTime",
            "createUserId",
            "updateUserId",
            "chartQuery",
        ]

        for field in ignore_fields:
            local_copy.pop(field, None)
            remote_copy.pop(field, None)

        return local_copy != remote_copy

    def compute_dashboard_operations(self):
        local_dashboards = self.get_local_dashboards_with_charts()
        if not local_dashboards:
            LOGGER.info("No local dashboards found in ./dashboards. Exiting.")
            return {}
        LOGGER.info(f"\nFound {len(local_dashboards)} local dashboard(s):")
        for name in sorted(local_dashboards.keys()):
            LOGGER.info(f"  - {name}")

        LOGGER.info("\nFetching remote dashboards from Google SecOps...")
        remote_dashboards = self.list_remote_dashboards()
        if not remote_dashboards:
            LOGGER.info("Could not retrieve any remote custom dashboards.")
        else:
            LOGGER.info(f"Found {len(remote_dashboards)} remote custom dashboard(s).")

        dashboards_ops = {}

        for name, local_data in local_dashboards.items():
            if name not in remote_dashboards:
                dashboards_ops[name] = {
                    "operation": DashboardOperation.CREATE,
                    "dashboard": local_data,
                }
            else:
                remote_data = remote_dashboards[name]
                local_charts_map = {
                    c["displayName"]: c for c in local_data.get("dashboardCharts", [])
                }
                remote_charts_map = {
                    c["displayName"]: c for c in remote_data.get("dashboardCharts", [])
                }

                charts_to_add = [
                    c
                    for cname, c in local_charts_map.items()
                    if cname not in remote_charts_map
                ]
                charts_to_delete = [
                    c
                    for cname, c in remote_charts_map.items()
                    if cname not in local_charts_map
                ]
                charts_to_update = []

                for chart_name, local_chart in local_charts_map.items():
                    if chart_name in remote_charts_map:
                        remote_chart = remote_charts_map[chart_name]
                        if self.are_charts_different(local_chart, remote_chart):
                            update_payload = local_chart.copy()
                            update_payload["name"] = remote_chart["name"]
                            charts_to_update.append(update_payload)

                # Also check top-level description differences
                remote_dash_obj = remote_data["dashboard"]
                local_dash_dict = local_data["dashboard"]
                meta_diff = local_dash_dict.get("description", "") != (
                    remote_dash_obj.description or ""
                )

                if charts_to_add or charts_to_delete or charts_to_update or meta_diff:
                    dashboards_ops[name] = {
                        "operation": DashboardOperation.UPDATE,
                        "dashboard_id": remote_dash_obj.name.split("/")[-1],
                        "dashboard": local_data,
                    }

        return dashboards_ops

    def plan(self):
        dashboards_ops = self.compute_dashboard_operations()

        LOGGER.info("\n" + "=" * 40)
        LOGGER.info("📊 Comparison Result")
        LOGGER.info("=" * 40)

        if not dashboards_ops:
            LOGGER.info("No dashboard needs to be created or updated.")
            return {}
        else:
            LOGGER.info(
                f"Following dashboards require updates/creation: {list(dashboards_ops.keys())}."
            )
            return dashboards_ops

    def apply(self):
        dashboards_ops = self.compute_dashboard_operations()

        LOGGER.info("\n" + "=" * 40)
        LOGGER.info("📊 Apply Operations")
        LOGGER.info("=" * 40)

        if not dashboards_ops:
            LOGGER.info("No dashboard needs to be created or updated.")
            return {}
        else:
            for name, config in dashboards_ops.items():
                if config["operation"] == DashboardOperation.CREATE:
                    LOGGER.info(f"Creating dashboard '{name}'...")
                    response = self.client.import_dashboard(
                        dashboard=config["dashboard"]
                    )
                    LOGGER.info(f"Response '{response}'")
                    LOGGER.info(f"'{name}' created successfully.")

                elif config["operation"] == DashboardOperation.UPDATE:
                    LOGGER.info(f"  -> Updating dashboard '{name}':")
                    dashboard_id = config["dashboard_id"]

                    self.client.delete_dashboard(dashboard_id=dashboard_id)
                    response = self.client.import_dashboard(
                        dashboard=config["dashboard"]
                    )
                    LOGGER.info(f"Response '{response}'")
                else:
                    raise ValueError(
                        "Dashboard operation is not CREATE or UPDATE, this is inconsistent."
                    )

            return dashboards_ops
