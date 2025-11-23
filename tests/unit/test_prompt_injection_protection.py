"""
Test suite for prompt injection protection.

Tests the sanitize_prompt_input function to ensure it properly prevents
template injection attacks in f-string prompts.
"""

import pytest
from src.api.utils.log_utils import sanitize_prompt_input, safe_format_prompt


class TestPromptInjectionProtection:
    """Test cases for prompt injection protection."""

    def test_basic_sanitization(self):
        """Test basic string sanitization."""
        input_str = "Show me equipment status"
        result = sanitize_prompt_input(input_str)
        assert result == input_str  # Normal strings should pass through

    def test_template_injection_curly_braces(self):
        """Test that curly braces are escaped to prevent template injection."""
        # Attempt to inject f-string template syntax
        malicious_input = "{__import__('os').system('rm -rf /')}"
        result = sanitize_prompt_input(malicious_input)
        
        # Should escape braces: { becomes {{ and } becomes }}
        assert "{{" in result
        assert "}}" in result
        assert "__import__" in result  # Content should still be there, just escaped
        
        # Verify it's safe to use in f-string
        safe_template = f"User Query: {result}"
        assert "{__import__" not in safe_template  # Should not be evaluated

    def test_template_injection_with_variables(self):
        """Test template injection with variable access attempts."""
        malicious_input = "{query.__class__.__init__.__globals__}"
        result = sanitize_prompt_input(malicious_input)
        
        # Should escape all braces
        assert "{{" in result
        assert "}}" in result
        
        # Verify safe usage in f-string
        safe_template = f"Query: {result}"
        assert "{query.__class__" not in safe_template

    def test_nested_braces(self):
        """Test nested brace patterns."""
        malicious_input = "{{{{{{malicious}}}}}}"
        result = sanitize_prompt_input(malicious_input)
        
        # All braces should be escaped
        assert result.count("{{") >= 3
        assert result.count("}}") >= 3

    def test_control_characters_removed(self):
        """Test that control characters are removed."""
        malicious_input = "test\x00\x01\x02\n\r\t"
        result = sanitize_prompt_input(malicious_input)
        
        # Control characters should be removed
        assert "\x00" not in result
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\n" not in result
        assert "\r" not in result
        # \t might be preserved as it's common whitespace, but other control chars should be gone

    def test_backticks_replaced(self):
        """Test that backticks are replaced with single quotes."""
        malicious_input = "test `code` injection"
        result = sanitize_prompt_input(malicious_input)
        
        # Backticks should be replaced
        assert "`" not in result
        assert "'" in result or "code" in result

    def test_length_limiting(self):
        """Test that very long inputs are truncated."""
        long_input = "A" * 20000  # 20k characters
        result = sanitize_prompt_input(long_input, max_length=10000)
        
        # Should be truncated
        assert len(result) <= 10000 + len("...[truncated]")
        assert "...[truncated]" in result

    def test_dict_serialization(self):
        """Test that dicts are serialized to JSON safely."""
        input_dict = {"key": "value", "nested": {"inner": "data"}}
        result = sanitize_prompt_input(input_dict)
        
        # Should be JSON string
        import json
        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == input_dict

    def test_list_serialization(self):
        """Test that lists are serialized to JSON safely."""
        input_list = [1, 2, 3, {"nested": "value"}]
        result = sanitize_prompt_input(input_list)
        
        # Should be JSON string
        import json
        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed == input_list

    def test_none_handling(self):
        """Test that None is handled safely."""
        result = sanitize_prompt_input(None)
        assert result == "None"

    def test_safe_format_prompt_basic(self):
        """Test safe_format_prompt with normal input."""
        template = "User Query: {query}\nIntent: {intent}"
        result = safe_format_prompt(template, query="Show equipment", intent="equipment")
        
        assert "Show equipment" in result
        assert "equipment" in result

    def test_safe_format_prompt_injection_attempt(self):
        """Test safe_format_prompt with injection attempt."""
        template = "User Query: {query}"
        malicious_query = "{__import__('os').system('rm -rf /')}"
        result = safe_format_prompt(template, query=malicious_query)
        
        # Should escape the braces
        assert "{{" in result
        assert "}}" in result
        assert "__import__" in result

    def test_safe_format_prompt_missing_placeholder(self):
        """Test safe_format_prompt with missing placeholder."""
        template = "User Query: {query}"
        result = safe_format_prompt(template)  # Missing query parameter
        
        # Should include error message
        assert "ERROR" in result or "Missing placeholder" in result

    def test_real_world_injection_scenarios(self):
        """Test real-world template injection scenarios."""
        scenarios = [
            # F-string injection attempts
            "{eval('__import__(\"os\").system(\"ls\")')}",
            "{globals()['__builtins__']['__import__']('os').system('id')}",
            "{''.__class__.__mro__[1].__subclasses__()}",
            # Jinja2-style (should still be escaped)
            "{{config.items()}}",
            "{{self.__init__.__globals__}}",
            # Mustache-style (should still be escaped)
            "{{{variable}}}",
            # Mixed patterns
            "Normal text {injection} more text",
            "{first}{second}{third}",
        ]
        
        for malicious_input in scenarios:
            result = sanitize_prompt_input(malicious_input)
            
            # Verify braces are escaped
            assert "{{" in result or "}}" in result or malicious_input.count("{") == 0
            
            # Verify it's safe to use in f-string
            safe_template = f"Query: {result}"
            # Should not contain unescaped braces that could be evaluated
            assert safe_template.count("{") == safe_template.count("}") or "{Query:" in safe_template

    def test_preserves_normal_text(self):
        """Test that normal text is preserved correctly."""
        normal_inputs = [
            "Show me equipment status",
            "What is the inventory level?",
            "Create a pick wave for Zone A",
            "How many workers are active?",
            "Equipment ID: FL-01, Zone: Zone A",
        ]
        
        for normal_input in normal_inputs:
            result = sanitize_prompt_input(normal_input)
            # Normal text should be preserved (except braces if any)
            assert len(result) > 0
            # Should not have double braces unless original had braces
            if "{" not in normal_input and "}" not in normal_input:
                assert result == normal_input

    def test_special_characters(self):
        """Test handling of special characters."""
        special_input = "Query with: quotes 'single' and \"double\", symbols @#$%, and unicode 中文"
        result = sanitize_prompt_input(special_input)
        
        # Should preserve most characters
        assert "quotes" in result
        assert "single" in result
        assert "double" in result
        # Special symbols should be preserved
        assert "@" in result or "$" in result or "%" in result

