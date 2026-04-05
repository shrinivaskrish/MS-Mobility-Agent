import os
import sqlite3
from datetime import datetime
from typing import TypedDict, List
from dotenv import load_dotenv

# API & Framework Imports
from github import Github
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_openai import ChatOpenAI

load_dotenv()

# --- DR. GRETCHEN HAWLEY EXERCISE LIBRARY ---
MS_EXERCISE_DB = {
    "foot_drop": [
        "Seated Ankle Pumps (Neuro-rehab style)",
        "Standing Wall-Supported Dorsiflexion",
        "Resistance Band 4-Way Ankle Strengthening"
    ],
    "marching": [
        "Seated High Marches (Functional Hip Flexion)",
        "Standing Marches with Countertop Support",
        "Slow-Motion Walking (Focus on Heel Strike)"
    ],
    "sit_to_stand": [
        "Powered-Up Sit-to-Stands (Focus on Glute Drive)",
        "Eccentric Loading (5-second sit-down)",
        "Staggered Stance Sit-to-Stands"
    ],
    "fatigue_recovery": [
        "Diaphragmatic Breathing",
        "Supine Nerve Glides",
        "Gentle Trunk Rotations"
    ]
}

# --- 1. STATE DEFINITION ---
class AgentState(TypedDict):
    fatigue_level: int
    carpet_trips: int
    workout_plan: List[str]
    safety_alert: bool

# --- 2. GITHUB LOGGING LOGIC ---
def log_to_github(content: str):
    try:
        g = Github(os.getenv("GITHUB_TOKEN"))
        repo = g.get_repo(os.getenv("GITHUB_REPO"))
        file_path = "progress_log.md"
        
        try:
            file_exists = repo.get_contents(file_path)
            new_content = file_exists.decoded_content.decode() + f"\n{content}"
            repo.update_file(file_path, f"Update log: {datetime.now().date()}", new_content, file_exists.sha)
        except:
            repo.create_file(file_path, "Initial log", f"# MS Mobility Progress Log\n| Date | Fatigue | Trips | Plan |\n|---|---|---|---|\n{content}")
        print("🚀 Sync: GitHub Log Updated.")
    except Exception as e:
        print(f"❌ GitHub Sync Failed: {e}")

# --- 3. LANGGRAPH NODES ---
def sentry_node(state: AgentState):
    fatigue = state.get("fatigue_level", 5)
    return {"safety_alert": fatigue > 7}

def physio_node(state: AgentState):
    fatigue = state.get("fatigue_level", 5)
    trips = state.get("carpet_trips", 0)
    
    plan = []

    # CASE 1: High Fatigue (Safety First)
    if state["safety_alert"]:
        plan = MS_EXERCISE_DB["fatigue_recovery"]
    
    # CASE 2: Moderate/Low Fatigue - Target the "Trips"
    else:
        # If trips > 2, prioritize Foot Drop (Ankle)
        if trips >= 2:
            plan.extend(MS_EXERCISE_DB["foot_drop"][:2])
            plan.append(MS_EXERCISE_DB["sit_to_stand"][0])
        # If trips are low but fatigue is moderate, do Marches
        else:
            plan.extend(MS_EXERCISE_DB["marching"][:2])
            plan.append(MS_EXERCISE_DB["sit_to_stand"][1])

    # Log to GitHub (as we did before)
    log_entry = f"| {datetime.now().strftime('%Y-%m-%d %H:%M')} | {fatigue} | {trips} | {', '.join(plan)} |"
    log_to_github(log_entry)
    
    return {"workout_plan": plan}

# --- 4. PERSISTENCE & GLOBAL APP COMPILATION ---
# Moved out of the 'main' block to ensure the Telegram function can see it
conn = sqlite3.connect("checkpoints.db", check_same_thread=False)
memory = SqliteSaver(conn)

workflow = StateGraph(AgentState)
workflow.add_node("sentry", sentry_node)
workflow.add_node("physio", physio_node)
workflow.set_entry_point("sentry")
workflow.add_edge("sentry", "physio")
workflow.add_edge("physio", END)

app = workflow.compile(checkpointer=memory)

# --- 5. TELEGRAM HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome home, Shrinivas. Send your status as: Fatigue, Trips\nExample: 4, 2"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    print(f"DEBUG: Processing text: '{text}'") 
    
    try:
        # Bulletproof Parsing
        parts = text.split(',')
        if len(parts) != 2:
            raise ValueError("Please use the format: Fatigue, Trips (e.g., 5, 2)")
            
        f_level = int(parts[0].strip())
        trips = int(parts[1].strip())
        
        # Run the Global 'app'
        config = {"configurable": {"thread_id": "shrinivas_001"}}
        user_input = {"fatigue_level": f_level, "carpet_trips": trips}
        
        final_plan = []
        for output in app.stream(user_input, config):
            for key, value in output.items():
                if "workout_plan" in value:
                    final_plan = value["workout_plan"]

        # Final Response to Telegram
        response = (
            f"✅ **Plan Generated & Synced**\n\n"
            f"**Fatigue:** {f_level} | **Trips:** {trips}\n\n"
            f"**Tonight's Routine:**\n" + 
            "\n".join([f"• {item}" for item in final_plan])
        )
        await update.message.reply_text(response, parse_mode='Markdown')

    except Exception as e:
        print(f"REAL ERROR: {e}")
        await update.message.reply_text(f"⚠️ Error: {e}")

# --- 6. MAIN EXECUTION ---
if __name__ == "__main__":
    print("🤖 Mobility Bot is LIVE. Waiting for Telegram messages...")
    
    # Initialize Telegram Bot
    tg_token = os.getenv("TELEGRAM_TOKEN")
    if not tg_token:
        print("❌ ERROR: TELEGRAM_TOKEN not found in .env file.")
    else:
        app_tg = ApplicationBuilder().token(tg_token).build()
        
        app_tg.add_handler(CommandHandler("start", start))
        app_tg.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
        
        app_tg.run_polling()