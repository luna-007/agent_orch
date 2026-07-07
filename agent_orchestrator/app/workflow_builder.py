import os
import json
import logging
from typing import Dict, List, Any
from app.manifest_schema import validate_manifest
from app.fsm import FSM
from app.agents.generic import GenericAgent
from app.router import Router
from app.supervisor import Supervisor
from app.orchestrator import Orchestrator

logger = logging.getLogger("agent_orch.workflow_builder")

class WorkflowBuilder:
    def __init__(self, manifests_dir: str, orchestrator: Orchestrator):
        self.manifests_dir = manifests_dir
        self.orchestrator = orchestrator
        self.workflows: Dict[str, dict] = {}
        self.load_and_validate_all()

    def load_and_validate_all(self):
        if not os.path.exists(self.manifests_dir):
            raise ValueError(f"Manifests directory not found: {self.manifests_dir}")
        
        for fn in os.listdir(self.manifests_dir):
            if fn.endswith(".json"):
                fp = os.path.join(self.manifests_dir, fn)
                try:
                    with open(fp, "r") as f:
                        data = json.load(f)
                    
                    # 1. Schema Validation (fail-fast)
                    validate_manifest(data)
                    
                    name = data["metadata"]["name"]
                    
                    # 2. Semantic Validation (fail-fast)
                    self.validate_semantic(data)
                    
                    self.workflows[name] = data
                    logger.info(f"Loaded and validated workflow: {name}")
                except Exception as e:
                    logger.error(f"Failed to load/validate manifest {fn}: {e}")
                    raise

    def validate_semantic(self, data: dict):
        # Ensure FSM transition targets are valid agent names or "FINISH"
        agents = data.get("agents", {})
        fsm = data.get("fsm", {})
        transitions = fsm.get("transitions", {})
        valid_targets = set(agents.keys()) | {"FINISH"}
        for state, target in transitions.items():
            if target not in valid_targets:
                raise ValueError(
                    f"Semantic validation error in manifest '{data['metadata']['name']}': "
                    f"FSM state '{state}' transitions to unknown target '{target}'."
                )

    def get_workflow_names(self) -> List[str]:
        return list(self.workflows.keys())

    def get_workflow_metadata_list(self) -> List[dict]:
        return [w["metadata"] for w in self.workflows.values()]

    def build_supervisor(self, workflow_name: str) -> Supervisor:
        data = self.workflows.get(workflow_name)
        if not data:
            raise ValueError(f"Workflow '{workflow_name}' not found.")

        # Build FSM
        fsm_data = data["fsm"]
        fsm = FSM(
            transitions=fsm_data["transitions"],
            decision_matrix=fsm_data["decision_matrix"]
        )

        # Build Router
        router = Router(self.orchestrator.llm)

        # Build Agents
        agents_map = {}
        fallback_states = {}
        for agent_name, agent_cfg in data["agents"].items():
            agents_map[agent_name] = GenericAgent(
                name=agent_name,
                system_prompt=agent_cfg["system_prompt"],
                allowed_tools=agent_cfg["tools"],
                orchestrator=self.orchestrator
            )
            if "fallback_state" in agent_cfg:
                fallback_states[agent_name] = agent_cfg["fallback_state"]

        metadata = data.get("metadata", {})
        goal = metadata.get("goal") or f"Execute workflow: {workflow_name}"

        return Supervisor(
            agents=agents_map,
            router=router,
            fsm=fsm,
            goal=goal,
            fallback_states=fallback_states
        )
