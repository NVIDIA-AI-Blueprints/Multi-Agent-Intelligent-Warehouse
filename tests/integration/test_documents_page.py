#!/usr/bin/env python3
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
Test script for Documents page functionality.
Tests document upload, status checking, and results retrieval.
"""

import requests
import json
import time
import sys
from pathlib import Path

# Security: HTTP protocol is acceptable for localhost in test environments
# For production deployments, HTTPS must be used to encrypt API communications
# SonarQube may flag HTTP usage, but it's acceptable for:
# - localhost (127.0.0.1, 0.0.0.0) - development/testing only
# Production external services must use HTTPS
BASE_URL = "http://localhost:8001/api/v1/document"

def test_document_analytics():
    """Test document analytics endpoint."""
    print("\n" + "="*60)
    print("TEST 1: Document Analytics")
    print("="*60)
    
    try:
        response = requests.get(f"{BASE_URL}/analytics?time_range=week")
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Status: {response.status_code}")
        print(f"📊 Total Documents: {data['metrics']['total_documents']}")
        print(f"📊 Processed Today: {data['metrics']['processed_today']}")
        print(f"📊 Average Quality: {data['metrics']['average_quality']}")
        print(f"📊 Success Rate: {data['metrics']['success_rate']}%")
        
        return True
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def test_document_status(document_id: str):
    """Test document status endpoint."""
    print("\n" + "="*60)
    print(f"TEST 2: Document Status - {document_id}")
    print("="*60)
    
    try:
        response = requests.get(f"{BASE_URL}/status/{document_id}")
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Status: {response.status_code}")
        print(f"📄 Document ID: {data['document_id']}")
        print(f"📊 Status: {data['status']}")
        print(f"📊 Progress: {data['progress']}%")
        print(f"📊 Current Stage: {data.get('current_stage', 'N/A')}")
        print(f"📊 Stages: {len(data.get('stages', []))}")
        
        for stage in data.get('stages', []):
            print(f"  - {stage['stage_name']}: {stage['status']}")
        
        return data
    except Exception as e:
        print(f"❌ Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return None

def test_document_results(document_id: str):
    """Test document results endpoint."""
    print("\n" + "="*60)
    print(f"TEST 3: Document Results - {document_id}")
    print("="*60)
    
    try:
        response = requests.get(f"{BASE_URL}/results/{document_id}")
        response.raise_for_status()
        data = response.json()
        
        print(f"✅ Status: {response.status_code}")
        print(f"📄 Document ID: {data['document_id']}")
        print(f"📄 Filename: {data.get('filename', 'N/A')}")
        print(f"📄 Document Type: {data.get('document_type', 'N/A')}")
        
        # Check if it's mock data
        extraction_results = data.get('extraction_results', [])
        print(f"📊 Extraction Results: {len(extraction_results)} stages")
        
        # Check for mock data indicators
        is_mock = False
        mock_indicators = [
            "ABC Supply Co.",
            "XYZ Manufacturing",
            "Global Logistics Inc.",
            "Tech Solutions Ltd."
        ]
        
        for result in extraction_results:
            processed_data = result.get('processed_data', {})
            vendor = processed_data.get('vendor', '')
            
            if vendor in mock_indicators:
                is_mock = True
                print(f"⚠️  WARNING: Mock data detected (vendor: {vendor})")
                break
        
        if not is_mock:
            print("✅ Real document data detected")
        
        # Display extraction results
        for i, result in enumerate(extraction_results, 1):
            print(f"\n  Stage {i}: {result.get('stage', 'N/A')}")
            print(f"    Model: {result.get('model_used', 'N/A')}")
            print(f"    Confidence: {result.get('confidence_score', 0):.2f}")
            processed_data = result.get('processed_data', {})
            if processed_data:
                print(f"    Extracted Fields: {list(processed_data.keys())[:5]}...")
        
        # Quality score
        quality_score = data.get('quality_score')
        if quality_score:
            if isinstance(quality_score, dict):
                overall = quality_score.get('overall_score', 0)
            else:
                overall = getattr(quality_score, 'overall_score', 0)
            print(f"\n📊 Quality Score: {overall:.2f}/5.0")
        
        # Routing decision
        routing = data.get('routing_decision')
        if routing:
            if isinstance(routing, dict):
                action = routing.get('routing_action', 'N/A')
            else:
                action = getattr(routing, 'routing_action', 'N/A')
            print(f"📊 Routing Decision: {action}")
        
        return data, is_mock
    except Exception as e:
        print(f"❌ Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"   Response: {e.response.text}")
        return None, False

def get_all_document_ids():
    """Get all document IDs from analytics or status file."""
    document_ids = []
    
    # Try to get from analytics (if available)
    try:
        response = requests.get(f"{BASE_URL}/analytics?time_range=week")
        if response.status_code == 200:
            # Analytics doesn't return document IDs, so we'll check status file
            pass
    except:
        pass
    
    # Check document_statuses.json file
    status_file = Path("document_statuses.json")
    if status_file.exists():
        try:
            with open(status_file, 'r') as f:
                data = json.load(f)
                document_ids = list(data.keys())
        except Exception as e:
            print(f"⚠️  Could not read status file: {e}")
    
    return document_ids

def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("DOCUMENTS PAGE API TEST SUITE")
    print("="*60)
    
    # Test 1: Analytics
    test_document_analytics()
    
    # Get document IDs
    document_ids = get_all_document_ids()
    
    if not document_ids:
        print("\n⚠️  No document IDs found. Please upload a document first.")
        print("   You can upload a document via the UI at http://localhost:3001/documents")
        return
    
    print(f"\n📋 Found {len(document_ids)} document(s)")
    
    # Test with the most recent document (last in list)
    if document_ids:
        latest_doc_id = document_ids[-1]
        print(f"\n🔍 Testing with latest document: {latest_doc_id}")
        
        # Test 2: Status
        status_data = test_document_status(latest_doc_id)
        
        # Test 3: Results
        results_data, is_mock = test_document_results(latest_doc_id)
        
        # Summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        
        if status_data:
            print(f"✅ Status check: PASSED")
            print(f"   Status: {status_data.get('status')}")
            print(f"   Progress: {status_data.get('progress')}%")
        else:
            print(f"❌ Status check: FAILED")
        
        if results_data:
            print(f"✅ Results retrieval: PASSED")
            if is_mock:
                print(f"⚠️  WARNING: Results contain mock/default data")
                print(f"   This indicates the document may not have been fully processed")
                print(f"   or processing results are not being stored correctly.")
            else:
                print(f"✅ Results contain real document data")
        else:
            print(f"❌ Results retrieval: FAILED")
        
        # Test with all documents
        if len(document_ids) > 1:
            print(f"\n📋 Testing all {len(document_ids)} documents...")
            mock_count = 0
            real_count = 0
            
            for doc_id in document_ids:
                _, is_mock = test_document_results(doc_id)
                if is_mock:
                    mock_count += 1
                else:
                    real_count += 1
            
            print(f"\n📊 Summary: {real_count} real, {mock_count} mock/default")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()

