"""
Research Service - Database persistence for manufacturers and dealers
Simple service to save extracted data from both Phase 1 (documents) and Phase 2 (external research)
"""
import logging
import re
from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from ..models.manufacturer import Manufacturer, ResearchStatus, VerificationStatus
from ..models.dealer import Dealer, ResearchStatus as DealerResearchStatus, VerificationStatus as DealerVerificationStatus
from ..models.clin import CLIN

logger = logging.getLogger(__name__)


def save_extracted_manufacturers(
    db: Session,
    opportunity_id: int,
    manufacturers: List[Dict],
    clins: Optional[List[CLIN]] = None
) -> List[Manufacturer]:
    """
    Save extracted manufacturers to database
    
    Args:
        db: Database session
        opportunity_id: Opportunity ID
        manufacturers: List of manufacturer dicts from LLM extraction
        clins: Optional list of CLIN objects to match manufacturers to
        
    Returns:
        List of created Manufacturer objects
    """
    created_manufacturers = []
    
    # Create a mapping of CLIN numbers to CLIN objects
    clin_map = {}
    if clins:
        for clin in clins:
            clin_map[clin.clin_number] = clin
    
    for mfg_data in manufacturers:
        try:
            # Find associated CLIN if clin_number is provided
            clin_id = None
            if mfg_data.get('clin_number') and mfg_data['clin_number'] in clin_map:
                clin_id = clin_map[mfg_data['clin_number']].id
            
            # Check if manufacturer already exists for this opportunity
            existing = db.query(Manufacturer).filter(
                Manufacturer.opportunity_id == opportunity_id,
                Manufacturer.name == mfg_data['name']
            ).first()
            
            if existing:
                # Update existing manufacturer
                existing.cage_code = mfg_data.get('cage_code') or existing.cage_code
                existing.part_number = mfg_data.get('part_number') or existing.part_number
                existing.nsn = mfg_data.get('nsn') or existing.nsn
                if clin_id:
                    existing.clin_id = clin_id
                existing.research_source = "document_extraction"
                existing.research_status = ResearchStatus.COMPLETED  # Document extraction complete
                existing.research_completed_at = datetime.utcnow()
                # Mark as needing external research if no website/contact info
                if not existing.website or not existing.contact_email:
                    if existing.additional_data is None:
                        existing.additional_data = {}
                    existing.additional_data['needs_external_research'] = True
                if mfg_data.get('source_location'):
                    existing.additional_data = existing.additional_data or {}
                    existing.additional_data['source_location'] = mfg_data['source_location']
                if mfg_data.get('notes'):
                    existing.additional_data = existing.additional_data or {}
                    existing.additional_data['extraction_notes'] = mfg_data['notes']
                created_manufacturers.append(existing)
                logger.info(f"Updated existing manufacturer: {mfg_data['name']}")
            else:
                # Create new manufacturer
                manufacturer = Manufacturer(
                    opportunity_id=opportunity_id,
                    clin_id=clin_id,
                    name=mfg_data['name'],
                    cage_code=mfg_data.get('cage_code'),
                    part_number=mfg_data.get('part_number'),
                    nsn=mfg_data.get('nsn'),
                    research_status=ResearchStatus.COMPLETED,  # Document extraction complete
                    research_source="document_extraction",  # Found in documents
                    verification_status="not_verified",  # Use string value for PostgreSQL enum
                    research_started_at=datetime.utcnow(),
                    research_completed_at=datetime.utcnow(),
                    # Note: website/contact info not found yet - will be searched externally
                    additional_data={
                        'source_location': mfg_data.get('source_location'),
                        'extraction_notes': mfg_data.get('notes'),
                        'needs_external_research': True,  # Flag for external search
                    } if mfg_data.get('source_location') or mfg_data.get('notes') else {'needs_external_research': True}
                )
                db.add(manufacturer)
                created_manufacturers.append(manufacturer)
                logger.info(f"Created manufacturer: {mfg_data['name']} (CAGE: {mfg_data.get('cage_code')})")
        
        except Exception as e:
            logger.error(f"Error saving manufacturer {mfg_data.get('name')}: {str(e)}")
            continue
    
    db.commit()
    return created_manufacturers


