from typing import Any

from fastapi.testclient import TestClient

from app.services.llm_client import Completion, Progress
from tests.conftest import ScriptedClient, reply, tool_call

SAMPLE = """# Why I stopped writing long READMEs

Nobody reads them. I didn't either.

So I write three lines: what it does, how to run it, where to ask."""

POST = """# Launching Ledger

Ledger tracks stock. That's it.

Run `ledger serve` and open the browser."""


def create_sample(client: TestClient, title: str = "Short READMEs") -> int:
    response = client.post(
        "/api/samples",
        json={"title": title, "format": "markdown", "content": SAMPLE, "notes": "Blog post."},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_job(
    client: TestClient, agent_id: int | None, sample_ids: list[int], **extra: Any
) -> int:
    payload = {
        "title": "Launch post",
        "instructions": "Write a launch post for Ledger.",
        "agent_id": agent_id,
        "sample_ids": sample_ids,
        "contexts": [{"title": "README", "content": "Ledger: an inventory tracker."}],
        "requested_outputs": [{"path": "launch.md", "description": "The blog post."}],
        **extra,
    }
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 201, response.json()
    return response.json()["id"]


def tool_results(conversation: dict[str, Any]) -> list[str]:
    return [message["content"] for message in conversation["messages"] if message["role"] == "tool"]


def run_job(client: TestClient, scripted_client: ScriptedClient, agent_id: int) -> dict[str, Any]:
    """Create and run a job to completion, returning the job detail."""
    sample_id = create_sample(client)
    job_id = create_job(client, agent_id, [sample_id])
    scripted_client.completions = [
        tool_call("read_sample", sample_id=sample_id),
        tool_call("write_document", path="launch.md", content=POST),
        tool_call("finish_job", summary="Wrote the launch post."),
        reply("Done. The post is in launch.md."),
    ]
    assert client.post(f"/api/jobs/{job_id}/start").status_code == 202
    return client.get(f"/api/jobs/{job_id}").json()


def test_job_is_run_after_reading_the_samples(
    client: TestClient, agent_id: int, scripted_client: ScriptedClient
):
    sample_id = create_sample(client)
    job_id = create_job(client, agent_id, [sample_id])
    job = client.get(f"/api/jobs/{job_id}").json()
    context_id = job["contexts"][0]["id"]
    scripted_client.completions = [
        tool_call("write_document", path="launch.md", content=POST),
        tool_call("read_sample", sample_id=sample_id),
        tool_call("read_context", context_id=context_id),
        tool_call("finish_job"),
        tool_call("write_document", path="launch.md", content=POST),
        tool_call("finish_job", summary="Wrote the launch post."),
        reply("Done."),
    ]

    response = client.post(f"/api/jobs/{job_id}/start")
    assert response.status_code == 202

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "completed"
    assert job["agent_summary"] == "Wrote the launch post."
    assert job["samples_read"] == [sample_id]
    assert job["settings_snapshot"]["agent"] == "Blogger"
    assert job["llm_calls"] == 7
    assert job["tool_calls"] == 6
    assert job["working_seconds"] > 0

    conversation = client.get(f"/api/conversations/{job['conversations'][0]['id']}").json()
    assert conversation["kind"] == "main"
    assert conversation["status"] == "idle", conversation["error"]
    results = tool_results(conversation)
    assert results[0].startswith("Error: Read every writing sample before writing")
    assert "Why I stopped writing long READMEs" in results[1]
    assert "inventory tracker" in results[2]
    assert results[3].startswith("Error: Write at least one document")
    assert results[4].startswith("Created launch.md")

    system_prompt = scripted_client.requests[0][0]["content"]
    assert "Short READMEs" in system_prompt
    assert "Keep posts under 800 words." in system_prompt
    assert "launch.md: The blog post." in system_prompt
    assert scripted_client.requests[0][1]["content"] == 'Please start the job "Launch post".'

    documents = client.get(f"/api/jobs/{job_id}/documents").json()
    assert [(item["path"], item["format"], item["content"]) for item in documents] == [
        ("launch.md", "markdown", POST)
    ]
    revisions = client.get(f"/api/documents/{documents[0]['id']}/revisions").json()
    assert [(item["number"], item["source"]) for item in revisions] == [(1, "agent")]


def test_requested_outputs_must_be_written_before_finishing(
    client: TestClient, agent_id: int, scripted_client: ScriptedClient
):
    job_id = create_job(
        client,
        agent_id,
        [],
        requested_outputs=[{"path": "launch.md"}, {"path": "launch.html"}],
    )
    scripted_client.completions = [
        tool_call("write_document", path="launch.md", content=POST),
        tool_call("finish_job"),
        reply("Still working."),
    ]
    client.post(f"/api/jobs/{job_id}/start")

    job = client.get(f"/api/jobs/{job_id}").json()
    assert job["status"] == "active"
    conversation = client.get(f"/api/conversations/{job['conversations'][0]['id']}").json()
    assert "have not been written: launch.html" in tool_results(conversation)[1]


def test_main_conversation_updates_documents_immediately(
    client: TestClient, agent_id: int, scripted_client: ScriptedClient
):
    job = run_job(client, scripted_client, agent_id)
    conversation_id = job["conversations"][0]["id"]
    scripted_client.completions = [
        tool_call(
            "edit_document",
            path="launch.md",
            original="Ledger tracks stock. That's it.",
            replacement="Ledger tracks stock, and nothing else.",
        ),
        reply("Tightened the opening."),
    ]

    response = client.post(
        f"/api/conversations/{conversation_id}/messages", json={"content": "Rework the opening."}
    )
    assert response.status_code == 202

    assert "finish_job" not in scripted_client.tools[-1]
    assert "write_document" in scripted_client.tools[-1]
    document = client.get(f"/api/jobs/{job['id']}/documents").json()[0]
    assert "Ledger tracks stock, and nothing else." in document["content"]
    assert document["revision_count"] == 2


def test_highlight_conversation_proposes_before_changing(
    client: TestClient, agent_id: int, scripted_client: ScriptedClient
):
    job = run_job(client, scripted_client, agent_id)
    document = job["documents"][0]
    scripted_client.completions = [reply("Do you want it shorter, or more playful?")]

    response = client.post(
        f"/api/jobs/{job['id']}/conversations",
        json={
            "document_id": document["id"],
            "quote": "Ledger tracks stock. That's it.",
            "prefix": "Launching Ledger",
            "suffix": "Run ledger serve",
            "content": "This line feels flat.",
        },
    )
    assert response.status_code == 202
    conversation_id = response.json()["id"]

    system_prompt = scripted_client.requests[-1][0]["content"]
    assert "<<<Ledger tracks stock. That's it.>>>" in system_prompt
    assert POST in system_prompt
    assert "propose_revision" in scripted_client.tools[-1]
    assert "write_document" not in scripted_client.tools[-1]

    scripted_client.completions = [
        tool_call(
            "propose_revision",
            original="Ledger tracks stock. That's it.",
            replacement="Ledger tracks stock. Nothing more, nothing less.",
            explanation="Adds rhythm.",
        ),
        tool_call("apply_revision", proposal_id=1),
        tool_call("write_document", path="launch.md", content="Replaced."),
        reply("Here is a proposal."),
    ]
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "Playful."})

    conversation = client.get(f"/api/conversations/{conversation_id}").json()
    results = tool_results(conversation)
    assert results[0].startswith("Proposal 1 is shown to the user")
    assert results[1].startswith("Error: The user has not responded to this proposal yet")
    assert results[2].startswith("Error: the tool 'write_document' is not available")
    assert conversation["pending_proposals"] == 1
    assert client.get(f"/api/documents/{document['id']}").json()["content"] == POST

    scripted_client.completions = [
        tool_call("apply_revision", proposal_id=1),
        reply("Applied."),
    ]
    client.post(f"/api/conversations/{conversation_id}/messages", json={"content": "Yes, do it."})

    content = client.get(f"/api/documents/{document['id']}").json()["content"]
    assert "Nothing more, nothing less." in content
    conversation = client.get(f"/api/conversations/{conversation_id}").json()
    assert conversation["proposals"][0]["status"] == "applied"
    revisions = client.get(f"/api/documents/{document['id']}/revisions").json()
    assert revisions[0]["source"] == "proposal"
    assert revisions[0]["conversation_id"] == conversation_id


