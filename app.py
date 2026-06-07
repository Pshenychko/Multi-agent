"""Flask API — Personal Finance Coach."""
from flask import Flask, request, jsonify
from dotenv import load_dotenv
load_dotenv()

from agents.crew import run_crew
from agents.baseline import run_baseline

app = Flask(__name__)

# In-memory conversation history per session
sessions = {}


@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    query = data.get("query", "")
    mode = data.get("mode", "crew")  # "crew" or "baseline"
    session_id = data.get("session_id", "default")

    if not query:
        return jsonify({"error": "query is required"}), 400

    history = sessions.get(session_id, [])

    if mode == "crew":
        result = run_crew(query, history=history)
    else:
        result = run_baseline(query, history=history)

    # Update history
    history.append({"role": "user", "content": query})
    history.append({"role": "assistant", "content": result["response"]})
    sessions[session_id] = history[-10:]  # keep last 10

    return jsonify({
        "response": result["response"],
        "trace": result["trace"],
        "usage": result["usage"],
        "latency_ms": result["latency_ms"],
        "mode": mode,
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/ask", methods=["POST"])
def ask():
    """Alias for /chat — for container homework compatibility."""
    return chat()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

