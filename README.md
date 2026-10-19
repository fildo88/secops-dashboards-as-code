# Google SecOps Dashboards as Code (`secops-lab-lowe-01`)

GitOps pipeline for managing Google Security Operations (Chronicle) Native Dashboards in **`secops-lab-lowe-01`** (`8a9bcdd8-288f-488c-b433-3fb2f1794b21`, `asia-southeast1`), adapted from [`GoogleCloudPlatform/secops-toolkit/pipelines/dashboards-as-code`](https://github.com/GoogleCloudPlatform/secops-toolkit/tree/main/pipelines/dashboards-as-code).

## Exported Custom Dashboards (`dashboards/`)

| Display Name | File |
| :--- | :--- |
| **Detection Rules** | `dashboards/detection_rules.json` |
| **Detections vs Endpoints - Overlaid on One Chart (Splunk overlay)** | `dashboards/detections_vs_endpoints_overlaid_on_one_chart_splunk_overlay.json` |
| **EDR Overview - CrowdStrike** | `dashboards/edr_overview_crowdstrike.json` |
| **Enabled & Alerting Detection Rules** | `dashboards/enabled_alerting_detection_rules.json` |
| **IOC Search - All Log Sources** | `dashboards/ioc_search_all_log_sources.json` |
| **IOC Search - Pi-hole & pfSense** | `dashboards/ioc_search_pi_hole_pfsense.json` |
| **Overlaid: Detections vs Endpoints (Two Lines)** | `dashboards/overlaid_detections_vs_endpoints_two_lines.json` |
| **pfSense Overview** | `dashboards/pfsense_overview.json` |
| **Pi-Hole Overview** | `dashboards/pi_hole_overview.json` |
| **X-Axis Time Bucketing & Local Timezone (AWST / AEDT)** | `dashboards/x_axis_time_bucketing_local_timezone_awst_aedt.json` |

## Usage

### Local CLI
```bash
# Export all custom dashboards (automatically sets access to DASHBOARD_PUBLIC)
PYTHONPATH=script .venv/bin/python script/main.py download --all

# Export a single custom dashboard by display name
PYTHONPATH=script .venv/bin/python script/main.py download --dashboard "Detection Rules"

# Plan changes (compare local JSON vs remote SecOps instance)
PYTHONPATH=script .venv/bin/python script/main.py plan

# Apply changes (import new or updated dashboards)
PYTHONPATH=script .venv/bin/python script/main.py apply
```

### GitHub Actions (`.github/workflows/secops.yaml`)
- **Pull Requests to `main`**: Runs `python script/main.py plan` and posts a summary comment on the PR.
- **Merge PR to `main`**: Runs `python script/main.py apply` and posts the deployment result on the PR.
- **Manual Trigger (`workflow_dispatch`)**: Run `plan` or `apply` on demand from the GitHub **Actions** tab.
