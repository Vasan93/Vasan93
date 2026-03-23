"""
Deploy ML Model from Dev Databricks to Prod Databricks
======================================================

Workflow:
1. Export the registered model from Dev workspace (MLflow)
2. Import/register the model in Prod workspace
3. Create a model serving endpoint in Prod

Prerequisites:
- pip install databricks-sdk mlflow
- Dev and Prod workspace tokens configured
"""

import mlflow
from mlflow.tracking import MlflowClient
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (
    EndpointCoreConfigInput,
    ServedEntityInput,
)
import time
import argparse


# ---------------------------------------------------------------------------
# Configuration — update these for your environment
# ---------------------------------------------------------------------------
CONFIG = {
    "dev": {
        "host": "https://<dev-workspace>.cloud.databricks.com",
        "token": "<dev-pat-token>",          # or use env: DATABRICKS_TOKEN
    },
    "prod": {
        "host": "https://<prod-workspace>.cloud.databricks.com",
        "token": "<prod-pat-token>",
    },
    "model_name": "your_model_name",          # registered model name in Dev
    "model_version": None,                     # None = latest Champion/Production version
    "prod_model_name": None,                   # None = same as model_name
    "endpoint_name": "your_model_endpoint",    # serving endpoint name in Prod
    "workload_size": "Small",                  # Small | Medium | Large
    "scale_to_zero": True,                     # scale down when idle
}


# ---------------------------------------------------------------------------
# Step 1: Export model artifact from Dev
# ---------------------------------------------------------------------------
def get_latest_model_version(client: MlflowClient, model_name: str, version: str = None):
    """Get the specified or latest production/champion version from Dev."""
    if version:
        return client.get_model_version(model_name, version)

    # Try Unity Catalog alias first (Databricks >= 2023.x)
    try:
        mv = client.get_model_version_by_alias(model_name, "Champion")
        print(f"Found Champion alias → version {mv.version}")
        return mv
    except Exception:
        pass

    # Fallback: get the latest version by version number
    versions = client.search_model_versions(f"name='{model_name}'")
    if not versions:
        raise ValueError(f"No versions found for model '{model_name}'")
    latest = max(versions, key=lambda v: int(v.version))
    print(f"Using latest version → {latest.version}")
    return latest


def download_model_from_dev(config: dict) -> str:
    """Download model artifacts from Dev workspace. Returns local path."""
    mlflow.set_tracking_uri(config["dev"]["host"])
    client = MlflowClient(
        tracking_uri=config["dev"]["host"],
        registry_uri=config["dev"]["host"],
    )
    # Authenticate
    import os
    os.environ["DATABRICKS_HOST"] = config["dev"]["host"]
    os.environ["DATABRICKS_TOKEN"] = config["dev"]["token"]

    mv = get_latest_model_version(client, config["model_name"], config["model_version"])
    model_uri = f"models:/{config['model_name']}/{mv.version}"

    local_path = f"/tmp/mlflow_model_{config['model_name']}_v{mv.version}"
    print(f"Downloading model from Dev: {model_uri}")
    mlflow.artifacts.download_artifacts(artifact_uri=model_uri, dst_path=local_path)
    print(f"Model downloaded to {local_path}")
    return local_path, mv


# ---------------------------------------------------------------------------
# Step 2: Register model in Prod
# ---------------------------------------------------------------------------
def register_model_in_prod(config: dict, local_path: str, dev_mv):
    """Upload and register the model in Prod workspace."""
    import os
    os.environ["DATABRICKS_HOST"] = config["prod"]["host"]
    os.environ["DATABRICKS_TOKEN"] = config["prod"]["token"]

    mlflow.set_tracking_uri(config["prod"]["host"])
    prod_model_name = config["prod_model_name"] or config["model_name"]

    print(f"Registering model '{prod_model_name}' in Prod workspace...")

    # Log model to a new Prod experiment run, then register
    with mlflow.start_run(run_name=f"prod_deploy_v{dev_mv.version}") as run:
        mlflow.log_param("source_workspace", "dev")
        mlflow.log_param("source_model", config["model_name"])
        mlflow.log_param("source_version", dev_mv.version)

        # Re-log the model artifacts
        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=None,       # artifacts already serialized
            artifacts={"model_dir": local_path},
        )
        model_uri = f"runs:/{run.info.run_id}/model"
        result = mlflow.register_model(model_uri, prod_model_name)

    print(f"Registered in Prod as '{prod_model_name}' version {result.version}")
    return prod_model_name, result.version


