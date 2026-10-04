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
        print(
            "Telegram request failed:",
            repr(e)
        )
        return False


# ============================================================
# HEARTBEAT
# ============================================================

def should_send_heartbeat():

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

        last_time = datetime.fromisoformat(
            last_string
        )

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

        f.write(
            now.isoformat()
        )

    print(
        "Heartbeat timestamp updated."
    )


# ============================================================
# CAPTCHA / CLOUDFLARE DETECTION
# ============================================================

async def detect_real_block(page):

    """
    Tries to detect an actual CAPTCHA / Cloudflare
    challenge instead of simply searching the entire
    body for the words "captcha" or "cloudflare".
    """

    try:

        title = (
            await page.title()
        ).strip()

        url = page.url

        body_text = (
            await page.locator(
                "body"
            ).inner_text()
        )

        body_lower = body_text.lower()

        print(
            "PAGE TITLE:",
            title
        )

        print(
            "PAGE URL:",
            url
        )

        # ----------------------------------------------------
        # Print a limited amount for debugging
        # ----------------------------------------------------

        print(
            "PAGE BODY PREVIEW:"
        )

        print(
            body_text[:5000]
        )

        # ----------------------------------------------------
        # Strong Cloudflare indicators
        # ----------------------------------------------------

        cloudflare_indicators = [
            "just a moment...",
            "checking your browser",
            "verify you are human",
            "performing security verification",
            "enable javascript and cookies",
            "attention required",
            "cf-chl",
            "challenge-platform",
        ]

        # ----------------------------------------------------
        # CAPTCHA indicators
        # ----------------------------------------------------

        captcha_indicators = [
            "verify you are human",
            "i'm not a robot",
            "im not a robot",
            "captcha challenge",
            "complete the captcha",
            "security check",
        ]

        cloudflare_found = any(
            indicator in body_lower
            for indicator in cloudflare_indicators
        )

        captcha_found = any(
            indicator in body_lower
            for indicator in captcha_indicators
        )

        # ----------------------------------------------------
        # Check visible iframe
        # ----------------------------------------------------

        iframe_count = await page.locator(
            "iframe"
        ).count()

        captcha_iframe_found = False

        for i in range(iframe_count):

            iframe = page.locator(
                "iframe"
            ).nth(i)

            try:

                src = (
                    await iframe.get_attribute(
                        "src"
                    )
                )

                title_attr = (
                    await iframe.get_attribute(
                        "title"
                    )
                )

                frame_info = (
                    f"{src or ''} "
                    f"{title_attr or ''}"
                ).lower()

                if (
                    "captcha" in frame_info
                    or "recaptcha" in frame_info
                    or "hcaptcha" in frame_info
                    or "challenge" in frame_info
                ):

                    captcha_iframe_found = True

                    print(
                        "Possible CAPTCHA iframe found:",
                        frame_info
                    )

            except Exception:
                continue

        # ----------------------------------------------------
        # Check visible challenge elements
        # ----------------------------------------------------

        challenge_selectors = [
            "#challenge-running",
            "#challenge-stage",
            ".cf-challenge",
            "[name='cf-turnstile-response']",
            ".g-recaptcha",
            ".h-captcha",
        ]

        challenge_element_found = False

        for selector in challenge_selectors:

            try:

                locator = page.locator(
                    selector
                )

                count = await locator.count()

                if count > 0:

                    for i in range(count):

                        element = locator.nth(i)

                        try:

                            if await element.is_visible():

                                challenge_element_found = True

                                print(
                                    "Visible challenge element:",
                                    selector
                                )

                                break

                        except Exception:
                            continue

                    if challenge_element_found:
                        break

            except Exception:
                continue

        # ----------------------------------------------------
        # Final decision
        # ----------------------------------------------------

        if (
            cloudflare_found
            or captcha_found
            or captcha_iframe_found
            or challenge_element_found
        ):

            print(
                "REAL CAPTCHA / CLOUDFLARE "
                "INDICATOR DETECTED."
            )

            return True

        print(
            "No strong CAPTCHA / Cloudflare "
            "indicator detected."
        )

        return False

    except Exception as e:

        print(
            "Block detection failed:",
            repr(e)
        )

        # Don't automatically classify an error
        # as CAPTCHA.
        return False


# ============================================================
# SELECT DFS
# ============================================================

async def select_dfs(page):

    print(
        "Selecting DFS..."
    )

    selects = page.locator(
        "select"
    )

    count = await selects.count()

    print(
        f"Select elements found: {count}"
    )

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
                f"Could not inspect DFS select {i}:",
                repr(e)
            )

            continue

    print(
        "DFS option was not found."
    )

    return False


# ============================================================
# SELECT CENTER
# ============================================================

async def select_center(page):

    print(
        "Selecting target center..."
    )

    selects = page.locator(
        "select"
    )

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

                if (
                    TARGET_CENTER.lower()
                    in text.lower()
                ):

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
        "Continuing to search for "
        "Taariikhda Ballanta..."
    )

    return False


# ============================================================
# EXTRACT OPTIONS
# ============================================================

