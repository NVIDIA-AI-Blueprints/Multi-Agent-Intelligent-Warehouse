"""
Clarifying Questions Engine for Enhanced Vector Search

This module implements intelligent clarifying questions generation for low-confidence scenarios:
- Question templates for common ambiguity types
- Context-aware questioning based on query type
- Question prioritization for most critical clarifications
- Question validation to ensure helpfulness
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
import logging
import re
from datetime import datetime

logger = logging.getLogger(__name__)

class AmbiguityType(Enum):
    """Types of ambiguity that require clarifying questions."""
    EQUIPMENT_SPECIFIC = "equipment_specific"
    LOCATION_SPECIFIC = "location_specific"
    TIME_SPECIFIC = "time_specific"
    QUANTITY_SPECIFIC = "quantity_specific"
    INTENT_UNCLEAR = "intent_unclear"
    MULTIPLE_OPTIONS = "multiple_options"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    TECHNICAL_TERMS = "technical_terms"

class QuestionPriority(Enum):
    """Priority levels for clarifying questions."""
    CRITICAL = "critical"  # Must be answered for accurate response
    HIGH = "high"         # Important for better response quality
    MEDIUM = "medium"     # Helpful for optimization
    LOW = "low"          # Nice to have

@dataclass
class ClarifyingQuestion:
    """Represents a clarifying question with metadata."""
    question: str
    ambiguity_type: AmbiguityType
    priority: QuestionPriority
    context: str
    expected_answer_type: str  # "equipment_id", "location", "time_period", "number", "text"
    validation_rules: List[str]
    follow_up_questions: List[str] = None
    metadata: Dict[str, Any] = None

@dataclass
class QuestionSet:
    """A set of clarifying questions for a specific scenario."""
    questions: List[ClarifyingQuestion]
    context: str
    query_type: str
    confidence_level: str
    total_priority_score: float
    estimated_completion_time: str  # "quick", "moderate", "extensive"

class ClarifyingQuestionsEngine:
    """Intelligent clarifying questions generator for low-confidence scenarios."""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or self._get_default_config()
        self.question_templates = self._build_question_templates()
        self.validation_rules = self._build_validation_rules()
        self.context_patterns = self._build_context_patterns()
        
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration for clarifying questions."""
        return {
            "max_questions": 3,
            "priority_threshold": 0.6,
            "context_window": 5,  # Number of previous interactions to consider
            "question_timeout": 300,  # 5 minutes in seconds
            "enable_follow_ups": True,
            "validation_enabled": True
        }
    
    def generate_questions(
        self,
        query: str,
        evidence_score: float,
        query_type: str,
        context: Optional[Dict[str, Any]] = None,
        previous_interactions: Optional[List[Dict[str, Any]]] = None
    ) -> QuestionSet:
        """
        Generate clarifying questions based on query analysis and evidence quality.
        
        Args:
            query: User query that needs clarification
            evidence_score: Evidence quality score (0.0 to 1.0)
            query_type: Type of query (equipment, operations, safety, etc.)
            context: Additional context for question generation
            previous_interactions: Previous conversation history
            
        Returns:
            QuestionSet with prioritized clarifying questions
        """
        # Analyze query for ambiguity types
        ambiguity_types = self._analyze_query_ambiguity(query, query_type)
        
        # Generate questions based on ambiguity types
        questions = []
        for ambiguity_type in ambiguity_types:
            type_questions = self._generate_questions_for_ambiguity_type(
                ambiguity_type, query, query_type, context
            )
            questions.extend(type_questions)
        
        # Prioritize and filter questions
        prioritized_questions = self._prioritize_questions(questions, evidence_score, query_type)
        
        # Limit number of questions
        final_questions = prioritized_questions[:self.config["max_questions"]]
        
        # Calculate metadata
        total_priority_score = sum(q.priority.value == "critical" for q in final_questions)
        estimated_time = self._estimate_completion_time(final_questions)
        
        return QuestionSet(
            questions=final_questions,
            context=query,
            query_type=query_type,
            confidence_level=self._determine_confidence_level(evidence_score),
            total_priority_score=total_priority_score,
            estimated_completion_time=estimated_time
        )
    
    def _analyze_query_ambiguity(self, query: str, query_type: str) -> List[AmbiguityType]:
        """Analyze query to identify types of ambiguity."""
        ambiguity_types = []
        query_lower = query.lower()
        
        # Equipment-specific ambiguity
        if any(word in query_lower for word in ["equipment", "device", "tool", "machine"]) and not any(word in query_lower for word in ["sku", "id", "specific", "particular"]):
            ambiguity_types.append(AmbiguityType.EQUIPMENT_SPECIFIC)
        
        # Location-specific ambiguity
        if any(word in query_lower for word in ["where", "location", "zone", "aisle"]) and not any(word in query_lower for word in ["specific", "particular", "exact"]):
            ambiguity_types.append(AmbiguityType.LOCATION_SPECIFIC)
        
        # Time-specific ambiguity
        if any(word in query_lower for word in ["when", "time", "date", "schedule"]) and not any(word in query_lower for word in ["specific", "exact", "precise"]):
            ambiguity_types.append(AmbiguityType.TIME_SPECIFIC)
        
        # Quantity-specific ambiguity
        if any(word in query_lower for word in ["how many", "quantity", "amount", "count"]) and not any(word in query_lower for word in ["exact", "precise", "specific"]):
            ambiguity_types.append(AmbiguityType.QUANTITY_SPECIFIC)
        
        # Intent unclear
        if len(query.split()) < 3 or any(word in query_lower for word in ["help", "what", "how", "can you"]):
            ambiguity_types.append(AmbiguityType.INTENT_UNCLEAR)
        
        # Multiple options
        if any(word in query_lower for word in ["or", "either", "both", "all", "any"]):
            ambiguity_types.append(AmbiguityType.MULTIPLE_OPTIONS)
        
        # Insufficient context
        if len(query.split()) < 5 and not any(word in query_lower for word in ["sku", "id", "specific"]):
            ambiguity_types.append(AmbiguityType.INSUFFICIENT_CONTEXT)
        
        # Technical terms
        technical_terms = ["atp", "loto", "pm", "sop", "kpi", "rfid", "amr", "agv"]
        if any(term in query_lower for term in technical_terms) and not any(word in query_lower for word in ["explain", "what is", "define"]):
            ambiguity_types.append(AmbiguityType.TECHNICAL_TERMS)
        
        return ambiguity_types
    
    def _generate_questions_for_ambiguity_type(
        self,
        ambiguity_type: AmbiguityType,
        query: str,
        query_type: str,
        context: Optional[Dict[str, Any]]
    ) -> List[ClarifyingQuestion]:
        """Generate questions for a specific ambiguity type."""
        questions = []
        
        if ambiguity_type == AmbiguityType.EQUIPMENT_SPECIFIC:
            questions.extend(self._generate_equipment_questions(query, query_type))
        elif ambiguity_type == AmbiguityType.LOCATION_SPECIFIC:
            questions.extend(self._generate_location_questions(query, query_type))
        elif ambiguity_type == AmbiguityType.TIME_SPECIFIC:
            questions.extend(self._generate_time_questions(query, query_type))
        elif ambiguity_type == AmbiguityType.QUANTITY_SPECIFIC:
            questions.extend(self._generate_quantity_questions(query, query_type))
        elif ambiguity_type == AmbiguityType.INTENT_UNCLEAR:
            questions.extend(self._generate_intent_questions(query, query_type))
        elif ambiguity_type == AmbiguityType.MULTIPLE_OPTIONS:
            questions.extend(self._generate_multiple_options_questions(query, query_type))
        elif ambiguity_type == AmbiguityType.INSUFFICIENT_CONTEXT:
            questions.extend(self._generate_context_questions(query, query_type))
        elif ambiguity_type == AmbiguityType.TECHNICAL_TERMS:
            questions.extend(self._generate_technical_questions(query, query_type))
        
        return questions
    
    def _generate_equipment_questions(self, query: str, query_type: str) -> List[ClarifyingQuestion]:
        """Generate equipment-specific clarifying questions."""
        questions = []
        
        # Equipment identification
        questions.append(ClarifyingQuestion(
            question="Which specific equipment are you asking about? Please provide the SKU, equipment ID, or name.",
            ambiguity_type=AmbiguityType.EQUIPMENT_SPECIFIC,
            priority=QuestionPriority.CRITICAL,
            context="Equipment identification needed for accurate response",
            expected_answer_type="equipment_id",
            validation_rules=["not_empty", "equipment_format"],
            follow_up_questions=["Is this the correct equipment?", "Do you need information about similar equipment?"]
        ))
        
        # Equipment type clarification
        if "equipment" in query.lower():
            questions.append(ClarifyingQuestion(
                question="What type of equipment are you interested in? (e.g., forklift, conveyor, scanner, robot)",
                ambiguity_type=AmbiguityType.EQUIPMENT_SPECIFIC,
                priority=QuestionPriority.HIGH,
                context="Equipment type helps narrow down the search",
                expected_answer_type="text",
                validation_rules=["not_empty", "equipment_type"]
            ))
        
        return questions
    
    def _generate_location_questions(self, query: str, query_type: str) -> List[ClarifyingQuestion]:
        """Generate location-specific clarifying questions."""
        questions = []
        
        # Location specification
        questions.append(ClarifyingQuestion(
            question="Which location are you asking about? Please specify the zone, aisle, or exact location.",
            ambiguity_type=AmbiguityType.LOCATION_SPECIFIC,
            priority=QuestionPriority.CRITICAL,
            context="Location specification needed for accurate response",
            expected_answer_type="location",
            validation_rules=["not_empty", "location_format"],
            follow_up_questions=["Is this the correct location?", "Do you need information about nearby locations?"]
        ))
        
        # Location scope
        if "where" in query.lower():
            questions.append(ClarifyingQuestion(
                question="Are you looking for a specific location or all locations where this item/equipment is stored?",
                ambiguity_type=AmbiguityType.LOCATION_SPECIFIC,
                priority=QuestionPriority.MEDIUM,
                context="Location scope helps determine response detail level",
                expected_answer_type="text",
                validation_rules=["not_empty"]
            ))
        
        return questions
    
    def _generate_time_questions(self, query: str, query_type: str) -> List[ClarifyingQuestion]:
        """Generate time-specific clarifying questions."""
        questions = []
        
        # Time period specification
        questions.append(ClarifyingQuestion(
            question="What time period are you interested in? Please specify a date range or time period (e.g., today, last week, this month).",
            ambiguity_type=AmbiguityType.TIME_SPECIFIC,
            priority=QuestionPriority.CRITICAL,
            context="Time period needed for accurate data retrieval",
            expected_answer_type="time_period",
            validation_rules=["not_empty", "time_format"],
            follow_up_questions=["Is this the correct time period?", "Do you need data for a different time period?"]
        ))
        
        # Time granularity
        if any(word in query.lower() for word in ["schedule", "when", "time"]):
            questions.append(ClarifyingQuestion(
                question="What level of detail do you need? (e.g., hourly, daily, weekly, monthly)",
                ambiguity_type=AmbiguityType.TIME_SPECIFIC,
                priority=QuestionPriority.MEDIUM,
                context="Time granularity helps determine response format",
                expected_answer_type="text",
                validation_rules=["not_empty"]
            ))
        
        return questions
    
    def _generate_quantity_questions(self, query: str, query_type: str) -> List[ClarifyingQuestion]:
        """Generate quantity-specific clarifying questions."""
        questions = []
        
        # Quantity specification
        questions.append(ClarifyingQuestion(
            question="What specific quantity information do you need? (e.g., current stock, available quantity, total count)",
            ambiguity_type=AmbiguityType.QUANTITY_SPECIFIC,
            priority=QuestionPriority.CRITICAL,
            context="Quantity type needed for accurate response",
            expected_answer_type="text",
            validation_rules=["not_empty"],
            follow_up_questions=["Is this the quantity information you're looking for?", "Do you need additional quantity details?"]
        ))
        
        # Quantity scope
        if "how many" in query.lower():
            questions.append(ClarifyingQuestion(
                question="Are you looking for the total quantity across all locations or quantity at a specific location?",
                ambiguity_type=AmbiguityType.QUANTITY_SPECIFIC,
                priority=QuestionPriority.HIGH,
                context="Quantity scope helps determine response detail",
                expected_answer_type="text",
                validation_rules=["not_empty"]
            ))
        
        return questions
    
    def _generate_intent_questions(self, query: str, query_type: str) -> List[ClarifyingQuestion]:
        """Generate intent clarification questions."""
        questions = []
        
        # Intent clarification
        questions.append(ClarifyingQuestion(
            question="What specific information are you looking for? Please be more specific about what you need to know.",
            ambiguity_type=AmbiguityType.INTENT_UNCLEAR,
            priority=QuestionPriority.CRITICAL,
            context="Intent clarification needed for accurate response",
            expected_answer_type="text",
            validation_rules=["not_empty", "min_length_10"],
            follow_up_questions=["Is this what you're looking for?", "Do you need additional information?"]
        ))
        
        # Action clarification
        if any(word in query.lower() for word in ["help", "can you", "what can"]):
            questions.append(ClarifyingQuestion(
                question="What would you like me to help you with? (e.g., check status, find information, perform an action)",
                ambiguity_type=AmbiguityType.INTENT_UNCLEAR,
                priority=QuestionPriority.HIGH,
                context="Action clarification helps determine appropriate response",
                expected_answer_type="text",
                validation_rules=["not_empty"]
            ))
        
        return questions
    
    def _generate_multiple_options_questions(self, query: str, query_type: str) -> List[ClarifyingQuestion]:
        """Generate questions for multiple options scenarios."""
        questions = []
        
        # Option selection
        questions.append(ClarifyingQuestion(
            question="I see multiple options in your query. Which specific option are you interested in?",
            ambiguity_type=AmbiguityType.MULTIPLE_OPTIONS,
            priority=QuestionPriority.CRITICAL,
            context="Option selection needed for accurate response",
            expected_answer_type="text",
            validation_rules=["not_empty"],
            follow_up_questions=["Is this the correct option?", "Do you need information about other options?"]
        ))
        
        return questions
    
    def _generate_context_questions(self, query: str, query_type: str) -> List[ClarifyingQuestion]:
        """Generate questions for insufficient context scenarios."""
        questions = []
        
        # Context expansion
        questions.append(ClarifyingQuestion(
            question="Could you provide more details about what you're looking for? The more specific you are, the better I can help you.",
            ambiguity_type=AmbiguityType.INSUFFICIENT_CONTEXT,
            priority=QuestionPriority.CRITICAL,
            context="Additional context needed for accurate response",
            expected_answer_type="text",
            validation_rules=["not_empty", "min_length_20"],
            follow_up_questions=["Is this the information you need?", "Do you need more specific details?"]
        ))
        
        return questions
    
    def _generate_technical_questions(self, query: str, query_type: str) -> List[ClarifyingQuestion]:
        """Generate questions for technical terms scenarios."""
        questions = []
        
        # Technical term clarification
        technical_terms = self._extract_technical_terms(query)
        if technical_terms:
            questions.append(ClarifyingQuestion(
                question=f"I notice you mentioned {', '.join(technical_terms)}. Are you familiar with these terms, or would you like me to explain them?",
                ambiguity_type=AmbiguityType.TECHNICAL_TERMS,
                priority=QuestionPriority.MEDIUM,
                context="Technical term understanding helps provide appropriate response",
                expected_answer_type="text",
                validation_rules=["not_empty"]
            ))
        
        return questions
    
    def _extract_technical_terms(self, query: str) -> List[str]:
        """Extract technical terms from query."""
        technical_terms = ["atp", "loto", "pm", "sop", "kpi", "rfid", "amr", "agv", "cobot", "siem"]
        found_terms = []
        query_lower = query.lower()
        
        for term in technical_terms:
            if term in query_lower:
                found_terms.append(term.upper())
        
        return found_terms
    
    def _prioritize_questions(
        self,
        questions: List[ClarifyingQuestion],
        evidence_score: float,
        query_type: str
    ) -> List[ClarifyingQuestion]:
        """Prioritize questions based on evidence score and query type."""
        # Sort by priority (critical first)
        priority_order = {
            QuestionPriority.CRITICAL: 0,
            QuestionPriority.HIGH: 1,
            QuestionPriority.MEDIUM: 2,
            QuestionPriority.LOW: 3
        }
        
        # Adjust priority based on evidence score
        adjusted_questions = []
        for question in questions:
            # Lower evidence score means higher priority for clarifying questions
            if evidence_score < 0.3 and question.priority == QuestionPriority.HIGH:
                question.priority = QuestionPriority.CRITICAL
            elif evidence_score < 0.5 and question.priority == QuestionPriority.MEDIUM:
                question.priority = QuestionPriority.HIGH
            
            adjusted_questions.append(question)
        
        # Sort by adjusted priority
        return sorted(adjusted_questions, key=lambda q: priority_order[q.priority])
    
    def _estimate_completion_time(self, questions: List[ClarifyingQuestion]) -> str:
        """Estimate completion time for questions."""
        critical_count = sum(1 for q in questions if q.priority == QuestionPriority.CRITICAL)
        total_count = len(questions)
        
        if critical_count >= 2 or total_count >= 4:
            return "extensive"
        elif critical_count >= 1 or total_count >= 2:
            return "moderate"
        else:
            return "quick"
    
    def _determine_confidence_level(self, evidence_score: float) -> str:
        """Determine confidence level based on evidence score."""
        if evidence_score >= 0.8:
            return "high"
        elif evidence_score >= 0.6:
            return "medium"
        else:
            return "low"
    
    def _build_question_templates(self) -> Dict[str, List[str]]:
        """Build question templates for different scenarios."""
        return {
            "equipment": [
                "Which specific equipment are you asking about?",
                "What type of equipment do you need information about?",
                "Do you have the equipment ID or SKU?"
            ],
            "location": [
                "Which location are you interested in?",
                "What zone or aisle are you asking about?",
                "Do you need information for a specific area?"
            ],
            "time": [
                "What time period are you interested in?",
                "When do you need this information for?",
                "What date range are you looking at?"
            ],
            "quantity": [
                "What specific quantity information do you need?",
                "Are you looking for current stock or available quantity?",
                "Do you need totals across all locations?"
            ]
        }
    
    def _build_validation_rules(self) -> Dict[str, callable]:
        """Build validation rules for question answers."""
        return {
            "not_empty": lambda x: len(x.strip()) > 0,
            "min_length_10": lambda x: len(x.strip()) >= 10,
            "min_length_20": lambda x: len(x.strip()) >= 20,
            "equipment_format": lambda x: bool(re.search(r'(SKU|ID|Equipment)', x, re.IGNORECASE)),
            "location_format": lambda x: bool(re.search(r'(Zone|Aisle|Location)', x, re.IGNORECASE)),
            "time_format": lambda x: bool(re.search(r'(today|yesterday|week|month|year|date)', x, re.IGNORECASE)),
            "equipment_type": lambda x: bool(re.search(r'(forklift|conveyor|scanner|robot|amr|agv)', x, re.IGNORECASE))
        }
    
    def _build_context_patterns(self) -> Dict[str, List[str]]:
        """Build context patterns for question generation."""
        return {
            "equipment_queries": ["equipment", "device", "tool", "machine", "sku"],
            "location_queries": ["where", "location", "zone", "aisle", "area"],
            "time_queries": ["when", "time", "date", "schedule", "period"],
            "quantity_queries": ["how many", "quantity", "amount", "count", "number"]
        }