def test_user_can_apply_and_reject_proposals(
    client: TestClient, agent_id: int, scripted_client: ScriptedClient
):
    job = run_job(client, scripted_client, agent_id)
    document = job["documents"][0]
    scripted_client.completions = [
        tool_call(
            "propose_revision",
            original="That's it.",
            replacement="Nothing else.",
            explanation="Firmer.",
        ),
        tool_call(
            "propose_revision",
            original="That's it.",
            replacement="Full stop.",
            explanation="Shorter.",
        ),
        reply("Two options; the second one stands."),
    ]
    conversation = client.post(
        f"/api/jobs/{job['id']}/conversations",
        json={"document_id": document["id"], "quote": "That's it.", "content": "Alternatives?"},
    ).json()
    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    first, second = detail["proposals"]
    assert (first["status"], second["status"]) == ("superseded", "pending")

    assert client.post(f"/api/proposals/{first['id']}/apply").status_code == 409
    applied = client.post(f"/api/proposals/{second['id']}/apply")
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert "Full stop." in client.get(f"/api/documents/{document['id']}").json()["content"]

    detail = client.get(f"/api/conversations/{conversation['id']}").json()
    assert detail["messages"][-1]["content"] == f"I applied proposal {second['id']}."


def test_job_cannot_start_without_a_running_agent(
    client: TestClient, agent_id: int, running_deployment: int
):
    unassigned = create_job(client, None, [])
    response = client.post(f"/api/jobs/{unassigned}/start")
    assert response.status_code == 409
    assert "Assign an agent" in response.json()["detail"]

    client.post(f"/api/deployments/{running_deployment}/stop")
    assigned = create_job(client, agent_id, [])
    response = client.post(f"/api/jobs/{assigned}/start")
    assert response.status_code == 409
    assert "not running" in response.json()["detail"]
    assert client.get(f"/api/jobs/{assigned}").json()["status"] == "draft"


