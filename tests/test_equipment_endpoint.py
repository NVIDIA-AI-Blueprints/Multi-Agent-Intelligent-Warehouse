#!/usr/bin/env python3
"""
Comprehensive test script for Equipment page and API endpoints.
Tests all equipment-related functionality including assets, assignments, maintenance, and telemetry.
"""

import requests
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "http://localhost:8001"
FRONTEND_URL = "http://localhost:3001"
BASE_API = f"{BACKEND_URL}/api/v1"

# Test results storage
test_results = []


def log_test(name: str, status: str, details: str = "", response_time: float = 0.0):
    """Log test result."""
    result = {
        "name": name,
        "status": status,
        "details": details,
        "response_time": response_time,
        "timestamp": datetime.now().isoformat()
    }
    test_results.append(result)
    status_icon = "✅" if status == "PASS" else "❌" if status == "FAIL" else "⚠️"
    print(f"{status_icon} {name}: {status}")
    if details:
        print(f"   {details}")
    if response_time > 0:
        print(f"   ⏱️  Response time: {response_time:.2f}s")


def test_endpoint(method: str, endpoint: str, expected_status: int = 200, 
                  payload: Optional[Dict] = None, params: Optional[Dict] = None,
                  description: str = "") -> Optional[Dict[str, Any]]:
    """Test an API endpoint."""
    url = f"{BASE_API}{endpoint}"
    test_name = f"{method} {endpoint}"
    if description:
        test_name = f"{test_name} - {description}"
    
    try:
        start_time = time.time()
        
        if method.upper() == "GET":
            response = requests.get(url, params=params, timeout=10)
        elif method.upper() == "POST":
            response = requests.post(url, json=payload, timeout=10)
        elif method.upper() == "PUT":
            response = requests.put(url, json=payload, timeout=10)
        elif method.upper() == "DELETE":
            response = requests.delete(url, timeout=10)
        else:
            log_test(test_name, "FAIL", f"Unsupported HTTP method: {method}")
            return None
        
        elapsed_time = time.time() - start_time
        
        if response.status_code == expected_status:
            try:
                data = response.json() if response.content else {}
                log_test(test_name, "PASS", f"Status: {response.status_code}", elapsed_time)
                return {"status_code": response.status_code, "data": data, "response_time": elapsed_time}
            except json.JSONDecodeError:
                log_test(test_name, "PASS", f"Status: {response.status_code} (No JSON body)", elapsed_time)
                return {"status_code": response.status_code, "data": None, "response_time": elapsed_time}
        else:
            error_msg = f"Expected {expected_status}, got {response.status_code}"
            try:
                error_data = response.json()
                error_msg += f" - {error_data.get('detail', '')}"
            except:
                error_msg += f" - {response.text[:100]}"
            log_test(test_name, "FAIL", error_msg, elapsed_time)
            return {"status_code": response.status_code, "error": error_msg, "response_time": elapsed_time}
    
    except requests.exceptions.Timeout:
        log_test(test_name, "FAIL", "Request timed out after 10 seconds", 10.0)
        return None
    except requests.exceptions.RequestException as e:
        log_test(test_name, "FAIL", f"Request failed: {str(e)}", 0.0)
        return None


def test_frontend_page():
    """Test if frontend Equipment page is accessible."""
    print("\n" + "="*80)
    print("1. TESTING FRONTEND PAGE ACCESSIBILITY")
    print("="*80)
    
    try:
        response = requests.get(f"{FRONTEND_URL}/equipment", timeout=5, allow_redirects=True)
        if response.status_code == 200:
            if "equipment" in response.text.lower() or "<!DOCTYPE html>" in response.text:
                log_test("Frontend Equipment Page", "PASS", "Page is accessible")
                return True
        log_test("Frontend Equipment Page", "FAIL", f"Status: {response.status_code}")
        return False
    except Exception as e:
        log_test("Frontend Equipment Page", "FAIL", f"Error: {str(e)}")
        return False


def test_get_all_equipment():
    """Test GET /equipment endpoint."""
    print("\n" + "="*80)
    print("2. TESTING GET ALL EQUIPMENT")
    print("="*80)
    
    # Test without filters
    result = test_endpoint("GET", "/equipment", description="No filters")
    
    # Test with type filter
    test_endpoint("GET", "/equipment", params={"equipment_type": "forklift"}, description="Filter by type")
    
    # Test with zone filter
    test_endpoint("GET", "/equipment", params={"zone": "Zone A"}, description="Filter by zone")
    
    # Test with status filter
    test_endpoint("GET", "/equipment", params={"status": "available"}, description="Filter by status")
    
    # Test with multiple filters
    test_endpoint("GET", "/equipment", params={
        "equipment_type": "forklift",
        "zone": "Zone A",
        "status": "available"
    }, description="Multiple filters")
    
    return result


