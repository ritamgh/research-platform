"""Upload and manage the eval dataset in LangSmith."""
import json
from pathlib import Path

from langsmith import Client

DATASET_PATH = Path(__file__).parent / "dataset.json"


def load_local_dataset(path: Path = DATASET_PATH) -> list[dict]:
    with open(path) as f:
        return json.load(f)


def ensure_langsmith_dataset(
    client: Client,
    name: str = "research-platform-v1",
    local_path: Path = DATASET_PATH,
) -> str:
    """Upload dataset to LangSmith if it doesn't exist. Returns dataset name."""
    data = load_local_dataset(local_path)

    try:
        ds = client.read_dataset(dataset_name=name)
        existing = list(client.list_examples(dataset_id=ds.id))
        if len(existing) == len(data):
            print(f"Dataset '{name}' already exists with {len(existing)} examples — skipping upload.")
            return name
        print(f"Dataset '{name}' exists but has {len(existing)}/{len(data)} examples — re-uploading missing.")
    except Exception:
        ds = client.create_dataset(name, description="Research platform eval dataset — 20 Q&A pairs")
        print(f"Created dataset '{name}' ({ds.id})")

    existing_ids = {str(e.metadata.get("q_id")) for e in client.list_examples(dataset_id=ds.id)}

    for entry in data:
        if entry["id"] in existing_ids:
            continue
        client.create_example(
            inputs=entry["inputs"],
            outputs=entry["outputs"],
            dataset_id=ds.id,
            metadata={"q_id": entry["id"], "route_type": entry["route_type"]},
        )

    print(f"Uploaded {len(data)} examples to '{name}'.")
    return name
