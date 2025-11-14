#!/usr/bin/env python3
"""
Test script to demonstrate Evidence Scoring and Clarifying Questions functionality.

This script shows how the new evidence scoring system and clarifying questions
engine work together to provide confidence assessment and intelligent questioning.
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.retrieval.vector.evidence_scoring import (
    EvidenceScoringEngine, EvidenceSource, EvidenceItem, EvidenceScore
)
from src.retrieval.vector.clarifying_questions import (
    ClarifyingQuestionsEngine, QuestionSet, AmbiguityType, QuestionPriority
)

async def test_evidence_scoring():
    """Test the evidence scoring system."""
    print("🔍 Testing Evidence Scoring System")
    print("=" * 50)
    
    # Initialize evidence scoring engine
    evidence_engine = EvidenceScoringEngine()
    
    # Create sample evidence sources
    sources = [
        EvidenceSource(
            source_id="manual_001",
            source_type="official_manual",
            authority_level=1.0,
            freshness_score=0.9,
            content_quality=0.95,
            last_updated=datetime.now(timezone.utc),
            source_credibility=1.0
        ),
        EvidenceSource(
            source_id="sop_002",
            source_type="sop",
            authority_level=0.95,
            freshness_score=0.8,
            content_quality=0.85,
            last_updated=datetime(2024, 1, 1, tzinfo=timezone.utc),
            source_credibility=0.95
        ),
        EvidenceSource(
            source_id="wiki_003",
            source_type="wiki",
            authority_level=0.6,
            freshness_score=0.7,
            content_quality=0.6,
            last_updated=datetime(2024, 6, 1, tzinfo=timezone.utc),
            source_credibility=0.6
        )
    ]
    
    # Create sample evidence items
    evidence_items = [
        EvidenceItem(
            content="Forklift safety procedures require daily inspection of brakes, steering, and hydraulic systems. All operators must complete safety training before operation.",
            source=sources[0],
            similarity_score=0.92,
            relevance_score=0.88,
            cross_references=["sop_002"],
            keywords=["forklift", "safety", "inspection", "training"],
            metadata={"category": "safety", "priority": "high"}
        ),
        EvidenceItem(
            content="Daily forklift inspection checklist: 1. Check brake function 2. Test steering response 3. Inspect hydraulic leaks 4. Verify safety equipment",
            source=sources[1],
            similarity_score=0.85,
            relevance_score=0.82,
            cross_references=["manual_001"],
            keywords=["forklift", "inspection", "checklist", "daily"],
            metadata={"category": "procedure", "priority": "high"}
        ),
        EvidenceItem(
            content="Some users report that forklift maintenance can be tricky. Make sure to check the manual for specific instructions.",
            source=sources[2],
            similarity_score=0.65,
            relevance_score=0.60,
            cross_references=[],
            keywords=["forklift", "maintenance", "manual"],
            metadata={"category": "user_generated", "priority": "low"}
        )
    ]
    
    # Calculate evidence score
    evidence_score = evidence_engine.calculate_evidence_score(evidence_items)
    
    print(f"📊 Evidence Scoring Results:")
    print(f"   Overall Score: {evidence_score.overall_score:.3f}")
    print(f"   Similarity Component: {evidence_score.similarity_component:.3f}")
    print(f"   Authority Component: {evidence_score.authority_component:.3f}")
    print(f"   Freshness Component: {evidence_score.freshness_component:.3f}")
    print(f"   Cross-Reference Component: {evidence_score.cross_reference_component:.3f}")
    print(f"   Source Diversity Score: {evidence_score.source_diversity_score:.3f}")
    print(f"   Confidence Level: {evidence_score.confidence_level}")
    print(f"   Evidence Quality: {evidence_score.evidence_quality}")
    print(f"   Validation Status: {evidence_score.validation_status}")
    print(f"   Sources Count: {evidence_score.sources_count}")
    print(f"   Distinct Sources: {evidence_score.distinct_sources}")
    
    return evidence_score

async def test_clarifying_questions():
    """Test the clarifying questions engine."""
    print("\n❓ Testing Clarifying Questions Engine")
    print("=" * 50)
    
    # Initialize clarifying questions engine
    questions_engine = ClarifyingQuestionsEngine()
    
    # Test different query scenarios
    test_queries = [
        {
            "query": "What equipment do we have?",
            "evidence_score": 0.25,
            "query_type": "equipment",
            "context": {"user_role": "operator"}
        },
        {
            "query": "Show me safety procedures",
            "evidence_score": 0.45,
            "query_type": "safety",
            "context": {"location": "warehouse_a"}
        },
        {
            "query": "How many SKU123 are available?",
            "evidence_score": 0.15,
            "query_type": "equipment",
            "context": {"urgency": "high"}
        },
        {
            "query": "What are the main tasks today?",
            "evidence_score": 0.75,
            "query_type": "operations",
            "context": {"shift": "morning"}
        }
    ]
    
    for i, test_case in enumerate(test_queries, 1):
        print(f"\n🔍 Test Case {i}: {test_case['query']}")
        print(f"   Evidence Score: {test_case['evidence_score']}")
        print(f"   Query Type: {test_case['query_type']}")
        
        # Generate clarifying questions
        question_set = questions_engine.generate_questions(
            query=test_case["query"],
            evidence_score=test_case["evidence_score"],
            query_type=test_case["query_type"],
            context=test_case["context"]
        )
        
        print(f"   Confidence Level: {question_set.confidence_level}")
        print(f"   Estimated Completion Time: {question_set.estimated_completion_time}")
        print(f"   Total Priority Score: {question_set.total_priority_score}")
        print(f"   Questions Generated: {len(question_set.questions)}")
        
        for j, question in enumerate(question_set.questions, 1):
            print(f"     {j}. [{question.priority.value.upper()}] {question.question}")
            print(f"        Type: {question.ambiguity_type.value}")
            print(f"        Expected Answer: {question.expected_answer_type}")
            if question.follow_up_questions:
                print(f"        Follow-ups: {', '.join(question.follow_up_questions)}")

async def test_integrated_workflow():
    """Test the integrated workflow of evidence scoring and clarifying questions."""
    print("\n🔄 Testing Integrated Workflow")
    print("=" * 50)
    
    # Initialize both engines
    evidence_engine = EvidenceScoringEngine()
    questions_engine = ClarifyingQuestionsEngine()
    
    # Simulate a low-confidence search scenario
    query = "What equipment is available for maintenance?"
    evidence_score = 0.28  # Low confidence
    
    print(f"Query: {query}")
    print(f"Evidence Score: {evidence_score}")
    
    # Generate clarifying questions
    question_set = questions_engine.generate_questions(
        query=query,
        evidence_score=evidence_score,
        query_type="equipment",
        context={"maintenance_type": "preventive"}
    )
    
    print(f"\n📋 Clarifying Questions Generated:")
    print(f"   Confidence Level: {question_set.confidence_level}")
    print(f"   Questions Count: {len(question_set.questions)}")
    
    for i, question in enumerate(question_set.questions, 1):
        print(f"\n   {i}. {question.question}")
        print(f"      Priority: {question.priority.value}")
        print(f"      Ambiguity Type: {question.ambiguity_type.value}")
        print(f"      Context: {question.context}")
    
    # Simulate user responses and re-evaluation
    print(f"\n🔄 Simulating User Responses...")
    
    # Simulate high-quality response
    improved_query = "What forklifts are available for preventive maintenance in Zone A?"
    improved_evidence_score = 0.85  # High confidence after clarification
    
    print(f"Improved Query: {improved_query}")
    print(f"Improved Evidence Score: {improved_evidence_score}")
    
    # Check if clarifying questions are still needed
    if improved_evidence_score >= 0.35:
        print("✅ No more clarifying questions needed - sufficient evidence!")
    else:
        print("❌ Still need more clarification")

async def main():
    """Main test function."""
    print("🚀 Evidence Scoring and Clarifying Questions Demo")
    print("=" * 60)
    
    try:
        # Test evidence scoring
        evidence_score = await test_evidence_scoring()
        
        # Test clarifying questions
        await test_clarifying_questions()
        
        # Test integrated workflow
        await test_integrated_workflow()
        
        print("\n✅ All tests completed successfully!")
        print("\n📈 Key Features Demonstrated:")
        print("   • Evidence scoring with multiple factors")
        print("   • Source authority and credibility assessment")
        print("   • Content freshness and quality evaluation")
        print("   • Cross-reference validation")
        print("   • Source diversity scoring")
        print("   • Intelligent clarifying questions generation")
        print("   • Context-aware question prioritization")
        print("   • Ambiguity type detection")
        print("   • Confidence-based question filtering")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
