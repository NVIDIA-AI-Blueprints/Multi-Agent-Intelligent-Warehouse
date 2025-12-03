"""
Agent Configuration Loader

Centralized configuration management for agent personas, prompts, and behavior.
Loads agent configurations from YAML files in data/config/agents/.
"""

import logging
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class AgentPersona:
    """Agent persona configuration."""
    
    system_prompt: str
    understanding_prompt: str
    response_prompt: str
    description: Optional[str] = None


@dataclass
class AgentConfig:
    """Complete agent configuration."""
    
    name: str
    description: str
    persona: AgentPersona
    intents: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    examples: list[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class AgentConfigLoader:
    """Loads and manages agent configurations from YAML files."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        Initialize the configuration loader.
        
        Args:
            config_dir: Directory containing agent config files. 
                       Defaults to data/config/agents/ relative to project root.
        """
        if config_dir is None:
            # Find project root (look for pyproject.toml or README.md)
            current = Path(__file__).resolve()
            project_root = None
            for parent in [current] + list(current.parents):
                if (parent / "pyproject.toml").exists() or (parent / "README.md").exists():
                    project_root = parent
                    break
            
            if project_root is None:
                raise ValueError("Could not find project root directory")
            
            config_dir = project_root / "data" / "config" / "agents"
        
        self.config_dir = Path(config_dir)
        self._cache: Dict[str, AgentConfig] = {}
        
        if not self.config_dir.exists():
            logger.warning(f"Agent config directory does not exist: {self.config_dir}")
            self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def load_agent_config(self, agent_name: str) -> AgentConfig:
        """
        Load configuration for a specific agent.
        
        Args:
            agent_name: Name of the agent (e.g., "operations", "safety", "equipment")
            
        Returns:
            AgentConfig object with loaded configuration
            
        Raises:
            FileNotFoundError: If config file doesn't exist
            ValueError: If config file is invalid
        """
        # Check cache first
        if agent_name in self._cache:
            return self._cache[agent_name]
        
        config_file = self.config_dir / f"{agent_name}_agent.yaml"
        
        if not config_file.exists():
            raise FileNotFoundError(
                f"Agent configuration file not found: {config_file}\n"
                f"Available configs: {list(self.config_dir.glob('*_agent.yaml'))}"
            )
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            if not config_data:
                raise ValueError(f"Empty configuration file: {config_file}")
            
            # Validate required fields
            required_fields = ['name', 'persona']
            missing_fields = [field for field in required_fields if field not in config_data]
            if missing_fields:
                raise ValueError(
                    f"Missing required fields in {config_file}: {missing_fields}"
                )
            
            # Validate persona structure
            persona_data = config_data['persona']
            required_persona_fields = ['system_prompt', 'understanding_prompt', 'response_prompt']
            missing_persona_fields = [
                field for field in required_persona_fields 
                if field not in persona_data
            ]
            if missing_persona_fields:
                raise ValueError(
                    f"Missing required persona fields in {config_file}: {missing_persona_fields}"
                )
            
            # Build AgentPersona
            persona = AgentPersona(
                system_prompt=persona_data['system_prompt'],
                understanding_prompt=persona_data['understanding_prompt'],
                response_prompt=persona_data['response_prompt'],
                description=persona_data.get('description')
            )
            
            # Build AgentConfig - include document_types in metadata if present
            metadata = config_data.get('metadata', {})
            if 'document_types' in config_data:
                metadata['document_types'] = config_data['document_types']
            
            config = AgentConfig(
                name=config_data['name'],
                description=config_data.get('description', ''),
                persona=persona,
                intents=config_data.get('intents', []),
                entities=config_data.get('entities', []),
                examples=config_data.get('examples', []),
                metadata=metadata
            )
            
            # Cache the config
            self._cache[agent_name] = config
            
            logger.info(f"Loaded agent configuration: {agent_name}")
            return config
            
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {config_file}: {e}")
        except Exception as e:
            raise ValueError(f"Error loading agent config from {config_file}: {e}")
    
    def reload_config(self, agent_name: str) -> AgentConfig:
        """Reload configuration for an agent (clears cache)."""
        if agent_name in self._cache:
            del self._cache[agent_name]
        return self.load_agent_config(agent_name)
    
    def get_all_agents(self) -> list[str]:
        """Get list of all available agent configurations."""
        return [
            f.stem.replace('_agent', '')
            for f in self.config_dir.glob('*_agent.yaml')
        ]


# Global instance
_config_loader: Optional[AgentConfigLoader] = None


def get_agent_config_loader() -> AgentConfigLoader:
    """Get the global agent configuration loader instance."""
    global _config_loader
    if _config_loader is None:
        _config_loader = AgentConfigLoader()
    return _config_loader


def load_agent_config(agent_name: str) -> AgentConfig:
    """
    Convenience function to load agent configuration.
    
    Args:
        agent_name: Name of the agent (e.g., "operations", "safety")
        
    Returns:
        AgentConfig object
    """
    return get_agent_config_loader().load_agent_config(agent_name)

