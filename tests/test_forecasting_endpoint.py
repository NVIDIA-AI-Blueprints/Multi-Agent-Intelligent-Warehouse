#!/usr/bin/env python3
"""
Comprehensive test script for Forecasting page and API endpoints.
Tests all forecasting-related functionality including dashboard, real-time forecasts,
reorder recommendations, model performance, and business intelligence.
"""

import requests
import json
import time
from typing import Dict, Any, Optional, List
from datetime import datetime

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
            response = requests.get(url, params=params, timeout=30)
        elif method.upper() == "POST":
            response = requests.post(url, json=payload, timeout=30)
        elif method.upper() == "PUT":
            response = requests.put(url, json=payload, timeout=30)
        elif method.upper() == "DELETE":
            response = requests.delete(url, timeout=30)
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
        log_test(test_name, "FAIL", "Request timed out after 30 seconds", 30.0)
        return None
    except requests.exceptions.RequestException as e:
        log_test(test_name, "FAIL", f"Request failed: {str(e)}", 0.0)
        return None


def test_frontend_page():
    """Test if frontend Forecasting page is accessible."""
    print("\n" + "="*80)
    print("1. TESTING FRONTEND PAGE ACCESSIBILITY")
    print("="*80)
    
    try:
        response = requests.get(f"{FRONTEND_URL}/forecasting", timeout=5, allow_redirects=True)
        if response.status_code == 200:
            if "forecast" in response.text.lower() or "<!DOCTYPE html>" in response.text:
                log_test("Frontend Forecasting Page", "PASS", "Page is accessible")
                return True
        log_test("Frontend Forecasting Page", "FAIL", f"Status: {response.status_code}")
        return False
    except Exception as e:
        log_test("Frontend Forecasting Page", "FAIL", f"Error: {str(e)}")
        return False


def test_forecasting_health():
    """Test GET /forecasting/health endpoint."""
    print("\n" + "="*80)
    print("2. TESTING FORECASTING HEALTH")
    print("="*80)
    
    result = test_endpoint("GET", "/forecasting/health", description="Health check")
    return result


def test_dashboard_endpoint():
    """Test GET /forecasting/dashboard endpoint."""
    print("\n" + "="*80)
    print("3. TESTING FORECASTING DASHBOARD")
    print("="*80)
    
    result = test_endpoint("GET", "/forecasting/dashboard", description="Dashboard summary")
    
    if result and result.get("data"):
        data = result["data"]
        # Check for expected keys
        expected_keys = ["business_intelligence", "reorder_recommendations", "model_performance", "forecast_summary"]
        missing_keys = [key for key in expected_keys if key not in data]
        if missing_keys:
            log_test("Dashboard Data Structure", "FAIL", f"Missing keys: {missing_keys}")
        else:
            log_test("Dashboard Data Structure", "PASS", "All expected keys present")
    
    return result


def test_real_time_forecast():
    """Test POST /forecasting/real-time endpoint."""
    print("\n" + "="*80)
    print("4. TESTING REAL-TIME FORECAST")
    print("="*80)
    
    # Test with valid SKU
    payload = {
        "sku": "LAY001",
        "horizon_days": 30,
        "include_confidence_intervals": True,
        "include_feature_importance": True
    }
    result = test_endpoint("POST", "/forecasting/real-time", payload=payload, description="Valid SKU (LAY001)")
    
    # Test with invalid SKU
    payload = {
        "sku": "INVALID_SKU_12345",
        "horizon_days": 30
    }
    test_endpoint("POST", "/forecasting/real-time", payload=payload, expected_status=500, description="Invalid SKU")
    
    # Test with missing required fields
    payload = {"horizon_days": 30}  # Missing sku
    test_endpoint("POST", "/forecasting/real-time", payload=payload, expected_status=422, description="Missing required fields")
    
    return result


def test_reorder_recommendations():
    """Test GET /forecasting/reorder-recommendations endpoint."""
    print("\n" + "="*80)
    print("5. TESTING REORDER RECOMMENDATIONS")
    print("="*80)
    
    result = test_endpoint("GET", "/forecasting/reorder-recommendations", description="Get recommendations")
    
    if result and result.get("data"):
        data = result["data"]
        # Backend returns {recommendations: [...], ...}, check for recommendations key
        if isinstance(data, dict) and "recommendations" in data:
            recommendations = data["recommendations"]
            log_test("Reorder Recommendations Format", "PASS", f"Returns dict with recommendations list ({len(recommendations)} items)")
            if len(recommendations) > 0:
                # Check first item structure
                first_item = recommendations[0]
                expected_keys = ["sku", "current_stock", "recommended_order_quantity", "urgency_level"]
                missing_keys = [key for key in expected_keys if key not in first_item]
                if missing_keys:
                    log_test("Reorder Recommendation Structure", "FAIL", f"Missing keys: {missing_keys}")
                else:
                    log_test("Reorder Recommendation Structure", "PASS", "All expected keys present")
        elif isinstance(data, list):
            log_test("Reorder Recommendations Format", "PASS", f"Returns list with {len(data)} items")
        else:
            log_test("Reorder Recommendations Format", "FAIL", f"Expected dict with recommendations or list, got {type(data)}")
    
    return result


