"""
Response Quality Control Demo for Warehouse Operational Assistant

Demonstrates the comprehensive response quality control system with validation,
enhancement, user experience improvements, and analytics.
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_response_validator():
    """Test the response validator functionality."""
    print("🧪 Testing Response Validator...")
    
    try:
        from src.retrieval.response_quality.response_validator import (
            ResponseValidator, UserRole, get_response_validator
        )
        
        # Initialize validator
        validator = get_response_validator()
        
        # Test cases with different quality levels
        test_cases = [
            {
                "response": "We have 6 active workers currently on shift. 3 are on morning shift and 3 are on afternoon shift.",
                "evidence_data": {
                    "evidence_score": {"overall_score": 0.9},
                    "sources": [
                        {"type": "database", "name": "PostgreSQL", "confidence": 0.95},
                        {"type": "api", "name": "HR System", "confidence": 0.85}
                    ],
                    "timestamp": datetime.now().isoformat()
                },
                "query_context": {"intent": "workforce", "route": "sql"},
                "expected_quality": "good"
            },
            {
                "response": "Some workers are available.",
                "evidence_data": {
                    "evidence_score": {"overall_score": 0.4},
                    "sources": [{"type": "estimated", "name": "Estimation", "confidence": 0.3}]
                },
                "query_context": {"intent": "workforce", "route": "vector"},
                "expected_quality": "poor"
            },
            {
                "response": "SKU123 has 100 units available in warehouse A, 50 units in warehouse B. Total ATP: 150 units. Last updated: 2024-09-07 10:30 AM.",
                "evidence_data": {
                    "evidence_score": {"overall_score": 0.95},
                    "sources": [
                        {"type": "database", "name": "PostgreSQL", "confidence": 0.98},
                        {"type": "api", "name": "WMS System", "confidence": 0.92}
                    ],
                    "completeness": 0.9
                },
                "query_context": {"intent": "equipment_lookup", "route": "sql"},
                "expected_quality": "excellent"
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n📝 Test Case {i}: {test_case['expected_quality'].upper()} Quality")
            
            validation = validator.validate_response(
                response=test_case["response"],
                evidence_data=test_case["evidence_data"],
                query_context=test_case["query_context"],
                user_role=UserRole.OPERATOR
            )
            
            print(f"✅ Validation: {'Valid' if validation.is_valid else 'Invalid'}")
            print(f"📊 Quality: {validation.quality.value.upper()}")
            print(f"🎯 Confidence: {validation.confidence.level.value.upper()} ({validation.confidence.score:.1%})")
            print(f"📈 Completeness: {validation.completeness_score:.1%}")
            print(f"🔄 Consistency: {validation.consistency_score:.1%}")
            print(f"📚 Sources: {len(validation.source_attributions)}")
            
            if validation.warnings:
                print(f"⚠️ Warnings: {', '.join(validation.warnings)}")
            
            if validation.suggestions:
                print(f"💡 Suggestions: {', '.join(validation.suggestions)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Response validator test failed: {e}")
        return False

async def test_response_enhancer():
    """Test the response enhancer functionality."""
    print("\n🧪 Testing Response Enhancer...")
    
    try:
        from src.retrieval.response_quality.response_enhancer import (
            ResponseEnhancementService, AgentResponse, get_response_enhancer
        )
        from src.retrieval.response_quality.response_validator import UserRole
        
        # Initialize enhancer
        enhancer = await get_response_enhancer()
        
        # Test cases for different user roles
        test_cases = [
            {
                "agent_response": AgentResponse(
                    response="We have 6 active workers on shift today.",
                    agent_name="Operations Agent",
                    intent="workforce",
                    confidence=0.85,
                    data={"total_workers": 6, "shifts": {"morning": 3, "afternoon": 3}}
                ),
                "user_role": UserRole.OPERATOR,
                "query_context": {"intent": "workforce", "route": "sql"}
            },
            {
                "agent_response": AgentResponse(
                    response="Current task status: 8 pending, 5 in progress, 12 completed.",
                    agent_name="Operations Agent",
                    intent="task_management",
                    confidence=0.90,
                    data={"pending": 8, "in_progress": 5, "completed": 12}
                ),
                "user_role": UserRole.SUPERVISOR,
                "query_context": {"intent": "task_management", "route": "sql"}
            },
            {
                "agent_response": AgentResponse(
                    response="SKU123 equipment status: Operational, last maintenance 2024-09-01.",
                    agent_name="Equipment Agent",
                    intent="equipment_lookup",
                    confidence=0.75,
                    data={"sku": "SKU123", "status": "operational", "maintenance_date": "2024-09-01"}
                ),
                "user_role": UserRole.MANAGER,
                "query_context": {"intent": "equipment_lookup", "route": "sql"}
            }
        ]
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\n👤 Test Case {i}: {test_case['user_role'].value.upper()} Role")
            
            enhanced_response = await enhancer.enhance_agent_response(
                agent_response=test_case["agent_response"],
                user_role=test_case["user_role"],
                query_context=test_case["query_context"]
            )
            
            print(f"📝 Original: {test_case['agent_response'].response}")
            print(f"✨ Enhanced: {enhanced_response.enhanced_response.enhanced_response}")
            print(f"🎯 UX Score: {enhanced_response.user_experience_score:.1%}")
            print(f"🔄 Personalization: {'Applied' if enhanced_response.personalization_applied else 'Not Applied'}")
            print(f"⏱️ Response Time: {enhanced_response.response_time_ms:.1f}ms")
            
            if enhanced_response.follow_up_queries:
                print(f"💬 Follow-ups: {', '.join(enhanced_response.follow_up_queries[:3])}")
        
        return True
        
    except Exception as e:
        print(f"❌ Response enhancer test failed: {e}")
        return False

async def test_chat_response_enhancement():
    """Test chat response enhancement."""
    print("\n🧪 Testing Chat Response Enhancement...")
    
    try:
        from src.retrieval.response_quality.response_enhancer import get_response_enhancer
        from src.retrieval.response_quality.response_validator import UserRole
        
        # Initialize enhancer
        enhancer = await get_response_enhancer()
        
        # Test chat response enhancement
        chat_response = await enhancer.enhance_chat_response(
            response_text="We have 6 active workers currently on shift.",
            agent_name="Operations Agent",
            user_role=UserRole.OPERATOR,
            query_context={"intent": "workforce", "route": "sql"},
            evidence_data={
                "evidence_score": {"overall_score": 0.9},
                "sources": [
                    {"type": "database", "name": "PostgreSQL", "confidence": 0.95}
                ]
            }
        )
        
        print("📱 Chat Response Enhancement:")
        print(f"Response: {chat_response['response']}")
        print(f"Quality Control: {chat_response['quality_control']}")
        print(f"User Experience: {chat_response['user_experience']}")
        print(f"Source Attribution: {len(chat_response['source_attribution'])} sources")
        
        if chat_response['warnings']:
            print(f"Warnings: {chat_response['warnings']}")
        
        if chat_response['suggestions']:
            print(f"Suggestions: {chat_response['suggestions']}")
        
        return True
        
    except Exception as e:
        print(f"❌ Chat response enhancement test failed: {e}")
        return False

async def test_ux_analytics():
    """Test UX analytics functionality."""
    print("\n🧪 Testing UX Analytics...")
    
    try:
        from src.retrieval.response_quality.ux_analytics import (
            UXAnalyticsService, MetricType, get_ux_analytics
        )
        from src.retrieval.response_quality.response_validator import UserRole
        
        # Initialize analytics
        analytics = await get_ux_analytics()
        
        # Record some sample metrics
        sample_metrics = [
            (MetricType.CONFIDENCE, 0.85, UserRole.OPERATOR, "Operations Agent", "workforce"),
            (MetricType.COMPLETENESS, 0.90, UserRole.OPERATOR, "Operations Agent", "workforce"),
            (MetricType.CONSISTENCY, 0.88, UserRole.OPERATOR, "Operations Agent", "workforce"),
            (MetricType.USER_SATISFACTION, 0.92, UserRole.OPERATOR, "Operations Agent", "workforce"),
            (MetricType.CONFIDENCE, 0.75, UserRole.SUPERVISOR, "Operations Agent", "task_management"),
            (MetricType.COMPLETENESS, 0.80, UserRole.SUPERVISOR, "Operations Agent", "task_management"),
            (MetricType.CONSISTENCY, 0.82, UserRole.SUPERVISOR, "Operations Agent", "task_management"),
            (MetricType.USER_SATISFACTION, 0.85, UserRole.SUPERVISOR, "Operations Agent", "task_management"),
            (MetricType.CONFIDENCE, 0.95, UserRole.MANAGER, "Equipment Agent", "equipment_lookup"),
            (MetricType.COMPLETENESS, 0.88, UserRole.MANAGER, "Equipment Agent", "equipment_lookup"),
            (MetricType.CONSISTENCY, 0.90, UserRole.MANAGER, "Equipment Agent", "equipment_lookup"),
            (MetricType.USER_SATISFACTION, 0.95, UserRole.MANAGER, "Equipment Agent", "equipment_lookup"),
        ]
        
        # Record metrics
        for metric_type, value, user_role, agent_name, query_intent in sample_metrics:
            await analytics.record_metric(
                metric_type=metric_type,
                value=value,
                user_role=user_role,
                agent_name=agent_name,
                query_intent=query_intent,
                session_id="demo_session_001"
            )
        
        print(f"📊 Recorded {len(sample_metrics)} metrics")
        
        # Generate trend analysis
        print("\n📈 Trend Analysis:")
        for metric_type in MetricType:
            trend = await analytics.generate_trend_analysis(metric_type, "hour", 1)
            print(f"{metric_type.value}: {trend.trend_direction} ({trend.trend_strength:.2f}) - {trend.current_average:.2f}")
        
        # Generate UX report
        print("\n📋 User Experience Report:")
        report = await analytics.generate_user_experience_report(hours=1)
        print(f"Overall Score: {report.overall_score:.2f}")
        print(f"Report Period: {report.report_period}")
        print(f"Role Performance: {report.role_performance}")
        print(f"Agent Performance: {report.agent_performance}")
        print(f"Intent Performance: {report.intent_performance}")
        
        if report.recommendations:
            print(f"Recommendations: {report.recommendations}")
        
        if report.key_insights:
            print(f"Key Insights: {report.key_insights}")
        
        # Get session analytics
        print("\n🔍 Session Analytics:")
        session_analytics = await analytics.get_session_analytics("demo_session_001")
        print(f"Session: {session_analytics.get('session_id', 'Unknown')}")
        print(f"Total Queries: {session_analytics.get('total_queries', 0)}")
        print(f"Statistics: {session_analytics.get('statistics', {})}")
        
        return True
        
    except Exception as e:
        print(f"❌ UX analytics test failed: {e}")
        return False

async def main():
    """Run all response quality control tests."""
    print("🚀 Starting Response Quality Control Demo for Warehouse Operational Assistant")
    print("=" * 80)
    
    test_results = []
    
    # Test Response Validator
    result1 = await test_response_validator()
    test_results.append(("Response Validator", result1))
    
    # Test Response Enhancer
    result2 = await test_response_enhancer()
    test_results.append(("Response Enhancer", result2))
    
    # Test Chat Response Enhancement
    result3 = await test_chat_response_enhancement()
    test_results.append(("Chat Response Enhancement", result3))
    
    # Test UX Analytics
    result4 = await test_ux_analytics()
    test_results.append(("UX Analytics", result4))
    
    # Print summary
    print("\n" + "=" * 80)
    print("📋 Test Results Summary:")
    print("=" * 80)
    
    passed = 0
    for test_name, result in test_results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall: {passed}/{len(test_results)} tests passed")
    
    if passed == len(test_results):
        print("🎉 All response quality control tests passed! The system is working correctly.")
    else:
        print("⚠️ Some tests failed. Check the logs above for details.")
    
    print("\n💡 Key Features Demonstrated:")
    print("• Response validation against evidence quality")
    print("• Source attribution and confidence indicators")
    print("• User role-based personalization")
    print("• Response consistency and completeness checks")
    print("• Follow-up suggestions generation")
    print("• User experience analytics and reporting")
    print("• Real-time performance monitoring")
    print("• Automated recommendations generation")

if __name__ == "__main__":
    asyncio.run(main())
