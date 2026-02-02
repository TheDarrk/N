"""
Validation utilities for wallet addresses and token names.
"""
from typing import Dict, Optional, List, Tuple
import re
from fuzzywuzzy import fuzz, process


def validate_near_address(address: str) -> bool:
    """
    Validate NEAR wallet address format.
    
    NEAR addresses can be:
    - Named accounts: alice.near, alice.testnet (alphanumeric with dots, hyphens, underscores)
    - Implicit accounts: 64-character hex string
    
    Args:
        address: The wallet address to validate
        
    Returns:
        bool: True if valid NEAR address format
    """
    if not address or not isinstance(address, str):
        return False
    
    address = address.strip()
    
    # Check for implicit account (64 hex chars)
    if re.match(r'^[a-f0-9]{64}$', address.lower()):
        return True
    
    # Check for named account
    # Pattern: lowercase letters, numbers, hyphens, underscores
    # Must end with .near or .testnet (or just be alphanumeric for subaccounts)
    # Min 2 chars, max 64 chars
    if re.match(r'^[a-z0-9_-]{2,}(\.[a-z0-9_-]{2,})*\.?(near|testnet)$', address.lower()):
        return True
    
    # Check for valid subaccount pattern without TLD
    if re.match(r'^[a-z0-9_-]{2,}(\.[a-z0-9_-]{2,})+$', address.lower()):
        return True
    
    return False


def validate_evm_address(address: str) -> bool:
    """
    Validate Ethereum/EVM wallet address format.
    
    Args:
        address: The wallet address to validate
        
    Returns:
        bool: True if valid EVM address format (basic validation)
    """
    if not address or not isinstance(address, str):
        return False
    
    address = address.strip()
    
    # Basic format check: 0x followed by 40 hex characters
    if not re.match(r'^0x[a-fA-F0-9]{40}$', address):
        return False
    
    try:
        from web3 import Web3
        # Use Web3 checksum validation if available
        return Web3.is_address(address)
    except ImportError:
        # Fallback to basic format validation
        return True


def get_chain_from_address(address: str) -> Optional[str]:
    """
    Determine the blockchain from address format.
    
    Args:
        address: The wallet address
        
    Returns:
        str: 'NEAR', 'EVM', or None if unrecognized
    """
    if validate_near_address(address):
        return 'NEAR'
    elif validate_evm_address(address):
        return 'EVM'
    return None


def fuzzy_match_token(
    input_token: str, 
    available_tokens: List[str],
    threshold: int = 70
) -> Dict[str, any]:
    """
    Find the best matching token from available tokens using fuzzy matching.
    
    Args:
        input_token: The user's input token name
        available_tokens: List of valid token symbols
        threshold: Minimum similarity score (0-100) to consider a match
        
    Returns:
        Dict with keys:
            - exact_match: bool
            - suggested_token: str or None
            - confidence: int (0-100)
            - alternatives: List of other possible matches
    """
    if not input_token or not available_tokens:
        return {
            'exact_match': False,
            'suggested_token': None,
            'confidence': 0,
            'alternatives': []
        }
    
    input_upper = input_token.upper().strip()
    available_upper = [t.upper() for t in available_tokens]
    
    # Check for exact match first
    if input_upper in available_upper:
        return {
            'exact_match': True,
            'suggested_token': input_upper,
            'confidence': 100,
            'alternatives': []
        }
    
    # Use fuzzy matching to find best match
    matches = process.extract(input_upper, available_upper, scorer=fuzz.ratio, limit=3)
    
    if not matches or matches[0][1] < threshold:
        return {
            'exact_match': False,
            'suggested_token': None,
            'confidence': 0,
            'alternatives': [m[0] for m in matches if m[1] >= 50]
        }
    
    best_match, confidence = matches[0]
    alternatives = [m[0] for m in matches[1:] if m[1] >= 50]
    
    return {
        'exact_match': False,
        'suggested_token': best_match,
        'confidence': confidence,
        'alternatives': alternatives
    }


def validate_token_pair(token_in: str, token_out: str, available_tokens: List[str]) -> Tuple[bool, str, Optional[str], Optional[str]]:
    """
    Validate and potentially correct a token pair.
    
    Args:
        token_in: Input token symbol
        token_out: Output token symbol
        available_tokens: List of available tokens
        
    Returns:
        Tuple of (is_valid, message, corrected_token_in, corrected_token_out)
    """
    match_in = fuzzy_match_token(token_in, available_tokens)
    match_out = fuzzy_match_token(token_out, available_tokens)
    
    # Both exact matches - all good
    if match_in['exact_match'] and match_out['exact_match']:
        return True, "Valid token pair", token_in.upper(), token_out.upper()
    
    # Handle input token issues
    if not match_in['exact_match']:
        if match_in['suggested_token']:
            if match_out['exact_match'] or match_out['suggested_token']:
                return False, f"Did you mean {match_in['suggested_token']} instead of {token_in}?", match_in['suggested_token'], match_out.get('suggested_token') or token_out.upper()
        else:
            return False, f"Token '{token_in}' not recognized. Available alternatives: {', '.join(match_in['alternatives'][:3]) if match_in['alternatives'] else 'none'}", None, None
    
    # Handle output token issues
    if not match_out['exact_match']:
        if match_out['suggested_token']:
            return False, f"Did you mean {match_out['suggested_token']} instead of {token_out}?", match_in.get('suggested_token') or token_in.upper(), match_out['suggested_token']
        else:
            return False, f"Token '{token_out}' not recognized. Available alternatives: {', '.join(match_out['alternatives'][:3]) if match_out['alternatives'] else 'none'}", None, None
    
    return True, "Valid token pair", match_in.get('suggested_token') or token_in.upper(), match_out.get('suggested_token') or token_out.upper()
