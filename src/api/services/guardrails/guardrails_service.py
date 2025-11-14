import logging
import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class GuardrailsConfig:
    """Configuration for NeMo Guardrails."""

    rails_file: str
    model_name: str = "nvidia/llama-3-70b-instruct"
    temperature: float = 0.1
    max_tokens: int = 1000
    top_p: float = 0.9


@dataclass
class GuardrailsResult:
    """Result from guardrails processing."""

    is_safe: bool
    response: Optional[str] = None
    violations: List[str] = None
    confidence: float = 1.0
    processing_time: float = 0.0


class GuardrailsService:
    """Service for NeMo Guardrails integration."""

    def __init__(self, config: GuardrailsConfig):
        self.config = config
        self.rails_config = None
        self._load_rails_config()

    def _load_rails_config(self):
        """Load the guardrails configuration from YAML file."""
        try:
            # Handle both absolute and relative paths
            rails_path = Path(self.config.rails_file)
            if not rails_path.is_absolute():
                # If relative, try to resolve from project root
                # From src/api/services/guardrails/guardrails_service.py -> project root is 4 levels up
                project_root = Path(__file__).parent.parent.parent.parent
                rails_path = project_root / rails_path
                # Also try resolving from current working directory
                if not rails_path.exists():
                    cwd_path = Path.cwd() / self.config.rails_file
                    if cwd_path.exists():
                        rails_path = cwd_path
            if not rails_path.exists():
                logger.warning(f"Guardrails config file not found: {rails_path}")
                return

            with open(rails_path, "r") as f:
                self.rails_config = yaml.safe_load(f)

            logger.info(f"Loaded guardrails configuration from {rails_path}")
        except Exception as e:
            logger.error(f"Failed to load guardrails config: {e}")
            self.rails_config = None

    async def check_input_safety(
        self, user_input: str, context: Optional[Dict[str, Any]] = None
    ) -> GuardrailsResult:
        """Check if user input is safe and compliant."""
        import time

        start_time = time.time()

        try:
            # Basic safety checks
            violations = []

            # Check for jailbreak attempts
            jailbreak_phrases = [
                "ignore previous instructions",
                "forget everything",
                "you are now",
                "pretend to be",
                "act as if",
                "roleplay as",
                "simulate",
                "override",
                "bypass",
                "jailbreak",
            ]

            user_lower = user_input.lower()
            for phrase in jailbreak_phrases:
                if phrase in user_lower:
                    violations.append(f"Potential jailbreak attempt: '{phrase}'")

            # Check for safety violations
            safety_violations = [
                "operate forklift without training",
                "bypass safety protocols",
                "ignore safety warnings",
                "work without PPE",
                "operate equipment unsafely",
            ]

            for violation in safety_violations:
                if violation in user_lower:
                    violations.append(f"Safety violation: '{violation}'")

            # Check for security violations
            security_violations = [
                "security codes",
                "access restricted areas",
                "alarm codes",
                "disable security",
                "warehouse layout for unauthorized access",
            ]

            for violation in security_violations:
                if violation in user_lower:
                    violations.append(f"Security violation: '{violation}'")

            # Check for compliance violations
            compliance_violations = [
                "avoid safety inspections",
                "skip compliance requirements",
                "ignore regulations",
                "work around safety rules",
            ]

            for violation in compliance_violations:
                if violation in user_lower:
                    violations.append(f"Compliance violation: '{violation}'")

            # Check for off-topic queries
            off_topic_phrases = [
                "weather",
                "joke",
                "capital of",
                "how to cook",
                "recipe",
                "sports",
                "politics",
                "entertainment",
            ]

            is_off_topic = any(phrase in user_lower for phrase in off_topic_phrases)
            if is_off_topic:
                violations.append(
                    "Off-topic query - please ask about warehouse operations"
                )

            processing_time = time.time() - start_time

            if violations:
                return GuardrailsResult(
                    is_safe=False,
                    violations=violations,
                    confidence=0.9,
                    processing_time=processing_time,
                )

            return GuardrailsResult(
                is_safe=True, confidence=0.95, processing_time=processing_time
            )

        except Exception as e:
            logger.error(f"Error in input safety check: {e}")
            return GuardrailsResult(
                is_safe=True,  # Default to safe on error
                confidence=0.5,
                processing_time=time.time() - start_time,
            )

    async def check_output_safety(
        self, response: str, context: Optional[Dict[str, Any]] = None
    ) -> GuardrailsResult:
        """Check if AI response is safe and compliant."""
        import time

        start_time = time.time()

        try:
            violations = []
            response_lower = response.lower()

            # Check for dangerous instructions
            dangerous_phrases = [
                "ignore safety",
                "bypass protocol",
                "skip training",
                "work without",
                "operate without",
                "disable safety",
            ]

            for phrase in dangerous_phrases:
                if phrase in response_lower:
                    violations.append(f"Dangerous instruction: '{phrase}'")

            # Check for security information leakage
            security_phrases = [
                "security code",
                "access code",
                "password",
                "master key",
                "restricted area",
                "alarm code",
                "encryption key",
            ]

            for phrase in security_phrases:
                if phrase in response_lower:
                    violations.append(f"Potential security leak: '{phrase}'")

            # Check for compliance violations
            compliance_phrases = [
                "avoid inspection",
                "skip compliance",
                "ignore regulation",
                "work around rule",
                "circumvent policy",
            ]

            for phrase in compliance_phrases:
                if phrase in response_lower:
                    violations.append(f"Compliance violation: '{phrase}'")

            processing_time = time.time() - start_time

            if violations:
                return GuardrailsResult(
                    is_safe=False,
                    violations=violations,
                    confidence=0.9,
                    processing_time=processing_time,
                )

            return GuardrailsResult(
                is_safe=True, confidence=0.95, processing_time=processing_time
            )

        except Exception as e:
            logger.error(f"Error in output safety check: {e}")
            return GuardrailsResult(
                is_safe=True,  # Default to safe on error
                confidence=0.5,
                processing_time=time.time() - start_time,
            )

    async def process_with_guardrails(
        self,
        user_input: str,
        ai_response: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> GuardrailsResult:
        """Process input and output through guardrails."""
        try:
            # Check input safety
            input_result = await self.check_input_safety(user_input, context)
            if not input_result.is_safe:
                return input_result

            # Check output safety
            output_result = await self.check_output_safety(ai_response, context)
            if not output_result.is_safe:
                return output_result

            # If both are safe, return success
            return GuardrailsResult(
                is_safe=True,
                response=ai_response,
                confidence=min(input_result.confidence, output_result.confidence),
                processing_time=input_result.processing_time
                + output_result.processing_time,
            )

        except Exception as e:
            logger.error(f"Error in guardrails processing: {e}")
            return GuardrailsResult(
                is_safe=True,  # Default to safe on error
                confidence=0.5,
                processing_time=0.0,
            )

    def get_safety_response(self, violations: List[str]) -> str:
        """Generate appropriate safety response based on violations."""
        if not violations:
            return "No safety violations detected."

        # Categorize violations
        jailbreak_violations = [v for v in violations if "jailbreak" in v.lower()]
        safety_violations = [v for v in violations if "safety" in v.lower()]
        security_violations = [v for v in violations if "security" in v.lower()]
        compliance_violations = [v for v in violations if "compliance" in v.lower()]
        off_topic_violations = [v for v in violations if "off-topic" in v.lower()]

        responses = []

        if jailbreak_violations:
            responses.append(
                "I cannot ignore my instructions or roleplay as someone else. I'm here to help with warehouse operations."
            )

        if safety_violations:
            responses.append(
                "Safety is our top priority. I cannot provide guidance that bypasses safety protocols. Please consult with your safety supervisor."
            )

        if security_violations:
            responses.append(
                "I cannot provide security-sensitive information. Please contact your security team for security-related questions."
            )

        if compliance_violations:
            responses.append(
                "Compliance with safety regulations and company policies is mandatory. Please follow all established procedures."
            )

        if off_topic_violations:
            responses.append(
                "I'm specialized in warehouse operations. I can help with inventory management, operations coordination, and safety compliance."
            )

        if not responses:
            responses.append(
                "I cannot assist with that request. Please ask about warehouse operations, inventory, or safety procedures."
            )

        return (
            " ".join(responses) + " How can I help you with warehouse operations today?"
        )


# Global instance
guardrails_service = GuardrailsService(
    GuardrailsConfig(
        rails_file="data/config/guardrails/rails.yaml", model_name="nvidia/llama-3-70b-instruct"
    )
)
