from flask import Flask, jsonify, render_template
import json
import os

app = Flask(__name__)

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'Activity_MasterData.json')

def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

@app.route('/')
def index():
    return render_template("index.html")

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404

@app.route('/api/cinnosti')
def api_cinnosti():
    data = load_data()
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=28000)
