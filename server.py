from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__)

# This is the "Database" that lives on the Pi
state = {
    "drinks": [],
    "food": [],
    "mode": "FOOD"
}

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

if __name__ == '__main__':
    # Runs the server on your local Wi-Fi network
    app.run(host='0.0.0.0', port=8080)
