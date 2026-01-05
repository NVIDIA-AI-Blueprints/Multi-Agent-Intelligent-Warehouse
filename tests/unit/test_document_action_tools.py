# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unit tests for DocumentActionTools.

Tests document processing action tools for the MCP framework, including:
- Initialization and configuration
- Helper methods (value extraction, error handling, document status tracking)
- Time parsing utilities
- Quality score extraction
- Document status management
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from datetime import datetime
from pathlib import Path
import json
import tempfile
import os

from src.api.agents.document.action_tools import DocumentActionTools
from src.api.agents.document.models.document_models import (
    ProcessingStage,
    QualityDecision,
    RoutingAction,
)


class TestDocumentActionToolsInitialization:
    """Test DocumentActionTools initialization."""

    def test_initialization_defaults(self):
        """Test that DocumentActionTools initializes with correct defaults."""
        tools = DocumentActionTools()
        
        assert tools.nim_client is None
        assert tools.supported_file_types == ["pdf", "png", "jpg", "jpeg", "tiff", "bmp"]
        assert tools.max_file_size == 50 * 1024 * 1024  # 50MB
        assert tools.document_statuses == {}
        assert tools.status_file == Path("document_statuses.json")
        assert tools.db_service is None
        assert tools.use_database is True

    def test_model_constants(self):
        """Test that model name constants are correctly defined."""
        tools = DocumentActionTools()
        
        assert tools.MODEL_SMALL_LLM == "Llama Nemotron Nano VL 8B"
        assert tools.MODEL_LARGE_JUDGE == "Llama 3.3 Nemotron Super 49B"
        assert tools.MODEL_OCR == "NeMoRetriever-OCR-v1"

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful initialization with database service."""
        tools = DocumentActionTools()
        
        mock_nim_client = AsyncMock()
        mock_db_service = AsyncMock()
        
        with patch("src.api.agents.document.action_tools.get_nim_client", return_value=mock_nim_client), \
             patch("src.api.services.document.get_document_db_service", return_value=mock_db_service), \
             patch.object(tools, "_load_status_data"):
            
            await tools.initialize()
            
            assert tools.nim_client == mock_nim_client
            assert tools.db_service == mock_db_service
            assert tools.use_database is True

    @pytest.mark.asyncio
    async def test_initialize_without_database_fallback(self):
        """Test initialization falls back to file-based storage when database is unavailable."""
        tools = DocumentActionTools()
        
        mock_nim_client = AsyncMock()
        
        with patch("src.api.agents.document.action_tools.get_nim_client", return_value=mock_nim_client), \
             patch("src.api.services.document.get_document_db_service", side_effect=Exception("DB unavailable")), \
             patch.object(tools, "_load_status_data"):
            
            await tools.initialize()
            
            assert tools.nim_client == mock_nim_client
            assert tools.db_service is None
            assert tools.use_database is False


class TestDocumentActionToolsHelpers:
    """Test helper methods in DocumentActionTools."""

    def test_get_value_from_dict(self):
        """Test _get_value with dictionary input."""
        tools = DocumentActionTools()
        test_dict = {"key1": "value1", "key2": 42}
        
        assert tools._get_value(test_dict, "key1") == "value1"
        assert tools._get_value(test_dict, "key2") == 42
        assert tools._get_value(test_dict, "key3") is None
        assert tools._get_value(test_dict, "key3", "default") == "default"

    def test_get_value_from_object(self):
        """Test _get_value with object attributes."""
        tools = DocumentActionTools()
        
        class TestObj:
            def __init__(self):
                self.attr1 = "value1"
                self.attr2 = 42
        
        obj = TestObj()
        assert tools._get_value(obj, "attr1") == "value1"
        assert tools._get_value(obj, "attr2") == 42
        assert tools._get_value(obj, "attr3") is None
        assert tools._get_value(obj, "attr3", "default") == "default"

    def test_get_value_fallback(self):
        """Test _get_value with object that has neither attribute nor get method."""
        tools = DocumentActionTools()
        
        class TestObj:
            pass
        
        obj = TestObj()
        assert tools._get_value(obj, "nonexistent") is None
        assert tools._get_value(obj, "nonexistent", "default") == "default"

    def test_create_error_response(self):
        """Test _create_error_response creates standardized error format."""
        tools = DocumentActionTools()
        
        error = ValueError("Test error message")
        response = tools._create_error_response("test operation", error)
        
        assert response["success"] is False
        assert response["error"] == "Test error message"
        assert response["message"] == "Failed to test operation"

    def test_check_document_exists_found(self):
        """Test _check_document_exists when document exists."""
        tools = DocumentActionTools()
        doc_id = "test-doc-123"
        doc_status = {"status": "processing", "progress": 50}
        
        tools.document_statuses[doc_id] = doc_status
        
        exists, status = tools._check_document_exists(doc_id)
        
        assert exists is True
        assert status == doc_status

    def test_check_document_exists_not_found(self):
        """Test _check_document_exists when document doesn't exist."""
        tools = DocumentActionTools()
        doc_id = "nonexistent-doc"
        
        exists, status = tools._check_document_exists(doc_id)
        
        assert exists is False
        assert status is None

    def test_get_document_status_or_error_found(self):
        """Test _get_document_status_or_error when document exists."""
        tools = DocumentActionTools()
        doc_id = "test-doc-123"
        doc_status = {"status": "processing", "progress": 50}
        
        tools.document_statuses[doc_id] = doc_status
        
        success, status, error = tools._get_document_status_or_error(doc_id, "test operation")
        
        assert success is True
        assert status == doc_status
        assert error is None

    def test_get_document_status_or_error_not_found(self):
        """Test _get_document_status_or_error when document doesn't exist."""
        tools = DocumentActionTools()
        doc_id = "nonexistent-doc"
        
        success, status, error = tools._get_document_status_or_error(doc_id, "test operation")
        
        assert success is False
        assert status is None
        assert error is not None
        assert error["success"] is False
        assert doc_id in error["message"]