def save_extracted_dealers(
    db: Session,
    opportunity_id: int,
    dealers: List[Dict],
    manufacturers: Optional[List[Manufacturer]] = None,
    clins: Optional[List[CLIN]] = None
) -> List[Dealer]:
    """
    Save extracted dealers to database
    
    Args:
        db: Database session
        opportunity_id: Opportunity ID
        dealers: List of dealer dicts from LLM extraction
        manufacturers: Optional list of Manufacturer objects to match dealers to
        clins: Optional list of CLIN objects to match dealers to
        
    Returns:
        List of created Dealer objects
    """
    created_dealers = []
    
    # Create mappings
    manufacturer_map = {}
    if manufacturers:
        for mfg in manufacturers:
            manufacturer_map[mfg.name.lower()] = mfg
    
    clin_map = {}
    if clins:
        for clin in clins:
            clin_map[clin.clin_number] = clin
    
    for dealer_data in dealers:
        try:
            # Find associated manufacturer if manufacturer_name is provided
            manufacturer_id = None
            if dealer_data.get('manufacturer_name'):
                mfg_name_lower = dealer_data['manufacturer_name'].lower()
                if mfg_name_lower in manufacturer_map:
                    manufacturer_id = manufacturer_map[mfg_name_lower].id
            
            # Find associated CLIN if clin_number is provided
            clin_id = None
            if dealer_data.get('clin_number') and dealer_data['clin_number'] in clin_map:
                clin_id = clin_map[dealer_data['clin_number']].id
            
            # Check if dealer already exists for this opportunity
            existing = db.query(Dealer).filter(
                Dealer.opportunity_id == opportunity_id,
                Dealer.company_name == dealer_data['company_name']
            ).first()
            
            if existing:
                # Update existing dealer
                existing.part_number = dealer_data.get('part_number') or existing.part_number
                existing.nsn = dealer_data.get('nsn') or existing.nsn
                if manufacturer_id:
                    existing.manufacturer_id = manufacturer_id
                if clin_id:
                    existing.clin_id = clin_id
                existing.research_source = "document_extraction"
                existing.research_status = DealerResearchStatus.COMPLETED
                existing.research_completed_at = datetime.utcnow()
                if dealer_data.get('source_location'):
                    existing.additional_data = existing.additional_data or {}
                    existing.additional_data['source_location'] = dealer_data['source_location']
                if dealer_data.get('notes'):
                    existing.additional_data = existing.additional_data or {}
                    existing.additional_data['extraction_notes'] = dealer_data['notes']
                created_dealers.append(existing)
                logger.info(f"Updated existing dealer: {dealer_data['company_name']}")
            else:
                # Create new dealer
                dealer = Dealer(
                    opportunity_id=opportunity_id,
                    clin_id=clin_id,
                    manufacturer_id=manufacturer_id,
                    company_name=dealer_data['company_name'],
                    part_number=dealer_data.get('part_number'),
                    nsn=dealer_data.get('nsn'),
                    research_status=DealerResearchStatus.COMPLETED,
                    research_source="document_extraction",
                    verification_status="not_verified",  # Use string value for PostgreSQL enum
                    research_started_at=datetime.utcnow(),
                    research_completed_at=datetime.utcnow(),
                    additional_data={
                        'source_location': dealer_data.get('source_location'),
                        'extraction_notes': dealer_data.get('notes'),
                    } if dealer_data.get('source_location') or dealer_data.get('notes') else None
                )
                db.add(dealer)
                created_dealers.append(dealer)
                logger.info(f"Created dealer: {dealer_data['company_name']}")
        
        except Exception as e:
            logger.error(f"Error saving dealer {dealer_data.get('company_name')}: {str(e)}")
            continue
    
    db.commit()
    return created_dealers


