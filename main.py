from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from automation import AutomationEngine
import uvicorn
from contextlib import asynccontextmanager

# Define global engine instance
engine = AutomationEngine(user_data_dir="user_data")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the browser on app startup
    await engine.start()
    yield
    # Stop the browser on app shutdown
    await engine.stop()

app = FastAPI(title="Auto Bidding Bot API", lifespan=lifespan)

class CommentRequest(BaseModel):
    url: str
    text: str
    platform: str # 'linkedin' or 'x'

@app.get("/search")
async def search(
    keyword: str = Query(..., description="The keyword to search for"),
    platform: str = Query(..., description="Platform: 'linkedin' or 'x'")
):
    platform = platform.lower()
    if platform == "linkedin":
        results = await engine.search_linkedin(keyword)
    elif platform == "x" or platform == "twitter":
        results = await engine.search_x(keyword)
    else:
        raise HTTPException(status_code=400, detail="Unsupported platform. Use 'linkedin' or 'x'.")
    
    return {"status": "success", "results": results}

@app.post("/comment")
async def comment(request: CommentRequest):
    platform = request.platform.lower()
    success = False
    
    if platform == "linkedin":
        success = await engine.comment_linkedin(request.url, request.text)
    elif platform == "x" or platform == "twitter":
        success = await engine.reply_x(request.url, request.text)
    else:
        raise HTTPException(status_code=400, detail="Unsupported platform. Use 'linkedin' or 'x'.")
    
    if success:
        return {"status": "success", "message": f"Comment posted on {platform}"}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to post comment on {platform}")

@app.post("/auto_bid")
async def auto_bid(niche: str, platform: str, background_tasks: BackgroundTasks):
    """
    Starts the fully autonomous loop: Search -> AI Generate -> Comment.
    Runs in the background.
    """
    platform = platform.lower()
    if platform not in ["linkedin", "x", "twitter"]:
        raise HTTPException(status_code=400, detail="Invalid platform.")
    
    background_tasks.add_task(engine.run_niche_automation, niche, platform)
    return {"status": "started", "message": f"Autonomous bidding started for niche: {niche} on {platform}"}

@app.get("/")
async def root():
    return {"message": "Auto Bidding Bot Automation API is running. Use /search and /comment."}

if __name__ == "__main__":
    print("Starting server on http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
