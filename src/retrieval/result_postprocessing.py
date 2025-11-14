"""
Result Post-Processing Service for Warehouse Operational Assistant

This module provides result post-processing, formatting, and consistency
ensuring across SQL and hybrid RAG query results.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone
import json

logger = logging.getLogger(__name__)


class ResultType(Enum):
    """Types of query results."""
    SQL_DATA = "sql_data"
    VECTOR_SEARCH = "vector_search"
    HYBRID_RAG = "hybrid_rag"
    ERROR = "error"


class DataQuality(Enum):
    """Data quality levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"


@dataclass
class ProcessedResult:
    """Result of post-processing."""
    original_data: Any
    processed_data: Any
    result_type: ResultType
    data_quality: DataQuality
    confidence: float
    metadata: Dict[str, Any]
    warnings: List[str]
    suggestions: List[str]


class ResultPostProcessor:
    """
    Advanced result post-processing service.
    
    This class ensures consistency, quality, and proper formatting
    across different types of query results.
    """
    
    def __init__(self):
        # Field mappings for consistency
        self.field_mappings = {
            'sku': ['sku', 'item_id', 'product_id', 'part_number'],
            'name': ['name', 'description', 'item_name', 'product_name'],
            'quantity': ['quantity', 'qty', 'amount', 'count', 'available_quantity'],
            'location': ['location', 'position', 'zone', 'area', 'bay'],
            'status': ['status', 'state', 'condition', 'operational_status'],
            'equipment_id': ['equipment_id', 'machine_id', 'device_id', 'asset_id'],
            'equipment_type': ['equipment_type', 'machine_type', 'device_type', 'asset_type'],
            'last_updated': ['last_updated', 'updated_at', 'modified_at', 'timestamp']
        }
        
        # Data quality thresholds
        self.quality_thresholds = {
            'completeness': 0.8,  # 80% of required fields present
            'consistency': 0.7,   # 70% consistency in data format
            'accuracy': 0.9,      # 90% accuracy in data values
            'timeliness': 0.6     # 60% of data is recent
        }
    
    async def process_result(
        self,
        data: Any,
        result_type: ResultType,
        query_context: Optional[Dict[str, Any]] = None
    ) -> ProcessedResult:
        """
        Process query result for consistency and quality.
        
        Args:
            data: Raw query result data
            result_type: Type of result (SQL, vector, hybrid)
            query_context: Context from the original query
            
        Returns:
            ProcessedResult with enhanced data
        """
        try:
            # Step 1: Normalize data structure
            normalized_data = await self._normalize_data_structure(data, result_type)
            
            # Step 2: Assess data quality
            quality_score, quality_level = await self._assess_data_quality(normalized_data, result_type)
            
            # Step 3: Standardize field names
            standardized_data = await self._standardize_field_names(normalized_data)
            
            # Step 4: Validate data consistency
            consistency_score, warnings = await self._validate_consistency(standardized_data, result_type)
            
            # Step 5: Enhance with metadata
            enhanced_data = await self._enhance_with_metadata(standardized_data, query_context)
            
            # Step 6: Generate suggestions
            suggestions = await self._generate_suggestions(enhanced_data, quality_level, warnings)
            
            # Calculate overall confidence
            confidence = await self._calculate_confidence(quality_score, consistency_score, warnings)
            
            return ProcessedResult(
                original_data=data,
                processed_data=enhanced_data,
                result_type=result_type,
                data_quality=quality_level,
                confidence=confidence,
                metadata={
                    'quality_score': quality_score,
                    'consistency_score': consistency_score,
                    'processing_timestamp': datetime.now(timezone.utc).isoformat(),
                    'result_count': len(enhanced_data) if isinstance(enhanced_data, list) else 1
                },
                warnings=warnings,
                suggestions=suggestions
            )
            
        except Exception as e:
            logger.error(f"Error in result post-processing: {e}")
            return ProcessedResult(
                original_data=data,
                processed_data=data,
                result_type=result_type,
                data_quality=DataQuality.POOR,
                confidence=0.0,
                metadata={'error': str(e)},
                warnings=[f"Post-processing error: {str(e)}"],
                suggestions=["Contact support if this error persists"]
            )
    
    async def _normalize_data_structure(
        self, 
        data: Any, 
        result_type: ResultType
    ) -> List[Dict[str, Any]]:
        """Normalize data to consistent structure."""
        if not data:
            return []
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        elif isinstance(data, str):
            try:
                # Try to parse as JSON
                parsed = json.loads(data)
                if isinstance(parsed, list):
                    return parsed
                elif isinstance(parsed, dict):
                    return [parsed]
                else:
                    return [{'content': data}]
            except json.JSONDecodeError:
                return [{'content': data}]
        else:
            return [{'content': str(data)}]
    
    async def _assess_data_quality(
        self, 
        data: List[Dict[str, Any]], 
        result_type: ResultType
    ) -> Tuple[float, DataQuality]:
        """Assess data quality score and level."""
        if not data:
            return 0.0, DataQuality.POOR
        
        # Calculate completeness score
        completeness = await self._calculate_completeness(data, result_type)
        
        # Calculate accuracy score
        accuracy = await self._calculate_accuracy(data, result_type)
        
        # Calculate timeliness score
        timeliness = await self._calculate_timeliness(data, result_type)
        
        # Overall quality score
        quality_score = (completeness + accuracy + timeliness) / 3
        
        # Determine quality level
        if quality_score >= 0.9:
            quality_level = DataQuality.EXCELLENT
        elif quality_score >= 0.7:
            quality_level = DataQuality.GOOD
        elif quality_score >= 0.5:
            quality_level = DataQuality.FAIR
        else:
            quality_level = DataQuality.POOR
        
        return quality_score, quality_level
    
    async def _calculate_completeness(
        self, 
        data: List[Dict[str, Any]], 
        result_type: ResultType
    ) -> float:
        """Calculate data completeness score."""
        if not data:
            return 0.0
        
        # Define required fields based on result type
        required_fields = self._get_required_fields(result_type)
        
        total_fields = len(required_fields)
        present_fields = 0
        
        for record in data:
            for field in required_fields:
                if field in record and record[field] is not None:
                    present_fields += 1
        
        return present_fields / (total_fields * len(data)) if data else 0.0
    
    async def _calculate_accuracy(
        self, 
        data: List[Dict[str, Any]], 
        result_type: ResultType
    ) -> float:
        """Calculate data accuracy score."""
        if not data:
            return 0.0
        
        accuracy_score = 1.0
        
        for record in data:
            # Check for valid SKU format
            if 'sku' in record:
                sku = str(record['sku'])
                if not sku.startswith('SKU') or not sku[3:].isdigit():
                    accuracy_score -= 0.1
            
            # Check for valid quantity
            if 'quantity' in record:
                try:
                    qty = float(record['quantity'])
                    if qty < 0:
                        accuracy_score -= 0.1
                except (ValueError, TypeError):
                    accuracy_score -= 0.1
            
            # Check for valid status
            if 'status' in record:
                valid_statuses = ['operational', 'maintenance', 'out_of_service', 'available', 'reserved']
                if record['status'].lower() not in valid_statuses:
                    accuracy_score -= 0.05
        
        return max(0.0, accuracy_score)
    
    async def _calculate_timeliness(
        self, 
        data: List[Dict[str, Any]], 
        result_type: ResultType
    ) -> float:
        """Calculate data timeliness score."""
        if not data:
            return 0.0
        
        timeliness_score = 1.0
        current_time = datetime.now(timezone.utc)
        
        for record in data:
            if 'last_updated' in record:
                try:
                    if isinstance(record['last_updated'], str):
                        updated_time = datetime.fromisoformat(record['last_updated'].replace('Z', '+00:00'))
                    else:
                        updated_time = record['last_updated']
                    
                    # Calculate age in hours
                    age_hours = (current_time - updated_time).total_seconds() / 3600
                    
                    # Penalize old data
                    if age_hours > 24:  # Older than 1 day
                        timeliness_score -= 0.1
                    elif age_hours > 168:  # Older than 1 week
                        timeliness_score -= 0.2
                    elif age_hours > 720:  # Older than 1 month
                        timeliness_score -= 0.3
                        
                except (ValueError, TypeError):
                    timeliness_score -= 0.1
        
        return max(0.0, timeliness_score)
    
    def _get_required_fields(self, result_type: ResultType) -> List[str]:
        """Get required fields for result type."""
        if result_type == ResultType.SQL_DATA:
            return ['sku', 'quantity', 'location']
        elif result_type == ResultType.VECTOR_SEARCH:
            return ['content', 'similarity_score']
        elif result_type == ResultType.HYBRID_RAG:
            return ['content', 'source', 'confidence']
        else:
            return ['content']
    
    async def _standardize_field_names(
        self, 
        data: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Standardize field names across different data sources."""
        standardized = []
        
        for record in data:
            standardized_record = {}
            
            for standard_field, variants in self.field_mappings.items():
                for variant in variants:
                    if variant in record:
                        standardized_record[standard_field] = record[variant]
                        break
            
            # Keep any unmapped fields
            for key, value in record.items():
                if key not in standardized_record:
                    standardized_record[key] = value
            
            standardized.append(standardized_record)
        
        return standardized
    
    async def _validate_consistency(
        self, 
        data: List[Dict[str, Any]], 
        result_type: ResultType
    ) -> Tuple[float, List[str]]:
        """Validate data consistency and return warnings."""
        warnings = []
        consistency_score = 1.0
        
        if not data:
            return 0.0, ["No data to validate"]
        
        # Check for duplicate records
        if len(data) > 1:
            seen_skus = set()
            for record in data:
                if 'sku' in record:
                    sku = record['sku']
                    if sku in seen_skus:
                        warnings.append(f"Duplicate SKU found: {sku}")
                        consistency_score -= 0.1
                    else:
                        seen_skus.add(sku)
        
        # Check for data type consistency
        for field in ['quantity', 'available_quantity', 'reserved_quantity']:
            if field in data[0]:
                expected_type = type(data[0][field])
                for i, record in enumerate(data[1:], 1):
                    if field in record and type(record[field]) != expected_type:
                        warnings.append(f"Inconsistent data type for {field} in record {i}")
                        consistency_score -= 0.05
        
        # Check for missing critical fields
        critical_fields = self._get_required_fields(result_type)
        for record in data:
            missing_fields = [field for field in critical_fields if field not in record or record[field] is None]
            if missing_fields:
                warnings.append(f"Missing critical fields: {missing_fields}")
                consistency_score -= 0.1
        
        return max(0.0, consistency_score), warnings
    
    async def _enhance_with_metadata(
        self, 
        data: List[Dict[str, Any]], 
        query_context: Optional[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Enhance data with additional metadata."""
        enhanced = []
        
        for i, record in enumerate(data):
            enhanced_record = record.copy()
            
            # Add processing metadata
            enhanced_record['_metadata'] = {
                'record_index': i,
                'processing_timestamp': datetime.now(timezone.utc).isoformat(),
                'query_context': query_context or {}
            }
            
            # Add computed fields
            if 'available_quantity' in record and 'reserved_quantity' in record:
                try:
                    available = float(record['available_quantity'])
                    reserved = float(record['reserved_quantity'])
                    enhanced_record['atp_quantity'] = available - reserved
                except (ValueError, TypeError):
                    pass
            
            # Add status indicators
            if 'quantity' in record:
                try:
                    qty = float(record['quantity'])
                    if qty == 0:
                        enhanced_record['status_indicator'] = 'out_of_stock'
                    elif qty < 10:
                        enhanced_record['status_indicator'] = 'low_stock'
                    else:
                        enhanced_record['status_indicator'] = 'in_stock'
                except (ValueError, TypeError):
                    pass
            
            enhanced.append(enhanced_record)
        
        return enhanced
    
    async def _generate_suggestions(
        self, 
        data: List[Dict[str, Any]], 
        quality_level: DataQuality, 
        warnings: List[str]
    ) -> List[str]:
        """Generate improvement suggestions based on data quality."""
        suggestions = []
        
        if quality_level == DataQuality.POOR:
            suggestions.append("Data quality is poor. Consider refining your query or checking data sources.")
        
        if warnings:
            if any("duplicate" in warning.lower() for warning in warnings):
                suggestions.append("Remove duplicate records for cleaner results.")
            
            if any("missing" in warning.lower() for warning in warnings):
                suggestions.append("Add missing field information for more complete results.")
            
            if any("inconsistent" in warning.lower() for warning in warnings):
                suggestions.append("Standardize data formats for better consistency.")
        
        if len(data) == 0:
            suggestions.append("No results found. Try broadening your search criteria.")
        elif len(data) == 1:
            suggestions.append("Only one result found. Consider if you need more comprehensive data.")
        elif len(data) > 100:
            suggestions.append("Many results found. Consider adding filters to narrow down results.")
        
        return suggestions
    
    async def _calculate_confidence(
        self, 
        quality_score: float, 
        consistency_score: float, 
        warnings: List[str]
    ) -> float:
        """Calculate overall confidence score."""
        # Base confidence from quality and consistency
        confidence = (quality_score + consistency_score) / 2
        
        # Penalize for warnings
        warning_penalty = len(warnings) * 0.05
        confidence -= warning_penalty
        
        # Ensure confidence is between 0 and 1
        return max(0.0, min(1.0, confidence))
    
    async def format_for_display(
        self, 
        processed_result: ProcessedResult,
        format_type: str = "table"
    ) -> str:
        """Format processed result for display."""
        data = processed_result.processed_data
        
        if format_type == "table" and isinstance(data, list) and data:
            # Create a simple table format
            headers = list(data[0].keys())
            rows = []
            
            for record in data:
                row = []
                for header in headers:
                    value = record.get(header, '')
                    if isinstance(value, (dict, list)):
                        value = str(value)
                    row.append(str(value))
                rows.append(row)
            
            # Simple table formatting
            col_widths = [max(len(str(header)), max(len(str(row[i])) for row in rows)) for i, header in enumerate(headers)]
            
            # Header row
            header_row = " | ".join(header.ljust(col_widths[i]) for i, header in enumerate(headers))
            separator = "-" * len(header_row)
            
            # Data rows
            data_rows = []
            for row in rows:
                data_row = " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
                data_rows.append(data_row)
            
            return f"{header_row}\n{separator}\n" + "\n".join(data_rows)
        
        elif format_type == "json":
            return json.dumps(data, indent=2, default=str)
        
        else:
            return str(data)
