"""
User Experience Analytics for Warehouse Operational Assistant

Provides comprehensive analytics and insights into user experience patterns,
response quality trends, and user satisfaction metrics.
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import json
import statistics

from .response_validator import UserRole, ConfidenceLevel, ResponseQuality

logger = logging.getLogger(__name__)

class MetricType(Enum):
    """Types of UX metrics."""
    CONFIDENCE = "confidence"
    COMPLETENESS = "completeness"
    CONSISTENCY = "consistency"
    RESPONSE_TIME = "response_time"
    USER_SATISFACTION = "user_satisfaction"
    SOURCE_ATTRIBUTION = "source_attribution"

@dataclass
class UXMetric:
    """Individual UX metric data point."""
    timestamp: datetime
    metric_type: MetricType
    value: float
    user_role: UserRole
    agent_name: str
    query_intent: str
    session_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

@dataclass
class UXTrend:
    """UX trend analysis."""
    metric_type: MetricType
    time_period: str  # "hour", "day", "week"
    trend_direction: str  # "improving", "declining", "stable"
    trend_strength: float  # 0.0 to 1.0
    current_average: float
    previous_average: float
    data_points: int

@dataclass
class UserExperienceReport:
    """Comprehensive user experience report."""
    report_period: str
    generated_at: datetime
    overall_score: float
    trends: List[UXTrend]
    role_performance: Dict[str, float]
    agent_performance: Dict[str, float]
    intent_performance: Dict[str, float]
    recommendations: List[str]
    key_insights: List[str]

class UXAnalyticsService:
    """
    User experience analytics service for tracking and analyzing response quality.
    
    Features:
    - Real-time UX metrics collection
    - Trend analysis and pattern detection
    - User role-based performance analysis
    - Agent performance comparison
    - Query intent effectiveness analysis
    - Automated recommendations generation
    """
    
    def __init__(self):
        self.metrics: List[UXMetric] = []
        self.session_data: Dict[str, List[UXMetric]] = {}
        self.role_performance: Dict[UserRole, List[float]] = {
            role: [] for role in UserRole
        }
        self.agent_performance: Dict[str, List[float]] = {}
        self.intent_performance: Dict[str, List[float]] = {}
        
    async def record_metric(
        self,
        metric_type: MetricType,
        value: float,
        user_role: UserRole,
        agent_name: str,
        query_intent: str,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a UX metric."""
        try:
            metric = UXMetric(
                timestamp=datetime.now(),
                metric_type=metric_type,
                value=value,
                user_role=user_role,
                agent_name=agent_name,
                query_intent=query_intent,
                session_id=session_id,
                metadata=metadata
            )
            
            self.metrics.append(metric)
            
            # Update role performance
            if user_role not in self.role_performance:
                self.role_performance[user_role] = []
            self.role_performance[user_role].append(value)
            
            # Update agent performance
            if agent_name not in self.agent_performance:
                self.agent_performance[agent_name] = []
            self.agent_performance[agent_name].append(value)
            
            # Update intent performance
            if query_intent not in self.intent_performance:
                self.intent_performance[query_intent] = []
            self.intent_performance[query_intent].append(value)
            
            # Update session data
            if session_id:
                if session_id not in self.session_data:
                    self.session_data[session_id] = []
                self.session_data[session_id].append(metric)
            
            logger.debug(f"Recorded UX metric: {metric_type.value}={value:.3f}")
            
        except Exception as e:
            logger.error(f"Error recording UX metric: {e}")
    
    async def record_response_metrics(
        self,
        response_data: Dict[str, Any],
        user_role: UserRole,
        agent_name: str,
        query_intent: str,
        session_id: Optional[str] = None
    ) -> None:
        """Record multiple metrics from response data."""
        try:
            quality_control = response_data.get("quality_control", {})
            user_experience = response_data.get("user_experience", {})
            
            # Record confidence metric
            confidence_score = quality_control.get("confidence_score", 0.0)
            await self.record_metric(
                MetricType.CONFIDENCE,
                confidence_score,
                user_role,
                agent_name,
                query_intent,
                session_id
            )
            
            # Record completeness metric
            completeness_score = quality_control.get("completeness_score", 0.0)
            await self.record_metric(
                MetricType.COMPLETENESS,
                completeness_score,
                user_role,
                agent_name,
                query_intent,
                session_id
            )
            
            # Record consistency metric
            consistency_score = quality_control.get("consistency_score", 0.0)
            await self.record_metric(
                MetricType.CONSISTENCY,
                consistency_score,
                user_role,
                agent_name,
                query_intent,
                session_id
            )
            
            # Record response time metric
            response_time = response_data.get("response_time_ms", 0.0)
            if response_time > 0:
                # Convert to seconds and normalize (lower is better)
                normalized_time = max(0.0, 1.0 - (response_time / 5000.0))  # 5s = 0 score
                await self.record_metric(
                    MetricType.RESPONSE_TIME,
                    normalized_time,
                    user_role,
                    agent_name,
                    query_intent,
                    session_id
                )
            
            # Record user satisfaction metric
            ux_score = user_experience.get("score", 0.0)
            await self.record_metric(
                MetricType.USER_SATISFACTION,
                ux_score,
                user_role,
                agent_name,
                query_intent,
                session_id
            )
            
            # Record source attribution metric
            source_attribution = response_data.get("source_attribution", [])
            attribution_score = min(1.0, len(source_attribution) / 3.0)  # 3+ sources = 1.0
            await self.record_metric(
                MetricType.SOURCE_ATTRIBUTION,
                attribution_score,
                user_role,
                agent_name,
                query_intent,
                session_id
            )
            
        except Exception as e:
            logger.error(f"Error recording response metrics: {e}")
    
    async def generate_trend_analysis(
        self,
        metric_type: MetricType,
        time_period: str = "day",
        hours: int = 24
    ) -> UXTrend:
        """Generate trend analysis for a specific metric."""
        try:
            # Filter metrics by type and time period
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_metrics = [
                m for m in self.metrics 
                if m.metric_type == metric_type and m.timestamp > cutoff_time
            ]
            
            if len(recent_metrics) < 2:
                return UXTrend(
                    metric_type=metric_type,
                    time_period=time_period,
                    trend_direction="stable",
                    trend_strength=0.0,
                    current_average=0.0,
                    previous_average=0.0,
                    data_points=len(recent_metrics)
                )
            
            # Split into two halves for comparison
            mid_point = len(recent_metrics) // 2
            first_half = recent_metrics[:mid_point]
            second_half = recent_metrics[mid_point:]
            
            first_avg = statistics.mean([m.value for m in first_half])
            second_avg = statistics.mean([m.value for m in second_half])
            
            # Calculate trend
            difference = second_avg - first_avg
            trend_strength = abs(difference) / max(first_avg, 0.001)
            
            if difference > 0.05:
                trend_direction = "improving"
            elif difference < -0.05:
                trend_direction = "declining"
            else:
                trend_direction = "stable"
            
            return UXTrend(
                metric_type=metric_type,
                time_period=time_period,
                trend_direction=trend_direction,
                trend_strength=min(1.0, trend_strength),
                current_average=second_avg,
                previous_average=first_avg,
                data_points=len(recent_metrics)
            )
            
        except Exception as e:
            logger.error(f"Error generating trend analysis: {e}")
            return UXTrend(
                metric_type=metric_type,
                time_period=time_period,
                trend_direction="stable",
                trend_strength=0.0,
                current_average=0.0,
                previous_average=0.0,
                data_points=0
            )
    
    async def generate_user_experience_report(
        self,
        hours: int = 24
    ) -> UserExperienceReport:
        """Generate comprehensive user experience report."""
        try:
            # Filter metrics by time period
            cutoff_time = datetime.now() - timedelta(hours=hours)
            recent_metrics = [m for m in self.metrics if m.timestamp > cutoff_time]
            
            if not recent_metrics:
                return UserExperienceReport(
                    report_period=f"Last {hours} hours",
                    generated_at=datetime.now(),
                    overall_score=0.0,
                    trends=[],
                    role_performance={},
                    agent_performance={},
                    intent_performance={},
                    recommendations=["No data available for analysis"],
                    key_insights=["Insufficient data for meaningful analysis"]
                )
            
            # Generate trends for all metric types
            trends = []
            for metric_type in MetricType:
                trend = await self.generate_trend_analysis(metric_type, "hour", hours)
                trends.append(trend)
            
            # Calculate role performance
            role_performance = {}
            for role in UserRole:
                role_metrics = [m for m in recent_metrics if m.user_role == role]
                if role_metrics:
                    role_performance[role.value] = statistics.mean([m.value for m in role_metrics])
            
            # Calculate agent performance
            agent_performance = {}
            for agent_name in set(m.agent_name for m in recent_metrics):
                agent_metrics = [m for m in recent_metrics if m.agent_name == agent_name]
                if agent_metrics:
                    agent_performance[agent_name] = statistics.mean([m.value for m in agent_metrics])
            
            # Calculate intent performance
            intent_performance = {}
            for intent in set(m.query_intent for m in recent_metrics):
                intent_metrics = [m for m in recent_metrics if m.query_intent == intent]
                if intent_metrics:
                    intent_performance[intent] = statistics.mean([m.value for m in intent_metrics])
            
            # Calculate overall score
            overall_score = statistics.mean([m.value for m in recent_metrics])
            
            # Generate recommendations
            recommendations = await self._generate_recommendations(trends, role_performance, agent_performance)
            
            # Generate key insights
            key_insights = await self._generate_key_insights(trends, role_performance, agent_performance, intent_performance)
            
            return UserExperienceReport(
                report_period=f"Last {hours} hours",
                generated_at=datetime.now(),
                overall_score=overall_score,
                trends=trends,
                role_performance=role_performance,
                agent_performance=agent_performance,
                intent_performance=intent_performance,
                recommendations=recommendations,
                key_insights=key_insights
            )
            
        except Exception as e:
            logger.error(f"Error generating UX report: {e}")
            return UserExperienceReport(
                report_period=f"Last {hours} hours",
                generated_at=datetime.now(),
                overall_score=0.0,
                trends=[],
                role_performance={},
                agent_performance={},
                intent_performance={},
                recommendations=[f"Error generating report: {str(e)}"],
                key_insights=["Unable to generate insights due to error"]
            )
    
    async def get_session_analytics(self, session_id: str) -> Dict[str, Any]:
        """Get analytics for a specific session."""
        try:
            if session_id not in self.session_data:
                return {"error": "Session not found"}
            
            session_metrics = self.session_data[session_id]
            
            if not session_metrics:
                return {"error": "No metrics for session"}
            
            # Calculate session statistics
            session_stats = {}
            for metric_type in MetricType:
                type_metrics = [m for m in session_metrics if m.metric_type == metric_type]
                if type_metrics:
                    values = [m.value for m in type_metrics]
                    session_stats[metric_type.value] = {
                        "average": statistics.mean(values),
                        "min": min(values),
                        "max": max(values),
                        "count": len(values)
                    }
            
            # Calculate session duration
            if len(session_metrics) > 1:
                duration = (max(m.timestamp for m in session_metrics) - 
                           min(m.timestamp for m in session_metrics)).total_seconds()
                session_stats["duration_seconds"] = duration
            
            return {
                "session_id": session_id,
                "total_queries": len(session_metrics),
                "statistics": session_stats,
                "user_role": session_metrics[0].user_role.value if session_metrics else "unknown"
            }
            
        except Exception as e:
            logger.error(f"Error getting session analytics: {e}")
            return {"error": str(e)}
    
    async def _generate_recommendations(
        self,
        trends: List[UXTrend],
        role_performance: Dict[str, float],
        agent_performance: Dict[str, float]
    ) -> List[str]:
        """Generate recommendations based on analytics."""
        recommendations = []
        
        try:
            # Trend-based recommendations
            for trend in trends:
                if trend.trend_direction == "declining" and trend.trend_strength > 0.3:
                    if trend.metric_type == MetricType.CONFIDENCE:
                        recommendations.append("Confidence scores are declining - review evidence quality and source reliability")
                    elif trend.metric_type == MetricType.RESPONSE_TIME:
                        recommendations.append("Response times are increasing - consider optimizing query processing")
                    elif trend.metric_type == MetricType.USER_SATISFACTION:
                        recommendations.append("User satisfaction is declining - review response quality and personalization")
            
            # Role-based recommendations
            for role, score in role_performance.items():
                if score < 0.6:
                    recommendations.append(f"Improve response quality for {role} role - consider role-specific enhancements")
            
            # Agent-based recommendations
            for agent, score in agent_performance.items():
                if score < 0.6:
                    recommendations.append(f"Optimize {agent} agent performance - review agent logic and data sources")
            
            # General recommendations
            if not recommendations:
                recommendations.append("Overall performance is good - continue monitoring for optimization opportunities")
            
            return recommendations
            
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return ["Unable to generate recommendations"]
    
    async def _generate_key_insights(
        self,
        trends: List[UXTrend],
        role_performance: Dict[str, float],
        agent_performance: Dict[str, float],
        intent_performance: Dict[str, float]
    ) -> List[str]:
        """Generate key insights from analytics."""
        insights = []
        
        try:
            # Trend insights
            improving_trends = [t for t in trends if t.trend_direction == "improving"]
            declining_trends = [t for t in trends if t.trend_direction == "declining"]
            
            if improving_trends:
                insights.append(f"{len(improving_trends)} metrics showing improvement trends")
            
            if declining_trends:
                insights.append(f"{len(declining_trends)} metrics showing decline - attention needed")
            
            # Performance insights
            if role_performance:
                best_role = max(role_performance.items(), key=lambda x: x[1])
                worst_role = min(role_performance.items(), key=lambda x: x[1])
                insights.append(f"Best performing role: {best_role[0]} ({best_role[1]:.2f})")
                insights.append(f"Role needing attention: {worst_role[0]} ({worst_role[1]:.2f})")
            
            if agent_performance:
                best_agent = max(agent_performance.items(), key=lambda x: x[1])
                insights.append(f"Top performing agent: {best_agent[0]} ({best_agent[1]:.2f})")
            
            if intent_performance:
                best_intent = max(intent_performance.items(), key=lambda x: x[1])
                insights.append(f"Most effective query intent: {best_intent[0]} ({best_intent[1]:.2f})")
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating key insights: {e}")
            return ["Unable to generate insights"]

# Global UX analytics service instance
_ux_analytics: Optional[UXAnalyticsService] = None

async def get_ux_analytics() -> UXAnalyticsService:
    """Get or create the global UX analytics service instance."""
    global _ux_analytics
    if _ux_analytics is None:
        _ux_analytics = UXAnalyticsService()
    return _ux_analytics
