import jsonschema

MANIFEST_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "metadata": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "version": {"type": "string"},
                "intent": {"type": "string"},
                "goal": {"type": "string"},
                "aliases": {
                    "type": "array",
                    "items": {"type": "string"}
                }
            },
            "required": ["name", "version"]
        },
        "agents": {
            "type": "object",
            "additionalProperties": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "system_prompt": {"type": "string"},
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"}
                    },
                    "fallback_state": {"type": "string"}
                },
                "required": ["system_prompt", "tools"]
            }
        },
        "fsm": {
            "type": "object",
            "properties": {
                "transitions": {
                    "type": "object",
                    "additionalProperties": {"type": "string"}
                },
                "decision_matrix": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"}
                        },
                        "required": ["name"]
                    }
                }
            },
            "required": ["transitions", "decision_matrix"]
        }
    },
    "required": ["metadata", "agents", "fsm"]
}

def validate_manifest(data: dict) -> None:
    """Validates the manifest dictionary against the JSON schema.
    Raises jsonschema.exceptions.ValidationError on invalid schema.
    """
    jsonschema.validate(instance=data, schema=MANIFEST_JSON_SCHEMA)
