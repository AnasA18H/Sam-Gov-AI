#!/usr/bin/env python3
"""
Manual test script for DocumentExtractor
Run this to test document extraction functionality
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from backend.app.services.document_extractor import DocumentExtractor
from backend.app.core.config import settings

def test_extractor(file_path: str, opportunity_id: int = 999, document_id: int = 999):
    """
    Test document extractor with a file
    
    Args:
        file_path: Path to the document file to test
        opportunity_id: Test opportunity ID (for debug folder)
        document_id: Test document ID (for debug file naming)
    """
    print("=" * 80)
    print("DOCUMENT EXTRACTOR TEST")
    print("=" * 80)
    print()
    
    # Check if file exists
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        print(f"❌ ERROR: File not found: {file_path}")
        print(f"   Please provide a valid file path.")
        return
    
    print(f"📄 Testing file: {file_path}")
    print(f"   File size: {file_path_obj.stat().st_size:,} bytes")
    print(f"   File type: {file_path_obj.suffix}")
    print()
    
    # Initialize extractor
    extractor = DocumentExtractor()
    
    print("🔍 Starting extraction...")
    print()
    
    try:
        # Extract text
        result = extractor.extract_text_robustly(
            file_path=file_path,
            opportunity_id=opportunity_id,
            document_id=document_id
        )
        
        # Display results
        print("=" * 80)
        print("EXTRACTION RESULTS")
        print("=" * 80)
        print()
        print(f"✅ Extraction Method Used: {result['method_used']}")
        print(f"📊 Quality Score: {result['quality_score']:.2f}/100")
        print(f"📏 Text Length: {len(result['text']):,} characters")
        print()
        
        # Show all extraction attempts
        if result.get('all_results'):
            print("=" * 80)
            print("ALL EXTRACTION ATTEMPTS:")
            print("=" * 80)
            for attempt in result['all_results']:
                print(f"  • {attempt['method']}:")
                print(f"    - Quality: {attempt['quality_score']:.2f}/100")
                print(f"    - Length: {attempt['length']:,} characters")
            print()
        
        # Show text preview
        text = result['text']
        if text:
            print("=" * 80)
            print("EXTRACTED TEXT PREVIEW (first 500 characters):")
            print("=" * 80)
            print(text[:500])
            if len(text) > 500:
                print(f"\n... ({len(text) - 500:,} more characters)")
            print()
        else:
            print("⚠️  WARNING: No text extracted!")
            print()
        
        # Check debug extract
        debug_dir = settings.DEBUG_EXTRACTS_DIR / f"opportunity_{opportunity_id}"
        if debug_dir.exists():
            debug_files = list(debug_dir.glob(f"{document_id}_*_extracted.txt"))
            if debug_files:
                print("=" * 80)
                print("DEBUG EXTRACT SAVED:")
                print("=" * 80)
                for debug_file in debug_files:
                    print(f"  ✅ {debug_file}")
                print()
        
        # Test CLIN extraction if PDF
        if file_path_obj.suffix.lower() == '.pdf':
            print("=" * 80)
            print("TESTING CLIN TABLE EXTRACTION:")
            print("=" * 80)
            try:
                clin_tables = extractor.extract_clin_tables(file_path_obj)
                if clin_tables:
                    print(f"✅ Found {len(clin_tables)} CLIN table rows")
                    print()
                    print("First few rows:")
                    for i, row in enumerate(clin_tables[:3], 1):
                        print(f"  Row {i}: {row}")
                else:
                    print("ℹ️  No CLIN tables found (this is normal for non-SF1449 documents)")
            except Exception as e:
                print(f"⚠️  CLIN extraction error: {str(e)}")
            print()
        
        # Test SF1449 field extraction if PDF
        if file_path_obj.suffix.lower() == '.pdf' and text:
            print("=" * 80)
            print("TESTING SF1449 FIELD EXTRACTION:")
            print("=" * 80)
            try:
                sf1449_fields = extractor.extract_sf1449_fields(text)
                if sf1449_fields:
                    print("✅ Found SF1449 fields:")
                    for field, value in sf1449_fields.items():
                        print(f"  • {field}: {value}")
                else:
                    print("ℹ️  No SF1449 fields found (this is normal for non-SF1449 documents)")
            except Exception as e:
                print(f"⚠️  SF1449 extraction error: {str(e)}")
            print()
        
        print("=" * 80)
        print("✅ TEST COMPLETED SUCCESSFULLY")
        print("=" * 80)
        
    except Exception as e:
        print("=" * 80)
        print("❌ EXTRACTION FAILED")
        print("=" * 80)
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()


def list_available_test_files():
    """List available test files in the documents directory"""
    print("=" * 80)
    print("AVAILABLE TEST FILES")
    print("=" * 80)
    print()
    
    # Check backend/data/documents for any files
    documents_dir = Path("backend/data/documents")
    if documents_dir.exists():
        print(f"📁 Checking: {documents_dir}")
        print()
        
        # Find all PDF, DOC, DOCX, XLS, XLSX, TXT files
        test_files = []
        for ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.txt']:
            test_files.extend(documents_dir.rglob(f'*{ext}'))
        
        if test_files:
            print(f"Found {len(test_files)} test files:")
            for i, file_path in enumerate(test_files[:10], 1):  # Show first 10
                try:
                    rel_path = file_path.relative_to(Path.cwd())
                except ValueError:
                    rel_path = file_path
                print(f"  {i}. {rel_path} ({file_path.stat().st_size:,} bytes)")
            if len(test_files) > 10:
                print(f"  ... and {len(test_files) - 10} more files")
        else:
            print("  No test files found in documents directory")
            print()
            print("💡 TIP: You can:")
            print("  1. Download a document from SAM.gov first")
            print("  2. Place a test file in backend/data/documents/")
            print("  3. Provide a full path to any document file")
    else:
        print(f"  Directory not found: {documents_dir}")
    
    print()


if __name__ == "__main__":
    print()
    
    # Check for command line argument
    if len(sys.argv) > 1:
        file_path = sys.argv[1]
        opportunity_id = int(sys.argv[2]) if len(sys.argv) > 2 else 999
        document_id = int(sys.argv[3]) if len(sys.argv) > 3 else 999
        test_extractor(file_path, opportunity_id, document_id)
    else:
        # Show available files and instructions
        list_available_test_files()
        print("=" * 80)
        print("USAGE")
        print("=" * 80)
        print()
        print("Run this script with a file path:")
        print()
        print("  python test_extractor.py <file_path> [opportunity_id] [document_id]")
        print()
        print("Examples:")
        print("  python test_extractor.py backend/data/documents/123/document.pdf")
        print("  python test_extractor.py /path/to/test.pdf 123 456")
        print("  python test_extractor.py test_document.docx")
        print()
        print("=" * 80)
