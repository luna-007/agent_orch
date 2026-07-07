import pytest
import os
import json
import tempfile
from jsonschema.exceptions import ValidationError
from app.manifest_schema import validate_manifest
from app.workflow_builder import WorkflowBuilder
from app.intent_classifier import IntentClassifier
from app.orchestrator import Orchestrator
from schemas.agent_schemas import Message
from schemas.llm_schema import LLMResponse, LLMClient
from typing import List

class FakeLLMClient(LLMClient):
    def __init__(self, response_content: str):
        self.response_content = response_content

    async def chat(self, messages: List[Message], tools: List[dict] | None = None) -> LLMResponse:
        return LLMResponse(content=self.response_content, tool_calls=None)

VALID_MANIFEST = {
    "metadata": {
        "name": "test_flow",
        "version": "1.0.0",
        "intent": "testing",
        "aliases": ["test", "dummy"]
    },
    "agents": {
        "test_agent": {
            "system_prompt": "You are a test agent.",
            "tools": ["dummy_tool"]
        }
    },
    "fsm": {
        "transitions": {
            "NEW": "test_agent",
            "TEST_DONE": "FINISH"
        },
        "decision_matrix": [
            {"name": "NEW", "description": "Start"},
            {"name": "TEST_DONE", "description": "End"}
        ]
    }
}

def test_json_schema_validation():
    # Valid manifest should pass
    validate_manifest(VALID_MANIFEST)
    
    # Missing required fsm key should fail
    invalid_manifest = VALID_MANIFEST.copy()
    del invalid_manifest["fsm"]
    with pytest.raises(ValidationError):
        validate_manifest(invalid_manifest)

@pytest.mark.asyncio
async def test_workflow_builder_validation_and_building():
    llm = FakeLLMClient("{}")
    orchestrator = Orchestrator(llm, None, None)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # 1. Write a valid manifest
        with open(os.path.join(temp_dir, "test_flow.json"), "w") as f:
            json.dump(VALID_MANIFEST, f)
            
        builder = WorkflowBuilder(temp_dir, orchestrator)
        assert "test_flow" in builder.get_workflow_names()
        
        # Test supervisor building
        supervisor = builder.build_supervisor("test_flow")
        assert "test_agent" in supervisor.agents

@pytest.mark.asyncio
async def test_workflow_builder_invalid_fsm_target():
    llm = FakeLLMClient("{}")
    orchestrator = Orchestrator(llm, None, None)
    
    with tempfile.TemporaryDirectory() as temp_dir:
        invalid_fsm_manifest = VALID_MANIFEST.copy()
        invalid_fsm_manifest["metadata"] = {"name": "invalid_fsm_flow", "version": "1.0.0"}
        invalid_fsm_manifest["fsm"] = {
            "transitions": {
                "NEW": "non_existent_agent" # unknown agent
            },
            "decision_matrix": [{"name": "NEW"}]
        }
        
        with open(os.path.join(temp_dir, "invalid_fsm_flow.json"), "w") as f:
            json.dump(invalid_fsm_manifest, f)
            
        with pytest.raises(ValueError) as exc:
            WorkflowBuilder(temp_dir, orchestrator)
        assert "transitions to unknown target 'non_existent_agent'" in str(exc.value)

@pytest.mark.asyncio
async def test_intent_classifier():
    llm = FakeLLMClient('{"workflow": "test_flow"}')
    classifier = IntentClassifier(llm)
    
    metadata_list = [VALID_MANIFEST["metadata"]]
    selected = await classifier.classify("Please run tests", metadata_list)
    assert selected == "test_flow"
    
    # Test fallback
    llm_garbage = FakeLLMClient('not valid json')
    classifier_garbage = IntentClassifier(llm_garbage)
    selected_fallback = await classifier_garbage.classify("Please run tests", metadata_list)
    assert selected_fallback == "none"