def save_external_dealers(
    db: Session,
    opportunity_id: int,
    dealers: List[Dict],
    manufacturer: Manufacturer,
    clins: Optional[List[CLIN]] = None
) -> List[Dealer]:
    """
    Save externally researched dealers to database
    
    Args:
        db: Database session
        opportunity_id: Opportunity ID
        dealers: List of dealer dicts from external research (LLM-guided)
        manufacturer: Manufacturer these dealers are associated with
        clins: Optional list of CLIN objects
        
    Returns:
        List of created/updated Dealer objects
    """
    created_dealers = []
    
    # Create CLIN mapping
    clin_map = {}
    if clins:
        for clin in clins:
            clin_map[clin.clin_number] = clin
    
    for dealer_data in dealers:
        try:
            # Find associated CLIN by part number
            clin_id = None
            if dealer_data.get('part_number') and clins:
                for clin in clins:
                    if clin.part_number == dealer_data['part_number']:
                        clin_id = clin.id
                        break
            
            # Check if dealer already exists
            existing = db.query(Dealer).filter(
                Dealer.opportunity_id == opportunity_id,
                Dealer.company_name == dealer_data['company_name']
            ).first()
            
            if existing:
                # Update existing dealer with external research data
                if dealer_data.get('website'):
                    existing.website = dealer_data['website']
                if dealer_data.get('contact_email'):
                    existing.contact_email = dealer_data['contact_email']
                if dealer_data.get('pricing'):
                    existing.pricing_info = dealer_data['pricing']
                    # Try to extract numeric price
                    try:
                        price_str = dealer_data['pricing'].replace('$', '').replace(',', '').strip()
                        existing.pricing_amount = float(re.findall(r'\d+\.?\d*', price_str)[0]) if re.findall(r'\d+\.?\d*', price_str) else None
                    except:
                        pass
                if dealer_data.get('stock_status'):
                    existing.stock_status = dealer_data['stock_status'].lower().replace(' ', '_')
                if dealer_data.get('rank_score'):
                    existing.rank_score = dealer_data['rank_score']
                if dealer_data.get('sam_gov_verified'):
                    existing.sam_gov_verified = True
                    existing.sam_gov_verification_date = datetime.utcnow()
                if dealer_data.get('manufacturer_authorized') is not None:
                    existing.manufacturer_authorized = dealer_data['manufacturer_authorized']
                if not existing.manufacturer_id:
                    existing.manufacturer_id = manufacturer.id
                if clin_id:
                    existing.clin_id = clin_id
                
                existing.research_source = "external_search"
                existing.research_status = DealerResearchStatus.COMPLETED
                existing.research_completed_at = datetime.utcnow()
                existing.website_verified = True
                existing.website_verification_date = datetime.utcnow()
                
                if dealer_data.get('verification_notes'):
                    existing.verification_notes = dealer_data['verification_notes']
                
                created_dealers.append(existing)
                logger.info(f"Updated dealer with external research: {dealer_data['company_name']}")
            else:
                # Create new dealer from external research
                dealer = Dealer(
                    opportunity_id=opportunity_id,
                    clin_id=clin_id,
                    manufacturer_id=manufacturer.id,
                    company_name=dealer_data['company_name'],
                    website=dealer_data.get('website'),
                    contact_email=dealer_data.get('contact_email'),
                    part_number=dealer_data.get('part_number') or manufacturer.part_number,
                    nsn=manufacturer.nsn,
                    pricing_info=dealer_data.get('pricing'),
                    stock_status=dealer_data.get('stock_status', '').lower().replace(' ', '_') if dealer_data.get('stock_status') else None,
                    rank_score=dealer_data.get('rank_score'),
                    sam_gov_verified=dealer_data.get('sam_gov_verified', False),
                    sam_gov_verification_date=datetime.utcnow() if dealer_data.get('sam_gov_verified') else None,
                    manufacturer_authorized=dealer_data.get('manufacturer_authorized'),
                    website_verified=True,
                    website_verification_date=datetime.utcnow(),
                    research_status=DealerResearchStatus.COMPLETED,
                    research_source="external_search",
                    research_started_at=datetime.utcnow(),
                    research_completed_at=datetime.utcnow(),
                    verification_notes=dealer_data.get('verification_notes'),
                    additional_data={
                        'external_research': True,
                        'search_method': 'llm_guided'
                    }
                )
                
                # Extract numeric price if available
                if dealer_data.get('pricing'):
                    try:
                        price_str = dealer_data['pricing'].replace('$', '').replace(',', '').strip()
                        price_match = re.findall(r'\d+\.?\d*', price_str)
                        if price_match:
                            dealer.pricing_amount = float(price_match[0])
                    except:
                        pass
                
                db.add(dealer)
                created_dealers.append(dealer)
                logger.info(f"Created dealer from external research: {dealer_data['company_name']}")
        
        except Exception as e:
            logger.error(f"Error saving external dealer {dealer_data.get('company_name')}: {str(e)}")
            continue
    
    db.commit()
    return created_dealers
