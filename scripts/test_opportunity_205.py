#!/usr/bin/env python3
"""
Test script for Opportunity Manufacturer/Dealer Extraction
Reads data from database and tests manufacturer/dealer extraction for any opportunity
Usage: python test_opportunity_205.py [opportunity_id]
Example: python test_opportunity_205.py 205
"""
import sys
import os
import argparse
from pathlib import Path

# Load environment variables from .env file
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)
    print(f"✅ Loaded environment variables from: {env_file}")
else:
    print(f"⚠️  Warning: .env file not found at {env_file}")
    print("   Using default database connection settings")

# Add backend to path
backend_path = project_root / "backend"
sys.path.insert(0, str(backend_path))

from app.core.database import SessionLocal
from app.models.opportunity import Opportunity
from app.models.document import Document
from app.models.clin import CLIN
from app.models.manufacturer import Manufacturer
from app.models.dealer import Dealer
from app.services.research_service import save_extracted_manufacturers, save_extracted_dealers
from app.core.config import settings
from sqlalchemy.orm import joinedload
import json

# Print database connection info
print(f"\n📊 Database Connection Info:")
print(f"   DATABASE_URL: {settings.DATABASE_URL.split('@')[0]}@***")  # Hide password
print(f"   PROJECT_ROOT: {settings.PROJECT_ROOT}\n")


def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_subsection(title: str):
    """Print a formatted subsection header"""
    print(f"\n--- {title} ---")


