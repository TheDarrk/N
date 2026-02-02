"""
LangChain tools for the NEAR swap agent.
Each tool is decorated with @tool and can be called by the LLM when needed.
"""
import asyncio
from typing import Optional, Dict, Any
from langchain_core.tools import tool

from tools import get_swap_quote as _get_swap_quote, get_available_tokens, create_near_intent_transaction
from validators import fuzzy_match_token
from knowledge_base import get_available_tokens_from_api, get_token_symbols_list, format_token_list_for_display


@tool
async def get_available_tokens_tool() -> str:
    """
    Get the list of all available tokens that can be swapped on NEAR Protocol.
    Use this when user asks about available tokens, supported tokens, or what they can swap.
    
    Returns: A formatted string with all available token symbols and names.
    """
    try:
        tokens = await get_available_tokens_from_api()
        # Format nicely for display
        token_list = []
        for token in tokens[:50]:  # Show first 50
            token_list.append(f"• {token['symbol']} - {token['name']}")
        
        result = "**Available Tokens:**\n" + "\n".join(token_list)
        if len(tokens) > 50:
            result += f"\n\n...and {len(tokens) - 50} more tokens"
        return result
    except Exception as e:
        return f"⚠️ Can't get supported tokens for now: {str(e)}"


@tool
async def validate_token_names_tool(token_in: str, token_out: str) -> str:
    """
    Validate token names and check for typos or misspellings.
    Use this when you suspect user might have misspelled a token name.
    
    Args:
        token_in: The input token symbol (what user is swapping from)
        token_out: The output token symbol (what user is swapping to)
    
    Returns: Validation result with suggestions if needed
    """
    try:
        tokens = await get_available_tokens_from_api()
        available = get_token_symbols_list(tokens)
        
        match_in = fuzzy_match_token(token_in, available)
        match_out = fuzzy_match_token(token_out, available)
        
        if match_in['exact_match'] and match_out['exact_match']:
            return f"✅ Both tokens are valid: {token_in.upper()} and {token_out.upper()}"
        
        issues = []
        if not match_in['exact_match']:
            if match_in['suggested_token']:
                issues.append(f"'{token_in}' → Did you mean '{match_in['suggested_token']}'?")
            else:
                issues.append(f"'{token_in}' is not recognized")
        
        if not match_out['exact_match']:
            if match_out['suggested_token']:
                issues.append(f"'{token_out}' → Did you mean '{match_out['suggested_token']}'?")
            else:
                issues.append(f"'{token_out}' is not recognized")
        
        return "⚠️ Token validation issues:\n" + "\n".join(issues)
    except Exception as e:
        return f"⚠️ Can't validate tokens right now: {str(e)}"


@tool
def get_swap_quote_tool(token_in: str, token_out: str, amount: float, account_id: str, destination_address: str = None) -> str:
    """
    Get a real-time swap quote for exchanging tokens.
    Use this when user wants to swap tokens or asks for a quote/rate.
    
    Args:
        token_in: Symbol of token to swap from (e.g., "NEAR")
        token_out: Symbol of token to swap to (e.g., "ETH")
        amount: Amount of token_in to swap
        account_id: User's wallet address (required for quote)
        destination_address: Optional. Destination wallet address for cross-chain swaps
    
    Returns: Quote information with rate and estimated output amount
    """
    if not account_id or account_id == "Not connected":
        return "⚠️ User wallet not connected. Please ask user to connect wallet first."
    
    # Check if this is a cross-chain swap
    from tools import is_cross_chain_swap
    is_cross_chain = is_cross_chain_swap(token_in, token_out)
    
    # For cross-chain swaps, we need destination address
    if is_cross_chain and not destination_address:
        return (
            "⚠️ This appears to be a cross-chain swap. For security, I need to know where you want to receive your tokens.\n\n"
            "Please provide your destination wallet address on the target blockchain."
        )
    
    # Use connected wallet as recipient for same-chain, or provided address for cross-chain
    recipient = destination_address if is_cross_chain else account_id
    
    quote = _get_swap_quote(token_in.upper(), token_out.upper(), amount, recipient_id=recipient)
    
    if "error" in quote:
        return f"❌ Error getting quote: {quote['error']}"
    
    # Store quote globally for confirmation
    global _last_quote
    _last_quote = {
        "token_in": token_in.upper(),
        "token_out": token_out.upper(),
        "amount": amount,
        "amount_out": quote['amount_out'],
        "min_amount_out": quote['amount_out'] * 0.99,  # 1% slippage
        "deposit_address": quote['deposit_address'],
        "recipient": recipient
    }
    
    # Format response WITHOUT showing internal deposit address
    return (
        f"✅ **Swap Quote**\n"
        f"**Swap**: {amount} {token_in.upper()} → ~{quote['amount_out']:.6f} {token_out.upper()}\n"
        f"**Rate**: 1 {token_in.upper()} = {quote['rate']:.6f} {token_out.upper()}\n"
        f"**Recipient**: {recipient}\n\n"
        f"[QUOTE_ID: {id(_last_quote)}]\n"
        f"If user confirms, call confirm_swap_tool() to prepare the transaction."
    )



# Global storage for last quote
_last_quote = None


@tool
def confirm_swap_tool() -> str:
    """
    Confirm and prepare the swap transaction after user approves the quote.
    Call this ONLY when user explicitly confirms (says yes, okay, proceed, go ahead, etc).
    This uses the most recent quote that was provided to the user.
    
    Returns: Status message about transaction preparation
    """
    global _last_quote
    
    if not _last_quote:
        return "❌ No recent quote found. Please get a quote first by asking for a swap."
    
    try:
        from tools import create_near_intent_transaction
        
        tx_payload = create_near_intent_transaction(
            _last_quote["token_in"],
            _last_quote["token_out"],
            _last_quote["amount"],
            _last_quote["min_amount_out"],
            _last_quote["deposit_address"]
        )
        
        # Return special marker that agents.py will detect
        return f"[TRANSACTION_READY] Transaction prepared successfully. User needs to sign in their wallet."
        
    except Exception as e:
        return f"❌ Error preparing transaction: {str(e)}"


# Tool metadata for agent configuration
TOOL_LIST = [
    get_available_tokens_tool,
    validate_token_names_tool,
    get_swap_quote_tool,
    confirm_swap_tool  # New simplified confirmation tool
]