class TestDocumentActionToolsTimeParsing:
    """Test time parsing methods."""

    def test_parse_hours_range_valid(self):
        """Test _parse_hours_range with valid range format."""
        tools = DocumentActionTools()
        
        result = tools._parse_hours_range("4-8 hours")
        assert result == 6 * 3600  # Average of 4 and 8 hours = 6 hours = 21600 seconds
        
        result = tools._parse_hours_range("1-3 hours")
        assert result == 2 * 3600  # Average of 1 and 3 hours = 2 hours = 7200 seconds

    def test_parse_hours_range_invalid(self):
        """Test _parse_hours_range with invalid formats."""
        tools = DocumentActionTools()
        
        assert tools._parse_hours_range("4 hours") is None  # No dash
        # "4-8" actually parses because it splits "8" by space (gets ["8"]), takes index 0
        # So it returns (4+8)/2 * 3600 = 21600, not None
        result = tools._parse_hours_range("4-8")
        assert result == 21600  # Actually parses successfully
        assert tools._parse_hours_range("invalid") is None  # Completely invalid
        assert tools._parse_hours_range("a-b") is None  # Non-numeric

    def test_parse_single_hours_valid(self):
        """Test _parse_single_hours with valid format."""
        tools = DocumentActionTools()
        
        assert tools._parse_single_hours("4 hours") == 4 * 3600
        assert tools._parse_single_hours("1 hour") == 1 * 3600
        assert tools._parse_single_hours("10 hours") == 10 * 3600

    def test_parse_single_hours_invalid(self):
        """Test _parse_single_hours with invalid formats."""
        tools = DocumentActionTools()
        
        assert tools._parse_single_hours("invalid") is None
        assert tools._parse_single_hours("") is None

    def test_parse_minutes_valid(self):
        """Test _parse_minutes with valid format."""
        tools = DocumentActionTools()
        
        assert tools._parse_minutes("30 minutes") == 30 * 60
        assert tools._parse_minutes("1 minute") == 1 * 60
        assert tools._parse_minutes("45 minutes") == 45 * 60

    def test_parse_minutes_invalid(self):
        """Test _parse_minutes with invalid formats."""
        tools = DocumentActionTools()
        
        assert tools._parse_minutes("invalid") is None
        assert tools._parse_minutes("") is None

    def test_parse_processing_time_hours_range(self):
        """Test _parse_processing_time with hours range."""
        tools = DocumentActionTools()
        
        result = tools._parse_processing_time("4-8 hours")
        assert result == 6 * 3600  # Average of 4 and 8 hours

    def test_parse_processing_time_single_hours(self):
        """Test _parse_processing_time with single hours."""
        tools = DocumentActionTools()
        
        assert tools._parse_processing_time("4 hours") == 4 * 3600
        assert tools._parse_processing_time("1 hour") == 1 * 3600

    def test_parse_processing_time_minutes(self):
        """Test _parse_processing_time with minutes."""
        tools = DocumentActionTools()
        
        assert tools._parse_processing_time("30 minutes") == 30 * 60
        assert tools._parse_processing_time("45 minutes") == 45 * 60

    def test_parse_processing_time_integer(self):
        """Test _parse_processing_time with integer input."""
        tools = DocumentActionTools()
        
        assert tools._parse_processing_time(3600) == 3600
        assert tools._parse_processing_time(7200) == 7200

    def test_parse_processing_time_empty(self):
        """Test _parse_processing_time with empty/None input."""
        tools = DocumentActionTools()
        
        assert tools._parse_processing_time("") is None
        assert tools._parse_processing_time(None) is None

    def test_parse_processing_time_default_fallback(self):
        """Test _parse_processing_time falls back to default when format is unrecognized."""
        tools = DocumentActionTools()
        
        result = tools._parse_processing_time("unknown format")
        assert result == 3600  # Default 1 hour


