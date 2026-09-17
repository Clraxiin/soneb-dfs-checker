import asyncio
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from playwright.async_api import async_playwright


# ============================================================
# CONFIG
# ============================================================

SONEB_URL = "https://appointment.soneb.gov.so/#2"

# Telegram
# Values are loaded from GitHub Actions Secrets / environment
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Checker settings
TIMEZONE = "Africa/Mogadishu"

# We check between 06:00 and 22:00
START_HOUR = 6
END_HOUR = 22

# Exact center
TARGET_CENTER = "Xarunta Dhexe Xafiiska Imtixaanaadka"


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    """
    Send a Telegram message.
    """

    if not TELEGRAM_BOT_TOKEN:
        print("ERROR: TELEGRAM_BOT_TOKEN is missing.")
        return False

    if not TELEGRAM_CHAT_ID:
        print("ERROR: TELEGRAM_CHAT_ID is missing.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            data=data,
            timeout=20,
        )

        print("Telegram status:", response.status_code)

        if response.status_code == 200:
            print("Telegram message sent successfully.")
            return True

        print("Telegram response:", response.text)
        return False

    except Exception as e:
        print("Telegram error:", repr(e))
        return False


# ============================================================
# TIME
# ============================================================

def get_local_time():
    return datetime.now(ZoneInfo(TIMEZONE))


def is_daytime():
    """
    Checker runs from 06:00 until before 22:00.
    """

    now = get_local_time()

    return START_HOUR <= now.hour < END_HOUR


# ============================================================
# DEBUG SELECTS
# ============================================================

async def print_selects(page, title=""):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)

    selects = page.locator("select")

    count = await selects.count()

    print(f"Found {count} select elements.")

    for i in range(count):
        select = selects.nth(i)

        try:
            options = await select.locator("option").all_text_contents()

            values = await select.locator("option").evaluate_all(
                """
                options => options.map(o => ({
                    text: o.textContent.trim(),
                    value: o.value
                }))
                """
            )

            print(f"\nSELECT #{i}")
            print("Options:")
            print(options)

            print("Values:")
            print(values)

        except Exception as e:
            print(
                f"Could not inspect select #{i}: "
                f"{repr(e)}"
            )


# ============================================================
# NETWORK DEBUG
# ============================================================

def setup_network_logging(page):
    """
    Log XHR and fetch requests.
    Useful for debugging the SONEB website/API.
    """

    def on_request(request):
        if request.resource_type in ["xhr", "fetch"]:
            print(
                f"\n>>> REQUEST: "
                f"{request.method} {request.url}"
            )

    def on_response(response):
        request = response.request

        if request.resource_type in ["xhr", "fetch"]:
            print(
                f"\n<<< RESPONSE: "
                f"{response.status} {response.url}"
            )

    page.on("request", on_request)
    page.on("response", on_response)


# ============================================================
# FIND DFS SELECT
# ============================================================

async def find_dfs_select(page):
    selects = page.locator("select")

    count = await selects.count()

    print(f"Searching {count} select elements for DFS...")

    for i in range(count):

        options = await selects.nth(i).locator(
            "option"
        ).all_text_contents()

        for option in options:

            if "DFS" in option.upper():

                print(
                    f"DFS found in SELECT #{i}: "
                    f"{option.strip()}"
                )

                return selects.nth(i)

    return None


# ============================================================
# SELECT DFS
# ============================================================

async def select_dfs(page):

    print("\nSearching for DFS exam...")

    select = await find_dfs_select(page)

    if select is None:
        raise RuntimeError(
            "Could not find DFS option."
        )

    values = await select.locator(
        "option"
    ).evaluate_all(
        """
        options => options.map(o => ({
            text: o.textContent.trim(),
            value: o.value
        }))
        """
    )

    target_value = None
    target_text = None

    for option in values:

        if "DFS" in option["text"].upper():

            target_value = option["value"]
            target_text = option["text"]

            break

    if target_value is None:
        raise RuntimeError(
            "DFS option was not found."
        )

    print(
        f"Selecting DFS: "
        f"{target_text} "
        f"(value: {target_value})"
    )

    await select.select_option(target_value)

    print("DFS selected.")

    # Give the website time to load dependent fields
    await page.wait_for_timeout(5000)


