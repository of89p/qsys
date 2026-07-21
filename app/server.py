import json
import threading
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    jsonify,
    make_response,
    request,
    send_from_directory,
    stream_with_context,
)

ROOT_DIR = Path(__file__).resolve().parents[1]
APP_DIR = Path(__file__).resolve().parent

load_dotenv(ROOT_DIR / ".env")

app = Flask(__name__)

# This is the "Database" that lives on the Pi
state = {
    "drinks": [],
    "chicken": [],
    "food": [],
    "mode": "FOOD",
    "ding_id": 0,
}
state_changed = threading.Condition()

MAX_VISIBLE_ORDERS = 3


def state_snapshot():
    return {
        "drinks": list(state["drinks"]),
        "chicken": list(state["chicken"]),
        "food": list(state["food"]),
        "mode": state["mode"],
        "ding_id": state["ding_id"],
    }


def sse_event(event_name, data):
    return f"event: {event_name}\ndata: {json.dumps(data)}\n\n"


# Serve the HTML page to the TV
@app.route("/")
def index():
    response = make_response(send_from_directory(APP_DIR, "index.html"))
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


# State snapshot endpoint, useful for manual checks.
@app.route("/api/state", methods=["GET"])
def get_state():
    with state_changed:
        response = jsonify(state_snapshot())
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.route("/api/events", methods=["GET"])
def stream_state():
    @stream_with_context
    def event_stream():
        with state_changed:
            snapshot = state_snapshot()
            last_ding_id = snapshot["ding_id"]

        yield sse_event("state", snapshot)

        while True:
            with state_changed:
                state_changed.wait_for(
                    lambda: state["ding_id"] != last_ding_id,
                    timeout=15,
                )
                snapshot = state_snapshot()

            if snapshot["ding_id"] == last_ding_id:
                yield ": heartbeat\n\n"
                continue

            last_ding_id = snapshot["ding_id"]
            yield sse_event("state", snapshot)

    response = Response(event_stream(), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["Connection"] = "keep-alive"
    response.headers["X-Accel-Buffering"] = "no"
    return response


@app.route("/api/queue", methods=["POST"])
def queue_number():
    data = request.json or {}
    station = str(data.get("station", "")).lower()
    number = str(data.get("number", "")).strip()

    if station not in ("drinks", "chicken", "food"):
        return jsonify(
            {"status": "error", "message": "station must be drinks, chicken or food"}
        ), 400
    if not number.isdigit():
        return jsonify(
            {"status": "error", "message": "number must contain digits only"}
        ), 400
    if len(number) > 3:
        return jsonify(
            {"status": "error", "message": "number must be at most 3 digits"}
        ), 400

    with state_changed:
        final_number = number.zfill(3)
        queue = [existing for existing in state[station] if existing != final_number]
        queue.insert(0, final_number)
        state[station] = queue[:MAX_VISIBLE_ORDERS]
        state["mode"] = station.upper()
        state["ding_id"] += 1
        snapshot = state_snapshot()
        state_changed.notify_all()

    return jsonify({"status": "success", "state": snapshot})


if __name__ == "__main__":
    # Runs the server on your local Wi-Fi network
    app.run(host="0.0.0.0", port=8080, threaded=True)