def test_get_equipment_by_id():
    """Test GET /equipment/{asset_id} endpoint."""
    print("\n" + "="*80)
    print("3. TESTING GET EQUIPMENT BY ID")
    print("="*80)
    
    # First, get all equipment to find a valid asset_id
    result = test_endpoint("GET", "/equipment")
    if result and result.get("data"):
        assets = result["data"]
        if assets and len(assets) > 0:
            asset_id = assets[0].get("asset_id")
            if asset_id:
                test_endpoint("GET", f"/equipment/{asset_id}", description=f"Valid asset_id: {asset_id}")
            else:
                log_test("GET /equipment/{asset_id}", "SKIP", "No asset_id found in response")
        else:
            log_test("GET /equipment/{asset_id}", "SKIP", "No equipment assets found")
    else:
        log_test("GET /equipment/{asset_id}", "SKIP", "Could not fetch equipment list")
    
    # Test with invalid asset_id
    test_endpoint("GET", "/equipment/INVALID_ASSET_ID_12345", expected_status=404, description="Invalid asset_id")


def test_get_equipment_status():
    """Test GET /equipment/{asset_id}/status endpoint."""
    print("\n" + "="*80)
    print("4. TESTING GET EQUIPMENT STATUS")
    print("="*80)
    
    # Get a valid asset_id
    result = test_endpoint("GET", "/equipment")
    if result and result.get("data"):
        assets = result["data"]
        if assets and len(assets) > 0:
            asset_id = assets[0].get("asset_id")
            if asset_id:
                test_endpoint("GET", f"/equipment/{asset_id}/status", description=f"Status for {asset_id}")
            else:
                log_test("GET /equipment/{asset_id}/status", "SKIP", "No asset_id found")
        else:
            log_test("GET /equipment/{asset_id}/status", "SKIP", "No equipment assets found")
    else:
        log_test("GET /equipment/{asset_id}/status", "SKIP", "Could not fetch equipment list")
    
    # Test with invalid asset_id
    test_endpoint("GET", "/equipment/INVALID_ASSET_ID_12345/status", expected_status=500, description="Invalid asset_id")


def test_get_assignments():
    """Test GET /equipment/assignments endpoint."""
    print("\n" + "="*80)
    print("5. TESTING GET EQUIPMENT ASSIGNMENTS")
    print("="*80)
    
    # Test without filters (active only by default)
    test_endpoint("GET", "/equipment/assignments", description="Active assignments only")
    
    # Test with active_only=false
    test_endpoint("GET", "/equipment/assignments", params={"active_only": "false"}, description="All assignments")
    
    # Test with asset_id filter
    result = test_endpoint("GET", "/equipment")
    if result and result.get("data"):
        assets = result["data"]
        if assets and len(assets) > 0:
            asset_id = assets[0].get("asset_id")
            if asset_id:
                test_endpoint("GET", "/equipment/assignments", params={"asset_id": asset_id}, description=f"Filter by asset_id: {asset_id}")
    
    # Test with assignee filter
    test_endpoint("GET", "/equipment/assignments", params={"assignee": "operator1"}, description="Filter by assignee")


def test_get_maintenance_schedule():
    """Test GET /equipment/maintenance/schedule endpoint."""
    print("\n" + "="*80)
    print("6. TESTING GET MAINTENANCE SCHEDULE")
    print("="*80)
    
    # Test without filters
    test_endpoint("GET", "/equipment/maintenance/schedule", description="All maintenance (30 days)")
    
    # Test with days_ahead parameter
    test_endpoint("GET", "/equipment/maintenance/schedule", params={"days_ahead": 7}, description="7 days ahead")
    
    # Test with asset_id filter
    result = test_endpoint("GET", "/equipment")
    if result and result.get("data"):
        assets = result["data"]
        if assets and len(assets) > 0:
            asset_id = assets[0].get("asset_id")
            if asset_id:
                test_endpoint("GET", "/equipment/maintenance/schedule", params={"asset_id": asset_id}, description=f"Filter by asset_id: {asset_id}")
    
    # Test with maintenance_type filter
    test_endpoint("GET", "/equipment/maintenance/schedule", params={"maintenance_type": "preventive"}, description="Filter by type")