# ============================================================
# FIND CENTER
# ============================================================

async def find_center(page):

    selects = page.locator("select")

    count = await selects.count()

    for i in range(count):

        options = await selects.nth(i).locator(
            "option"
        ).all_text_contents()

        clean_options = [
            x.strip()
            for x in options
            if x.strip()
        ]

        for option in clean_options:

            if TARGET_CENTER.lower() in option.lower():

                print(
                    f"Center found in SELECT #{i}: "
                    f"{option}"
                )

                return selects.nth(i)

    return None


# ============================================================
# SELECT CENTER
# ============================================================

async def select_center(page):

    print("\nSearching for center...")

    for attempt in range(10):

        print(
            f"Waiting for center options... "
            f"attempt {attempt + 1}/10"
        )

        center_select = await find_center(page)

        if center_select is not None:

            values = await center_select.locator(
                "option"
            ).evaluate_all(
                """
                options => options.map(o => ({
                    text: o.textContent.trim(),
                    value: o.value
                }))
                """
            )

            for option in values:

                if TARGET_CENTER.lower() in option["text"].lower():

                    print(
                        "Selecting center:",
                        option["text"]
                    )

                    await center_select.select_option(
                        option["value"]
                    )

                    await page.wait_for_timeout(3000)

                    print("Center selected.")

                    return center_select

        await page.wait_for_timeout(2000)

    raise RuntimeError(
        "Could not find center: "
        + TARGET_CENTER
    )


# ============================================================
# GET APPOINTMENT DATES
# ============================================================

async def get_appointment_dates(page):

    print("\nChecking appointment dates...")

    selects = page.locator("select")

    select_count = await selects.count()

    print(
        f"Total select elements: {select_count}"
    )

    # --------------------------------------------------------
    # First try to identify the date select dynamically.
    # --------------------------------------------------------

    date_select = None

    for i in range(select_count):

        select = selects.nth(i)

        try:

            options = await select.locator(
                "option"
            ).all_text_contents()

            for option in options:

                text = option.strip()

                if re.match(
                    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$",
                    text
                ):
                    date_select = select
                    print(
                        f"Date select found dynamically: "
                        f"SELECT #{i}"
                    )
                    break

                if re.match(
                    r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}$",
                    text
                ):
                    date_select = select
                    print(
                        f"Date select found dynamically: "
                        f"SELECT #{i}"
                    )
                    break

            if date_select is not None:
                break

        except Exception:
            continue

    # --------------------------------------------------------
    # Fallback to original SELECT #3
    # --------------------------------------------------------

    if date_select is None and select_count > 3:

        print(
            "Dynamic date select not found. "
            "Using SELECT #3 fallback."
        )

        date_select = selects.nth(3)

    if date_select is None:

        print(
            "Appointment date dropdown not found."
        )

        return []

    await page.wait_for_timeout(2000)

    values = await date_select.locator(
        "option"
    ).evaluate_all(
        """
        options => options.map(o => ({
            text: o.textContent.trim(),
            value: o.value
        }))
        """
    )

    dates = []

    for option in values:

        text = option["text"].strip()

        if not text:
            continue

        if text.lower() in [
            "please select",
            "select",
            "choose",
            "choose date",
        ]:
            continue

        is_date = (
            bool(
                re.match(
                    r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}$",
                    text
                )
            )
            or
            bool(
                re.match(
                    r"^\d{1,2}[-/]\d{1,2}[-/]\d{4}$",
                    text
                )
            )
        )

        if is_date:

            dates.append(text)

    print(
        "Valid appointment dates:",
        dates
    )

    return dates


