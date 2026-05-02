"""Setup accuracy benchmark fixtures from resumes.

Reads all resumes from Resumes/ folder, runs the pipeline on each,
and saves extracted data as ground truth JSON in tests/accuracy/fixtures/.

Usage:
    python setup_fixtures.py
"""
import asyncio
import json
import shutil
from pathlib import Path

from app.pipeline.runner import run_pipeline

RESUMES_DIR = Path("Resumes")
FIXTURES_DIR = Path("tests/accuracy/fixtures")


async def setup_fixtures():
    """Process all resumes and create ground truth fixtures."""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    
    resume_files = sorted(RESUMES_DIR.glob("*.pdf"))
    if not resume_files:
        print("❌ No PDF files found in Resumes/ folder")
        return
    
    print(f"Found {len(resume_files)} resumes. Processing...\n")
    
    for idx, resume_path in enumerate(resume_files, start=1):
        print(f"[{idx}/{len(resume_files)}] Processing {resume_path.name}...", end=" ")
        
        try:
            # Read resume content
            content = resume_path.read_bytes()
            
            # Run pipeline
            result = await run_pipeline(resume_path.name, content)
            parsed = result.schema.model_dump()
            
            # Create fixture names
            base_name = f"resume_{idx:02d}"
            fixture_resume = FIXTURES_DIR / f"{base_name}.pdf"
            fixture_gt = FIXTURES_DIR / f"{base_name}.gt.json"
            
            # Copy resume to fixtures
            shutil.copy(resume_path, fixture_resume)
            
            # Save extracted data as ground truth
            fixture_gt.write_text(json.dumps(parsed, indent=2, default=str))
            
            print(f"✓ Saved as {base_name}")
            
        except Exception as e:
            print(f"✗ Error: {e}")
            continue
    
    print(f"\n✅ Done! Created {len(list(FIXTURES_DIR.glob('*.gt.json')))} fixtures in tests/accuracy/fixtures/")
    print("\n⚠️  IMPORTANT: Review and manually correct the extracted JSON files!")
    print("   Each *.gt.json should have accurate data before running benchmark.")


if __name__ == "__main__":
    asyncio.run(setup_fixtures())
