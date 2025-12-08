"""
Generate comprehensive quality report from test results.

Analyzes test results and generates a detailed markdown report with insights and recommendations.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def load_test_results() -> Dict[str, Any]:
    """Load test results from JSON file."""
    results_file = project_root / "tests" / "quality" / "quality_test_results_enhanced.json"
    
    if not results_file.exists():
        print(f"❌ Results file not found: {results_file}")
        print("   Please run tests/quality/test_answer_quality_enhanced.py first")
        sys.exit(1)
    
    with open(results_file, "r") as f:
        return json.load(f)


def analyze_results(results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze test results and extract insights."""
    analysis = {
        "summary": results.get("summary", {}),
        "agent_breakdown": {},
        "log_insights": {},
        "performance_metrics": {},
        "quality_metrics": {},
        "issues": [],
        "recommendations": []
    }
    
    # Agent breakdown
    agent_stats = defaultdict(lambda: {
        "tests": 0,
        "successful": 0,
        "valid": 0,
        "scores": [],
        "confidences": [],
        "processing_times": [],
        "tools_used": [],
        "errors": 0,
        "warnings": 0
    })
    
    for result in results.get("results", []):
        agent = result.get("agent", "unknown")
        stats = agent_stats[agent]
        stats["tests"] += 1
        
        if "error" not in result:
            stats["successful"] += 1
            
            validation = result.get("validation", {})
            if validation.get("is_valid", False):
                stats["valid"] += 1
            
            stats["scores"].append(validation.get("score", 0))
            stats["confidences"].append(result.get("response", {}).get("confidence", 0))
            stats["processing_times"].append(result.get("processing_time_seconds", 0))
            stats["tools_used"].append(result.get("response", {}).get("tools_used_count", 0))
            
            # Count errors and warnings from log analysis
            log_analysis = result.get("log_analysis", {})
            patterns = log_analysis.get("patterns", {})
            stats["errors"] += patterns.get("errors", {}).get("count", 0)
            stats["warnings"] += patterns.get("warnings", {}).get("count", 0)
    
    # Calculate averages
    for agent, stats in agent_stats.items():
        analysis["agent_breakdown"][agent] = {
            "tests": stats["tests"],
            "successful": stats["successful"],
            "valid": stats["valid"],
            "valid_percentage": (stats["valid"] / stats["successful"] * 100) if stats["successful"] > 0 else 0,
            "avg_score": sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0,
            "avg_confidence": sum(stats["confidences"]) / len(stats["confidences"]) if stats["confidences"] else 0,
            "avg_processing_time": sum(stats["processing_times"]) / len(stats["processing_times"]) if stats["processing_times"] else 0,
            "avg_tools_used": sum(stats["tools_used"]) / len(stats["tools_used"]) if stats["tools_used"] else 0,
            "total_errors": stats["errors"],
            "total_warnings": stats["warnings"]
        }
    
    # Log insights
    log_analysis = results.get("log_analysis", {})
    analysis["log_insights"] = {
        "aggregate_patterns": log_analysis.get("aggregate_patterns", {}),
        "insights": log_analysis.get("insights", []),
        "recommendations": log_analysis.get("recommendations", [])
    }
    
    # Performance metrics
    all_times = [r.get("processing_time_seconds", 0) for r in results.get("results", []) if "error" not in r]
    if all_times:
        analysis["performance_metrics"] = {
            "avg_time": sum(all_times) / len(all_times),
            "min_time": min(all_times),
            "max_time": max(all_times),
            "p95_time": sorted(all_times)[int(len(all_times) * 0.95)] if len(all_times) > 0 else 0
        }
    
    # Quality metrics
    all_scores = [r.get("validation", {}).get("score", 0) for r in results.get("results", []) if "error" not in r]
    if all_scores:
        analysis["quality_metrics"] = {
            "avg_score": sum(all_scores) / len(all_scores),
            "min_score": min(all_scores),
            "max_score": max(all_scores),
            "perfect_scores": len([s for s in all_scores if s >= 1.0]),
            "high_scores": len([s for s in all_scores if s >= 0.9]),
            "low_scores": len([s for s in all_scores if s < 0.7])
        }
    
    # Identify issues
    for result in results.get("results", []):
        if "error" in result:
            analysis["issues"].append({
                "type": "error",
                "agent": result.get("agent"),
                "query": result.get("query"),
                "error": result.get("error")
            })
        
        validation = result.get("validation", {})
        if not validation.get("is_valid", False):
            analysis["issues"].append({
                "type": "validation_failure",
                "agent": result.get("agent"),
                "query": result.get("query"),
                "score": validation.get("score", 0),
                "issues": validation.get("issues", [])
            })
    
    # Generate recommendations
    analysis["recommendations"] = generate_recommendations(analysis)
    
    return analysis


