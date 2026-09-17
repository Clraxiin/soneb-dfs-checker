
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

# Heartbeat: 60 minutes
HEARTBEAT_FILE = "heartbeat.txt"

# ============================================================
# TELEGRAM
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
        print("Telegram request failed:", e)
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
        with open(HEARTBEAT_FILE, "r", encoding="utf-8") as f:
            last_string = f.read().strip()

        last_time = datetime.fromisoformat(last_string)

        elapsed_minutes = (now - last_time).total_seconds() / 60

        print(f"Minutes since last heartbeat: {elapsed_minutes:.1f}")

        return elapsed_minutes >= 60

    except Exception as e:
        print("Could not read heartbeat:", e)
        return True


def update_heartbeat():
    now = datetime.now(TIMEZONE)

    with open(HEARTBEAT_FILE, "w", encoding="utf-8") as f:
        f.write(now.isoformat())

    print("Heartbeat timestamp updated.")


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

            print("Opening SONEB...")

            await page.goto(
                SONEB_URL,
                wait_until="networkidle",
                timeout=60000
            )

            await page.wait_for_timeout(3000)

            body_text = (await page.locator("body").inner_text()).lower()

            if "captcha" in body_text or "cloudflare" in body_text:
                print("CAPTCHA / Cloudflare detected.")
                return []

            # ====================================================
            # SELECT DFS
            # ====================================================

            print("Selecting DFS...")

            dfs_found = False

            selects = page.locator("select")

            count = await selects.count()

            print(f"Select elements found: {count}")

            for i in range(count):

                select = selects.nth(i)

                try:

                    options = await select.locator("option").all_inner_texts()

                    for option in options:

                        if "DFS" in option.upper():

                            await select.select_option(
                                label=option
                            )

                            dfs_found = True

                            print(f"DFS selected: {option}")

                            break

                    if dfs_found:
                        break

                except Exception:
                    continue

            if not dfs_found:
                print("DFS option was not found.")
                return []

            await page.wait_for_timeout(2000)

            # ====================================================
            # SELECT CENTER
            # ====================================================

            print("Selecting target center...")

            center_found = False

            selects = page.locator("select")
            count = await selects.count()

            for i in range(count):

                select = selects.nth(i)

                try:

                    options = await select.locator("option").all_inner_texts()

                    for option in options:

                        if TARGET_CENTER.lower() in option.lower():

                            await select.select_option(
                                label=option
                            )

                            center_found = True

                            print(f"Center selected: {option}")

                            break

                    if center_found:
                        break

                except Exception:
                    continue

            if not center_found:
                print("Target center was not found.")
                return []

            await page.wait_for_timeout(2000)

            # ====================================================
            # FIND DATE SELECT
            # ====================================================

            print("Checking appointment dates...")

            selects = page.locator("select")
            count = await selects.count()

            appointment_dates = []

            for i in range(count):

                select = selects.nth(i)

                try:

                    options = await select.locator("option").all_inner_texts()

                    for option in options:

                        text = option.strip()

                        if not text:
                            continue

                        lower = text.lower()

                        # Ignore generic/select placeholder options
                        if any(
                            word in lower
                            for word in [
                                "select",
                                "door",
                                "choose",
                                "xulo",
                                "dooro"
                            ]
                        ):
                            continue

                        # Detect date-like options
                        if any(
                            month in lower
                            for month in [
                                "jan",
                                "feb",
                                "mar",
                                "apr",
                                "may",
                                "jun",
                                "jul",
                                "aug",
                                "sep",
                                "oct",
                                "nov",
                                "dec"
                            ]
                        ):
                            appointment_dates.append(text)

                except Exception:
                    continue

            # Remove duplicates
            appointment_dates = list(dict.fromkeys(appointment_dates))

            print("Appointment dates:", appointment_dates)

            return appointment_dates

        except Exception as e:

            print("Checker error:", repr(e))

            try:
                await page.screenshot(
                    path="soneb_error.png",
                    full_page=True
                )
            except Exception:
                pass

            return []

        finally:

            await browser.close()


# ============================================================
# MAIN
# ============================================================


async def main():

    now = datetime.now(TIMEZONE)

    print("=" * 70)
    print("SONEB DFS APPOINTMENT CHECKER")
    print("=" * 70)
    print("Time:", now.strftime("%Y-%m-%d %H:%M:%S"))
    print("Timezone: Africa/Mogadishu")
    print("Target:", TARGET_CENTER)
    print("=" * 70)

    # ========================================================
    # CHECK HOURS
    # ========================================================

    if not (START_HOUR <= now.hour < END_HOUR):

        print("Outside checking hours.")

        return

    # ========================================================
    # CHECK SONEB
    # ========================================================

    dates = await check_appointment()

    # ========================================================
    # APPOINTMENT FOUND
    # ========================================================

    if dates:

        message = (
            "🚨 SONEB DFS APPOINTMENT OPEN!\n\n"
            f"Xarunta:\n{TARGET_CENTER}\n\n"
            "📅 Taariikhaha la helay:\n"
            + "\n".join(f"• {date}" for date in dates)
            + "\n\n"
            "⚡ Fadlan hadda hubi website-ka."
        )

        send_telegram(message)

        print("Appointment FOUND!")

        return

    # ========================================================
    # NO APPOINTMENT
    # ========================================================

    print("No appointment found.")

    # Send heartbeat every 60 minutes
    if should_send_heartbeat():

        message = (
            "🔄 SONEB DFS STATUS\n\n"
            "❌ Wali ballan lama furin.\n\n"
            "✅ Checker-ku wuu shaqeynayaa.\n"
            "⏱️ Wuxuu hubinayaa SONEB 10 daqiiqo kasta.\n\n"
            f"🕐 {now.strftime('%Y-%m-%d %H:%M:%S')}"
        )

        if send_telegram(message):
            update_heartbeat()

    else:

        print("Heartbeat not due yet.")


if __name__ == "__main__":
    asyncio.run(main())

