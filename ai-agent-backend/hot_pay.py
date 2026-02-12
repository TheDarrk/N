"""
HOT Pay integration for Neptune AI.
Handles payment link generation and payment tracking via HOT Pay REST API.

HOT PAY is a non-custodial open source crypto payments platform.
- Accept crypto from 30+ chains
- Users pay with any token
- Merchant receives one token of choice
- No platform fees, no KYC
- Built on NEAR Intents / OmniBridge

Docs: https://hot-labs.gitbook.io/hot-pay
API:  https://api.hot-labs.org
"""
import os
import httpx
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode

HOT_PAY_BASE_URL = "https://api.hot-labs.org"
HOT_PAY_FRONTEND_URL = "https://pay.hot-labs.org"

# API token for partner endpoints (optional, for payment tracking)
HOT_PAY_API_TOKEN = os.getenv("HOT_PAY_API_TOKEN", "")


def create_payment_link(
    merchant_wallet: str,
    amount: float,
    token: str = "USDC",
    memo: str = "",
    description: str = "",
) -> Dict[str, Any]:
    """
    Generate a HOT Pay payment link.
    
    Anyone with the link can pay from 30+ chains using any token.
    The merchant receives the specified token on NEAR.
    
    Args:
        merchant_wallet: Merchant's NEAR wallet address (receives payment)
        amount: Amount to receive
        token: Token to receive (e.g., "USDC", "NEAR", "USDT")
        memo: Optional memo/order ID for tracking
        description: Optional human-readable description
    
    Returns:
        Dict with payment_url, amount, token, memo
    """
    # Build query params for HOT Pay
    params = {
        "to": merchant_wallet,
        "amount": str(amount),
        "token": token.upper(),
    }
    
    if memo:
        params["memo"] = memo
    
    payment_url = f"{HOT_PAY_FRONTEND_URL}/?{urlencode(params)}"
    
    return {
        "payment_url": payment_url,
        "merchant_wallet": merchant_wallet,
        "amount": amount,
        "token": token.upper(),
        "memo": memo,
        "description": description,
        "note": "Anyone can pay using this link from 30+ chains with any token. You will receive the specified token on NEAR.",
    }


async def get_payment_history(
    limit: int = 10,
    offset: int = 0,
    item_id: Optional[str] = None,
    memo: Optional[str] = None,
    sender_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetch processed payments from HOT Pay API.
    Requires HOT_PAY_API_TOKEN to be set.
    
    Args:
        limit: Max payments to return (default 10)
        offset: Pagination offset
        item_id: Optional filter by payment link ID
        memo: Optional filter by memo/order ID
        sender_id: Optional filter by sender address
    
    Returns:
        Dict with payments list and pagination info
    """
    if not HOT_PAY_API_TOKEN:
        return {
            "error": "HOT Pay API token not configured. Get one at https://pay.hot-labs.org/admin/api-keys",
            "setup_instructions": (
                "1. Go to https://pay.hot-labs.org/admin/api-keys\n"
                "2. Generate an API token\n"
                "3. Set HOT_PAY_API_TOKEN in your .env file"
            )
        }
    
    params: Dict[str, Any] = {"limit": limit, "offset": offset}
    if item_id:
        params["item_id"] = item_id
    if memo:
        params["memo"] = memo
    if sender_id:
        params["sender_id"] = sender_id
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{HOT_PAY_BASE_URL}/partners/processed_payments",
                headers={"Authorization": HOT_PAY_API_TOKEN},
                params=params,
                timeout=10.0,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            return {"error": "Invalid HOT Pay API token. Check your HOT_PAY_API_TOKEN."}
        return {"error": f"HOT Pay API error: {e.response.status_code}"}
    except Exception as e:
        return {"error": f"Failed to reach HOT Pay API: {str(e)}"}