def test_opportunity_extraction(opportunity_id: int):
    """Test opportunity data and extraction for any opportunity ID
    
    Args:
        opportunity_id: The ID of the opportunity to test
    """
    db = SessionLocal()
    
    try:
        # 1. Read Opportunity from database
        print_section(f"OPPORTUNITY {opportunity_id} - DATABASE DATA")
        
        opportunity = db.query(Opportunity).options(
            joinedload(Opportunity.documents),
            joinedload(Opportunity.clins),
            joinedload(Opportunity.manufacturers),
            joinedload(Opportunity.dealers)
        ).filter(Opportunity.id == opportunity_id).first()
        
        if not opportunity:
            print(f"❌ ERROR: Opportunity {opportunity_id} not found in database!")
            return
        
        print(f"✅ Found Opportunity {opportunity_id}")
        print(f"\nBasic Info:")
        print(f"  ID: {opportunity.id}")
        print(f"  Title: {opportunity.title}")
        print(f"  Notice ID: {opportunity.notice_id}")
        print(f"  Status: {opportunity.status}")
        print(f"  SAM.gov URL: {opportunity.sam_gov_url}")
        print(f"  Agency: {opportunity.agency}")
        print(f"  Solicitation Type: {opportunity.solicitation_type}")
        print(f"  Classification Confidence: {opportunity.classification_confidence}")
        
        # 2. Documents
        print_subsection("Documents")
        documents = opportunity.documents
        print(f"  Total Documents: {len(documents)}")
        for i, doc in enumerate(documents, 1):
            print(f"  [{i}] {doc.file_name}")
            print(f"      Type: {doc.file_type}, Size: {doc.file_size} bytes")
            print(f"      Path: {doc.file_path}")
        
        # 3. CLINs
        print_subsection("CLINs")
        clins = opportunity.clins
        print(f"  Total CLINs: {len(clins)}")
        for i, clin in enumerate(clins, 1):
            print(f"  [{i}] CLIN {clin.clin_number}: {clin.product_name}")
            print(f"      Part Number: {clin.part_number}")
            print(f"      Manufacturer (from CLIN): {clin.manufacturer_name}")
            print(f"      Description: {clin.product_description[:100] if clin.product_description else 'N/A'}...")
        
        # 4. Manufacturers (existing)
        print_subsection("Manufacturers (Existing in DB)")
        manufacturers = opportunity.manufacturers
        print(f"  Total Manufacturers: {len(manufacturers)}")
        for i, mfg in enumerate(manufacturers, 1):
            print(f"  [{i}] {mfg.name}")
            print(f"      CAGE Code: {mfg.cage_code}")
            print(f"      Part Number: {mfg.part_number}")
            print(f"      NSN: {mfg.nsn}")
            print(f"      Research Status: {mfg.research_status}")
            print(f"      Research Source: {mfg.research_source}")
            print(f"      Website: {mfg.website}")
            print(f"      Contact Email: {mfg.contact_email}")
            print(f"      CLIN ID: {mfg.clin_id}")
        
        # 5. Dealers (existing)
        print_subsection("Dealers (Existing in DB)")
        dealers = opportunity.dealers
        print(f"  Total Dealers: {len(dealers)}")
        for i, dealer in enumerate(dealers, 1):
            print(f"  [{i}] {dealer.company_name}")
            print(f"      Part Number: {dealer.part_number}")
            print(f"      NSN: {dealer.nsn}")
            print(f"      Manufacturer: {dealer.manufacturer_id}")
            print(f"      Research Status: {dealer.research_status}")
            print(f"      Research Source: {dealer.research_source}")
            print(f"      Website: {dealer.website}")
            print(f"      CLIN ID: {dealer.clin_id}")
        
        # 6. Test Manufacturer/Dealer Extraction
        print_section("TESTING MANUFACTURER/DEALER EXTRACTION")
        
        if not documents:
            print("⚠️  WARNING: No documents found. Cannot test extraction.")
            return
        
        if not clins:
            print("⚠️  WARNING: No CLINs found. Extraction will proceed without CLIN context.")
        
        # Load document texts
        print_subsection("Loading Document Texts")
        from app.services.document_analyzer import DocumentAnalyzer
        analyzer = DocumentAnalyzer()
        document_texts = []
        
        for doc in documents:
            try:
                # Get absolute file path
                doc_file_path = Path(doc.file_path)
                if not doc_file_path.is_absolute():
                    doc_file_path = Path(settings.PROJECT_ROOT) / doc.file_path
                
                print(f"  Extracting text from: {doc.file_name}")
                text = analyzer.extract_text(doc.file_path)
                if text and text.strip():
                    document_texts.append((doc.file_name, text))
                    print(f"    ✅ Extracted {len(text)} characters")
                else:
                    print(f"    ⚠️  No text extracted")
            except Exception as e:
                print(f"    ❌ Error extracting text: {str(e)}")
        
        if not document_texts:
            print("❌ ERROR: No document texts extracted. Cannot proceed with extraction.")
            return
        
        # Load reference material
        print_subsection("Loading Reference Material")
        reference_text = None
        try:
            reference_file = Path(settings.PROJECT_ROOT) / "extras" / "Dealers_Manufactural.md"
            if reference_file.exists():
                with open(reference_file, 'r', encoding='utf-8') as f:
                    reference_text = f.read()
                print(f"  ✅ Loaded reference material: {len(reference_text)} characters")
            else:
                print(f"  ⚠️  Reference file not found: {reference_file}")
        except Exception as ref_error:
            print(f"  ⚠️  Failed to load reference material: {str(ref_error)}")
        
        # Prepare CLINs for extraction
        print_subsection("Preparing CLIN Context")
        clins_for_extraction = []
        for clin in clins:
            clins_for_extraction.append({
                'clin_number': clin.clin_number,
                'product_name': clin.product_name,
                'part_number': clin.part_number,
                'manufacturer_name': clin.manufacturer_name,
                'nsn': None,
                'product_description': clin.product_description,
            })
        print(f"  ✅ Prepared {len(clins_for_extraction)} CLINs for extraction context")
        
        # Run extraction (CLINs, deadlines, manufacturers, dealers all in one call)
        print_subsection("Running LLM Extraction")
        print("  This may take a minute...")
        print("  Extracting CLINs, deadlines, manufacturers, and dealers together...")
        
        from app.services.document_analyzer import DocumentAnalyzer
        analyzer = DocumentAnalyzer()
        
        # Extract everything together (CLINs, deadlines, manufacturers, dealers)
        clins_data, deadlines_data, manufacturers_data, dealers_data = analyzer.extract_clins_batch(document_texts)
        
        print(f"  ✅ Extraction complete!")
        print(f"     CLINs found: {len(clins_data)}")
        print(f"     Deadlines found: {len(deadlines_data)}")
        print(f"     Manufacturers found: {len(manufacturers_data)}")
        print(f"     Dealers found: {len(dealers_data)}")
        
        # Display results
        print_section("EXTRACTION RESULTS")
        
        print_subsection("Manufacturers Extracted")
        for i, mfg in enumerate(manufacturers_data, 1):
            print(f"  [{i}] {mfg.get('name', 'N/A')}")
            print(f"      CAGE Code: {mfg.get('cage_code', 'N/A')}")
            print(f"      Part Number: {mfg.get('part_number', 'N/A')}")
            print(f"      NSN: {mfg.get('nsn', 'N/A')}")
            print(f"      CLIN Number: {mfg.get('clin_number', 'N/A')}")
            print(f"      Source Location: {mfg.get('source_location', 'N/A')}")
            if mfg.get('notes'):
                print(f"      Notes: {mfg.get('notes', 'N/A')[:100]}...")
        
        print_subsection("Dealers Extracted")
        for i, dealer in enumerate(dealers_data, 1):
            print(f"  [{i}] {dealer.get('company_name', 'N/A')}")
            print(f"      Part Number: {dealer.get('part_number', 'N/A')}")
            print(f"      NSN: {dealer.get('nsn', 'N/A')}")
            print(f"      Manufacturer: {dealer.get('manufacturer_name', 'N/A')}")
            print(f"      CLIN Number: {dealer.get('clin_number', 'N/A')}")
            print(f"      Source Location: {dealer.get('source_location', 'N/A')}")
            if dealer.get('notes'):
                print(f"      Notes: {dealer.get('notes', 'N/A')[:100]}...")
        
        # Option to save results
        print_section("SAVE RESULTS?")
        print("  Extracted manufacturers and dealers are displayed above.")
        print("  To save them to the database, uncomment the save code below.")
        
        # Uncomment to save:
        # if manufacturers_data:
        #     saved_manufacturers = save_extracted_manufacturers(
        #         db=db,
        #         opportunity_id=opportunity_id,
        #         manufacturers=manufacturers_data,
        #         clins=list(clins)
        #     )
        #     print(f"  ✅ Saved {len(saved_manufacturers)} manufacturers to database")
        # 
        # if dealers_data:
        #     saved_manufacturers_list = db.query(Manufacturer).filter(
        #         Manufacturer.opportunity_id == opportunity_id
        #     ).all()
        #     saved_dealers = save_extracted_dealers(
        #         db=db,
        #         opportunity_id=opportunity_id,
        #         dealers=dealers_data,
        #         manufacturers=saved_manufacturers_list if manufacturers_data else None,
        #         clins=list(clins)
        #     )
        #     print(f"  ✅ Saved {len(saved_dealers)} dealers to database")
        
        print_section("TEST COMPLETE")
        print("✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Test manufacturer/dealer extraction for an opportunity",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_opportunity_205.py 205          # Test opportunity 205
  python test_opportunity_205.py 123         # Test opportunity 123
  python test_opportunity_205.py --list      # List all opportunities
        """
    )
    parser.add_argument(
        "opportunity_id",
        type=int,
        nargs="?",
        help="The ID of the opportunity to test (default: 205)"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all opportunities in the database"
    )
    
    args = parser.parse_args()
    
    # If --list flag, show all opportunities
    if args.list:
        db = SessionLocal()
        try:
            opportunities = db.query(Opportunity).order_by(Opportunity.id.desc()).limit(20).all()
            print("\n" + "=" * 80)
            print("  AVAILABLE OPPORTUNITIES")
            print("=" * 80)
            if not opportunities:
                print("  No opportunities found in database.")
            else:
                print(f"\n  Showing {len(opportunities)} most recent opportunities:\n")
                print(f"  {'ID':<6} {'Title':<50} {'Status':<15} {'Notice ID':<20}")
                print("  " + "-" * 95)
                for opp in opportunities:
                    title = (opp.title or "N/A")[:47] + "..." if opp.title and len(opp.title) > 50 else (opp.title or "N/A")
                    notice_id = opp.notice_id or "N/A"
                    print(f"  {opp.id:<6} {title:<50} {opp.status:<15} {notice_id:<20}")
                print("\n  Usage: python test_opportunity_205.py <ID>")
        finally:
            db.close()
        sys.exit(0)
    
    # Get opportunity ID (default to 205 if not provided)
    opportunity_id = args.opportunity_id if args.opportunity_id is not None else 205
    
    # Validate opportunity ID
    if opportunity_id <= 0:
        print(f"❌ ERROR: Invalid opportunity ID: {opportunity_id}")
        print("   Opportunity ID must be a positive integer")
        sys.exit(1)
    
    # Run the test
    test_opportunity_extraction(opportunity_id)