def test_model_performance():
    """Test GET /forecasting/model-performance endpoint."""
    print("\n" + "="*80)
    print("6. TESTING MODEL PERFORMANCE")
    print("="*80)
    
    result = test_endpoint("GET", "/forecasting/model-performance", description="Get model performance")
    
    if result and result.get("data"):
        data = result["data"]
        # Backend returns {model_metrics: [...], ...}, check for model_metrics key
        if isinstance(data, dict) and "model_metrics" in data:
            metrics = data["model_metrics"]
            log_test("Model Performance Format", "PASS", f"Returns dict with model_metrics list ({len(metrics)} models)")
            if len(metrics) > 0:
                # Check first model structure
                first_model = metrics[0]
                expected_keys = ["model_name", "accuracy_score", "mape", "last_training_date"]
                missing_keys = [key for key in expected_keys if key not in first_model]
                if missing_keys:
                    log_test("Model Performance Structure", "FAIL", f"Missing keys: {missing_keys}")
                else:
                    log_test("Model Performance Structure", "PASS", "All expected keys present")
        elif isinstance(data, list):
            log_test("Model Performance Format", "PASS", f"Returns list with {len(data)} models")
        else:
            log_test("Model Performance Format", "FAIL", f"Expected dict with model_metrics or list, got {type(data)}")
    
    return result


def test_business_intelligence():
    """Test GET /forecasting/business-intelligence endpoint."""
    print("\n" + "="*80)
    print("7. TESTING BUSINESS INTELLIGENCE")
    print("="*80)
    
    # Test basic endpoint
    result = test_endpoint("GET", "/forecasting/business-intelligence", description="Basic BI summary")
    
    # Test enhanced endpoint
    test_endpoint("GET", "/forecasting/business-intelligence/enhanced", description="Enhanced BI summary")
    
    return result


def test_batch_forecast():
    """Test POST /forecasting/batch-forecast endpoint."""
    print("\n" + "="*80)
    print("8. TESTING BATCH FORECAST")
    print("="*80)
    
    # Test with valid SKUs
    payload = {
        "skus": ["LAY001", "LAY002", "DOR001"],
        "horizon_days": 30
    }
    result = test_endpoint("POST", "/forecasting/batch-forecast", payload=payload, description="Valid SKUs")
    
    # Test with empty SKU list
    payload = {
        "skus": [],
        "horizon_days": 30
    }
    test_endpoint("POST", "/forecasting/batch-forecast", payload=payload, expected_status=400, description="Empty SKU list")
    
    # Test with missing skus field
    payload = {
        "horizon_days": 30
    }
    test_endpoint("POST", "/forecasting/batch-forecast", payload=payload, expected_status=422, description="Missing skus field")
    
    return result


def test_training_endpoints():
    """Test training-related endpoints."""
    print("\n" + "="*80)
    print("9. TESTING TRAINING ENDPOINTS")
    print("="*80)
    
    # Test get training status
    test_endpoint("GET", "/training/status", description="Get training status")
    
    # Test get training history
    test_endpoint("GET", "/training/history", description="Get training history")
    
    # Test start training (may take time, so we'll just check if endpoint exists)
    payload = {
        "training_type": "basic",
        "force_retrain": False
    }
    # Note: We won't actually start training, just test the endpoint
    # test_endpoint("POST", "/training/start", payload=payload, description="Start training (not executed)")
    
    return None


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
    slow_tests = [r for r in test_results if r["response_time"] > 10.0]
    if slow_tests:
        issues.append(f"{len(slow_tests)} test(s) took longer than 10 seconds")
        recommendations.append("Investigate performance bottlenecks in forecasting service")
    
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
    """Run all forecasting endpoint tests."""
    print("="*80)
    print("FORECASTING ENDPOINT COMPREHENSIVE TEST")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Frontend URL: {FRONTEND_URL}")
    print(f"Test started: {datetime.now().isoformat()}")
    
    # Test frontend
    test_frontend_page()
    
    # Test all API endpoints
    test_forecasting_health()
    test_dashboard_endpoint()
    test_real_time_forecast()
    test_reorder_recommendations()
    test_model_performance()
    test_business_intelligence()
    test_batch_forecast()
    test_training_endpoints()
    
    # Generate summary
    generate_summary()
    
    return test_results


if __name__ == "__main__":
    run_all_tests()

