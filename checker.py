import asyncio
import os
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

# Heartbeat every 60 minutes
HEARTBEAT_FILE = "heartbeat.txt"


# ============================================================
# TELEGRAM
# ============================================================

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets are missing.")
        return False

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
    }

    try:
        response = requests.post(
            url,
            data=data,
            timeout=20
        )

        if response.ok:
            print("Telegram notification sent.")
            return True

        print("Telegram error:", response.text)
        return False

    except Exception as e:
        print("Telegram request failed:", repr(e))
        return False


# ============================================================
# HEARTBEAT
# ============================================================

def should_send_heartbeat():
    """
    Returns True if:
    - heartbeat.txt does not exist
    OR
    - 60 minutes have passed since the last heartbeat.
    """

    now = datetime.now(TIMEZONE)

    if not os.path.exists(HEARTBEAT_FILE):
        return True

    try:
        with open(
            HEARTBEAT_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            last_string = f.read().strip()

        last_time = datetime.fromisoformat(last_string)

        elapsed_minutes = (
            now - last_time
        ).total_seconds() / 60

        print(
            f"Minutes since last heartbeat: "
            f"{elapsed_minutes:.1f}"
        )

        return elapsed_minutes >= 60

    except Exception as e:
        print(
            "Could not read heartbeat:",
            repr(e)
        )
        return True


def update_heartbeat():
    now = datetime.now(TIMEZONE)

    with open(
        HEARTBEAT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        f.write(now.isoformat())

    print("Heartbeat timestamp updated.")


# ============================================================
# FIND DFS
# ============================================================

async def select_dfs(page):
    """
    Search all select elements for an option containing DFS.
    """

    print("Selecting DFS...")

    selects = page.locator("select")
    count = await selects.count()

    print(f"Select elements found: {count}")

    for i in range(count):

        select = selects.nth(i)

        try:
            options = await select.locator(
                "option"
            ).all_inner_texts()

            for option in options:

                text = option.strip()

                if not text:
                    continue

                if "DFS" in text.upper():

                    await select.select_option(
                        label=option
                    )

                    print(
                        f"DFS selected: {text}"
                    )

                    return True

        except Exception as e:

            print(
                f"Could not inspect select {i}:",
                repr(e)
            )

            continue

    print("DFS option was not found.")

    return False


# ============================================================
# FIND CENTER
# ============================================================

async def select_center(page):
    """
    Search all select elements for TARGET_CENTER.

    IMPORTANT:
    If the center is not found, this function returns False.
    The main checker DOES NOT stop because of this.
    """

    print("Selecting target center...")

    selects = page.locator("select")
    count = await selects.count()

    for i in range(count):

        select = selects.nth(i)

        try:

            options = await select.locator(
                "option"
            ).all_inner_texts()

            for option in options:

                text = option.strip()

                if not text:
                    continue

                if TARGET_CENTER.lower() in text.lower():

                    await select.select_option(
                        label=option
                    )

                    print(
                        f"Center selected: {text}"
                    )

                    return True

        except Exception as e:

            print(
                f"Could not inspect center select {i}:",
                repr(e)
            )

            continue

    print(
        "Target center was NOT found."
    )

    print(
        "IMPORTANT: Continuing to search "
        "for Taariikhda Ballanta..."
    )

    return False


# ============================================================
# FIND "TAARIIKHDA BALLANTA" SELECT
# ============================================================

async def find_appointment_date_options(page):
    """
    Find the select related to:

        Taariikhda Ballanta

    IMPORTANT:
    We DO NOT try to understand date formats.

    Whatever option text exists in this select
    will be returned exactly as the website shows it,
    except for placeholder options such as:

        Select
        Choose
        Dooro
        Xulo
    """

    print(
        "Searching for "
        "'Taariikhda Ballanta'..."
    )

    # --------------------------------------------------------
    # METHOD 1:
    # Search labels containing "Taariikhda Ballanta"
    # --------------------------------------------------------

    labels = page.locator("label")
    label_count = await labels.count()

    print(
        f"Labels found: {label_count}"
    )

    for i in range(label_count):

        label = labels.nth(i)

        try:

            label_text = (
                await label.inner_text()
            ).strip()

            if (
                "taariikhda ballanta"
                in label_text.lower()
            ):

                print(
                    f"Appointment label found: "
                    f"{label_text}"
                )

                # ------------------------------------------------
                # Try to find associated select through "for"
                # ------------------------------------------------

                label_for = await label.get_attribute(
                    "for"
                )

                if label_for:

                    select = page.locator(
                        f"select#{label_for}"
                    )

                    if await select.count() > 0:

                        print(
                            "Associated select found "
                            "using label 'for'."
                        )

                        return await extract_select_options(
                            select
                        )

                # ------------------------------------------------
                # Try select inside the same parent
                # ------------------------------------------------

                parent = label.locator(
                    ".."
                )

                select = parent.locator(
                    "select"
                )

                if await select.count() > 0:

                    print(
                        "Associated select found "
                        "inside label parent."
                    )

                    return await extract_select_options(
                        select
                    )

        except Exception as e:

            print(
                "Error checking label:",
                repr(e)
            )

            continue

    # --------------------------------------------------------
    # METHOD 2:
    # Search visible text directly
    # --------------------------------------------------------

    print(
        "Label method did not find it."
    )

    text_locator = page.get_by_text(
        "Taariikhda Ballanta",
        exact=False
    )

    try:

        text_count = await text_locator.count()

        print(
            f"Matching text elements: "
            f"{text_count}"
        )

        for i in range(text_count):

            element = text_locator.nth(i)

            try:

                # Look for nearby select
                parent = element.locator(
                    ".."
                )

                select = parent.locator(
                    "select"
                )

                if await select.count() > 0:

                    print(
                        "Select found near "
                        "'Taariikhda Ballanta'."
                    )

                    return await extract_select_options(
                        select
                    )

                # Try parent's parent
                parent2 = parent.locator(
                    ".."
                )

                select = parent2.locator(
                    "select"
                )

                if await select.count() > 0:

                    print(
                        "Select found in "
                        "parent's parent."
                    )

                    return await extract_select_options(
                        select
                    )

            except Exception:
                continue

    except Exception as e:

        print(
            "Direct text search error:",
            repr(e)
        )

    # --------------------------------------------------------
    # METHOD 3:
    # Search select elements by surrounding text
    # --------------------------------------------------------

    print(
        "Searching all selects by surrounding text..."
    )

    selects = page.locator("select")
    count = await selects.count()

    for i in range(count):

        select = selects.nth(i)

        try:

            # Get parent text
            parent = select.locator("..")

            parent_text = (
                await parent.inner_text()
            ).strip()

            if (
                "taariikhda ballanta"
                in parent_text.lower()
            ):

                print(
                    "Appointment select found "
                    "through parent text."
                )

                return await extract_select_options(
                    select
                )

            # Try grandparent
            grandparent = parent.locator(
                ".."
            )

            grandparent_text = (
                await grandparent.inner_text()
            ).strip()

            if (
                "taariikhda ballanta"
                in grandparent_text.lower()
            ):

                print(
                    "Appointment select found "
                    "through grandparent text."
                )

                return await extract_select_options(
                    select
                )

        except Exception:
            continue

    print(
        "'Taariikhda Ballanta' select "
        "was not found."
    )

    return []


# ============================================================
# EXTRACT ALL OPTIONS
# ============================================================

async def extract_select_options(select):
    """
    Return ALL useful options from a specific select.

    We do NOT care about date format.

    Example accepted:

        23-10-2026
        23-Oct-2026
        23 October 2026
        2026-10-23
        23/10/2026
        Any other format

    Everything is returned exactly as website text.

    Only obvious placeholders are ignored.
    """

    try:

        options = await select.locator(
            "option"
        ).all_inner_texts()

        print(
            f"Options found in appointment select: "
            f"{len(options)}"
        )

        useful_options = []

        ignored_words = [
            "select",
            "choose",
            "door",
            "dooro",
            "xulo",
            "xul",
            "please select",
            "select date",
            "choose date",
            "dooro taariikh",
            "xulo taariikh",
        ]

        for option in options:

            text = option.strip()

            if not text:
                continue

            lower = text.lower()

            # Ignore obvious placeholder
            if any(
                word == lower
                or lower.startswith(word + " ")
                for word in ignored_words
            ):
                print(
                    f"Ignoring placeholder: {text}"
                )
                continue

            useful_options.append(text)

        # Remove duplicates but preserve order
        useful_options = list(
            dict.fromkeys(
                useful_options
            )
        )

        print(
            "Useful appointment options:",
            useful_options
        )

        return useful_options

    except Exception as e:

        print(
            "Could not extract appointment options:",
            repr(e)
        )

        return []


# ============================================================
# CHECK APPOINTMENT
# ============================================================

async def check_appointment():

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            headless=True
        )

        page = await browser.new_page()

        try:

            print(
                "Opening SONEB..."
            )

            await page.goto(
                SONEB_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            print(
                "SONEB page loaded."
            )

            await page.wait_for_timeout(
                3000
            )

            # ------------------------------------------------
            # CAPTCHA / CLOUDFLARE
            # ------------------------------------------------

            body_text = (
                await page.locator(
                    "body"
                ).inner_text()
            ).lower()

            if (
                "captcha" in body_text
                or "cloudflare" in body_text
            ):

                print(
                    "CAPTCHA / Cloudflare detected."
                )

                return {
                    "status": "BLOCKED",
                    "dates": []
                }

            # ------------------------------------------------
            # SELECT DFS
            # ------------------------------------------------

            dfs_found = await select_dfs(
                page
            )

            if not dfs_found:

                return {
                    "status": "DFS_NOT_FOUND",
                    "dates": []
                }

            # Give dependent fields time to load
            await page.wait_for_timeout(
                3000
            )

            # ------------------------------------------------
            # SELECT CENTER
            # ------------------------------------------------

            center_found = await select_center(
                page
            )

            if center_found:

                # Give appointment field time
                # to load after center selection
                await page.wait_for_timeout(
                    3000
                )

            else:

                # IMPORTANT:
                # Do NOT stop here.
                print(
                    "Center not found."
                )

                print(
                    "Continuing anyway..."
                )

                await page.wait_for_timeout(
                    2000
                )

            # ------------------------------------------------
            # FIND APPOINTMENT DATE SELECT
            # ------------------------------------------------

            dates = await find_appointment_date_options(
                page
            )

            # ------------------------------------------------
            # RESULT
            # ------------------------------------------------

            if dates:

                return {
                    "status": "APPOINTMENT_FOUND",
                    "dates": dates,
                    "center_found": center_found
                }

            # ------------------------------------------------
            # NO OPTIONS
            # ------------------------------------------------

            return {
                "status": "NO_APPOINTMENT",
                "dates": [],
                "center_found": center_found
            }

        except Exception as e:

            print(
                "Checker error:",
                repr(e)
            )

            # ------------------------------------------------
            # Screenshot for debugging
            # ------------------------------------------------

            try:

                await page.screenshot(
                    path="soneb_error.png",
                    full_page=True
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

            return {
                "status": "CHECK_ERROR",
                "dates": []
            }

        finally:

            await browser.close()


# ============================================================
# MAIN
# ============================================================

async def main():

    now = datetime.now(
        TIMEZONE
    )

    print("=" * 70)
    print(
        "SONEB DFS APPOINTMENT CHECKER"
    )
    print("=" * 70)

    print(
        "Time:",
        now.strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    print(
        "Timezone: Africa/Mogadishu"
    )

    print(
        "Target:",
        TARGET_CENTER
    )

    print("=" * 70)

    # ========================================================
    # CHECK HOURS
    # ========================================================

    if not (
        START_HOUR
        <= now.hour
        < END_HOUR
    ):

        print(
            "Outside checking hours."
        )

        return

    # ========================================================
    # CHECK SONEB
    # ========================================================

    result = await check_appointment()

    status = result.get(
        "status"
    )

    dates = result.get(
        "dates",
        []
    )

    center_found = result.get(
        "center_found",
        False
    )

    print(
        "Final status:",
        status
    )

    print(
        "Center found:",
        center_found
    )

    print(
        "Appointment options:",
        dates
    )

    # ========================================================
    # APPOINTMENT FOUND
    # ========================================================

    if status == "APPOINTMENT_FOUND":

        message = (
            "🚨 SONEB DFS APPOINTMENT OPEN!\n\n"
            f"Xarunta:\n"
            f"{TARGET_CENTER}\n\n"
            "📅 Taariikhda Ballanta:\n"
            + "\n".join(
                f"• {date}"
                for date in dates
            )
            + "\n\n"
            "⚡ Fadlan hadda hubi website-ka."
        )

        send_telegram(
            message
        )

        print(
            "Appointment FOUND!"
        )

        return

    # ========================================================
    # CENTER NOT FOUND BUT NO APPOINTMENT OPTIONS
    # ========================================================

    if (
        status == "NO_APPOINTMENT"
        and not center_found
    ):

        print(
            "Center was not found, "
            "but appointment select "
            "had no usable options."
        )

        # Do NOT send false "appointment closed"
        # message as an error.
        #
        # Continue with heartbeat below.

    # ========================================================
    # BLOCKED
    # ========================================================

    if status == "BLOCKED":

        message = (
            "⚠️ SONEB CHECKER WARNING\n\n"
            "CAPTCHA / Cloudflare ayaa la helay.\n\n"
            "Checker-ku ma xaqiijin karo "
            "in ballan jiro ama uusan jirin.\n\n"
            f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        send_telegram(
            message
        )

        return

    # ========================================================
    # CHECK ERROR
    # ========================================================

    if status == "CHECK_ERROR":

        message = (
            "🔴 SONEB CHECKER ERROR\n\n"
            "Website-ka ama checker-ka "
            "ayaa qalad galay.\n\n"
            "❗ Tani macnaheedu ma aha "
            "in ballan uusan jirin.\n\n"
            f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        send_telegram(
            message
        )

        return

    # ========================================================
    # DFS NOT FOUND
    # ========================================================

    if status == "DFS_NOT_FOUND":

        print(
            "DFS was not found."
        )

        # Don't report "no appointment"
        # because the page could not be checked.
        return

    # ========================================================
    # NO APPOINTMENT
    # ========================================================

    print(
        "No appointment options found."
    )

    # ========================================================
    # HEARTBEAT EVERY 60 MINUTES
    # ========================================================

    if should_send_heartbeat():

        message = (
            "🔄 SONEB DFS STATUS\n\n"
            "❌ Wali ballan lama helin.\n\n"
            "✅ Checker-ku wuu shaqeynayaa.\n"
            "⏱️ Wuxuu hubinayaa SONEB "
            "10 daqiiqo kasta.\n\n"
            f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        if send_telegram(
            message
        ):

            update_heartbeat()

    else:

        print(
            "Heartbeat not due yet."
        )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
