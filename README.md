# Auto Bidding Bot - Automation Layer

This is the browser automation layer for the Auto Bidding Bot, built with Python, Playwright, and FastAPI. It handles interactions with LinkedIn and X (Twitter) while mimicking human behavior to avoid detection.

## Setup Instructions

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Install Playwright Browsers**:
   ```bash
   python -m playwright install chromium
   ```

3. **Run the Server**:
   ```bash
   python main.py
   ```

## Initial Login (Crucial)
On the first run, a Chromium window will open.
- Navigate to [LinkedIn](https://linkedin.com) and log in.
- Navigate to [X.com](https://x.com) and log in.
Your session data will be saved in the `user_data/` directory. You won't need to log in again as long as this folder exists.

## API Endpoints

### 1. Search Posts
**Endpoint**: `GET /search`
**Parameters**:
- `keyword`: The search term (e.g., "React Developer")
- `platform`: `linkedin` or `x`

**Example**: `http://localhost:8000/search?keyword=hiring&platform=linkedin`

### 2. Post Comment / Reply
**Endpoint**: `POST /comment`
**Body (JSON)**:
```json
{
  "url": "https://www.linkedin.com/posts/...",
  "text": "This is my bidding comment!",
  "platform": "linkedin"
}
```

## Anti-Detection Features
- **Persistent Context**: Uses real browser profiles and cookies.
- **Human Typing**: Random pauses between keystrokes.
- **Smooth Scrolling**: Incremental scrolling with varying speeds.
- **Randomized Delays**: Wait times between navigation and interaction actions.
- **Stealth Args**: Disables common automation flags (`--disable-blink-features=AutomationControlled`).
