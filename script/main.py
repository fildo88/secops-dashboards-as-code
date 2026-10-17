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
    for name, data in sorted(remote_dashboards.items()):
        if download_all or dashboard is None or name == dashboard:
            file_path = dashboard_dir / f"{_slugify(name)}.json"
            LOGGER.info(f"  -> Exporting dashboard '{name}' ({data.name}) to {file_path}...")
            dashboard_export = manager.export_dashboard(dashboard_names=[data.name])
            inline_dest = dashboard_export["inlineDestination"]
            if make_public:
                for d_entry in inline_dest.get("dashboards", []):
                    if "dashboard" in d_entry:
                        d_entry["dashboard"]["access"] = "DASHBOARD_PUBLIC"
            with open(file_path, "w") as f:
                json.dump(inline_dest, f, indent=2)
            downloaded += 1

    if downloaded == 0 and dashboard:
        LOGGER.warning(
            f"Dashboard '{dashboard}' not found among remote custom dashboards: "
            f"{list(remote_dashboards.keys())}"
        )
    else:
        LOGGER.info(f"\n✅ Download complete ({downloaded} dashboard(s) exported).")


if __name__ == "__main__":
    cli()
