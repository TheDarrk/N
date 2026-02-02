"""
LangChain agent for NEAR token swaps using tool calling.
LLM decides which tools to call based on user query.
"""
import json
import os
from typing import Dict, Any

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from agent_tools import TOOL_LIST
from prompts import MASTER_SYSTEM_PROMPT


# Initialize LLM with NEAR AI endpoint
llm = ChatOpenAI(
    model="openai/gpt-oss-120b",
    temperature=0.3,
    openai_api_key=os.getenv("NEAR_AI_API_KEY"),
    openai_api_base="https://cloud-api.near.ai/v1"
)

# Bind tools to LLM
llm_with_tools = llm.bind_tools(TOOL_LIST)

# System message for the agent
SYSTEM_MESSAGE = MASTER_SYSTEM_PROMPT + """

You have access to these tools:
- get_available_tokens_tool: Get list of all tokens that can be swapped
- validate_token_names_tool: Check if token names are correct and suggest corrections
- get_swap_quote_tool: Get real-time quote for a token swap
- prepare_swap_transaction_tool: Prepare transaction after user confirms

Use tools when you need specific data. For general questions, answer directly.
Be conversational, friendly, and concise.
"""


async def process_message(
    user_msg: str,
    session_state: Dict[str, Any],
    user_context: Dict[str, Any] = {}
) -> Dict[str, Any]:
    """
    Process user message using tool-calling LLM.
    LLM decides what tools to call (if any) and formulates response.
    
    Args:
        user_msg: User's message
        session_state: Current session state
        user_context: User context (account_id, etc.)
    
    Returns:
        Dict with response, action, payload, and new state
    """
    account_id = user_context.get("account_id", "Not connected")
    current_step = session_state.get("step", "IDLE")
    
    print(f"[AGENT] Processing: {user_msg} | Step: {current_step} | Account: {account_id}")
    
    # Ensure token cache is populated for cross-chain detection
    try:
        from knowledge_base import _token_cache, get_available_tokens_from_api
        if not _token_cache:
            print("[AGENT] Populating token cache...")
            await get_available_tokens_from_api()
    except Exception as e:
        print(f"[AGENT] Warning: Could not populate token cache: {e}")
    
    # Handle confirmation state
    if current_step == "WAITING_CONFIRMATION":
        pending = session_state.get("pending_quote", {})
        
        user_lower = user_msg.lower().strip()
        is_confirmed = any(word in user_lower for word in ["yes", "confirm", "go", "proceed", "ok", "sure", "yep", "yeah"])
        
        if is_confirmed:
            from tools import create_near_intent_transaction
            
            tx_payload = create_near_intent_transaction(
                pending["token_in"],
                pending["token_out"],
                pending["amount"],
                pending["min_amount_out"],
                pending["deposit_address"]
            )
            
            return {
                "response": "✅ Perfect! Transaction is ready. Please review and sign it in your wallet.",
                "action": "SIGN_TRANSACTION",
                "payload": tx_payload,
                "new_state": {"step": "IDLE"}
            }
        else:
            return {
                "response": "No problem! Swap cancelled. Let me know if you'd like to try a different swap!",
                "new_state": {"step": "IDLE"}
            }
    
    # Process with LLM and tools
    try:
        # Convert history to LangChain messages
        history = user_context.get("history", [])
        
        # Limit history to last 6 messages (3 exchanges) to avoid context issues
        # Tool calling with long history can cause problems
        recent_history = history[-6:] if len(history) > 6 else history
        
        messages = [SystemMessage(content=SYSTEM_MESSAGE)]
        
        # Add recent conversation history only
        for msg in recent_history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            elif msg["role"] == "ai":
                messages.append(AIMessage(content=msg["content"]))
        
        # Add current message
        messages.append(HumanMessage(content=f"{user_msg}\n\n[User wallet: {account_id}]"))
        
        print(f"[AGENT] Sending {len(messages)} messages (including {len(recent_history)} recent history items)")
        
        # Call LLM
        response = await llm_with_tools.ainvoke(messages)
        
        # Check if LLM wants to call tools
        if response.tool_calls:
            print(f"[AGENT] LLM calling {len(response.tool_calls)} tool(s)")
            
            # Execute each tool call
            tool_messages = []
            transaction_prepared = False
            tx_payload = None
            
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                
                print(f"[AGENT] Calling tool: {tool_name} with args: {tool_args}")
                
                # Special handling for transaction preparation
                if tool_name == "prepare_swap_transaction_tool":
                    transaction_prepared = True
                    # Get the actual transaction payload
                    from tools import create_near_intent_transaction
                    try:
                        tx_payload = create_near_intent_transaction(
                            tool_args["token_in"],
                            tool_args["token_out"],
                            tool_args["amount"],
                            tool_args["min_amount_out"],
                            tool_args["deposit_address"]
                        )
                        tool_result = "✅ Transaction prepared successfully and ready for user signature."
                    except Exception as e:
                        tool_result = f"❌ Error preparing transaction: {str(e)}"
                        print(f"[AGENT] Transaction prep error: {e}")
                else:
                    # Find and execute the tool normally
                    tool_result = None
                    for tool in TOOL_LIST:
                        if tool.name == tool_name:
                            try:
                                print(f"[AGENT] Executing tool: {tool_name}")
                                tool_result = await tool.ainvoke(tool_args)
                                print(f"[AGENT] Tool result: {tool_result[:200] if isinstance(tool_result, str) else tool_result}")
                            except Exception as e:
                                print(f"[AGENT] ERROR in tool execution: {e}")
                                import traceback
                                traceback.print_exc()
                                tool_result = f"Error calling tool: {str(e)}"
                            break
                    
                    if tool_result is None:
                        tool_result = f"Tool {tool_name} not found"
                        print(f"[AGENT] WARNING: {tool_result}")
                
                # Add tool result using HumanMessage (NEAR AI workaround)
                # NEAR AI ignores ToolMessage content, so we use HumanMessage instead
                tool_messages.append(HumanMessage(
                    content=f"Tool '{tool_name}' returned:\n{tool_result}"
                ))
            
            # Get final response from LLM with tool results
            print(f"[AGENT] Getting final response from LLM with {len(tool_messages)} tool results")
            
            # For NEAR AI: Use HumanMessage instead of ToolMessage (workaround)
            # Include last exchange for context, then add tool results as HumanMessages
            tool_response_messages = [SystemMessage(content=SYSTEM_MESSAGE)]
            
            # Add last exchange if available (for context on confirmations)
            if len(recent_history) >= 2:
                last_user = recent_history[-2]
                last_ai = recent_history[-1]
                if last_user.get("role") == "user" and last_ai.get("role") == "ai":
                    tool_response_messages.append(HumanMessage(content=last_user["content"]))
                    tool_response_messages.append(AIMessage(content=last_ai["content"]))
            
            # Add current exchange + tool results
            tool_response_messages.append(HumanMessage(content=f"{user_msg}\n\n[User wallet: {account_id}]"))
            # Note: Don't add AIMessage with tool_calls, NEAR AI doesn't need it
            tool_response_messages.extend(tool_messages)  # Tool results as HumanMessages
            
            # Debug: Show message types being sent
            msg_types = [f"{type(m).__name__}({getattr(m, 'content', 'tool_calls')[:30] if isinstance(getattr(m, 'content', ''), str) else 'tool_calls'}...)" for m in tool_response_messages]
            print(f"[AGENT] Tool response sequence: {' → '.join(msg_types)}")
            
            print(f"[AGENT] Sending {len(tool_response_messages)} messages to LLM for final response")
            final_response = await llm.ainvoke(tool_response_messages)
            
            print(f"[AGENT] LLM raw response type: {type(final_response)}")
            print(f"[AGENT] LLM response content: {final_response.content if hasattr(final_response, 'content') else final_response}")
            
            response_text = final_response.content if hasattr(final_response, 'content') else str(final_response)
            
            if not response_text or response_text.strip() == "":
                print("[AGENT] WARNING: Empty response from LLM!")
                response_text = "I apologize, I encountered an issue generating a response. Could you please rephrase your request?"
            
            print(f"[AGENT] Final response ({len(response_text)} chars): {response_text[:200]}")
            
            # Check if transaction was prepared by confirm_swap_tool
            transaction_prepared = False
            for msg in tool_messages:
                if hasattr(msg, 'content') and '[TRANSACTION_READY]' in msg.content:
                    transaction_prepared = True
                    break
            
            if transaction_prepared:
                # Get the actual transaction payload
                from agent_tools import _last_quote
                if _last_quote:
                    from tools import create_near_intent_transaction
                    try:
                        tx_payload = create_near_intent_transaction(
                            _last_quote["token_in"],
                            _last_quote["token_out"],
                            _last_quote["amount"],
                            _last_quote["min_amount_out"],
                            _last_quote["deposit_address"]
                        )
                        print(f"[AGENT] Transaction prepared, returning to frontend for signing")
                        return {
                            "response": "✅ Transaction prepared! Please review and sign it in your wallet.",
                            "action": "SIGN_TRANSACTION",
                            "payload": tx_payload,
                            "new_state": {"step": "IDLE"}
                        }
                    except Exception as e:
                        print(f"[AGENT] Error creating transaction payload: {e}")
        else:
            # No tools needed, use direct response
            response_text = response.content
            print(f"[AGENT] Direct response (no tools): {response_text[:200]}")
        
        return {
            "response": response_text,
            "new_state": {"step": "IDLE"}
        }
        
    except Exception as e:
        print(f"[AGENT] Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "response": "I encountered an error processing your request. Could you try rephrasing?",
            "new_state": {"step": "IDLE"}
        }


# Import asyncio for async tool execution
import asyncio
