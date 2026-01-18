"""
SAM.gov URL validation and utilities
"""
import re
from urllib.parse import urlparse
from typing import Optional, Tuple
from ..core.config import settings


def validate_sam_gov_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate SAM.gov opportunity URL
    
    Returns:
        (is_valid, error_message)
    """
    if not url or not isinstance(url, str):
        return False, "URL is required and must be a string"
    
    # Parse URL
    parsed = urlparse(url)
    
    # Check domain
    if parsed.netloc not in ["sam.gov", "www.sam.gov"]:
        return False, "URL must be from sam.gov domain"
    
    # Check if it's an opportunity URL
    # SAM.gov opportunity URLs typically look like:
    # https://sam.gov/workspace/contract/opp/[id]/view (new format)
    # https://sam.gov/opp/[id]/view (legacy format)
    # https://sam.gov/opportunities/[id]/view (alternative format)
    
    path_patterns = [
        r'^/workspace/contract/opp/[^/]+/view',  # /workspace/contract/opp/{id}/view (current format)
        r'^/opp/[^/]+/view',  # /opp/{id}/view (legacy format)
        r'^/opportunities/[^/]+/view',  # /opportunities/{id}/view (alternative format)
        r'^/workspace/contract/opp/[^/]+$',  # /workspace/contract/opp/{id}
        r'^/opp/[^/]+$',  # /opp/{id}
        r'^/opportunities/[^/]+$',  # /opportunities/{id}
    ]
    
    is_valid_path = any(re.match(pattern, parsed.path) for pattern in path_patterns)
    
    if not is_valid_path:
        return False, "URL does not appear to be a valid SAM.gov opportunity URL"
    
    return True, None


def extract_opportunity_id(url: str) -> Optional[str]:
    """
    Extract opportunity ID from SAM.gov URL
    
    Examples:
        https://sam.gov/opp/abc123/view -> abc123
        https://sam.gov/opportunities/xyz789/view -> xyz789
    """
    parsed = urlparse(url)
    path = parsed.path.strip('/')
    
    # Try to extract ID from path
    patterns = [
        r'workspace/contract/opp/([^/]+)',  # /workspace/contract/opp/{id}
        r'opp/([^/]+)',  # /opp/{id}
        r'opportunities/([^/]+)',  # /opportunities/{id}
    ]
    
    for pattern in patterns:
        match = re.search(pattern, path)
        if match:
            return match.group(1)
    
    return None


def normalize_sam_gov_url(url: str) -> str:
    """
    Normalize SAM.gov URL to standard format
    """
    parsed = urlparse(url)
    
    # Ensure HTTPS
    scheme = "https"
    
    # Normalize domain
    netloc = "sam.gov"
    
    # Reconstruct URL
    normalized = f"{scheme}://{netloc}{parsed.path}"
    if parsed.query:
        normalized += f"?{parsed.query}"
    
    return normalized