async def extract_select_options(select):

    try:

        options = await select.locator(
            "option"
        ).all_inner_texts()

        print(
            "All options in appointment select:"
        )

        for option in options:
            print(
                repr(option)
            )

        useful_options = []

        placeholders = [
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
            "taariikh dooro",
        ]

        for option in options:

            text = option.strip()

            if not text:
                continue

            lower = text.lower()

            # ------------------------------------------------
            # Ignore only obvious placeholders
            # ------------------------------------------------

            is_placeholder = False

            for placeholder in placeholders:

                if lower == placeholder:
                    is_placeholder = True
                    break

                if lower.startswith(
                    placeholder + " "
                ):
                    is_placeholder = True
                    break

            if is_placeholder:

                print(
                    f"Ignoring placeholder: {text}"
                )

                continue

            # ------------------------------------------------
            # IMPORTANT:
            # DO NOT parse date format.
            # Accept whatever the website gives us.
            # ------------------------------------------------

            useful_options.append(
                text
            )

        # Remove duplicates
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
            "Could not extract options:",
            repr(e)
        )

        return []


# ============================================================
# FIND TAARIIKHDA BALLANTA
# ============================================================

async def find_appointment_date_options(page):

    print(
        "Searching for "
        "'Taariikhda Ballanta'..."
    )

    # --------------------------------------------------------
    # METHOD 1: labels
    # --------------------------------------------------------

    labels = page.locator(
        "label"
    )

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

                label_for = (
                    await label.get_attribute(
                        "for"
                    )
                )

                # --------------------------------------------
                # Associated select using "for"
                # --------------------------------------------

                if label_for:

                    select = page.locator(
                        f"select#{label_for}"
                    )

                    if await select.count() > 0:

                        print(
                            "Select found using "
                            "label 'for'."
                        )

                        return await extract_select_options(
                            select
                        )

                # --------------------------------------------
                # Select inside parent
                # --------------------------------------------

                parent = label.locator(
                    ".."
                )

                select = parent.locator(
                    "select"
                )

                if await select.count() > 0:

                    print(
                        "Select found inside "
                        "label parent."
                    )

                    return await extract_select_options(
                        select
                    )

        except Exception as e:

            print(
                "Label inspection error:",
                repr(e)
            )

            continue

    # --------------------------------------------------------
    # METHOD 2: text locator
    # --------------------------------------------------------

    print(
        "Searching visible text..."
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
            "Text search error:",
            repr(e)
        )

    # --------------------------------------------------------
    # METHOD 3: search all selects by parent text
    # --------------------------------------------------------

    print(
        "Searching select parents..."
    )

    selects = page.locator(
        "select"
    )

    count = await selects.count()

    for i in range(count):

        select = selects.nth(i)

        try:

            parent = select.locator(
                ".."
            )

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
# MAIN CHECKER
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
                5000
            )

            # ------------------------------------------------
            # CAPTCHA / CLOUDFLARE
            # ------------------------------------------------

            blocked = await detect_real_block(
                page
            )

            if blocked:

                return {
                    "status": "BLOCKED",
                    "dates": [],
                    "center_found": False
                }

            # ------------------------------------------------
            # DFS
            # ------------------------------------------------

            dfs_found = await select_dfs(
                page
            )

            if not dfs_found:

                return {
                    "status": "DFS_NOT_FOUND",
                    "dates": [],
                    "center_found": False
                }

            # Give dependent fields time
            await page.wait_for_timeout(
                3000
            )

            # ------------------------------------------------
            # CENTER
            # ------------------------------------------------

            center_found = await select_center(
                page
            )

            if center_found:

                await page.wait_for_timeout(
                    4000
                )

            else:

                # IMPORTANT:
                # Do NOT stop.
                print(
                    "Center not found."
                )

                print(
                    "Continuing anyway to "
                    "appointment date field..."
                )

                await page.wait_for_timeout(
                    2000
                )

            # ------------------------------------------------
            # APPOINTMENT DATE
            # ------------------------------------------------

            dates = await find_appointment_date_options(
                page
            )

            # ------------------------------------------------
            # APPOINTMENT FOUND
            # ------------------------------------------------

            if dates:

                return {
                    "status": "APPOINTMENT_FOUND",
                    "dates": dates,
                    "center_found": center_found
                }

            # ------------------------------------------------
            # NO APPOINTMENT
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
            # Screenshot
            # ------------------------------------------------

            try:

                await page.screenshot(
                    path="soneb_error.png",
                    full_page=True
                )

                print(
                    "Screenshot saved:"
                    " soneb_error.png"
                )

            except Exception as screenshot_error:

                print(
                    "Screenshot failed:",
                    repr(screenshot_error)
                )

            return {
                "status": "CHECK_ERROR",
                "dates": [],
                "center_found": False
            }

        finally:

            await browser.close()


# ============================================================
# PROGRAM
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
    # CHECKING HOURS
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
    # CHECK
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

    print("=" * 70)

    print(
        "FINAL STATUS:",
        status
    )

    print(
        "CENTER FOUND:",
        center_found
    )

    print(
        "DATES:",
        dates
    )

    print("=" * 70)

    # ========================================================
    # APPOINTMENT FOUND
    # ========================================================

    if status == "APPOINTMENT_FOUND":

        message = (
            "🚨 SONEB DFS APPOINTMENT OPEN!\n\n"
            "Xarunta:\n"
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
    # REAL BLOCK
    # ========================================================

    if status == "BLOCKED":

        message = (
            "⚠️ SONEB CHECKER WARNING\n\n"
            "CAPTCHA / Cloudflare challenge "
            "ayaa la helay.\n\n"
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
            "Checker-ku wuxuu la kulmay "
            "qalad.\n\n"
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

        return

    # ========================================================
    # NO APPOINTMENT
    # ========================================================

    if status == "NO_APPOINTMENT":

        print(
            "No appointment options found."
        )

        # ----------------------------------------------------
        # HEARTBEAT
        # ----------------------------------------------------

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

        return


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
