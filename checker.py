import asyncio
import os
import random
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from playwright.async_api import async_playwright


# ============================================================
# CONFIG
# ============================================================

SONEB_URL = "https://appointment.soneb.gov.so/#2"
TARGET_CENTER = "Xarunta Dhexe Xafiiska Imtixaanaadka"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

TIMEZONE = ZoneInfo("Africa/Mogadishu")

START_HOUR = 6
END_HOUR = 22

HEARTBEAT_FILE = "heartbeat.txt"


# ============================================================
# TELEGRAM NOTIFICATION
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets are missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:
        response = requests.post(url, data=data, timeout=20)
        if response.ok:
            print("Telegram notification sent.")
            return True
        print("Telegram error:", response.text)
        return False
    except Exception as e:
        print("Telegram request failed:", repr(e))
        return False


# ============================================================
# HEARTBEAT SYSTEM
# ============================================================

def should_send_heartbeat():
    now = datetime.now(TIMEZONE)
    if not os.path.exists(HEARTBEAT_FILE):
        return True

    try:
        with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
            last_string = f.read().strip()

        last_time = datetime.fromisoformat(last_string)
        elapsed_minutes = (now - last_time).total_seconds() / 60
        print(f"Minutes since last heartbeat: {elapsed_minutes:.1f}")

        return elapsed_minutes >= 60
    except Exception as e:
        print("Could not read heartbeat:", repr(e))
        return True


def update_heartbeat():
    now = datetime.now(TIMEZONE)
    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
        f.write(now.isoformat())
    print("Heartbeat timestamp updated.")


# ============================================================
# CLOUDFLARE / CAPTCHA DETECTION
# ============================================================

async def detect_real_block(page):
    """
    Detects active Cloudflare block/challenge screens by checking page title
    and visible challenge elements, avoiding internal script matches.
    """
    try:
        title = (await page.title()).strip()
        print("PAGE TITLE:", title)
        print("PAGE URL:", page.url)

        # 1. Cloudflare Title Check
        blocking_titles = [
            "just a moment...",
            "attention required!",
            "access denied",
            "security check"
        ]

        if any(b_title in title.lower() for b_title in blocking_titles):
            print("REAL CLOUDFLARE BLOCK: Match found in page title.")
            return True

        # 2. Check visible Cloudflare Challenge UI elements
        challenge_selectors = [
            "#challenge-running",
            "#challenge-stage",
            ".cf-challenge",
            "[name='cf-turnstile-response']",
            ".cf-turnstile"
        ]

        for selector in challenge_selectors:
            try:
                locator = page.locator(selector)
                if await locator.count() > 0:
                    for i in range(await locator.count()):
                        if await locator.nth(i).is_visible():
                            print(f"REAL BLOCK: Visible element detected ({selector}).")
                            return True
            except Exception:
                continue

        # 3. Visible Challenge IFrames
        iframes = page.locator("iframe")
        for i in range(await iframes.count()):
            iframe = iframes.nth(i)
            try:
                src = (await iframe.get_attribute("src") or "").lower()
                if "challenges.cloudflare.com" in src or "recaptcha" in src:
                    if await iframe.is_visible():
                        print("REAL CAPTCHA IFRAME DETECTED:", src)
                        return True
            except Exception:
                continue

        print("No Cloudflare block detected.")
        return False

    except Exception as e:
        print("Block detection error:", repr(e))
        return False


# ============================================================
# FORM INTERACTION FUNCTIONS
# ============================================================

async def select_dfs(page):
    print("Selecting DFS...")
    selects = page.locator("select")
    count = await selects.count()

    for i in range(count):
        select = selects.nth(i)
        try:
            options = await select.locator("option").all_inner_texts()
            for option in options:
                text = option.strip()
                if text and "DFS" in text.upper():
                    await select.select_option(label=option)
                    print(f"DFS selected: {text}")
                    return True
        except Exception:
            continue

    print("DFS option was not found.")
    return False


async def select_center(page):
    print("Selecting target center...")
    selects = page.locator("select")
    count = await selects.count()

    for i in range(count):
        select = selects.nth(i)
        try:
            options = await select.locator("option").all_inner_texts()
            for option in options:
                text = option.strip()
                if text and TARGET_CENTER.lower() in text.lower():
                    await select.select_option(label=option)
                    print(f"Center selected: {text}")
                    return True
        except Exception:
            continue

    print("Target center was NOT found. Continuing anyway...")
    return False