# ============================================================
# MAIN SONEB CHECK
# ============================================================

async def check_appointment():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page(
            viewport={
                "width": 1366,
                "height": 900,
            }
        )

        try:

            print(
                "\n"
                + "=" * 70
                + "\nOpening SONEB...\n"
                + "=" * 70
            )

            # Uncomment this when debugging network/API
            # setup_network_logging(page)

            await page.goto(
                SONEB_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )

            print(
                "SONEB page loaded."
            )

            await page.wait_for_timeout(5000)

            # ------------------------------------------------
            # CAPTCHA / CLOUDFLARE CHECK
            # ------------------------------------------------

            content = await page.locator(
                "body"
            ).inner_text()

            content_lower = content.lower()

            if (
                "captcha" in content_lower
                or "cloudflare" in content_lower
            ):

                print(
                    "\nWARNING: "
                    "CAPTCHA/Cloudflare detected."
                )

                return []

            # ------------------------------------------------
            # SELECT DFS
            # ------------------------------------------------

            await select_dfs(page)

            # ------------------------------------------------
            # SELECT CENTER
            # ------------------------------------------------

            await select_center(page)

            # ------------------------------------------------
            # GET DATES
            # ------------------------------------------------

            dates = await get_appointment_dates(
                page
            )

            return dates

        except Exception as e:

            print(
                "\nCHECK ERROR:",
                type(e).__name__,
                ":",
                str(e),
            )

            # Save screenshot for debugging
            try:

                await page.screenshot(
                    path="soneb_error.png",
                    full_page=True,
                )

                print(
                    "Error screenshot saved:"
                    " soneb_error.png"
                )

            except Exception as screenshot_error:

                print(
                    "Could not save screenshot:",
                    repr(screenshot_error)
                )

            return []

        finally:

            await browser.close()


# ============================================================
# TELEGRAM NOTIFICATION
# ============================================================

def notify_open(dates):

    now_str = get_local_time().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    message = (
        "🟢 SONEB DFS APPOINTMENT WAA FURAN YAHAY!\n\n"
        f"⏰ Waqtiga: {now_str}\n"
        f"📍 Center: {TARGET_CENTER}\n\n"
        "📅 Taariikhaha Furan:\n"
        + "\n".join(
            f"• {date}"
            for date in dates
        )
        + "\n\n"
        f"🔗 Ballanso Hadda:\n{SONEB_URL}"
    )

    print(
        "\nAppointment FOUND!"
    )

    send_telegram(message)


def notify_error():

    now_str = get_local_time().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    message = (
        "⚠️ SONEB CHECKER ERROR\n\n"
        f"⏰ Waqtiga: {now_str}\n"
        f"📍 Center: {TARGET_CENTER}\n\n"
        "Checker-ku wuxuu la kulmay error "
        "markii uu website-ka hubinayay."
    )

    send_telegram(message)


# ============================================================
# MAIN
# ============================================================

async def main():

    print("=" * 70)
    print("SONEB DFS APPOINTMENT CHECKER")
    print("=" * 70)

    now = get_local_time()

    print(
        f"\nCurrent Somalia time: "
        f"{now.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    # --------------------------------------------------------
    # CHECK TIME
    # --------------------------------------------------------

    if not is_daytime():

        print(
            f"Outside checking hours "
            f"({START_HOUR:02d}:00-"
            f"{END_HOUR:02d}:00)."
        )

        return

    # --------------------------------------------------------
    # RUN SONEB CHECK
    # --------------------------------------------------------

    dates = await check_appointment()

    # --------------------------------------------------------
    # IMPORTANT
    #
    # We only notify Telegram when appointments are found.
    # This prevents Telegram spam every 10 minutes.
    # --------------------------------------------------------

    if dates:

        notify_open(dates)

    else:

        print(
            "\n🔴 No appointment dates found."
        )

        print(
            "No Telegram notification sent."
        )

    print(
        "\nCheck completed successfully."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "\nChecker stopped by user."
        )

