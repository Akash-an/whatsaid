from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from whatsaid.llm.client import LLMClient

class WorkflowState(TypedDict):
    input_text: str
    result: str

def process_node(state: WorkflowState) -> WorkflowState:
    client = LLMClient()
    # Simple extraction task using the client
    prompt = f"Extract details from this text: {state['input_text']}"
    response = client.generate(prompt=prompt)
    
    return {"result": response}

def create_workflow():
    workflow = StateGraph(WorkflowState)
    
    # Add our single node
    workflow.add_node("process", process_node)
    
    # Define edges
    workflow.add_edge(START, "process")
    workflow.add_edge("process", END)
    
    # Compile
    return workflow.compile()
