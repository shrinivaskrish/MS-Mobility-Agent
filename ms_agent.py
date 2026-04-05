import os
from typing import TypedDict, List
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

load_dotenv() # Loads your API key from .env

class AgentState(TypedDict):
    fatigue_level: int
    carpet_trips: int
    workout_plan: List[str]
    safety_alert: bool

llm = ChatOpenAI(model="gpt-4o", temperature=0)

def sentry_node(state: AgentState):
    fatigue = state.get("fatigue_level", 5)
    # Logic: High fatigue or high trip count triggers safety mode
    if fatigue > 8:
        return {"safety_alert": True}
    return {"safety_alert": False}

def physio_node(state: AgentState):
    if state["safety_alert"]:
        plan = ["Rest", "Magnesium Glycinate", "Deep Breathing"]
    elif state["fatigue_level"] > 6:
        plan = ["Seated Toe Lifts", "Seated Glute Squeezes"]
    else:
        plan = ["Standing Toe Raises", "Sit-to-Stands", "Tandem Stance"]
    return {"workout_plan": plan}

workflow = StateGraph(AgentState)
workflow.add_node("sentry", sentry_node)
workflow.add_node("physio", physio_node)
workflow.set_entry_point("sentry")
workflow.add_edge("sentry", "physio")
workflow.add_edge("physio", END)

app = workflow.compile()

if __name__ == "__main__":
    # Simulate your 8:00 PM check-in
    user_input = {"fatigue_level": 4, "carpet_trips": 1}
    for output in app.stream(user_input):
        print(output)
