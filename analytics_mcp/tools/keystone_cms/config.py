"""Configuration parser for Keystone CMS Profiles."""

import os
from typing import Any, Dict, List, Optional
import yaml


class CMSProfileConfig:
    """Represents a Keystone CMS instance configuration profile."""

    def __init__(self, data: Dict[str, Any], file_path: Optional[str] = None):
        self.raw_data = data
        self.file_path = file_path
        
        self.cms_name: str = data.get("cms_name", "Keystone CMS")
        self.tool_prefix: str = data.get("tool_prefix", "cms_")
        self.graphql_endpoint: str = data.get("graphql_endpoint", "https://cms.mirrormedia.mg/api/graphql")
        
        self.env_vars: Dict[str, str] = data.get("env_vars", {})
        self.schema: Dict[str, Any] = data.get("schema", {})

        # Resolve environment variable overrides for endpoint & auth
        endpoint_env = self.env_vars.get("endpoint_env")
        if endpoint_env and os.getenv(endpoint_env):
            self.graphql_endpoint = os.getenv(endpoint_env)

    @classmethod
    def load_from_yaml(cls, file_path: str) -> "CMSProfileConfig":
        """Loads a CMS profile configuration from a YAML file."""
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(data, file_path=file_path)


def load_all_profiles(profiles_dir: Optional[str] = None) -> List[CMSProfileConfig]:
    """Scans and loads all YAML configuration profiles from the profiles directory."""
    if not profiles_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        profiles_dir = os.path.join(base_dir, "profiles")

    profiles = []
    if not os.path.exists(profiles_dir):
        return profiles

    for filename in sorted(os.listdir(profiles_dir)):
        if filename.endswith(".yaml") or filename.endswith(".yml"):
            full_path = os.path.join(profiles_dir, filename)
            try:
                profile = CMSProfileConfig.load_from_yaml(full_path)
                profiles.append(profile)
            except Exception as e:
                print(f"[Warning] Failed to load CMS profile {filename}: {e}")

    return profiles