def test_get_telemetry():
    """Test GET /equipment/{asset_id}/telemetry endpoint."""
    print("\n" + "="*80)
    print("7. TESTING GET EQUIPMENT TELEMETRY")
    print("="*80)
    
    # Get a valid asset_id
    result = test_endpoint("GET", "/equipment")
    if result and result.get("data"):
        assets = result["data"]
        if assets and len(assets) > 0:
            asset_id = assets[0].get("asset_id")
            if asset_id:
                # Test without filters (default 168 hours)
                test_endpoint("GET", f"/equipment/{asset_id}/telemetry", description=f"Default (168h) for {asset_id}")
                
                # Test with hours_back parameter
                test_endpoint("GET", f"/equipment/{asset_id}/telemetry", params={"hours_back": 24}, description="24 hours back")
                
                # Test with metric filter
                test_endpoint("GET", f"/equipment/{asset_id}/telemetry", params={"metric": "battery_level"}, description="Filter by metric")
            else:
                log_test("GET /equipment/{asset_id}/telemetry", "SKIP", "No asset_id found")
        else:
            log_test("GET /equipment/{asset_id}/telemetry", "SKIP", "No equipment assets found")
    else:
        log_test("GET /equipment/{asset_id}/telemetry", "SKIP", "Could not fetch equipment list")
    
    # Test with invalid asset_id
    test_endpoint("GET", "/equipment/INVALID_ASSET_ID_12345/telemetry", expected_status=500, description="Invalid asset_id")


def test_assign_equipment():
    """Test POST /equipment/assign endpoint."""
    print("\n" + "="*80)
    print("8. TESTING ASSIGN EQUIPMENT")
    print("="*80)
    
    # Get a valid asset_id
    result = test_endpoint("GET", "/equipment")
    if result and result.get("data"):
        assets = result["data"]
        if assets and len(assets) > 0:
            asset_id = assets[0].get("asset_id")
            if asset_id:
                # Test valid assignment
                payload = {
                    "asset_id": asset_id,
                    "assignee": "test_operator",
                    "assignment_type": "task",
                    "notes": "Test assignment from automated test"
                }
                test_endpoint("POST", "/equipment/assign", payload=payload, description=f"Assign {asset_id}")
            else:
                log_test("POST /equipment/assign", "SKIP", "No asset_id found")
        else:
            log_test("POST /equipment/assign", "SKIP", "No equipment assets found")
    else:
        log_test("POST /equipment/assign", "SKIP", "Could not fetch equipment list")
    
    # Test with invalid asset_id
    payload = {
        "asset_id": "INVALID_ASSET_ID_12345",
        "assignee": "test_operator",
        "assignment_type": "task"
    }
    test_endpoint("POST", "/equipment/assign", payload=payload, expected_status=400, description="Invalid asset_id")
    
    # Test with missing required fields
    payload = {"asset_id": "TEST-001"}  # Missing assignee
    test_endpoint("POST", "/equipment/assign", payload=payload, expected_status=422, description="Missing required fields")


def test_release_equipment():
    """Test POST /equipment/release endpoint."""
    print("\n" + "="*80)
    print("9. TESTING RELEASE EQUIPMENT")
    print("="*80)
    
    # Get a valid asset_id (preferably one that's assigned)
    result = test_endpoint("GET", "/equipment/assignments", params={"active_only": "true"})
    if result and result.get("data") and len(result["data"]) > 0:
        asset_id = result["data"][0].get("asset_id")
        if asset_id:
            payload = {
                "asset_id": asset_id,
                "released_by": "test_operator",
                "notes": "Test release from automated test"
            }
            test_endpoint("POST", "/equipment/release", payload=payload, description=f"Release {asset_id}")
        else:
            log_test("POST /equipment/release", "SKIP", "No assigned asset found")
    else:
        # Try with any asset
        result = test_endpoint("GET", "/equipment")
        if result and result.get("data"):
            assets = result["data"]
            if assets and len(assets) > 0:
                asset_id = assets[0].get("asset_id")
                if asset_id:
                    payload = {
                        "asset_id": asset_id,
                        "released_by": "test_operator"
                    }
                    test_endpoint("POST", "/equipment/release", payload=payload, description=f"Release {asset_id} (may fail if not assigned)")
    
    # Test with invalid asset_id
    payload = {
        "asset_id": "INVALID_ASSET_ID_12345",
        "released_by": "test_operator"
    }
    test_endpoint("POST", "/equipment/release", payload=payload, expected_status=400, description="Invalid asset_id")
    
    # Test with missing required fields
    payload = {"asset_id": "TEST-001"}  # Missing released_by
    test_endpoint("POST", "/equipment/release", payload=payload, expected_status=422, description="Missing required fields")