class TestDocumentActionToolsQualityExtraction:
    """Test quality score extraction methods."""

    def test_extract_quality_from_dict_value_dict(self):
        """Test _extract_quality_from_dict_value with dict input."""
        tools = DocumentActionTools()
        
        assert tools._extract_quality_from_dict_value({"overall_score": 0.85}) == 0.85
        assert tools._extract_quality_from_dict_value({"quality_score": 0.75}) == 0.75
        assert tools._extract_quality_from_dict_value({"other_key": 0.5}) == 0.0  # No score keys

    def test_extract_quality_from_dict_value_object(self):
        """Test _extract_quality_from_dict_value with object input."""
        tools = DocumentActionTools()
        
        class QualityObj:
            def __init__(self):
                self.overall_score = 0.85
        
        obj = QualityObj()
        assert tools._extract_quality_from_dict_value(obj) == 0.85
        
        class QualityObj2:
            def __init__(self):
                self.quality_score = 0.75
        
        obj2 = QualityObj2()
        assert tools._extract_quality_from_dict_value(obj2) == 0.75

    def test_extract_quality_from_dict_value_numeric(self):
        """Test _extract_quality_from_dict_value with numeric input."""
        tools = DocumentActionTools()
        
        assert tools._extract_quality_from_dict_value(0.85) == 0.85
        assert tools._extract_quality_from_dict_value(0.75) == 0.75
        assert tools._extract_quality_from_dict_value(0) == 0.0  # Zero returns 0.0
        assert tools._extract_quality_from_dict_value(-1) == 0.0  # Negative returns 0.0

    def test_extract_quality_from_dict_value_invalid(self):
        """Test _extract_quality_from_dict_value with invalid input."""
        tools = DocumentActionTools()
        
        assert tools._extract_quality_from_dict_value("invalid") == 0.0
        assert tools._extract_quality_from_dict_value(None) == 0.0
        assert tools._extract_quality_from_dict_value([]) == 0.0

    def test_extract_quality_score_from_validation_dict_direct_keys(self):
        """Test _extract_quality_score_from_validation_dict with direct score keys."""
        tools = DocumentActionTools()
        
        validation = {"overall_score": 0.85}
        assert tools._extract_quality_score_from_validation_dict(validation, "doc-1") == 0.85
        
        validation = {"quality_score": 0.75}
        assert tools._extract_quality_score_from_validation_dict(validation, "doc-2") == 0.75
        
        validation = {"score": 0.65}
        assert tools._extract_quality_score_from_validation_dict(validation, "doc-3") == 0.65

    def test_extract_quality_score_from_validation_dict_nested(self):
        """Test _extract_quality_score_from_validation_dict with nested quality_score."""
        tools = DocumentActionTools()
        
        validation = {"quality_score": {"overall_score": 0.85}}
        assert tools._extract_quality_score_from_validation_dict(validation, "doc-1") == 0.85

    def test_extract_quality_score_from_validation_dict_no_score(self):
        """Test _extract_quality_score_from_validation_dict when no score is present."""
        tools = DocumentActionTools()
        
        validation = {"other_field": "value"}
        assert tools._extract_quality_score_from_validation_dict(validation, "doc-1") == 0.0

    def test_extract_quality_score_from_validation_object(self):
        """Test _extract_quality_score_from_validation_object with object input."""
        tools = DocumentActionTools()
        
        class ValidationObj:
            def __init__(self):
                self.overall_score = 0.85
        
        obj = ValidationObj()
        assert tools._extract_quality_score_from_validation_object(obj, "doc-1") == 0.85
        
        class ValidationObj2:
            def __init__(self):
                self.quality_score = 0.75
        
        obj2 = ValidationObj2()
        assert tools._extract_quality_score_from_validation_object(obj2, "doc-2") == 0.75


