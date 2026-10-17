# Google SecOps Dashboards as Code (`secops-lab-lowe-01`)

GitOps pipeline for managing Google Security Operations (Chronicle) Native Dashboards in **`secops-lab-lowe-01`** (`8a9bcdd8-288f-488c-b433-3fb2f1794b21`, `asia-southeast1`), adapted from [`GoogleCloudPlatform/secops-toolkit/pipelines/dashboards-as-code`](https://github.com/GoogleCloudPlatform/secops-toolkit/tree/main/pipelines/dashboards-as-code).

## Exported Custom Dashboards (`dashboards/`)

| Display Name | File | Remote UUID |
| :--- | :--- | :--- |
| **Detection Rules** | `dashboards/detection_rules.json` | `6441de81-1c5f-4a1c-860f-40dd809796d6` |
| **Detections vs Endpoints - Overlaid on One Chart (Splunk overlay)** | `dashboards/detections_vs_endpoints_overlaid_on_one_chart_splunk_overlay.json` | `17b1e6dc-6207-4bdf-b209-893cdcab6e67` |
| **EDR Overview - CrowdStrike** | `dashboards/edr_overview_crowdstrike.json` | `04771b18-42e3-44f3-bc93-a53ddf9f7349` |
| **IOC Search - All Log Sources** | `dashboards/ioc_search_all_log_sources.json` | `0c0347d4-7858-4a39-92a6-0bac4acaac39` |
| **IOC Search - Pi-hole & pfSense** | `dashboards/ioc_search_pi_hole_pfsense.json` | `a4b43ddd-9ac1-4cf8-a5f0-8519bd4d290f` |
| **pfSense Overview** | `dashboards/pfsense_overview.json` | `10c13078-f7b4-4df9-a1f7-4323c228cbd5` |
| **Pi-Hole Overview** | `dashboards/pi_hole_overview.json` | `835465a6-620a-4074-b872-241a15fdf8ac` |
| **X-Axis Time Bucketing & Local Timezone (AWST / AEDT)** | `dashboards/x_axis_time_bucketing_local_timezone_awst_aedt.json` | `77748e21-564b-4e55-8f68-8abb5cd620c7` |

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