def generate_recommendations(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate recommendations based on analysis."""
    recommendations = []
    
    # Performance recommendations
    perf_metrics = analysis.get("performance_metrics", {})
    if perf_metrics.get("avg_time", 0) > 30:
        recommendations.append({
            "priority": "high",
            "category": "performance",
            "title": "High Average Processing Time",
            "description": f"Average processing time is {perf_metrics['avg_time']:.2f}s, which exceeds the 30s threshold.",
            "action": "Optimize slow operations, implement caching, or parallelize independent operations"
        })
    
    if perf_metrics.get("p95_time", 0) > 60:
        recommendations.append({
            "priority": "high",
            "category": "performance",
            "title": "High P95 Processing Time",
            "description": f"P95 processing time is {perf_metrics['p95_time']:.2f}s, indicating some queries are very slow.",
            "action": "Identify and optimize slow query patterns"
        })
    
    # Quality recommendations
    quality_metrics = analysis.get("quality_metrics", {})
    if quality_metrics.get("low_scores", 0) > 0:
        recommendations.append({
            "priority": "medium",
            "category": "quality",
            "title": "Low Quality Responses Detected",
            "description": f"{quality_metrics['low_scores']} responses have validation scores below 0.7.",
            "action": "Review low-scoring responses and improve prompt engineering or response generation"
        })
    
    # Error recommendations
    log_patterns = analysis.get("log_insights", {}).get("aggregate_patterns", {})
    if log_patterns.get("errors", 0) > 20:
        recommendations.append({
            "priority": "high",
            "category": "reliability",
            "title": "High Error Rate",
            "description": f"{log_patterns['errors']} errors detected in logs. Review error patterns.",
            "action": "Analyze error logs and improve error handling and recovery mechanisms"
        })
    
    # Tool usage recommendations
    for agent, stats in analysis.get("agent_breakdown", {}).items():
        if stats.get("avg_tools_used", 0) == 0:
            recommendations.append({
                "priority": "medium",
                "category": "functionality",
                "title": f"No Tools Used in {agent.capitalize()} Agent",
                "description": f"{agent.capitalize()} agent is not using any tools.",
                "action": "Verify tool discovery and ensure tools are being called appropriately"
            })
    
    return recommendations


def generate_markdown_report(analysis: Dict[str, Any], results: Dict[str, Any]) -> str:
    """Generate comprehensive markdown report."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    report = f"""# Comprehensive Quality Assessment Report

**Generated**: {timestamp}  
**Test Script**: `tests/quality/test_answer_quality_enhanced.py`  
**Report Type**: Enhanced Quality Assessment with Log Analysis

---

## Executive Summary

### Overall Performance

| Metric | Value | Status |
|--------|-------|--------|
| **Total Tests** | {results['summary']['total_tests']} | - |
| **Successful Tests** | {results['summary']['successful_tests']} ({results['summary']['successful_tests']/results['summary']['total_tests']*100:.1f}%) | {'✅' if results['summary']['successful_tests'] == results['summary']['total_tests'] else '⚠️'} |
| **Valid Responses** | {results['summary']['valid_responses']} ({results['summary']['valid_responses']/results['summary']['successful_tests']*100:.1f}%) | {'✅' if results['summary']['valid_responses'] == results['summary']['successful_tests'] else '⚠️'} |
| **Average Validation Score** | {results['summary']['avg_validation_score']:.2f} | {'✅' if results['summary']['avg_validation_score'] >= 0.9 else '⚠️'} |
| **Average Confidence** | {results['summary']['avg_confidence']:.2f} | {'✅' if results['summary']['avg_confidence'] >= 0.8 else '⚠️'} |
| **Average Processing Time** | {results['summary']['avg_processing_time_seconds']:.2f}s | {'✅' if results['summary']['avg_processing_time_seconds'] < 30 else '⚠️'} |

### Key Achievements

"""
    
    # Add achievements
    if results['summary']['valid_responses'] == results['summary']['successful_tests']:
        report += "- ✅ **100% Valid Responses** - All responses pass validation\n"
    
    if results['summary']['avg_validation_score'] >= 0.95:
        report += "- ✅ **Excellent Quality Scores** - Average validation score above 0.95\n"
    
    if results['summary']['avg_confidence'] >= 0.9:
        report += "- ✅ **High Confidence** - Average confidence above 0.9\n"
    
    report += "\n---\n\n## Agent Performance Breakdown\n\n"
    
    # Agent breakdown
    for agent, stats in analysis['agent_breakdown'].items():
        report += f"### {agent.capitalize()} Agent\n\n"
        report += f"| Metric | Value | Status |\n"
        report += f"|--------|-------|--------|\n"
        report += f"| Tests | {stats['tests']} | - |\n"
        report += f"| Successful | {stats['successful']} | {'✅' if stats['successful'] == stats['tests'] else '⚠️'} |\n"
        report += f"| Valid Responses | {stats['valid']} ({stats['valid_percentage']:.1f}%) | {'✅' if stats['valid_percentage'] == 100 else '⚠️'} |\n"
        report += f"| Avg Validation Score | {stats['avg_score']:.2f} | {'✅' if stats['avg_score'] >= 0.9 else '⚠️'} |\n"
        report += f"| Avg Confidence | {stats['avg_confidence']:.2f} | {'✅' if stats['avg_confidence'] >= 0.8 else '⚠️'} |\n"
        report += f"| Avg Processing Time | {stats['avg_processing_time']:.2f}s | {'✅' if stats['avg_processing_time'] < 30 else '⚠️'} |\n"
        report += f"| Avg Tools Used | {stats['avg_tools_used']:.1f} | - |\n"
        report += f"| Total Errors (Logs) | {stats['total_errors']} | {'✅' if stats['total_errors'] == 0 else '⚠️'} |\n"
        report += f"| Total Warnings (Logs) | {stats['total_warnings']} | {'✅' if stats['total_warnings'] == 0 else '⚠️'} |\n"
        report += "\n"
    
    # Performance metrics
    report += "---\n\n## Performance Metrics\n\n"
    perf = analysis.get('performance_metrics', {})
    if perf:
        report += f"| Metric | Value |\n"
        report += f"|--------|-------|\n"
        report += f"| Average Processing Time | {perf.get('avg_time', 0):.2f}s |\n"
        report += f"| Minimum Processing Time | {perf.get('min_time', 0):.2f}s |\n"
        report += f"| Maximum Processing Time | {perf.get('max_time', 0):.2f}s |\n"
        report += f"| P95 Processing Time | {perf.get('p95_time', 0):.2f}s |\n"
        report += "\n"
    
    # Quality metrics
    report += "---\n\n## Quality Metrics\n\n"
    quality = analysis.get('quality_metrics', {})
    if quality:
        report += f"| Metric | Value |\n"
        report += f"|--------|-------|\n"
        report += f"| Average Validation Score | {quality.get('avg_score', 0):.2f} |\n"
        report += f"| Minimum Score | {quality.get('min_score', 0):.2f} |\n"
        report += f"| Maximum Score | {quality.get('max_score', 0):.2f} |\n"
        report += f"| Perfect Scores (1.0) | {quality.get('perfect_scores', 0)} |\n"
        report += f"| High Scores (≥0.9) | {quality.get('high_scores', 0)} |\n"
        report += f"| Low Scores (<0.7) | {quality.get('low_scores', 0)} |\n"
        report += "\n"
    
    # Log analysis
    report += "---\n\n## Log Analysis Insights\n\n"
    log_insights = analysis.get('log_insights', {})
    
    if log_insights.get('aggregate_patterns'):
        report += "### Aggregate Log Patterns\n\n"
        report += "| Pattern | Count |\n"
        report += "|---------|-------|\n"
        for pattern, count in sorted(log_insights['aggregate_patterns'].items(), key=lambda x: x[1], reverse=True):
            report += f"| {pattern} | {count} |\n"
        report += "\n"
    
    if log_insights.get('insights'):
        report += "### Key Insights\n\n"
        for insight in log_insights['insights'][:10]:  # Top 10 insights
            report += f"- {insight}\n"
        report += "\n"
    
    # Issues
    if analysis.get('issues'):
        report += "---\n\n## Issues Identified\n\n"
        for issue in analysis['issues'][:10]:  # Top 10 issues
            report += f"### {issue.get('type', 'unknown').replace('_', ' ').title()}\n\n"
            report += f"- **Agent**: {issue.get('agent', 'unknown')}\n"
            report += f"- **Query**: {issue.get('query', 'unknown')}\n"
            if issue.get('error'):
                report += f"- **Error**: {issue['error']}\n"
            if issue.get('score'):
                report += f"- **Score**: {issue['score']:.2f}\n"
            report += "\n"
    
    # Recommendations
    if analysis.get('recommendations'):
        report += "---\n\n## Recommendations\n\n"
        for rec in analysis['recommendations']:
            priority_emoji = "🔴" if rec['priority'] == 'high' else "🟡" if rec['priority'] == 'medium' else "🟢"
            report += f"### {priority_emoji} {rec['title']} ({rec['priority'].upper()} Priority)\n\n"
            report += f"**Category**: {rec['category']}\n\n"
            report += f"**Description**: {rec['description']}\n\n"
            report += f"**Recommended Action**: {rec['action']}\n\n"
    
    report += "---\n\n## Conclusion\n\n"
    
    # Overall assessment
    if results['summary']['valid_responses'] == results['summary']['successful_tests']:
        report += "✅ **All responses are valid and passing validation!**\n\n"
    
    if results['summary']['avg_validation_score'] >= 0.95:
        report += "✅ **Excellent quality scores achieved across all agents!**\n\n"
    
    if results['summary']['avg_processing_time_seconds'] < 30:
        report += "✅ **Processing times are within acceptable limits!**\n\n"
    else:
        report += "⚠️ **Processing times exceed recommended thresholds. Consider optimization.**\n\n"
    
    report += f"\n**Report Generated**: {timestamp}\n"
    report += f"**Test Duration**: See individual test results\n"
    report += f"**Status**: {'✅ All Tests Passing' if results['summary']['failed_tests'] == 0 else '⚠️ Some Tests Failed'}\n"
    
    return report


def main():
    """Main function to generate report."""
    print("📊 Loading test results...")
    results = load_test_results()
    
    print("🔍 Analyzing results...")
    analysis = analyze_results(results)
    
    print("📝 Generating markdown report...")
    report = generate_markdown_report(analysis, results)
    
    # Save report
    report_file = project_root / "docs" / "analysis" / "COMPREHENSIVE_QUALITY_REPORT.md"
    report_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(report_file, "w") as f:
        f.write(report)
    
    print(f"✅ Report generated: {report_file}")
    print(f"\n📊 Summary:")
    print(f"   Total Tests: {results['summary']['total_tests']}")
    print(f"   Valid Responses: {results['summary']['valid_responses']}/{results['summary']['successful_tests']}")
    print(f"   Avg Score: {results['summary']['avg_validation_score']:.2f}")
    print(f"   Avg Time: {results['summary']['avg_processing_time_seconds']:.2f}s")
    print(f"   Recommendations: {len(analysis['recommendations'])}")


if __name__ == "__main__":
    main()

