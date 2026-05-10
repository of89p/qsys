from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# This is the "Database" that lives on the Pi
state = {
    "drinks": [],
    "food": [],
    "mode": "FOOD"
}

MAX_VISIBLE_ORDERS = 4

# Serve the HTML page to the TV
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

# The TV will constantly ask this URL: "Are there new numbers?"
@app.route('/api/state', methods=['GET'])
def get_state():
    return jsonify(state)

# The Pi will send numbers to this URL when you type
@app.route('/api/update', methods=['POST'])
def update_state():
    global state
    data = request.json
    state['drinks'] = data.get('drinks', state['drinks'])
    state['food'] = data.get('food', state['food'])
    state['mode'] = data.get('mode', state['mode'])
    return jsonify({"status": "success"})

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

    return jsonify({"status": "success", "state": state})

if __name__ == '__main__':
    # Runs the server on your local Wi-Fi network
    app.run(host='0.0.0.0', port=8080)