# ---------------------------------------------------------------------------
# Step 2-ALT (Recommended): Unity Catalog model copy
# ---------------------------------------------------------------------------
def copy_model_unity_catalog(config: dict):
    """
    If both workspaces share a Unity Catalog metastore, you can skip
    export/import and directly reference the model across workspaces.

    Register your model under a UC three-level namespace:
        catalog.schema.model_name

    Example:
        Dev:  dev_catalog.ml_models.my_model
        Prod: prod_catalog.ml_models.my_model

    Then copy using the MLflow Client:
    """
    import os
    os.environ["DATABRICKS_HOST"] = config["prod"]["host"]
    os.environ["DATABRICKS_TOKEN"] = config["prod"]["token"]

    client = MlflowClient()
    src = f"models:/dev_catalog.ml_models.{config['model_name']}@Champion"
    dst = f"prod_catalog.ml_models.{config['model_name']}"

    # Copy model version across catalogs
    client.copy_model_version(src_model_uri=src, dst_name=dst)
    print(f"Model copied to {dst} in Prod Unity Catalog")
    return dst


# ---------------------------------------------------------------------------
# Step 3: Create serving endpoint in Prod
# ---------------------------------------------------------------------------
def create_serving_endpoint(config: dict, prod_model_name: str, prod_version: str):
    """Create or update a Model Serving endpoint in Prod Databricks."""
    w = WorkspaceClient(
        host=config["prod"]["host"],
        token=config["prod"]["token"],
    )

    endpoint_name = config["endpoint_name"]
    served_entity = ServedEntityInput(
        entity_name=prod_model_name,
        entity_version=prod_version,
        workload_size=config["workload_size"],
        scale_to_zero_enabled=config["scale_to_zero"],
    )
    endpoint_config = EndpointCoreConfigInput(served_entities=[served_entity])

    # Check if endpoint already exists
    try:
        existing = w.serving_endpoints.get(endpoint_name)
        print(f"Endpoint '{endpoint_name}' exists — updating...")
        w.serving_endpoints.update_config(
            name=endpoint_name,
            served_entities=[served_entity],
        )
    except Exception:
        print(f"Creating new endpoint '{endpoint_name}'...")
        w.serving_endpoints.create(
            name=endpoint_name,
            config=endpoint_config,
        )

    # Wait for endpoint to be ready
    print("Waiting for endpoint to be ready...")
    for i in range(60):
        ep = w.serving_endpoints.get(endpoint_name)
        state = ep.state.ready
        if str(state) == "READY":
            print(f"Endpoint '{endpoint_name}' is READY!")
            print(f"URL: {config['prod']['host']}/serving-endpoints/{endpoint_name}/invocations")
            return ep
        time.sleep(30)
        print(f"  Status: {state} (waited {(i+1)*30}s)")

    print("WARNING: Endpoint did not become ready within 30 minutes.")
    return None


# ---------------------------------------------------------------------------
# Step 4: Test the endpoint
# ---------------------------------------------------------------------------
def test_endpoint(config: dict):
    """Send a sample request to the serving endpoint."""
    import requests
    import json

    url = f"{config['prod']['host']}/serving-endpoints/{config['endpoint_name']}/invocations"
    headers = {
        "Authorization": f"Bearer {config['prod']['token']}",
        "Content-Type": "application/json",
    }
    # Adjust the payload to match your model's input schema
    payload = {
        "dataframe_records": [
            {"feature_1": 1.0, "feature_2": "example"}
        ]
    }
    resp = requests.post(url, headers=headers, json=payload)
    print(f"Status: {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")
    return resp


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Deploy ML model from Dev to Prod Databricks")
    parser.add_argument("--model-name", help="Override model name from CONFIG")
    parser.add_argument("--model-version", help="Specific version to deploy")
    parser.add_argument("--endpoint-name", help="Override endpoint name from CONFIG")
    parser.add_argument("--use-unity-catalog", action="store_true",
                        help="Use Unity Catalog cross-workspace copy instead of export/import")
    parser.add_argument("--test-only", action="store_true",
                        help="Only test an existing endpoint")
    args = parser.parse_args()

    config = CONFIG.copy()
    if args.model_name:
        config["model_name"] = args.model_name
    if args.model_version:
        config["model_version"] = args.model_version
    if args.endpoint_name:
        config["endpoint_name"] = args.endpoint_name

    if args.test_only:
        test_endpoint(config)
        return

    if args.use_unity_catalog:
        # Unity Catalog path (recommended if workspaces share a metastore)
        prod_model_name = copy_model_unity_catalog(config)
        prod_version = "1"  # UC copy creates a new version
    else:
        # Export/Import path
        local_path, dev_mv = download_model_from_dev(config)
        prod_model_name, prod_version = register_model_in_prod(config, local_path, dev_mv)

    create_serving_endpoint(config, prod_model_name, prod_version)
    print("\nDeployment complete!")


if __name__ == "__main__":
    main()