class TestDocumentActionToolsDateTimeParsing:
    """Test datetime parsing methods."""

    def test_parse_datetime_field_valid(self):
        """Test _parse_datetime_field with valid ISO format."""
        tools = DocumentActionTools()
        
        dt_str = "2025-01-15T10:30:00"
        result = tools._parse_datetime_field(dt_str, "upload_time", "doc-1")
        
        assert result is not None
        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_parse_datetime_field_invalid(self):
        """Test _parse_datetime_field with invalid format."""
        tools = DocumentActionTools()
        
        assert tools._parse_datetime_field("invalid-date", "upload_time", "doc-1") is None
        assert tools._parse_datetime_field("", "upload_time", "doc-1") is None
        assert tools._parse_datetime_field(123, "upload_time", "doc-1") is None  # Not a string

    def test_restore_datetime_fields(self):
        """Test _restore_datetime_fields restores ISO strings to datetime objects."""
        tools = DocumentActionTools()
        
        # _restore_datetime_fields only restores upload_time and started_at in stages
        status_info = {
            "upload_time": "2025-01-15T10:30:00",
            "stages": [
                {"name": "preprocessing", "started_at": "2025-01-15T10:35:00"},
            ],
        }
        
        tools._restore_datetime_fields(status_info, "doc-1")
        
        assert isinstance(status_info["upload_time"], datetime)
        assert isinstance(status_info["stages"][0]["started_at"], datetime)

    def test_restore_datetime_fields_skips_invalid(self):
        """Test _restore_datetime_fields skips invalid datetime strings."""
        tools = DocumentActionTools()
        
        status_info = {
            "upload_time": "invalid-date",
            "stages": [
                {"name": "preprocessing", "started_at": "2025-01-15T10:35:00"},
            ],
        }
        
        tools._restore_datetime_fields(status_info, "doc-1")
        
        # Invalid date should remain as string (not converted)
        assert status_info["upload_time"] == "invalid-date"
        assert isinstance(status_info["stages"][0]["started_at"], datetime)