def test_schedule_maintenance():
    """Test POST /equipment/maintenance endpoint."""
    print("\n" + "="*80)
    print("10. TESTING SCHEDULE MAINTENANCE")
    print("="*80)
    
    # Get a valid asset_id
    result = test_endpoint("GET", "/equipment")
    if result and result.get("data"):
        assets = result["data"]
        if assets and len(assets) > 0:
            asset_id = assets[0].get("asset_id")
            if asset_id:
                # Schedule maintenance for 7 days from now
                scheduled_for = (datetime.now() + timedelta(days=7)).isoformat()
                payload = {
                    "asset_id": asset_id,
                    "maintenance_type": "preventive",
                    "description": "Test maintenance from automated test",
                    "scheduled_by": "test_operator",
                    "scheduled_for": scheduled_for,
                    "estimated_duration_minutes": 60,
                    "priority": "medium"
                }
                test_endpoint("POST", "/equipment/maintenance", payload=payload, description=f"Schedule maintenance for {asset_id}")
            else:
                log_test("POST /equipment/maintenance", "SKIP", "No asset_id found")
        else:
            log_test("POST /equipment/maintenance", "SKIP", "No equipment assets found")
    else:
        log_test("POST /equipment/maintenance", "SKIP", "Could not fetch equipment list")
    
    # Test with invalid asset_id
    scheduled_for = (datetime.now() + timedelta(days=7)).isoformat()
    payload = {
        "asset_id": "INVALID_ASSET_ID_12345",
        "maintenance_type": "preventive",
        "description": "Test",
        "scheduled_by": "test_operator",
        "scheduled_for": scheduled_for
    }
    test_endpoint("POST", "/equipment/maintenance", payload=payload, expected_status=400, description="Invalid asset_id")
    
    # Test with missing required fields
    payload = {"asset_id": "TEST-001"}  # Missing required fields
    test_endpoint("POST", "/equipment/maintenance", payload=payload, expected_status=422, description="Missing required fields")


def generate_summary():
    """Generate test summary."""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    total_tests = len(test_results)
    passed = sum(1 for r in test_results if r["status"] == "PASS")
    failed = sum(1 for r in test_results if r["status"] == "FAIL")
    skipped = sum(1 for r in test_results if r["status"] == "SKIP")
    
    print(f"\nTotal Tests: {total_tests}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"⏭️  Skipped: {skipped}")
    print(f"Success Rate: {(passed/total_tests*100):.1f}%" if total_tests > 0 else "N/A")
    
    # Response time statistics
    response_times = [r["response_time"] for r in test_results if r["response_time"] > 0]
    if response_times:
        avg_time = sum(response_times) / len(response_times)
        max_time = max(response_times)
        min_time = min(response_times)
        print(f"\nResponse Time Statistics:")
        print(f"  Average: {avg_time:.2f}s")
        print(f"  Min: {min_time:.2f}s")
        print(f"  Max: {max_time:.2f}s")
    
    # Failed tests
    failed_tests = [r for r in test_results if r["status"] == "FAIL"]
    if failed_tests:
        print(f"\n❌ Failed Tests ({len(failed_tests)}):")
        for test in failed_tests:
            print(f"  • {test['name']}: {test['details']}")
    
    # Issues and recommendations
    print("\n" + "="*80)
    print("ISSUES & RECOMMENDATIONS")
    print("="*80)
    
    issues = []
    recommendations = []
    
    # Check for slow responses
    slow_tests = [r for r in test_results if r["response_time"] > 5.0]
    if slow_tests:
        issues.append(f"{len(slow_tests)} test(s) took longer than 5 seconds")
        recommendations.append("Investigate performance bottlenecks in equipment queries")
    
    # Check for high failure rate
    if total_tests > 0 and (failed / total_tests) > 0.2:
        issues.append(f"High failure rate: {(failed/total_tests*100):.1f}%")
        recommendations.append("Review error handling and API endpoint implementations")
    
    if issues:
        for issue in issues:
            print(f"  ⚠️  {issue}")
    else:
        print("  ✅ No major issues detected")
    
    print()
    if recommendations:
        print("Recommendations:")
        for rec in recommendations:
            print(f"  • {rec}")
    else:
        print("  ✅ No recommendations at this time")
    
    print()


def run_all_tests():
    """Run all equipment endpoint tests."""
    print("="*80)
    print("EQUIPMENT ENDPOINT COMPREHENSIVE TEST")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Frontend URL: {FRONTEND_URL}")
    print(f"Test started: {datetime.now().isoformat()}")
    
    # Test frontend
    test_frontend_page()
    
    # Test all API endpoints
    test_get_all_equipment()
    test_get_equipment_by_id()
    test_get_equipment_status()
    test_get_assignments()
    test_get_maintenance_schedule()
    test_get_telemetry()
    test_assign_equipment()
    test_release_equipment()
    test_schedule_maintenance()
    
    # Generate summary
    generate_summary()
    
    return test_results


if __name__ == "__main__":
    run_all_tests()

