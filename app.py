# app.py
from flask import Flask, render_template, request, jsonify
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import re
import time
import threading

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# === CONFIG ===
TIKTOK_SHEET_ID = "1F4WsEcIby3liWlW0bmz3cpE3nGGXmQQ2BYsfTSzVY2Y"
TOKEN = "lSNX5D8FW02vlTX4"
ROOT_URL = "https://ensembledata.com/apis"
ENDPOINT = "/tt/post/info"

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
client = gspread.authorize(creds)
spreadsheet = client.open_by_key(TIKTOK_SHEET_ID)

WORKSHEETS = ["SCRIPTED", "REPOST", "ARK"]

task_status = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current": "",
    "log": [],
    "worksheet": None
}

def clean_url(url):
    match = re.search(r"(https://www\.tiktok\.com/@[^/]+/video/\d+)", url)
    return match.group(1) if match else url

def get_stats(raw_url):
    url = clean_url(raw_url)
    params = {"url": url, "token": TOKEN, "new_version": False, "download_video": False}
    try:
        data = requests.get(ROOT_URL + ENDPOINT, params=params, timeout=12).json()
        if "data" not in data or not data["data"]:
            return None
        s = data["data"][0]["statistics"]
        return {
            "VIEWS": s["play_count"],
            "COMMENTS": s["comment_count"],
            "SHARES": s["share_count"],
            "LIKES": s["digg_count"]
        }
    except Exception as e:
        print(f"[ERROR] {e}")
        return None

def scraper_task(worksheet_name):
    global task_status
    task_status["running"] = True
    task_status["progress"] = 0
    task_status["log"] = [f"Scraping <strong>{worksheet_name}</strong>..."]

    try:
        sheet = spreadsheet.worksheet(worksheet_name)
        links = sheet.col_values(1)

        if not links or links[0] != "LINK":
            task_status["log"].append("Column A must be exactly <code>LINK</code>")
            task_status["running"] = False
            return

        total = sum(1 for l in links[1:] if l.strip())
        task_status["total"] = total

        updates = []
        for i, link in enumerate(links[1:], start=2):
            if not link.strip():
                task_status["log"].append("Empty row → stopped")
                break

            short = link[:45] + "..." if len(link) > 45 else link
            task_status["current"] = short
            task_status["progress"] = int((i - 1) / total * 100) if total else 0
            task_status["log"].append(f"Row {i}: {short}")

            stats = get_stats(link)
            row = [
                stats["VIEWS"] if stats else "ERROR",
                stats["COMMENTS"] if stats else "ERROR",
                stats["SHARES"] if stats else "ERROR",
                stats["LIKES"] if stats else "ERROR"
            ]
            updates.append({"range": f"B{i}:E{i}", "values": [row]})
            time.sleep(1.1)

        if updates:
            sheet.batch_update(updates)
            task_status["log"].append(f"Updated <strong>{len(updates)}</strong> rows")

    except Exception as e:
        task_status["log"].append(f"Error: {str(e)}")
    finally:
        task_status["running"] = False
        task_status["progress"] = 100

@app.route('/')
def index():
    return render_template('index.html', worksheets=WORKSHEETS)

@app.route('/start', methods=['POST'])
def start():
    global task_status
    if task_status["running"]:
        return jsonify({"error": "Running"}), 400

    ws = request.json.get("worksheet")
    if ws not in WORKSHEETS:
        return jsonify({"error": "Invalid"}), 400

    task_status.update({
        "running": True, "progress": 0, "current": "", "log": [], "worksheet": ws
    })

    threading.Thread(target=scraper_task, args=(ws,), daemon=True).start()
    return jsonify({"status": "started"})

@app.route('/status')
def status():
    return jsonify(task_status)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)