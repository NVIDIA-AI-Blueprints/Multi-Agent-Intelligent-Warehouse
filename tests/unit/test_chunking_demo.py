#!/usr/bin/env python3
"""
Simple demonstration of the enhanced chunking service
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.append(str(project_root))

from src.retrieval.vector.chunking_service import ChunkingService

def main():
    """Demonstrate chunking service functionality."""
    print("🔧 Enhanced Chunking Service Demo")
    print("=" * 50)
    
    # Initialize chunking service
    chunking_service = ChunkingService(
        chunk_size=512,
        overlap_size=64,
        min_chunk_size=100
    )
    
    # Sample text for chunking
    sample_text = """
    Forklift Safety Procedures and Equipment Maintenance Guidelines
    
    Before operating any forklift, operators must complete a comprehensive pre-operation inspection checklist.
    This includes checking the hydraulic system, brakes, steering mechanism, and load backrest for any signs of damage or wear.
    All operators must be properly certified and wear appropriate personal protective equipment including hard hats and safety shoes.
    
    When operating the forklift, maintain a safe speed appropriate for the working environment and always look in the direction of travel.
    Never exceed the rated capacity of the forklift and ensure all loads are properly secured before movement.
    Use the horn when approaching intersections and always yield the right of way to pedestrians.
    
    Regular maintenance is crucial for forklift safety and performance. Schedule preventive maintenance every 250 hours of operation or monthly, whichever comes first.
    This includes checking fluid levels, inspecting hydraulic hoses, testing brake systems, and verifying steering responsiveness.
    Keep detailed maintenance logs for all equipment including dates, services performed, and parts replaced.
    
    After operation, park the forklift in designated areas with the forks lowered and parking brake engaged.
    Report any mechanical issues immediately to the maintenance department and tag out equipment that requires repair.
    Follow all lockout/tagout procedures when performing maintenance or repairs.
    
    Training and certification are essential for safe forklift operation. All operators must complete initial training and pass a written and practical examination.
    Refresher training should be conducted annually or whenever there are changes in equipment or procedures.
    Supervisors should conduct regular safety observations and provide feedback to operators.
    """
    
    print(f"Original text length: {len(sample_text)} characters")
    print(f"Target chunk size: 512 tokens")
    print(f"Overlap size: 64 tokens")
    print()
    
    # Create chunks
    chunks = chunking_service.create_chunks(
        text=sample_text,
        source_id="safety_manual_001",
        source_type="manual",
        category="safety",
        section="equipment_operations"
    )
    
    print(f"✅ Created {len(chunks)} chunks")
    print()
    
    # Display chunk details
    for i, chunk in enumerate(chunks):
        print(f"📄 Chunk {i+1}:")
        print(f"   ID: {chunk.metadata.chunk_id}")
        print(f"   Tokens: {chunk.metadata.token_count}")
        print(f"   Characters: {chunk.metadata.char_count}")
        print(f"   Quality Score: {chunk.metadata.quality_score:.2f}")
        print(f"   Keywords: {', '.join(chunk.metadata.keywords[:5])}")
        print(f"   Content Preview: {chunk.content[:150]}...")
        print()
    
    # Display statistics
    stats = chunking_service.get_chunk_statistics(chunks)
    print("📊 Chunk Statistics:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    print()
    print("🎉 Chunking demonstration completed successfully!")

if __name__ == "__main__":
    main()
