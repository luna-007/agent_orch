#!/usr/bin/env python3
import os
import sys
import json
import logging
from app.manifest_schema import validate_manifest

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("validate_manifests")

def main():
    workspace_dir = os.path.dirname(os.path.abspath(__file__))
    manifests_dir = os.path.join(workspace_dir, "manifests")
    
    if not os.path.exists(manifests_dir):
        logger.error(f"Manifests directory not found at {manifests_dir}")
        sys.exit(1)
        
    json_files = [f for f in os.listdir(manifests_dir) if f.endswith(".json")]
    if not json_files:
        logger.warning(f"No JSON manifests found in {manifests_dir}")
        sys.exit(0)
        
    errors = 0
    for filename in json_files:
        filepath = os.path.join(manifests_dir, filename)
        logger.info(f"Validating manifest: {filename}")
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            validate_manifest(data)
            logger.info(f"✓ {filename} is schema-valid")
        except Exception as e:
            logger.error(f"✗ {filename} failed validation: {e}")
            errors += 1
            
    if errors > 0:
        logger.error(f"Validation completed with {errors} errors.")
        sys.exit(1)
    else:
        logger.info("All manifests validated successfully.")
        sys.exit(0)

if __name__ == "__main__":
    main()
