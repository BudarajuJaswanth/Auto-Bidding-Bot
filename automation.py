import asyncio
import random
import os
import sqlite3
import httpx
from datetime import datetime
from playwright.async_api import async_playwright
from dotenv import load_dotenv

load_dotenv()

class Database:
    def __init__(self, db_path="bids.db"):
        self.conn = sqlite3.connect(db_path)
        self.create_table()

    def create_table(self):
        cursor = self.conn.cursor()
        # Processed posts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS processed_posts (
                post_id TEXT PRIMARY KEY,
                platform TEXT,
                timestamp DATETIME
            )
        ''')
        # Daily activity tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_activity (
                date TEXT,
                platform TEXT,
                count INTEGER,
                PRIMARY KEY (date, platform)
            )
        ''')
        self.conn.commit()

    def is_processed(self, post_id):
        cursor = self.conn.cursor()
        cursor.execute('SELECT 1 FROM processed_posts WHERE post_id = ?', (post_id,))
        return cursor.fetchone() is not None

    def mark_as_processed(self, post_id, platform):
        cursor = self.conn.cursor()
        cursor.execute('INSERT OR IGNORE INTO processed_posts VALUES (?, ?, ?)', 
                       (post_id, platform, datetime.now()))
        self.conn.commit()
        self.increment_daily_count(platform)

    def get_daily_count(self, platform):
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.cursor()
        cursor.execute('SELECT count FROM daily_activity WHERE date = ? AND platform = ?', (today, platform))
        row = cursor.fetchone()
        return row[0] if row else 0

    def increment_daily_count(self, platform):
        today = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO daily_activity (date, platform, count)
            VALUES (?, ?, 1)
            ON CONFLICT(date, platform) DO UPDATE SET count = count + 1
        ''', (today, platform))
        self.conn.commit()

class AutomationEngine:
    def __init__(self, user_data_dir="user_data"):
        self.user_data_dir = os.path.abspath(user_data_dir)
        if not os.path.exists(self.user_data_dir):
            os.makedirs(self.user_data_dir)
        self.browser_context = None
        self.playwright = None
        self.db = Database()
        # Daily limits
        self.limits = {"linkedin": 15, "x": 10}
        self.counts = {"linkedin": 0, "x": 0}
        # Business hours (9 AM to 6 PM)
        self.business_hours = (9, 18)
        # AI Configuration
        self.ai_api_key = os.getenv("AI_API_KEY")
        self.ai_base_url = os.getenv("AI_BASE_URL", "https://api.groq.com/openai/v1")
        self.ai_model = os.getenv("AI_MODEL", "llama-3.1-8b-instant")
        self.user_skills = os.getenv("USER_SKILLS", "Fullstack Developer, React, Python, Playwright")

    def is_business_hours(self):
        now = datetime.now()
        # 0 is Monday, 4 is Friday. (Checks for Mon-Fri)
        if now.weekday() > 4:
            return False
        return self.business_hours[0] <= now.hour < self.business_hours[1]

    async def generate_ai_comment(self, post_content):
        if not self.ai_api_key:
            print("[AI] Warning: No AI_API_KEY found in .env. Using fallback comment.")
            return "Hi! I'm interested in this project. I have the skills mentioned. Let's connect!"
        
        prompt = f"""
        You are a freelancer bidding for a job. 
        Post Content: {post_content}
        My Skills: {self.user_skills}
        
        Write a very short, professional, 1-2 sentence bid comment for this post. 
        Be natural, concise, and mention how my skills fit. 
        Do not use hashtags or emojis. 
        Output ONLY the comment text.
        """
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ai_base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.ai_api_key}"},
                    json={
                        "model": self.ai_model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.7
                    },
                    timeout=30.0
                )
                data = response.json()
                if 'choices' in data and len(data['choices']) > 0:
                    return data['choices'][0]['message']['content'].strip()
                else:
                    print(f"[AI] Error Response: {data}")
                    return "I'm interested in this role and have the required skills. Let's discuss further!"
        except Exception as e:
            print(f"[AI] Exception: {e}")
            return "I'd love to help with this! I have extensive experience in the areas you mentioned. When can we discuss further?"

    async def run_niche_automation(self, niche, platform):
        if not self.is_business_hours():
            print("[AUTO] Outside of business hours. Sleeping to reduce detection risk.")
            return

        # Check daily limits from DB
        current_count = self.db.get_daily_count(platform)
        if current_count >= self.limits.get(platform, 10):
            print(f"[AUTO] Daily limit reached for {platform} ({current_count}/{self.limits[platform]}). Stopping.")
            return

        print(f"\n[AUTO] Starting autonomous run for Niche: '{niche}' on {platform}")
        print(f"[AUTO] Current daily count: {current_count}/{self.limits[platform]}")
        
        # 1. Search for posts
        if platform == "linkedin":
            posts = await self.search_linkedin(niche)
        else:
            posts = await self.search_x(niche)
            
        if not posts:
            print("[AUTO] No new posts found in this niche.")
            return

        # 2. Process each post
        for post in posts:
            url = post['url']
            content = post['content']
            
            if self.db.is_processed(url):
                print(f"[AUTO] Skipping already processed: {url}")
                continue
                
            # MANDATORY FILTER: Check for "Python" in the content
            if "python" not in content.lower():
                print(f"[AUTO] Skipping post as it does not explicitly mention 'python': {url}")
                continue

            print(f"[AUTO] Processing post: {url}")
            
            # 3. Generate AI Comment
            comment_text = await self.generate_ai_comment(content)
            print(f"[AUTO] Generated Bid: {comment_text}")
            
            # 4. Post it
            success = False
            if platform == "linkedin":
                success = await self.comment_linkedin(url, comment_text)
            else:
                success = await self.reply_x(url, comment_text)
                
            if success:
                print(f"[AUTO] Successfully bid on {url}")
                # Wait a long random delay between posts (30-60 seconds for testing, increase for prod)
                wait_time = random.randint(30, 60)
                print(f"[AUTO] Waiting {wait_time}s before next bid...")
                await asyncio.sleep(wait_time)
            else:
                print(f"[AUTO] Failed to bid on {url}")

    async def start(self):
        self.playwright = await async_playwright().start()
        self.browser_context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=self.user_data_dir,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # Open login pages
        page1 = await self.browser_context.new_page()
        await page1.goto("https://www.linkedin.com/feed/")
        
        page2 = await self.browser_context.new_page()
        await page2.goto("https://x.com/home")
        
        print("\n[!] Browser opened. Please ensure you are logged in to LinkedIn and X.")
        print("[!] Once logged in, your session will be saved automatically.\n")

    async def stop(self):
        if self.browser_context:
            await self.browser_context.close()
        if self.playwright:
            await self.playwright.stop()

    async def human_delay(self, min_sec=1, max_sec=3):
        await asyncio.sleep(random.uniform(min_sec, max_sec))

    async def human_typing(self, page, selector, text):
        await page.wait_for_selector(selector)
        for char in text:
            await page.type(selector, char)
            await asyncio.sleep(random.uniform(0.05, 0.2))

    async def human_scroll(self, page, distance=500):
        current_scroll = 0
        while current_scroll < distance:
            step = random.randint(100, 300)
            await page.mouse.wheel(0, step)
            current_scroll += step
            # Randomized side movements
            if random.random() > 0.7:
                await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
            await self.human_delay(0.5, 1.5)

    async def like_linkedin_post(self, page):
        try:
            # Try to find the Like button
            like_btn = await page.wait_for_selector("button.react-button__trigger, .artdeco-button__text:has-text('Like')", timeout=5000)
            is_pressed = await like_btn.get_attribute("aria-pressed")
            if is_pressed == "false":
                print("[LinkedIn] Liking post for stealth...")
                await like_btn.click()
                await self.human_delay(1, 2)
            return True
        except:
            print("[LinkedIn] Could not find Like button, skipping...")
            return False

    async def like_x_post(self, page):
        try:
            like_btn = await page.wait_for_selector("div[data-testid='like']", timeout=5000)
            print("[X] Liking post for stealth...")
            await like_btn.click()
            await self.human_delay(1, 2)
            return True
        except:
            print("[X] Could not find Like button, skipping...")
            return False

    async def search_linkedin(self, keyword):
        page = await self.browser_context.new_page()
        try:
            # DIRECT SEARCH: Skip the search bar and go straight to the posts results
            encoded_keyword = keyword.replace(" ", "%20")
            search_url = f"https://www.linkedin.com/search/results/content/?keywords={encoded_keyword}"
            
            print(f"[LinkedIn] Navigating directly to search: {search_url}")
            await page.goto(search_url, wait_until="load", timeout=60000)
            await self.human_delay(5, 8)

            # Click 'Posts'
            try:
                posts_btn = await page.wait_for_selector("button:has-text('Posts'), a:has-text('Posts')", timeout=5000)
                await posts_btn.click()
                print("[LinkedIn] Clicked 'Posts' filter.")
                await self.human_delay(5, 8)
            except:
                print("[LinkedIn] Warning: Could not find 'Posts' filter button.")

            # CRITICAL: Wait for results to load
            print("[LinkedIn] Waiting for results to appear...")
            try:
                await page.wait_for_selector(".reusable-search__result-container, .search-results-container, .feed-shared-update-v2", timeout=15000)
            except:
                print("[LinkedIn] Timeout waiting for results. Trying to scroll anyway...")

            # Scroll and Scan
            print("[LinkedIn] Scrolling to load more results...")
            for _ in range(6): # Increased scrolling
                await page.evaluate("window.scrollBy(0, 1000)")
                await self.human_delay(1, 2)

            posts = []
            buttons = await page.query_selector_all("button")
            for btn in buttons:
                label = await btn.get_attribute("aria-label") or ""
                text = await btn.inner_text() or ""
                if "comment" in label.lower() or "comment" in text.lower():
                    # Find link and content
                    post_data = await page.evaluate('''(btn) => {
                        let curr = btn;
                        for (let i = 0; i < 40; i++) {
                            curr = curr.parentElement;
                            if (!curr) break;
                            
                            // Try to find the specific content div
                            let contentDiv = curr.querySelector(".feed-shared-update-v2__description, .update-components-text, .feed-shared-text");
                            let link = curr.querySelector("a[href*='/posts/'], a[href*='/feed/update/']");
                            
                            if (link && contentDiv) {
                                return { 
                                    url: link.href, 
                                    content: contentDiv.innerText 
                                };
                            }
                            // Fallback if contentDiv not found yet
                            if (link && i > 10) {
                                return { url: link.href, content: curr.innerText };
                            }
                        }
                        return null;
                    }''', btn)
                    if post_data:
                        full_url = post_data['url'].split('?')[0]
                        if not any(p['url'] == full_url for p in posts):
                            posts.append({"platform": "LinkedIn", "content": post_data['content'][:500], "url": full_url})
                if len(posts) >= 5: break
            
            print(f"[LinkedIn] Found {len(posts)} posts.")
            return posts
        finally:
            await page.close()

    async def comment_linkedin(self, post_url, text):
        page = await self.browser_context.new_page()
        try:
            await page.goto(post_url, wait_until="load", timeout=60000)
            await self.human_delay(5, 8)
            await page.evaluate("window.scrollTo(0, 300)")
            
            # STEALTH: Like the post first
            await self.like_linkedin_post(page)
            
            # Find editor
            editor = await page.wait_for_selector(".ql-editor, [role='textbox'][contenteditable='true']", timeout=10000)
            await editor.click()
            await self.human_typing(page, ".ql-editor, [role='textbox'][contenteditable='true']", text)
            await self.human_delay(2, 3)
            
            # Post
            post_btn = await page.wait_for_selector("button.comments-comment-box__submit-button, button:has-text('Post')", timeout=5000)
            await post_btn.click()
            self.db.mark_as_processed(post_url, "linkedin")
            self.counts["linkedin"] += 1
            return True
        except Exception as e:
            print(f"[LinkedIn] Comment Error: {e}")
            return False
        finally:
            await page.close()

    async def search_x(self, keyword):
        page = await self.browser_context.new_page()
        try:
            url = f"https://x.com/search?q={keyword}&src=typed_query&f=live"
            await page.goto(url)
            await self.human_delay(5, 8)
            await self.human_scroll(page, 1000)

            posts = []
            tweets = await page.query_selector_all("article[data-testid='tweet']")
            for tweet in tweets[:5]:
                content_el = await tweet.query_selector("div[data-testid='tweetText']")
                link_el = await tweet.query_selector("a[href*='/status/']")
                if content_el and link_el:
                    content = await content_el.inner_text()
                    link = "https://x.com" + await link_el.get_attribute("href")
                    posts.append({"platform": "X", "content": content, "url": link})
            return posts
        finally:
            await page.close()

    async def reply_x(self, post_url, text):
        page = await self.browser_context.new_page()
        try:
            await page.goto(post_url, wait_until="load", timeout=60000)
            await self.human_delay(5, 8)
            
            # STEALTH: Like the post first
            await self.like_x_post(page)

            # Click Reply
            reply_box = await page.wait_for_selector("div[data-testid='reply'], [role='textbox']", timeout=10000)
            await reply_box.click()
            await self.human_typing(page, "div[data-testid='tweetTextarea_0'], [role='textbox']", text)
            await self.human_delay(2, 4)
            
            # Click Send
            send_btn = await page.wait_for_selector("div[data-testid='tweetButtonInline'], [data-testid='tweetButton'], button:has-text('Reply')", timeout=5000)
            await send_btn.click()
            self.db.mark_as_processed(post_url, "x")
            self.counts["x"] += 1
            return True
        except Exception as e:
            print(f"[X] Reply Error: {e}")
            return False
        finally:
            await page.close()
