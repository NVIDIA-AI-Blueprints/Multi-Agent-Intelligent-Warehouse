#!/bin/bash
# Run comprehensive quality assessment with log analysis

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$PROJECT_ROOT"

echo "🚀 Starting Comprehensive Quality Assessment"
echo "=============================================="
echo ""

# Activate virtual environment
if [ -d "env" ]; then
    echo "🔌 Activating virtual environment..."
    source env/bin/activate
else
    echo "❌ Virtual environment not found!"
    exit 1
fi

# Run enhanced quality tests
echo "📊 Running enhanced quality tests with log analysis..."
echo ""
python tests/quality/test_answer_quality_enhanced.py

# Check if tests completed successfully
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Tests completed successfully"
    echo ""
    
    # Generate comprehensive report
    echo "📝 Generating comprehensive quality report..."
    echo ""
    python tests/quality/generate_quality_report.py
    
    if [ $? -eq 0 ]; then
        echo ""
        echo "✅ Quality assessment completed successfully!"
        echo ""
        echo "📄 Report location: docs/analysis/COMPREHENSIVE_QUALITY_REPORT.md"
        echo "📊 Results location: tests/quality/quality_test_results_enhanced.json"
    else
        echo "❌ Failed to generate report"
        exit 1
    fi
else
    echo "❌ Tests failed"
    exit 1
fi

