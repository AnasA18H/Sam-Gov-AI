#!/usr/bin/env python3
"""
Comprehensive test script for both Phase 1 and Phase 2:
- Phase 1: Document Extraction (extract manufacturers/dealers from documents)
- Phase 2: External Research (LLM-guided web search)
Usage: python test_phase2_external_research.py [opportunity_id]
Example: python test_phase2_external_research.py 205
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
from app.models.manufacturer import Manufacturer, ResearchStatus
from app.models.dealer import Dealer
from app.services.research_service import save_extracted_manufacturers, save_extracted_dealers, save_external_dealers
from app.services.llm_external_research_service import LLMExternalResearchService
from app.services.document_analyzer import DocumentAnalyzer
from app.core.config import settings
from sqlalchemy.orm import joinedload
import json
from datetime import datetime

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


def test_phase1_document_extraction(db, opportunity_id: int, opportunity: Opportunity):
    """Test Phase 1: Extract manufacturers/dealers from documents
    
    Returns:
        tuple: (manufacturers_data, dealers_data, clins)
    """
    print_section("PHASE 1: DOCUMENT EXTRACTION")
    
    # Get documents
    documents = db.query(Document).filter(Document.opportunity_id == opportunity_id).all()
    
    if not documents:
        print("⚠️  WARNING: No documents found. Cannot test Phase 1 extraction.")
        return None, None, None
    
    print_subsection("Documents Found")
    print(f"  Total Documents: {len(documents)}")
    for i, doc in enumerate(documents, 1):
        print(f"  [{i}] {doc.file_name} ({doc.file_type})")
    
    # Get CLINs for context
    clins = db.query(CLIN).filter(CLIN.opportunity_id == opportunity_id).all()
    print_subsection("CLINs for Context")
    print(f"  Total CLINs: {len(clins)}")
    for i, clin in enumerate(clins, 1):
        print(f"  [{i}] CLIN {clin.clin_number}: {clin.product_name}")
        print(f"      Part Number: {clin.part_number}")
        print(f"      Manufacturer: {clin.manufacturer_name}")
    
    # Load document texts
    print_subsection("Extracting Text from Documents")
    analyzer = DocumentAnalyzer()
    document_texts = []
    
    for doc in documents:
        try:
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
        print("❌ ERROR: No document texts extracted. Cannot proceed with Phase 1.")
        return None, None, None
    
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
    
    # Run Phase 1 extraction (CLINs, deadlines, manufacturers, dealers all together)
    print_subsection("Running Phase 1: LLM Extraction from Documents")
    print("  This may take a minute...")
    print("  Extracting CLINs, deadlines, manufacturers, and dealers together...")
    
    from app.services.document_analyzer import DocumentAnalyzer
    analyzer = DocumentAnalyzer()
    
    # Extract everything together (CLINs, deadlines, manufacturers, dealers)
    clins_data, deadlines_data, manufacturers_data, dealers_data = analyzer.extract_clins_batch(document_texts)
    
    print(f"  ✅ Phase 1 extraction complete!")
    print(f"     CLINs found: {len(clins_data)}")
    print(f"     Deadlines found: {len(deadlines_data)}")
    print(f"     Manufacturers found: {len(manufacturers_data)}")
    print(f"     Dealers found: {len(dealers_data)}")
    
    # Display Phase 1 results
    print_subsection("Phase 1 Results: Manufacturers")
    for i, mfg in enumerate(manufacturers_data, 1):
        print(f"  [{i}] {mfg.get('name', 'N/A')}")
        print(f"      CAGE Code: {mfg.get('cage_code', 'N/A')}")
        print(f"      Part Number: {mfg.get('part_number', 'N/A')}")
        print(f"      NSN: {mfg.get('nsn', 'N/A')}")
        print(f"      Source Location: {mfg.get('source_location', 'N/A')}")
    
    print_subsection("Phase 1 Results: Dealers")
    for i, dealer in enumerate(dealers_data, 1):
        print(f"  [{i}] {dealer.get('company_name', 'N/A')}")
        print(f"      Part Number: {dealer.get('part_number', 'N/A')}")
        print(f"      Manufacturer: {dealer.get('manufacturer_name', 'N/A')}")
        print(f"      Source Location: {dealer.get('source_location', 'N/A')}")
    
    # Ask if user wants to save Phase 1 results
    print_subsection("Save Phase 1 Results?")
    save_phase1 = input("  Save manufacturers/dealers to database? (yes/no, default: yes): ").strip().lower()
    
    if save_phase1 not in ['no', 'n']:
        # Save Phase 1 results
        saved_manufacturers = []
        saved_dealers = []
        
        if manufacturers_data:
            saved_manufacturers = save_extracted_manufacturers(
                db=db,
                opportunity_id=opportunity_id,
                manufacturers=manufacturers_data,
                clins=clins
            )
            print(f"  ✅ Saved {len(saved_manufacturers)} manufacturers to database")
        
        if dealers_data:
            saved_manufacturers_list = db.query(Manufacturer).filter(
                Manufacturer.opportunity_id == opportunity_id
            ).all()
            saved_dealers = save_extracted_dealers(
                db=db,
                opportunity_id=opportunity_id,
                dealers=dealers_data,
                manufacturers=saved_manufacturers_list if manufacturers_data else None,
                clins=clins
            )
            print(f"  ✅ Saved {len(saved_dealers)} dealers to database")
        
        print(f"\n  ✅ Phase 1 complete! Ready for Phase 2.")
        return saved_manufacturers, saved_dealers, clins
    else:
        print(f"  ⏭️  Phase 1 results not saved (display only)")
        print(f"  ⚠️  Phase 2 will use existing manufacturers from database")
        return None, None, clins


def test_phase2_external_research(db, opportunity_id: int, manufacturers: list, clins: list):
    """Test Phase 2: External research (LLM-guided web search)
    
    Args:
        db: Database session
        opportunity_id: Opportunity ID
        manufacturers: List of Manufacturer objects to research
        clins: List of CLIN objects for context
    """
    print_section("PHASE 2: EXTERNAL RESEARCH (LLM-GUIDED)")
    
    if not manufacturers:
        print("⚠️  WARNING: No manufacturers provided for Phase 2.")
        return
    
    print(f"  Researching {len(manufacturers)} manufacturer(s)...")
    print("  This will:")
    print("    1. Use LLM to determine search strategy")
    print("    2. Find manufacturer's official website")
    print("    3. Extract sales contact email")
    print("    4. Find top 8 authorized dealers")
    print("    5. Extract dealer contact info and pricing")
    print("\n  ⚠️  This will perform actual web searches and may take several minutes...")
    
    user_input = input("\n  Continue with Phase 2? (yes/no): ").strip().lower()
    if user_input not in ['yes', 'y']:
        print("  ❌ Phase 2 cancelled by user")
        return
    
    # Load reference material
    print_subsection("Loading Online Search Guide")
    reference_text = None
    try:
        reference_file = Path(settings.PROJECT_ROOT) / "extras" / "ONLINE_SEARCH_GUIDE.md"
        if reference_file.exists():
            with open(reference_file, 'r', encoding='utf-8') as f:
                reference_text = f.read()
            print(f"  ✅ Loaded online search guide: {len(reference_text)} characters")
        else:
            print(f"  ⚠️  Reference file not found: {reference_file}")
    except Exception as ref_error:
        print(f"  ⚠️  Failed to load online search guide: {str(ref_error)}")
    
    clin_part_map = {clin.id: clin.part_number for clin in clins if clin.part_number}
    
    # Research each manufacturer
    with LLMExternalResearchService() as research_service:
        for mfg_idx, manufacturer in enumerate(manufacturers, 1):
            try:
                print_subsection(f"Researching Manufacturer {mfg_idx}/{len(manufacturers)}: {manufacturer.name}")
                
                # Get part number from CLIN if not in manufacturer
                part_number = manufacturer.part_number
                if not part_number and manufacturer.clin_id and manufacturer.clin_id in clin_part_map:
                    part_number = clin_part_map[manufacturer.clin_id]
                
                print(f"  Part Number: {part_number or 'Not available'}")
                print(f"  NSN: {manufacturer.nsn or 'Not available'}")
                print(f"  CAGE Code: {manufacturer.cage_code or 'Not available'}")
                print(f"\n  🔍 Starting LLM-guided research...")
                
                # Research manufacturer and dealers
                research_results = research_service.research_manufacturer_and_dealers(
                    manufacturer=manufacturer,
                    part_number=part_number,
                    nsn=manufacturer.nsn,
                    reference_text=reference_text
                )
                
                # Display manufacturer results
                mfg_results = research_results.get('manufacturer', {})
                print(f"\n  ✅ Manufacturer Research Complete:")
                print(f"     Website: {mfg_results.get('website', 'Not found')}")
                print(f"     Contact Email: {mfg_results.get('contact_email', 'Not found')}")
                print(f"     Contact Phone: {mfg_results.get('contact_phone', 'Not found')}")
                print(f"     Address: {mfg_results.get('address', 'Not found')}")
                print(f"     SAM.gov Verified: {mfg_results.get('sam_gov_verified', False)}")
                print(f"     Website Verified: {mfg_results.get('website_verified', False)}")
                
                # Display dealer results
                dealers_found = research_results.get('dealers', [])
                print(f"\n  ✅ Dealers Found: {len(dealers_found)}")
                
                if dealers_found:
                    print(f"\n  Top {len(dealers_found)} Dealers:")
                    for i, dealer in enumerate(dealers_found, 1):
                        print(f"\n  [{i}] {dealer.get('company_name', 'N/A')}")
                        print(f"      Website: {dealer.get('website', 'N/A')}")
                        print(f"      Contact Email: {dealer.get('contact_email', 'N/A')}")
                        print(f"      Pricing: {dealer.get('pricing', 'Not available')}")
                        print(f"      Stock Status: {dealer.get('stock_status', 'Unknown')}")
                        print(f"      Rank Score: {dealer.get('rank_score', 'N/A')}")
                        print(f"      SAM.gov Verified: {dealer.get('sam_gov_verified', False)}")
                        print(f"      Manufacturer Authorized: {dealer.get('manufacturer_authorized', 'Unknown')}")
                else:
                    print("     No dealers found")
                
                # Ask if user wants to save results
                print(f"\n  💾 Save Phase 2 results to database?")
                save_input = input("  (yes/no, default: yes): ").strip().lower()
                
                if save_input not in ['no', 'n']:
                    # Update manufacturer
                    if mfg_results.get('website'):
                        manufacturer.website = mfg_results['website']
                        manufacturer.website_verified = mfg_results.get('website_verified', False)
                        manufacturer.website_verification_date = datetime.utcnow()
                    
                    if mfg_results.get('contact_email'):
                        manufacturer.contact_email = mfg_results['contact_email']
                    
                    if mfg_results.get('contact_phone'):
                        manufacturer.contact_phone = mfg_results['contact_phone']
                    
                    if mfg_results.get('address'):
                        manufacturer.address = mfg_results['address']
                    
                    if mfg_results.get('sam_gov_verified'):
                        manufacturer.sam_gov_verified = True
                        manufacturer.sam_gov_verification_date = datetime.utcnow()
                    
                    manufacturer.research_source = "document_extraction,external_search"
                    manufacturer.research_status = ResearchStatus.COMPLETED
                    manufacturer.research_completed_at = datetime.utcnow()
                    
                    if manufacturer.additional_data:
                        manufacturer.additional_data.pop('needs_external_research', None)
                    
                    db.commit()
                    print(f"  ✅ Manufacturer updated in database")
                    
                    # Save dealers
                    if dealers_found:
                        saved_dealers = save_external_dealers(
                            db=db,
                            opportunity_id=opportunity_id,
                            dealers=dealers_found,
                            manufacturer=manufacturer,
                            clins=clins
                        )
                        print(f"  ✅ Saved {len(saved_dealers)} dealers to database")
                else:
                    print(f"  ⏭️  Results not saved (display only)")
                
                # Rate limiting between manufacturers
                if mfg_idx < len(manufacturers):
                    print(f"\n  ⏳ Waiting 5 seconds before next manufacturer...")
                    import time
                    time.sleep(5)
            
            except Exception as mfg_error:
                print(f"\n  ❌ Error researching manufacturer {manufacturer.name}: {str(mfg_error)}")
                import traceback
                traceback.print_exc()
                continue


def test_both_phases(opportunity_id: int):
    """Test both Phase 1 and Phase 2 for an opportunity
    
    Args:
        opportunity_id: The ID of the opportunity to test
    """
    db = SessionLocal()
    
    try:
        # 1. Read Opportunity from database
        print_section(f"OPPORTUNITY {opportunity_id} - COMPREHENSIVE TEST (PHASE 1 + PHASE 2)")
        
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
        print(f"  Title: {opportunity.title}")
        print(f"  Status: {opportunity.status}")
        print(f"  Notice ID: {opportunity.notice_id}")
        
        # Check existing manufacturers
        existing_manufacturers = db.query(Manufacturer).filter(
            Manufacturer.opportunity_id == opportunity_id
        ).all()
        
        print_subsection("Existing Data in Database")
        print(f"  Existing Manufacturers: {len(existing_manufacturers)}")
        print(f"  Existing Dealers: {len(opportunity.dealers)}")
        print(f"  Existing CLINs: {len(opportunity.clins)}")
        print(f"  Existing Documents: {len(opportunity.documents)}")
        
        # Ask user what to do
        print_subsection("Test Options")
        print("  1. Run Phase 1 only (Document Extraction)")
        print("  2. Run Phase 2 only (External Research) - requires Phase 1 completed")
        print("  3. Run both Phase 1 and Phase 2 (Full Test)")
        print("  4. Skip to results summary")
        
        user_choice = input("\n  Choose option (1/2/3/4, default: 3): ").strip() or "3"
        
        manufacturers_for_phase2 = None
        clins = None
        
        if user_choice == "1":
            # Phase 1 only
            manufacturers_data, dealers_data, clins = test_phase1_document_extraction(
                db, opportunity_id, opportunity
            )
            if manufacturers_data:
                manufacturers_for_phase2 = manufacturers_data
            else:
                # Get from database if not saved
                manufacturers_for_phase2 = db.query(Manufacturer).filter(
                    Manufacturer.opportunity_id == opportunity_id,
                    Manufacturer.research_source == "document_extraction"
                ).all()
        
        elif user_choice == "2":
            # Phase 2 only
            manufacturers_for_phase2 = db.query(Manufacturer).filter(
                Manufacturer.opportunity_id == opportunity_id,
                Manufacturer.research_source == "document_extraction"
            ).all()
            
            if not manufacturers_for_phase2:
                print("⚠️  No manufacturers found with research_source='document_extraction'")
                print("   Please run Phase 1 first or choose option 3 to run both phases.")
                return
            
            clins = db.query(CLIN).filter(CLIN.opportunity_id == opportunity_id).all()
            test_phase2_external_research(db, opportunity_id, manufacturers_for_phase2, clins)
        
        elif user_choice == "3":
            # Both phases
            manufacturers_data, dealers_data, clins = test_phase1_document_extraction(
                db, opportunity_id, opportunity
            )
            
            # Get manufacturers for Phase 2
            if manufacturers_data:
                manufacturers_for_phase2 = manufacturers_data
            else:
                manufacturers_for_phase2 = db.query(Manufacturer).filter(
                    Manufacturer.opportunity_id == opportunity_id,
                    Manufacturer.research_source == "document_extraction"
                ).all()
            
            if manufacturers_for_phase2:
                test_phase2_external_research(db, opportunity_id, manufacturers_for_phase2, clins)
            else:
                print("⚠️  No manufacturers found for Phase 2. Phase 1 may not have saved results.")
        
        elif user_choice == "4":
            # Results summary only
            pass
        else:
            print(f"❌ Invalid choice: {user_choice}")
            return
        
        # Final results summary
        print_section("FINAL RESULTS SUMMARY")
        
        # Refresh from database
        db.refresh(opportunity)
        all_manufacturers = db.query(Manufacturer).filter(
            Manufacturer.opportunity_id == opportunity_id
        ).all()
        
        all_dealers = db.query(Dealer).filter(
            Dealer.opportunity_id == opportunity_id
        ).all()
        
        print_subsection("Manufacturers")
        print(f"  Total: {len(all_manufacturers)}")
        phase1_mfgs = [m for m in all_manufacturers if m.research_source == "document_extraction"]
        phase2_mfgs = [m for m in all_manufacturers if m.research_source and "external_search" in m.research_source]
        print(f"  From Phase 1 (documents): {len(phase1_mfgs)}")
        print(f"  From Phase 2 (external): {len(phase2_mfgs)}")
        
        for mfg in all_manufacturers:
            print(f"\n  • {mfg.name}")
            print(f"    Source: {mfg.research_source or 'None'}")
            print(f"    Website: {mfg.website or 'Not found'}")
            print(f"    Email: {mfg.contact_email or 'Not found'}")
        
        print_subsection("Dealers")
        print(f"  Total: {len(all_dealers)}")
        phase1_dealers = [d for d in all_dealers if d.research_source == "document_extraction"]
        phase2_dealers = [d for d in all_dealers if d.research_source == "external_search"]
        print(f"  From Phase 1 (documents): {len(phase1_dealers)}")
        print(f"  From Phase 2 (external): {len(phase2_dealers)}")
        
        for dealer in all_dealers[:10]:  # Show first 10
            print(f"\n  • {dealer.company_name}")
            print(f"    Source: {dealer.research_source or 'None'}")
            print(f"    Website: {dealer.website or 'N/A'}")
            print(f"    Email: {dealer.contact_email or 'N/A'}")
            print(f"    Pricing: {dealer.pricing_info or 'Not available'}")
        
        if len(all_dealers) > 10:
            print(f"\n  ... and {len(all_dealers) - 10} more dealers")
        
        print_section("TEST COMPLETE")
        print("✅ Comprehensive test completed!")
        
    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Comprehensive test for Phase 1 (document extraction) and Phase 2 (external research)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python test_phase2_external_research.py 205    # Test opportunity 205 (both phases)
  python test_phase2_external_research.py 123    # Test opportunity 123 (both phases)
        """
    )
    parser.add_argument(
        "opportunity_id",
        type=int,
        nargs="?",
        help="The ID of the opportunity to test (default: 205)"
    )
    
    args = parser.parse_args()
    
    # Get opportunity ID (default to 205 if not provided)
    opportunity_id = args.opportunity_id if args.opportunity_id is not None else 205
    
    # Validate opportunity ID
    if opportunity_id <= 0:
        print(f"❌ ERROR: Invalid opportunity ID: {opportunity_id}")
        print("   Opportunity ID must be a positive integer")
        sys.exit(1)
    
    # Run the comprehensive test
    test_both_phases(opportunity_id)
