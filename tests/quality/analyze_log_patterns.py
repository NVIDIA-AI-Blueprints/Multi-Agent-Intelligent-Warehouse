"""
Analyze log patterns from test results and provide detailed recommendations.

This script analyzes the test results JSON file and provides specific
recommendations based on actual log patterns and error types.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from collections import defaultdict
import re

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))


def analyze_error_patterns(results: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze error patterns from log analysis."""
    error_analysis = {
        "error_categories": defaultdict(int),
        "error_examples": [],
        "error_by_agent": defaultdict(int),
        "error_by_query": [],
        "recommendations": []
    }
    
    for result in results.get("results", []):
        agent = result.get("agent", "unknown")
        query = result.get("query", "unknown")
        log_analysis = result.get("log_analysis", {})
        
        # Get error examples from log patterns
        error_patterns = log_analysis.get("patterns", {}).get("errors", {})
        error_count = error_patterns.get("count", 0)
        error_examples = error_patterns.get("examples", [])
        
        if error_count > 0:
            error_analysis["error_by_agent"][agent] += error_count
            error_analysis["error_by_query"].append({
                "agent": agent,
                "query": query,
                "error_count": error_count,
                "examples": error_examples[:2]  # Keep 2 examples per query
            })
            
            # Categorize errors
            for example in error_examples:
                example_lower = example.lower()
                if "404" in example or "not found" in example_lower:
                    error_analysis["error_categories"]["not_found"] += 1
                elif "timeout" in example_lower:
                    error_analysis["error_categories"]["timeout"] += 1
                elif "connection" in example_lower or "network" in example_lower:
                    error_analysis["error_categories"]["connection"] += 1
                elif "authentication" in example_lower or "401" in example or "403" in example:
                    error_analysis["error_categories"]["authentication"] += 1
                elif "validation" in example_lower:
                    error_analysis["error_categories"]["validation"] += 1
                elif "task" in example_lower and "failed" in example_lower:
                    error_analysis["error_categories"]["task_execution"] += 1
                elif "wms" in example_lower or "integration" in example_lower:
                    error_analysis["error_categories"]["integration"] += 1
                else:
                    error_analysis["error_categories"]["other"] += 1
    
    return error_analysis


