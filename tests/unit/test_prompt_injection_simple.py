"""
Simple test script for prompt injection protection (no pytest dependency).
Run with: python tests/unit/test_prompt_injection_simple.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.api.utils.log_utils import sanitize_prompt_input, safe_format_prompt


def test_template_injection_protection():
    """Test that template injection attempts are properly escaped."""
    print("Testing prompt injection protection...")
    
    # Test 1: Basic template injection attempt
    print("\n1. Testing basic template injection...")
    malicious = "{__import__('os').system('rm -rf /')}"
    result = sanitize_prompt_input(malicious)
    print(f"   Input:  {malicious}")
    print(f"   Output: {result}")
    assert "{{" in result and "}}" in result, "Braces should be escaped"
    
    # Verify it's safe in f-string - the escaped braces should be literal in final output
    safe_template = f"Query: {result}"
    # The result contains {{ and }}, so final template should have literal braces
    assert safe_template.count("{{") >= 1, "Should contain escaped braces as literals"
    assert safe_template.count("}}") >= 1, "Should contain escaped braces as literals"
    # Should not have single unescaped braces that could be evaluated
    assert safe_template.count("{") == safe_template.count("}"), "Braces should be balanced"
    print("   ✓ PASSED: Template injection prevented")
    
    # Test 2: Variable access attempt
    print("\n2. Testing variable access injection...")
    malicious = "{query.__class__.__init__.__globals__}"
    result = sanitize_prompt_input(malicious)
    print(f"   Input:  {malicious}")
    print(f"   Output: {result}")
    assert "{{" in result, "Braces should be escaped"
    print("   ✓ PASSED: Variable access injection prevented")
    
    # Test 3: Control characters
    print("\n3. Testing control character removal...")
    malicious = "test\x00\x01\x02\n\r"
    result = sanitize_prompt_input(malicious)
    print(f"   Input:  {repr(malicious)}")
    print(f"   Output: {repr(result)}")
    assert "\x00" not in result and "\x01" not in result, "Control chars should be removed"
    print("   ✓ PASSED: Control characters removed")
    
    # Test 4: Normal text preservation
    print("\n4. Testing normal text preservation...")
    normal = "Show me equipment status"
    result = sanitize_prompt_input(normal)
    print(f"   Input:  {normal}")
    print(f"   Output: {result}")
    assert result == normal, "Normal text should be preserved"
    print("   ✓ PASSED: Normal text preserved")
    
    # Test 5: Dict serialization
    print("\n5. Testing dict serialization...")
    data = {"key": "value", "nested": {"inner": "data"}}
    result = sanitize_prompt_input(data)
    print(f"   Input:  {data}")
    print(f"   Output: {result[:50]}...")
    import json
    parsed = json.loads(result)
    assert parsed == data, "Dict should be serialized to JSON"
    print("   ✓ PASSED: Dict serialized correctly")
    
    # Test 6: Length limiting
    print("\n6. Testing length limiting...")
    long_input = "A" * 20000
    result = sanitize_prompt_input(long_input, max_length=10000)
    print(f"   Input length:  20000")
    print(f"   Output length: {len(result)}")
    assert len(result) <= 10000 + 20, "Should be truncated"
    assert "...[truncated]" in result, "Should have truncation marker"
    print("   ✓ PASSED: Length limiting works")
    
    # Test 7: safe_format_prompt
    print("\n7. Testing safe_format_prompt...")
    template = "User Query: {query}"
    malicious_query = "{__import__('os').system('ls')}"
    result = safe_format_prompt(template, query=malicious_query)
    print(f"   Template: {template}")
    print(f"   Query:    {malicious_query}")
    print(f"   Output:   {result}")
    assert "{{" in result, "Should escape braces"
    print("   ✓ PASSED: safe_format_prompt works correctly")
    
    # Test 8: Real-world scenarios
    print("\n8. Testing real-world injection scenarios...")
    scenarios = [
        "{eval('__import__(\"os\").system(\"ls\")')}",
        "{globals()['__builtins__']}",
        "{{config.items()}}",
        "Normal {injection} text",
    ]
    for scenario in scenarios:
        result = sanitize_prompt_input(scenario)
        safe_template = f"Query: {result}"
        # Verify braces are escaped - result should contain {{ or }}
        if "{" in scenario or "}" in scenario:
            # Check that braces in result are escaped (double braces)
            assert "{{" in result or "}}" in result or result.count("{") == 0, f"Failed for: {scenario}"
    print("   ✓ PASSED: Real-world scenarios handled correctly")
    
    print("\n" + "="*60)
    print("ALL TESTS PASSED! ✓")
    print("="*60)


if __name__ == "__main__":
    try:
        test_template_injection_protection()
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