async def extract_select_options(select):
    try:
        options = await select.locator("option").all_inner_texts()
        useful_options = []
        placeholders = ["select", "choose", "door", "dooro", "xulo", "dooro taariikh"]

        for option in options:
            text = option.strip()
            if not text:
                continue

            lower = text.lower()
            if any(lower == p or lower.startswith(p + " ") for p in placeholders):
                continue

            useful_options.append(text)

        useful_options = list(dict.fromkeys(useful_options))
        print("Useful appointment dates found:", useful_options)
        return useful_options

    except Exception as e:
        print("Error extracting options:", repr(e))
        return []


async def find_appointment_date_options(page):
    print("Searching for 'Taariikhda Ballanta'...")

    # Method 1: Search by text matching
    text_locator = page.get_by_text("Taariikhda Ballanta", exact=False)
    try:
        count = await text_locator.count()
        for i in range(count):
            element = text_locator.nth(i)
            parent = element.locator("..")
            select = parent.locator("select")
            if await select.count() > 0:
                return await extract_select_options(select)

            grandparent = parent.locator("..")
            select = grandparent.locator("select")
            if await select.count() > 0:
                return await extract_select_options(select)
    except Exception:
        pass

    # Method 2: Search through all selects directly
    selects = page.locator("select")
    for i in range(await selects.count()):
        select = selects.nth(i)
        try:
            parent = select.locator("..")
            parent_text = (await parent.inner_text()).strip().lower()
            if "taariikhda ballanta" in parent_text:
                return await extract_select_options(select)
        except Exception:
            continue

    print("'Taariikhda Ballanta' option not available.")
    return []


# ============================================================
# MAIN CHECKER (STEALTH ENHANCED)
# ============================================================

async def check_appointment():
    async with async_playwright() as p:
        # STEALTH CONFIGURATION
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-position=0,0",
                "--ignore-certificate-errors"
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="Africa/Mogadishu"
        )

        page = await context.new_page()

        # Hide Webdriver & Automation Signals
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
        """)

        try:
            print("Opening SONEB Website...")
            await page.goto(SONEB_URL, wait_until="networkidle", timeout=60000)

            # Random Human-like Delay
            await page.wait_for_timeout(random.randint(4000, 7000))

            # 1. Check Cloudflare
            if await detect_real_block(page):
                return {"status": "BLOCKED", "dates": [], "center_found": False}

            # 2. Select DFS
            if not await select_dfs(page):
                return {"status": "DFS_NOT_FOUND", "dates": [], "center_found": False}

            await page.wait_for_timeout(random.randint(2500, 4000))

            # 3. Select Center
            center_found = await select_center(page)
            await page.wait_for_timeout(random.randint(3000, 5000))

            # 4. Find Dates
            dates = await find_appointment_date_options(page)

            if dates:
                return {"status": "APPOINTMENT_FOUND", "dates": dates, "center_found": center_found}

            return {"status": "NO_APPOINTMENT", "dates": [], "center_found": center_found}

        except Exception as e:
            print("Checker error:", repr(e))
            return {"status": "CHECK_ERROR", "dates": [], "center_found": False}

        finally:
            await browser.close()


# ============================================================
# PROGRAM RUNNER
# ============================================================

async def main():
    now = datetime.now(TIMEZONE)

    print("=" * 60)
    print("SONEB DFS CHECKER (ULTIMATE STEALTH VERSION)")
    print("Time:", now.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)

    if not (START_HOUR <= now.hour < END_HOUR):
        print("Outside checking hours (6 AM - 10 PM).")
        return

    result = await check_appointment()
    status = result.get("status")
    dates = result.get("dates", [])

    print("=" * 60)
    print("STATUS:", status)
    print("DATES:", dates)
    print("=" * 60)

    if status == "APPOINTMENT_FOUND":
        message = (
            "🚨 SONEB DFS APPOINTMENT OPEN!\n\n"
            f"Xarunta:\n{TARGET_CENTER}\n\n"
            "📅 Taariikhda Ballanta:\n"
            + "\n".join(f"• {d}" for d in dates)
            + "\n\n⚡ Fadlan hadda hubi website-ka!"
        )
        send_telegram(message)

    elif status == "BLOCKED":
        send_telegram("⚠️ SONEB CHECKER: Real Cloudflare challenge encountered.")

    elif status == "NO_APPOINTMENT":
        if should_send_heartbeat():
            msg = (
                "🔄 SONEB DFS STATUS\n\n"
                "❌ Wali ballan lama helin.\n"
                "✅ Checker-ku si caadi ah ayuu u shaqeynayaa.\n\n"
                f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            if send_telegram(msg):
                update_heartbeat()


if __name__ == "__main__":
    asyncio.run(main())
