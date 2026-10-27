from fastapi.testclient import TestClient

from app.context import AppContext
from app.models import DownloadStatus, Job, LanguageModel, RevisionSource
from app.services.documents import write_document


def test_managed_runtime_requires_command_template(client: TestClient):
    response = client.post("/api/runtimes", json={"name": "llama.cpp", "kind": "managed"})
    assert response.status_code == 422


def test_external_runtime_requires_url(client: TestClient):
    response = client.post(
        "/api/runtimes", json={"name": "Ollama", "kind": "external", "base_url": "localhost"}
    )
    assert response.status_code == 422


def test_runtime_crud(client: TestClient):
    payload = {
        "name": "llama.cpp",
        "kind": "managed",
        "command_template": "llama-server -m {model_path} --port {port} --jinja",
    }
    created = client.post("/api/runtimes", json=payload)
    assert created.status_code == 201
    runtime_id = created.json()["id"]

    assert client.post("/api/runtimes", json=payload).status_code == 409

    updated = client.put(
        f"/api/runtimes/{runtime_id}", json={**payload, "description": "CPU and GPU inference"}
    )
    assert updated.json()["description"] == "CPU and GPU inference"
    assert client.delete(f"/api/runtimes/{runtime_id}").status_code == 204
    assert client.get("/api/runtimes").json() == []


def test_deployment_validates_model_file(client: TestClient, context: AppContext, tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "weights.gguf").write_bytes(b"gguf")
    with context.session_factory() as db:
        model = LanguageModel(
            repo_id="example/model", local_path=str(model_dir), status=DownloadStatus.READY
        )
        db.add(model)
        db.commit()
        model_id = model.id
    runtime_id = client.post(
        "/api/runtimes",
        json={"name": "llama.cpp", "kind": "managed", "command_template": "llama-server"},
    ).json()["id"]

    base = {"name": "Local", "model_id": model_id, "runtime_id": runtime_id}
    missing = client.post("/api/deployments", json={**base, "model_file": "absent.gguf"})
    assert missing.status_code == 422

    created = client.post("/api/deployments", json={**base, "model_file": "weights.gguf"})
    assert created.status_code == 201
    assert created.json()["status"] == "stopped"
    assert created.json()["model_repo_id"] == "example/model"

    files = client.get(f"/api/models/{model_id}/files").json()
    assert files == [{"path": "weights.gguf", "size_bytes": 4}]

    assert client.delete(f"/api/runtimes/{runtime_id}").status_code == 409
    assert client.delete(f"/api/models/{model_id}").status_code == 409


def test_unknown_resources_return_not_found(client: TestClient):
    assert client.get("/api/jobs/999").status_code == 404
    assert client.get("/api/samples/999").status_code == 404
    assert client.get("/api/conversations/999").status_code == 404
    assert client.post("/api/deployments/999/start").status_code == 404


def test_model_can_be_registered_without_downloading(client: TestClient):
    response = client.post(
        "/api/models", json={"repo_id": "example/served-elsewhere", "register_only": True}
    )
    assert response.status_code == 202
    assert response.json()["status"] == "ready"
    assert response.json()["downloaded_bytes"] == 0


def test_writing_sample_crud(client: TestClient):
    created = client.post(
        "/api/samples",
        json={"title": "On naming", "format": "markdown", "content": "Names matter. " * 100},
    )
    assert created.status_code == 201
    sample = created.json()
    assert sample["word_count"] == 200
    assert len(sample["excerpt"]) == 240

    listed = client.get("/api/samples").json()
    assert [item["title"] for item in listed] == ["On naming"]
    assert "content" not in listed[0]

    updated = client.put(
        f"/api/samples/{sample['id']}",
        json={"title": "On naming things", "format": "text", "content": "Short."},
    )
    assert updated.json()["format"] == "text"
    assert client.delete(f"/api/samples/{sample['id']}").status_code == 204
    assert client.get("/api/samples").json() == []


def test_agent_crud_and_assignment(client: TestClient, running_deployment: int):
    payload = {"name": "Editor", "deployment_id": running_deployment, "instructions": "Be terse."}
    created = client.post("/api/agents", json=payload)
    assert created.status_code == 201
    agent = created.json()
    assert agent["deployment_status"] == "running"
    assert agent["model_repo_id"] == "example/writer"
    assert client.post("/api/agents", json=payload).status_code == 409

    job = client.post("/api/jobs", json={"title": "Post", "instructions": "Write."}).json()
    assert job["status"] == "draft"
    assert job["agent_id"] is None

    assigned = client.put(f"/api/jobs/{job['id']}/agent", json={"agent_id": agent["id"]})
    assert assigned.json()["agent_name"] == "Editor"

    assert client.delete(f"/api/agents/{agent['id']}").status_code == 409
    assert client.delete(f"/api/deployments/{running_deployment}").status_code == 409
    client.put(f"/api/jobs/{job['id']}/agent", json={"agent_id": None})
    assert client.delete(f"/api/agents/{agent['id']}").status_code == 204


def test_job_validation(client: TestClient):
    base = {"title": "Post", "instructions": "Write."}
    bad_path = client.post(
        "/api/jobs", json={**base, "requested_outputs": [{"path": "../escape.md"}]}
    )
    assert bad_path.status_code == 422
    bad_extension = client.post(
        "/api/jobs", json={**base, "requested_outputs": [{"path": "post.docx"}]}
    )
    assert bad_extension.status_code == 422
    duplicate = client.post(
        "/api/jobs",
        json={**base, "requested_outputs": [{"path": "a.md"}, {"path": "./a.md"}]},
    )
    assert duplicate.status_code == 422
    assert client.post("/api/jobs", json={**base, "sample_ids": [42]}).status_code == 404

    created = client.post(
        "/api/jobs",
        json={
            **base,
            "contexts": [{"title": "Goal", "content": "More sign-ups."}],
            "requested_outputs": [{"path": "site/index.html", "description": "Landing page"}],
        },
    )
    assert created.status_code == 201
    job = created.json()
    assert job["requested_outputs"] == [{"path": "site/index.html", "description": "Landing page"}]
    assert job["contexts"][0]["title"] == "Goal"


def test_user_edits_and_restores_revisions(client: TestClient, context: AppContext):
    job_id = client.post("/api/jobs", json={"title": "Page", "instructions": "Write."}).json()["id"]
    with context.session_factory() as db:
        job = db.get_one(Job, job_id)
        document = write_document(
            job, "page.html", "<p>First</p>", RevisionSource.AGENT, limit=1000
        )
        db.commit()
        document_id = document.id

    edited = client.put(f"/api/documents/{document_id}", json={"content": "<p>Second</p>"})
    assert edited.json()["revision_count"] == 2
    assert edited.json()["format"] == "html"

    revisions = client.get(f"/api/documents/{document_id}/revisions").json()
    assert [(item["number"], item["source"]) for item in revisions] == [(2, "user"), (1, "agent")]
    first = client.get(f"/api/documents/{document_id}/revisions/{revisions[1]['id']}").json()
    assert first["content"] == "<p>First</p>"

    restored = client.post(f"/api/documents/{document_id}/revisions/{first['id']}/restore")
    assert restored.json()["content"] == "<p>First</p>"
    assert restored.json()["revision_count"] == 3
    again = client.post(f"/api/documents/{document_id}/revisions/{first['id']}/restore")
    assert again.status_code == 409

    assert client.delete(f"/api/documents/{document_id}").status_code == 204
    assert client.get(f"/api/jobs/{job_id}/documents").json() == []