def test_user_can_work_while_the_agent_is_writing(
    client: TestClient, agent_id: int, scripted_client: ScriptedClient
):
    job = run_job(client, scripted_client, agent_id)
    document = job["documents"][0]
    main_id = job["conversations"][0]["id"]
    queued: dict[str, Any] = {}

    def user_acts_meanwhile(_on_progress: Any) -> Completion:
        edited = client.put(
            f"/api/documents/{document['id']}",
            json={"content": POST.replace("That's it.", "Nothing else.")},
        )
        assert edited.status_code == 200
        response = client.post(
            f"/api/jobs/{job['id']}/conversations",
            json={"document_id": document["id"], "quote": "Nothing else.", "content": "Hmm?"},
        )
        assert response.status_code == 202
        queued.update(response.json())
        again = client.post(f"/api/conversations/{main_id}/messages", json={"content": "And?"})
        assert again.status_code == 409
        return tool_call(
            "edit_document",
            path="launch.md",
            original="Nothing else.",
            replacement="Nothing more.",
        )

    scripted_client.completions = [
        user_acts_meanwhile,
        reply("Done."),
        reply("Which part feels off?"),
    ]
    client.post(f"/api/conversations/{main_id}/messages", json={"content": "Rework the opening."})

    assert queued["status"] == "queued"
    main = client.get(f"/api/conversations/{main_id}").json()
    assert tool_results(main)[-1].startswith("Edited launch.md (revision 3)")
    content = client.get(f"/api/documents/{document['id']}").json()["content"]
    assert "Ledger tracks stock. Nothing more." in content

    discussion = client.get(f"/api/conversations/{queued['id']}").json()
    assert discussion["status"] == "idle"
    assert discussion["messages"][-1]["content"] == "Which part feels off?"


def test_stop_abandons_the_model_call_in_progress(
    client: TestClient, agent_id: int, scripted_client: ScriptedClient
):
    job = run_job(client, scripted_client, agent_id)
    main_id = job["conversations"][0]["id"]

    def stopped_while_generating(on_progress: Any) -> Completion:
        assert client.post(f"/api/conversations/{main_id}/cancel").status_code == 202
        on_progress(Progress(reasoning="", content="Half a thou"))
        raise AssertionError("The progress callback should have stopped the call.")

    scripted_client.completions = [stopped_while_generating]
    client.post(f"/api/conversations/{main_id}/messages", json={"content": "Rewrite it all."})

    main = client.get(f"/api/conversations/{main_id}").json()
    assert main["status"] == "idle"
    assert main["error"] is None
    assert main["messages"][-1]["content"] == "Rewrite it all."