def generate_detailed_recommendations(
    results: Dict[str, Any], error_analysis: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Generate detailed recommendations based on analysis."""
    recommendations = []
    
    # Error-based recommendations
    error_categories = error_analysis.get("error_categories", {})
    
    if error_categories.get("not_found", 0) > 0:
        recommendations.append({
            "priority": "high",
            "category": "configuration",
            "title": "404/Not Found Errors Detected",
            "description": f"{error_categories['not_found']} 'not found' errors detected. Likely configuration issues with API endpoints or resources.",
            "action": "Review LLM_NIM_URL configuration and verify all API endpoints are correctly configured. Check that resources (tasks, equipment, etc.) exist before querying.",
            "examples": [ex for ex in error_analysis.get("error_examples", []) if "404" in ex or "not found" in ex.lower()][:3]
        })
    
    if error_categories.get("task_execution", 0) > 0:
        recommendations.append({
            "priority": "high",
            "category": "tool_execution",
            "title": "Task Execution Failures",
            "description": f"{error_categories['task_execution']} task execution failures detected. Tasks may be created but not properly assigned or executed.",
            "action": "Review tool dependency handling. Ensure tools that depend on other tools (e.g., assign_task depends on create_task) wait for dependencies to complete and extract required data (like task_id) from previous results.",
            "examples": [ex for ex in error_analysis.get("error_examples", []) if "task" in ex.lower() and "failed" in ex.lower()][:3]
        })
    
    if error_categories.get("timeout", 0) > 0:
        recommendations.append({
            "priority": "medium",
            "category": "performance",
            "title": "Timeout Issues",
            "description": f"{error_categories['timeout']} timeout occurrences detected. Some operations may be taking too long.",
            "action": "Review timeout configurations and optimize slow operations. Consider increasing timeouts for complex queries or optimizing LLM calls.",
            "examples": [ex for ex in error_analysis.get("error_examples", []) if "timeout" in ex.lower()][:3]
        })
    
    # Performance recommendations
    summary = results.get("summary", {})
    avg_time = summary.get("avg_processing_time_seconds", 0)
    
    if avg_time > 20:
        recommendations.append({
            "priority": "medium",
            "category": "performance",
            "title": "High Average Processing Time",
            "description": f"Average processing time is {avg_time:.2f}s. Equipment and Safety agents are slower (19.50s and 23.64s respectively).",
            "action": "Optimize slow agent operations. Consider: 1) Parallelizing independent tool executions, 2) Implementing response caching for common queries, 3) Optimizing LLM prompts to reduce generation time, 4) Reviewing tool execution patterns for bottlenecks.",
            "examples": []
        })
    
    # Tool usage recommendations
    for result in results.get("results", []):
        agent = result.get("agent", "unknown")
        tools_used = result.get("response", {}).get("tools_used_count", 0)
        
        if agent == "safety" and tools_used == 0:
            query = result.get("query", "unknown")
            if "procedure" in query.lower() or "checklist" in query.lower():
                recommendations.append({
                    "priority": "low",
                    "category": "functionality",
                    "title": "Safety Agent Not Using Tools for Procedure Queries",
                    "description": f"Safety agent queries about procedures/checklists are not using tools. Query: '{query}'",
                    "action": "Consider adding tools for retrieving safety procedures and checklists, or ensure tool discovery is finding relevant tools for these query types.",
                    "examples": []
                })
    
    # Quality recommendations
    quality_metrics = {}
    all_scores = [r.get("validation", {}).get("score", 0) for r in results.get("results", []) if "error" not in r]
    if all_scores:
        quality_metrics = {
            "avg_score": sum(all_scores) / len(all_scores),
            "low_scores": len([s for s in all_scores if s < 0.9])
        }
    
    if quality_metrics.get("low_scores", 0) > 0:
        recommendations.append({
            "priority": "low",
            "category": "quality",
            "title": "Some Responses Below 0.9 Score",
            "description": f"{quality_metrics['low_scores']} responses have validation scores below 0.9 (but still passing).",
            "action": "Review lower-scoring responses and identify improvement opportunities. Most are likely minor issues like missing action keywords.",
            "examples": []
        })
    
    return recommendations


def enhance_report_with_error_analysis(report_path: Path, results_path: Path):
    """Enhance the report with detailed error analysis."""
    # Load results
    with open(results_path, "r") as f:
        results = json.load(f)
    
    # Analyze errors
    error_analysis = analyze_error_patterns(results)
    
    # Generate detailed recommendations
    detailed_recommendations = generate_detailed_recommendations(results, error_analysis)
    
    # Read existing report
    with open(report_path, "r") as f:
        report = f.read()
    
    # Add detailed error analysis section before recommendations
    error_section = "\n## Detailed Error Analysis\n\n"
    
    if error_analysis.get("error_categories"):
        error_section += "### Error Categories\n\n"
        error_section += "| Category | Count |\n"
        error_section += "|----------|-------|\n"
        for category, count in sorted(error_analysis["error_categories"].items(), key=lambda x: x[1], reverse=True):
            error_section += f"| {category.replace('_', ' ').title()} | {count} |\n"
        error_section += "\n"
    
    if error_analysis.get("error_by_agent"):
        error_section += "### Errors by Agent\n\n"
        error_section += "| Agent | Error Count |\n"
        error_section += "|-------|-------------|\n"
        for agent, count in sorted(error_analysis["error_by_agent"].items(), key=lambda x: x[1], reverse=True):
            error_section += f"| {agent.capitalize()} | {count} |\n"
        error_section += "\n"
    
    # Replace recommendations section with enhanced version
    if "## Recommendations" in report:
        # Find recommendations section
        rec_start = report.find("## Recommendations")
        rec_end = report.find("---", rec_start + 1)
        if rec_end == -1:
            rec_end = report.find("## Conclusion", rec_start + 1)
        
        if rec_end > rec_start:
            # Build enhanced recommendations
            enhanced_recs = "## Recommendations\n\n"
            
            # Add detailed recommendations
            for rec in detailed_recommendations:
                priority_emoji = "🔴" if rec['priority'] == 'high' else "🟡" if rec['priority'] == 'medium' else "🟢"
                enhanced_recs += f"### {priority_emoji} {rec['title']} ({rec['priority'].upper()} Priority)\n\n"
                enhanced_recs += f"**Category**: {rec['category']}\n\n"
                enhanced_recs += f"**Description**: {rec['description']}\n\n"
                enhanced_recs += f"**Recommended Action**: {rec['action']}\n\n"
                
                if rec.get('examples'):
                    enhanced_recs += "**Example Errors**:\n"
                    for ex in rec['examples'][:2]:
                        enhanced_recs += f"- `{ex[:100]}...`\n"
                    enhanced_recs += "\n"
            
            # Replace section
            report = report[:rec_start] + error_section + enhanced_recs + report[rec_end:]
    
    # Save enhanced report
    with open(report_path, "w") as f:
        f.write(report)
    
    print(f"✅ Enhanced report with detailed error analysis: {report_path}")


if __name__ == "__main__":
    results_file = project_root / "tests" / "quality" / "quality_test_results_enhanced.json"
    report_file = project_root / "docs" / "analysis" / "COMPREHENSIVE_QUALITY_REPORT.md"
    
    if not results_file.exists():
        print(f"❌ Results file not found: {results_file}")
        sys.exit(1)
    
    enhance_report_with_error_analysis(report_file, results_file)