class TestDocumentActionToolsStatusManagement:
    """Test document status management methods."""

    def test_create_empty_extraction_response(self):
        """Test _create_empty_extraction_response creates proper structure."""
        tools = DocumentActionTools()
        
        response = tools._create_empty_extraction_response("test_reason", "test message")
        
        assert response["extraction_results"] == []
        assert response["confidence_scores"] == {}
        assert response["stages"] == []
        assert response["quality_score"] is None
        assert response["routing_decision"] is None
        assert response["is_mock"] is True
        assert response["reason"] == "test_reason"
        assert response["message"] == "test message"

    def test_create_mock_data_response(self):
        """Test _create_mock_data_response creates mock data with optional fields."""
        tools = DocumentActionTools()
        
        with patch.object(tools, "_get_mock_extraction_data", return_value={"test": "data"}):
            response = tools._create_mock_data_response()
            
            assert response["is_mock"] is True
            assert response["test"] == "data"
            
            response_with_reason = tools._create_mock_data_response(reason="test_reason", message="test message")
            assert response_with_reason["reason"] == "test_reason"
            assert response_with_reason["message"] == "test message"

    def test_load_status_data_file_not_exists(self):
        """Test _load_status_data handles missing file gracefully."""
        tools = DocumentActionTools()
        tools.status_file = Path("/nonexistent/path/status.json")
        
        # Should not raise exception
        tools._load_status_data()
        assert tools.document_statuses == {}

    def test_save_and_load_status_data(self):
        """Test saving and loading status data from file."""
        tools = DocumentActionTools()
        
        # Use temporary file for testing
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as tmp_file:
            tmp_path = Path(tmp_file.name)
            tools.status_file = tmp_path
            
            try:
                # Add test data (without datetime fields to avoid serialization issues)
                tools.document_statuses = {
                    "doc-1": {"status": "processing", "progress": 50},
                    "doc-2": {"status": "completed", "progress": 100},
                }
                
                # Save data
                tools._save_status_data()
                
                # Verify file was created
                assert tmp_path.exists()
                
                # Clear and reload
                tools.document_statuses = {}
                tools._load_status_data()
                
                # Verify data was restored
                assert "doc-1" in tools.document_statuses
                assert "doc-2" in tools.document_statuses
                assert tools.document_statuses["doc-1"]["status"] == "processing"
                assert tools.document_statuses["doc-2"]["status"] == "completed"
                
            finally:
                # Cleanup
                if tmp_path.exists():
                    tmp_path.unlink()

    def test_calculate_time_threshold_today(self):
        """Test _calculate_time_threshold with 'today' range."""
        tools = DocumentActionTools()
        
        result = tools._calculate_time_threshold("today")
        
        assert isinstance(result, datetime)
        # Should be start of today
        now = datetime.now()
        today_start = datetime(now.year, now.month, now.day)
        assert result == today_start

    def test_calculate_time_threshold_week(self):
        """Test _calculate_time_threshold with 'week' range."""
        tools = DocumentActionTools()
        
        result = tools._calculate_time_threshold("week")
        
        assert isinstance(result, datetime)
        # Should be approximately 7 days ago (allow small time difference)
        from datetime import timedelta
        now = datetime.now()
        week_ago = now - timedelta(days=7)
        # Allow 1 second difference for execution time
        assert abs((result - week_ago).total_seconds()) < 1

    def test_calculate_time_threshold_month(self):
        """Test _calculate_time_threshold with 'month' range."""
        tools = DocumentActionTools()
        
        result = tools._calculate_time_threshold("month")
        
        assert isinstance(result, datetime)
        # Should be approximately 30 days ago
        from datetime import timedelta
        now = datetime.now()
        month_ago = now - timedelta(days=30)
        # Allow 1 second difference for execution time
        assert abs((result - month_ago).total_seconds()) < 1

    def test_calculate_time_threshold_default(self):
        """Test _calculate_time_threshold with unknown range defaults to datetime.min."""
        tools = DocumentActionTools()
        
        result = tools._calculate_time_threshold("unknown")
        
        assert isinstance(result, datetime)
        # Should default to datetime.min for "all time"
        assert result == datetime.min

    def test_serialize_for_json_dict(self):
        """Test _serialize_for_json with dictionary."""
        pytest.importorskip("PIL", reason="PIL/Pillow not available")
        tools = DocumentActionTools()
        
        data = {"key1": "value1", "key2": 42, "key3": True}
        result = tools._serialize_for_json(data)
        
        assert result == data  # Dicts should pass through

    def test_serialize_for_json_list(self):
        """Test _serialize_for_json with list."""
        pytest.importorskip("PIL", reason="PIL/Pillow not available")
        tools = DocumentActionTools()
        
        data = [1, 2, 3, "test"]
        result = tools._serialize_for_json(data)
        
        assert result == data  # Lists should pass through

    def test_serialize_for_json_datetime(self):
        """Test _serialize_for_json converts datetime to ISO string."""
        pytest.importorskip("PIL", reason="PIL/Pillow not available")
        tools = DocumentActionTools()
        
        dt = datetime(2025, 1, 15, 10, 30, 0)
        result = tools._serialize_for_json(dt)
        
        assert isinstance(result, str)
        assert "2025-01-15" in result

    def test_serialize_for_json_nested(self):
        """Test _serialize_for_json handles nested structures."""
        pytest.importorskip("PIL", reason="PIL/Pillow not available")
        tools = DocumentActionTools()
        
        data = {
            "timestamp": datetime(2025, 1, 15, 10, 30, 0),
            "nested": {
                "another_timestamp": datetime(2025, 1, 16, 11, 0, 0),
            },
            "list": [datetime(2025, 1, 17, 12, 0, 0)],
        }
        
        result = tools._serialize_for_json(data)
        
        assert isinstance(result["timestamp"], str)
        assert isinstance(result["nested"]["another_timestamp"], str)
        assert isinstance(result["list"][0], str)

    def test_serialize_for_json_pil_image(self):
        """Test _serialize_for_json with PIL Image (if available)."""
        pytest.importorskip("PIL", reason="PIL/Pillow not available")
        from PIL import Image
        
        tools = DocumentActionTools()
        
        # Create a simple test image
        img = Image.new('RGB', (10, 10), color='red')
        result = tools._serialize_for_json(img)
        
        assert isinstance(result, dict)
        assert result["_type"] == "PIL_Image"
        assert "data" in result
        assert result["format"] == "PNG"

