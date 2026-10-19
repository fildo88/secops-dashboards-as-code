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
import re
import sys
from pathlib import Path

import click
from dashboard_manager import DashboardManager
from dotenv import load_dotenv
from utils import generate_pr_comment_output, setup_logging

load_dotenv()

setup_logging()
LOGGER = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_").lower()
    return slug or "dashboard"


def _normalize_export(data: dict) -> dict:
    """Normalizes an exported dashboard payload by stripping volatile export UUIDs and ETags.

    SecOps ExportNativeDashboard calls duplicateDashboardChartsQueriesWithNewID on every export,
    generating fresh UUIDs (and new ETags) and returning charts/queries in non-deterministic order
    even when the dashboard has not changed.
    """
    entry = data.get("dashboards", [{}])[0]
    dash = json.loads(json.dumps(entry.get("dashboard", {})))
    charts = json.loads(json.dumps(entry.get("dashboardCharts", [])))
    queries = json.loads(json.dumps(entry.get("dashboardQueries", [])))

    chart_by_id = {c.get("name"): c for c in charts}
    query_by_id = {q.get("name"): q for q in queries}

    dash.pop("name", None)
    dash.pop("etag", None)
    if "definition" in dash:
        defn = dash["definition"]
        if "charts" in defn:
            norm_layout_charts = []
            for ch_ref in defn.get("charts", []):
                ch_obj = chart_by_id.get(ch_ref.get("dashboardChart"), {})
                norm_layout_charts.append(
                    {
                        "chartDisplayName": ch_obj.get("displayName", ""),
                        "chartLayout": ch_ref.get("chartLayout", {}),
                    }
                )
            defn["charts"] = sorted(
                norm_layout_charts, key=lambda x: json.dumps(x, sort_keys=True)
            )
        if "filters" in defn:
            for flt in defn["filters"]:
                if "chartIds" in flt:
                    flt["chartIds"] = sorted(
                        chart_by_id.get(cid, {}).get("displayName", cid)
                        for cid in flt["chartIds"]
                    )

    norm_charts = []
    for c in charts:
        c.pop("name", None)
        c.pop("etag", None)
        cds = c.get("chartDatasource", {})
        qid = cds.pop("dashboardQuery", None)
        q_obj = query_by_id.get(qid, {})
        cds["queryText"] = q_obj.get("query", "")
        cds["queryInput"] = q_obj.get("input", {})
        c["chartDatasource"] = cds
        norm_charts.append(c)
    norm_charts.sort(
        key=lambda x: (x.get("displayName", ""), json.dumps(x, sort_keys=True))
    )

    norm_queries = []
    for q in queries:
        q.pop("name", None)
        q.pop("etag", None)
        norm_queries.append(q)
    norm_queries.sort(key=lambda x: json.dumps(x, sort_keys=True))

    return {
        "dashboard": dash,
        "dashboardCharts": norm_charts,
        "dashboardQueries": norm_queries,
    }


@click.group()
@click.pass_context
def cli(ctx):
    try:
        ctx.obj = DashboardManager()
    except Exception as e:
        LOGGER.critical(f"Fatal Initialization Error: {e}", exc_info=True)
        sys.exit(1)


@cli.command(name="plan")
@click.pass_obj
def plan(manager: DashboardManager):
    LOGGER.info("🚀 Starting Dashboard as Code deployment plan...")
    plan_res = {}
    has_errors = False
    try:
        LOGGER.info("--- Planning Dashboards deployment ---")
        plan_res = manager.plan()
    except Exception:
        LOGGER.exception("A pipeline error occurred")
        has_errors = True
    finally:
        generate_pr_comment_output(plan_res, has_errors)
        if has_errors:
            sys.exit(1)

    LOGGER.info("\n" + "=" * 40)


@cli.command(name="apply")
@click.pass_obj
def apply(manager: DashboardManager):
    LOGGER.info("🚀 Starting Dashboard as Code deployment ...")
    result = {}
    has_errors = False
    try:
        LOGGER.info("Deploy Dashboards")
        result = manager.apply()
    except Exception:
        LOGGER.exception("A pipeline error occurred")
        has_errors = True
    finally:
        generate_pr_comment_output(result, has_errors)
        if has_errors:
            sys.exit(1)

    LOGGER.info("\n" + "=" * 40)


@cli.command(name="download")
@click.option(
    "--dashboard",
    type=str,
    default=None,
    help="Name of Custom Dashboard to download (or omit / use --all to download all custom dashboards).",
)
@click.option(
    "--all",
    "download_all",
    is_flag=True,
    default=False,
    help="Download all custom dashboards in the tenant.",
)
@click.option(
    "--public/--keep-private",
    "make_public",
    default=True,
    help="Set exported dashboard access to DASHBOARD_PUBLIC (recommended for CI/CD; default: True).",
)
@click.pass_obj
def download(
    manager: DashboardManager,
    dashboard: str | None,
    download_all: bool,
    make_public: bool,
):
    LOGGER.info("🚀 Starting dashboard download...")
    remote_dashboards = manager.list_remote_dashboards(include_charts=False)
    if not remote_dashboards:
        LOGGER.info("No remote custom dashboards found. Exiting.")
        return

    dashboard_dir = Path("./dashboards")
    dashboard_dir.mkdir(exist_ok=True)

    downloaded = 0
    updated = 0
    for name, data in sorted(remote_dashboards.items()):
        if download_all or dashboard is None or name == dashboard:
            file_path = dashboard_dir / f"{_slugify(name)}.json"
            LOGGER.info(f"  -> Exporting dashboard '{name}' ({data.name})...")
            dashboard_export = manager.export_dashboard(dashboard_names=[data.name])
            inline_dest = dashboard_export["inlineDestination"]
            if make_public:
                for d_entry in inline_dest.get("dashboards", []):
                    if "dashboard" in d_entry:
                        d_entry["dashboard"]["access"] = "DASHBOARD_PUBLIC"

            downloaded += 1
            if file_path.exists():
                try:
                    with open(file_path, "r") as existing_f:
                        existing_json = json.load(existing_f)
                    if _normalize_export(existing_json) == _normalize_export(inline_dest):
                        LOGGER.info(f"     ⏭️  Unchanged (keeping existing {file_path})")
                        continue
                except Exception:
                    pass

            with open(file_path, "w") as f:
                json.dump(inline_dest, f, indent=2)
            LOGGER.info(f"     ✍️  Updated {file_path}")
            updated += 1

    if downloaded == 0 and dashboard:
        LOGGER.warning(
            f"Dashboard '{dashboard}' not found among remote custom dashboards: "
            f"{list(remote_dashboards.keys())}"
        )
    else:
        LOGGER.info(
            f"\n✅ Download complete ({downloaded} checked, {updated} new/updated file(s) written)."
        )


if __name__ == "__main__":
    cli()
