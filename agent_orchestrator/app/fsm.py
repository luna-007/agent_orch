import logging
from typing import Dict, List, Any

logger = logging.getLogger("agent_orch.fsm")

class FSM:
    def __init__(self, transitions: Dict[str, str], decision_matrix: List[Dict[str, Any]]):
        self.transitions = transitions
        self.decision_matrix = decision_matrix

    def get_next_agent(self, state: str) -> str:
        """Looks up the next agent based on the current state name."""
        next_agent = self.transitions.get(state, "FINISH")
        logger.info(f"FSM Transition lookup: '{state}' -> next agent target '{next_agent}'")
        return next_agent

    def get_valid_states(self) -> List[Dict[str, Any]]:
        """Returns the decision matrix of valid states and their descriptions."""
        return self.decision_matrix
