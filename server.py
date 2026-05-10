from flask import Flask, request, jsonify, make_response, send_from_directory

app = Flask(__name__)

# This is the "Database" that lives on the Pi
state = {
    "drinks": [],
    "food": [],
    "mode": "FOOD",
    "ding_id": 0,
}

MAX_VISIBLE_ORDERS = 3

# Serve the HTML page to the TV
@app.route('/')
def index():
    response = make_response(send_from_directory('.', 'index.html'))
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response

# The TV will constantly ask this URL: "Are there new numbers?"
@app.route('/api/state', methods=['GET'])
def get_state():
    response = jsonify(state)
    response.headers['Cache-Control'] = 'no-store, max-age=0'
    return response

@app.route('/api/queue', methods=['POST'])
def queue_number():
    data = request.json or {}
    station = str(data.get('station', '')).lower()
    number = str(data.get('number', '')).strip()

    if station not in ("drinks", "food"):
        return jsonify({"status": "error", "message": "station must be drinks or food"}), 400
    if not number.isdigit():
        return jsonify({"status": "error", "message": "number must contain digits only"}), 400
    if len(number) > 3:
        return jsonify({"status": "error", "message": "number must be at most 3 digits"}), 400

    final_number = number.zfill(3)
    queue = [existing for existing in state[station] if existing != final_number]
    queue.insert(0, final_number)
    state[station] = queue[:MAX_VISIBLE_ORDERS]
    state["mode"] = station.upper()
    state["ding_id"] += 1

    return jsonify({"status": "success", "state": state})

if __name__ == '__main__':
    # Runs the server on your local Wi-Fi network
    app.run(host='0.0.0.0', port=8080)
