with open("/home/viptech/questboard/start_day_boot.log", "a") as f:
    f.write("start_day.py launched\n")

try:
    import sys
    print(f"Python executable: {sys.executable}")
    with open("/home/viptech/questboard/python_path.log", "a") as f:
        f.write(f"\nMouse call used: {sys.executable}\n")


    from datetime import datetime, time, timedelta
    from messenger import send_telegram
    import subprocess
    import requests
    import os
    import re
    import json
    import traceback
    import logging

    FLAG_FILE = "/tmp/day_started.flag"
    AFFIRMATION_CACHE = "/tmp/daily_affirmation.txt"
except Exception:
    with open("/tmp/start_day_error.log", "a") as f:
        f.write("\n[FATAL ERROR BEFORE MAIN — imports or setup failed]\n")
        import traceback
        f.write(traceback.format_exc())
    # Optional: exit silently or raise here depending on behavior you want
    exit(1)

def get_daily_quote():
    if os.path.exists(AFFIRMATION_CACHE):
        with open(AFFIRMATION_CACHE, "r") as f:
            return f.read()

    try:
        response = requests.get("https://zenquotes.io/api/today")
        if response.status_code == 200:
            data = response.json()
            quote = data[0]["q"]
            author = data[0]["a"]
            quote_text = f"{quote} — {author}"

            with open(AFFIRMATION_CACHE, "w") as f:
                f.write(quote_text)

            return quote_text
    except Exception as e:
        print("ZenQuotes API failed:", e)

    return "Today is a gift. Use it well."

def say(text):
    try:
        subprocess.run(["espeak-ng", text], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Voice feedback failed: {e}")

def notify(message):
    for chat_id in ['<CHAT_ID_1>', '<CHAT_ID_2>']:
        requests.post(
            f'https://api.telegram.org/bot<YOUR_BOT_TOKEN>/sendMessage',
            data={'chat_id': chat_id, 'text': message}
        )

def parse_duration(duration_str):
    duration_str = duration_str.lower()
    hours = 0
    minutes = 0

    hour_match = re.search(r'(\d+)\s*h', duration_str)
    minute_match = re.search(r'(\d+)\s*m', duration_str)

    if hour_match:
        hours = int(hour_match.group(1))
    if minute_match:
        minutes += int(minute_match.group(1))

    return hours * 60 + minutes

def schedule_day():
    os.system("play -nq -t alsa synth 0.3 sine 880")  # Beep tone
    send_telegram("🟢 Start Day initiated — loading today’s questboard.")
    now = datetime.now()
    latest_start_time = datetime.combine(now.date(), time(21, 0))
    end_of_day = datetime.combine(now.date(), time(19, 0))
    available_minutes = int((end_of_day - now).total_seconds() / 60)

    response = requests.get('http://localhost:5000/api/tasks/today')

    if response.status_code == 200 and response.text.strip():
        try:
            tasks = response.json()
        except Exception as e:
            print(f"JSON decoding failed: {e}")
            tasks = []
    else:
        print(f"Empty or invalid response: {response.status_code}")
        tasks = []

    assigned = []
    current_time = now + timedelta(minutes=20)  # Anchor time for Meds task

    # 🩺 Schedule Meds task only if Start Day was run in the morning
    meds_task = next((t for t in tasks if "meds" in t["name"].lower()), None)
    if meds_task and now.time() <= time(12, 0):
        meds_task['start_time'] = current_time.strftime("%H:%M")
        assigned.append(meds_task)

        duration = parse_duration(meds_task['duration'])
        current_time += timedelta(minutes=duration)
        available_minutes -= duration
    elif meds_task:
        print("Skipping Meds task — Start Day was launched too late for morning meds.")

    # 🧮 Schedule remaining tasks (excluding the Meds task if already scheduled)
    for task in tasks:
        if available_minutes <= 0:
            break
        if task == meds_task or not task['priority']:
            continue

        if current_time > latest_start_time:
            print(f"Skipping task '{task['name']}' — start time would be after 21:00.")
            continue

        task['start_time'] = current_time.strftime("%H:%M")
        assigned.append(task)

        duration = parse_duration(task['duration'])
        current_time += timedelta(minutes=duration)
        available_minutes -= duration

    # ⏱️ Total time calculation
    total_minutes = sum(parse_duration(t['duration']) for t in assigned)
    hours = total_minutes // 60
    mins = total_minutes % 60

    # 🕒 Estimate day end
    final_time = current_time.strftime("%H:%M")

    # 📜 Log the summary
    summary = f"🕒 Scheduled {len(assigned)} tasks totaling {hours}h {mins}m. Day ends at {final_time}."
    print(summary)
    say(summary)
    notify(summary)

    # 🔐 Save today's scheduled tasks
    with open("/home/viptech/questboard/today_schedule.json", "w") as f:
        json.dump(assigned, f, indent=2)


def speak_next_task():
    try:
        with open("/home/viptech/questboard/today_schedule.json", "r") as f:
            tasks = json.load(f)
    except Exception as e:
        print(f"Failed to load scheduled tasks: {e}")
        say("Couldn't find today's schedule.")
        return

    now = datetime.now().strftime("%H:%M")

    upcoming = [t for t in tasks if t.get("start_time") > now]
    if upcoming:
        next_task = upcoming[0]
        msg = f"Next task: {next_task['name']} at {next_task['start_time']}."
        say(msg)
        notify(msg)
    else:
        say("All tasks for today are completed.")
        notify("No upcoming tasks remaining.")

def speak_current_task():
    response = requests.get('http://localhost:5000/api/task/current')

    if response.status_code == 200 and response.text.strip():
        try:
            task = response.json()
        except Exception as e:
            print(f"JSON decoding failed for current task: {e}")
            task = None
    else:
        print(f"Empty or invalid response for current task: {response.status_code}")
        task = None

    if task:
        msg = f"Current task: {task['title']}. Estimated duration: {task['duration']} minutes."
        say(msg)
        notify(msg)
    else:
        say("No active task at the moment.")
        notify("No active task to report.")

def speak_smart_task():
    try:
        with open("/tmp/current_task.flag", "r") as f:
            
            task = json.load(f)
    except Exception:
        speak_next_task()
        return

    now = datetime.now().strftime("%H:%M")
    start = task.get("start")
    duration = parse_duration(task.get("duration", "0m"))

    # Compare current time with task window
    try:
        start_dt = datetime.strptime(start, "%H:%M")
        end_dt = start_dt + timedelta(minutes=duration)
        now_dt = datetime.strptime(now, "%H:%M")

        if start_dt <= now_dt < end_dt:
            msg = f"Current task: {task['title']} — started at {start}, ends at {end_dt.strftime('%H:%M')}."
            say(msg)
            notify(msg)
        else:
            speak_next_task()
    except Exception as e:
        print(f"Time parsing failed: {e}")
        speak_next_task()


def log_error(exc_trace):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("/home/viptech/questboard/start_day_error.log", "a") as f:
        f.write(f"\n[{timestamp}] Uncaught exception:\n")
        f.write(exc_trace)


def main():
    try:
        if os.path.exists(FLAG_FILE):
            logging.info("FLAG_FILE exists — running speak_smart_task()")
            speak_smart_task()
        else:
            logging.info("FLAG_FILE missing — running schedule_day()")
            schedule_day()
            subprocess.run(["systemctl", "--user", "restart", "task-notifier.service"])
            with open(FLAG_FILE, "w") as f:
                f.write("started")
    except Exception:
        trace = traceback.format_exc()
        log_error(trace)
        exit(1)

if __name__ == "__main__":
    main()
