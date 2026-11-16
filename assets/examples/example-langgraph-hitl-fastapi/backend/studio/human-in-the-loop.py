from typing import Literal, Optional
import os
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import StateGraph, MessagesState, START, END
from langchain_deepseek import ChatDeepSeek
from langchain_core.messages import HumanMessage, SystemMessage

# backend/.env, whether Studio started here or the file was run directly
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# --- Model Definition ---
# DEEPSEEK_API_KEY configured in backend/.env or the environment
model = ChatDeepSeek(model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"))


# --- Graph State Definition ---
class DraftReviewState(MessagesState):
    human_request: str
    human_comment: Optional[str]
    status: Literal["approved", "feedback"]
    assistant_response: str


# --- Graph Nodes Definition ---
def assistant_draft(state: DraftReviewState) -> DraftReviewState:
    user_message = HumanMessage(content=state["human_request"])
    status = state.get("status", "approved")

    if (status == "feedback" and state.get("human_comment")):
        human_comment = HumanMessage(content=state["human_comment"])

        system_message = SystemMessage(content=(f"""
        You are an AI assistant revising your previous draft. Carefully review the human's 
        feedback and update your reply accordingly. Address all comments, corrections, 
        or suggestions provided by the human. Ensure your revised response fully 
        integrates the feedback, improves clarity, and resolves any issues raised.
        """))

        messages = [user_message] + state["messages"] + [system_message, human_comment]
        all_messages = state["messages"] + [human_comment]

    else:
        system_message = SystemMessage(content=("""
        You are an AI assistant. Your goal is to fully understand and fulfill the user's 
        request by preparing a relevant, clear, and helpful draft reply. Focus on addressing 
        the user's needs directly and comprehensively. 
        Do not reference any previous human feedback at this stage.
        """))
        messages = [system_message, user_message]
        all_messages = state["messages"]
    
    response = model.invoke(messages)

    all_messages = all_messages + [response]

    return {
        **state,
        "messages": all_messages,
        "assistant_response": response.content
    }


def human_feedback(state: DraftReviewState):
    pass


def assistant_finalize(state: DraftReviewState) -> DraftReviewState:
    system_message = """
    You are an AI assistant. The user has approved your draft. Carefully 
    review your reply and make any final improvements to clarity, tone, and 
    completeness. Ensure the response is polished, professional, and ready 
    to be delivered as the final answer.
    """
    messages = [system_message] + state["messages"]
    response = model.invoke(messages)

    all_messages = state['messages'] + [response]

    return {
        **state,
        "messages": all_messages,
        "assistant_response": response.content
    }
    

# --- Router Function ---
def feedback_router(state: DraftReviewState) -> str:
    if state['status'] == 'approved':
        return 'assistant_finalize'
    else:
        return 'assistant_draft'

# --- Graph Construction ---
builder = StateGraph(DraftReviewState)

# builder.add_node('start', start_node)
builder.add_node('assistant_draft', assistant_draft)
builder.add_node('human_feedback', human_feedback)
builder.add_node('assistant_finalize', assistant_finalize)

builder.add_edge(START, 'assistant_draft')
builder.add_edge('assistant_draft', 'human_feedback')
builder.add_conditional_edges('human_feedback', feedback_router, {'assistant_finalize': 'assistant_finalize', 'assistant_draft': 'assistant_draft'})
builder.add_edge('assistant_finalize', END)

graph = builder.compile(interrupt_before=["human_feedback"])
