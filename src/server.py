"""Minimal Flask web server providing a local API for Smart Job Apply Assistant."""

from flask import Flask, request, jsonify

from src.config import load_config
from src.db import init_db, get_jobs, get_job, confirm_submission, get_logs

try:
    from src.orchestrator import run_single
except ImportError:
    run_single = None

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Smart Job Apply Assistant</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #333; }
  h1 { font-size: 1.4rem; }
  table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
  th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #ddd; }
  th { background: #f5f5f5; }
  button { padding: 0.3rem 0.8rem; border: none; border-radius: 4px; cursor: pointer; color: #fff; }
  .btn-start { background: #2563eb; }
  .btn-confirm { background: #16a34a; }
  .btn-start:hover { background: #1d4ed8; }
  .btn-confirm:hover { background: #15803d; }
  .status { font-size: 0.85rem; padding: 0.15rem 0.5rem; border-radius: 3px; }
  #msg { margin-top: 1rem; padding: 0.5rem; display: none; border-radius: 4px; }
</style>
</head>
<body>
<h1>Smart Job Apply Assistant</h1>
<div id="msg"></div>
<table>
  <thead><tr><th>ID</th><th>Company</th><th>Role</th><th>Status</th><th>Action</th></tr></thead>
  <tbody id="jobs"></tbody>
</table>
<script>
const TOKEN = "";
function headers() {
  const h = {"Content-Type": "application/json"};
  if (TOKEN) h["Authorization"] = "Bearer " + TOKEN;
  return h;
}
function showMsg(text, ok) {
  const el = document.getElementById("msg");
  el.textContent = text;
  el.style.display = "block";
  el.style.background = ok ? "#dcfce7" : "#fee2e2";
  setTimeout(() => el.style.display = "none", 4000);
}
function loadJobs() {
  fetch("/api/jobs", {headers: headers()}).then(r => r.json()).then(data => {
    const tbody = document.getElementById("jobs");
    tbody.innerHTML = "";
    data.jobs.forEach(j => {
      let action = "";
      if (j.status === "pending")
        action = `<button class="btn-start" onclick="startJob(${j.id})">Start</button>`;
      else if (j.status === "ready_for_submit")
        action = `<button class="btn-confirm" onclick="confirmJob(${j.id})">Confirm Submit</button>`;
      tbody.innerHTML += `<tr><td>${j.id}</td><td>${j.company || ""}</td><td>${j.role || ""}</td><td><span class="status">${j.status}</span></td><td>${action}</td></tr>`;
    });
  });
}
function startJob(id) {
  showMsg("Starting job " + id + "…", true);
  fetch("/api/jobs/" + id + "/start", {method: "POST", headers: headers()})
    .then(r => r.json()).then(d => { showMsg(JSON.stringify(d.result), !d.result.error); loadJobs(); });
}
function confirmJob(id) {
  fetch("/api/jobs/" + id + "/confirm-submit", {method: "POST", headers: headers()})
    .then(r => r.json()).then(() => { showMsg("Job " + id + " submitted!", true); loadJobs(); });
}
loadJobs();
</script>
</body>
</html>"""


def create_app(config=None):
    """Create and return the Flask application."""
    if config is None:
        config = load_config()

    db_path = config.get("db_path", "jobs.db")
    init_db(db_path)

    app = Flask(__name__)
    app.config["APP_CONFIG"] = config

    server_token = config.get("server_token", "")

    @app.before_request
    def _check_auth():
        if not request.path.startswith("/api/"):
            return None
        if not server_token:
            return None
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {server_token}":
            return jsonify({"error": "unauthorized"}), 401
        return None

    @app.route("/")
    def dashboard():
        return DASHBOARD_HTML

    @app.route("/api/jobs", methods=["GET"])
    def list_jobs():
        status = request.args.get("status")
        jobs = get_jobs(db_path, status=status)
        return jsonify({"jobs": jobs})

    @app.route("/api/jobs/<int:job_id>", methods=["GET"])
    def get_single_job(job_id):
        job = get_job(db_path, job_id)
        if job is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"job": job})

    @app.route("/api/jobs/<int:job_id>/start", methods=["POST"])
    def start_job(job_id):
        if run_single is None:
            return jsonify({"error": "orchestrator not available"}), 503
        result = run_single(job_id, config)
        return jsonify({"result": result})

    @app.route("/api/jobs/<int:job_id>/confirm-submit", methods=["POST"])
    def confirm_submit(job_id):
        confirm_submission(db_path, job_id)
        return jsonify({"status": "submitted", "job_id": job_id})

    @app.route("/api/logs", methods=["GET"])
    def list_logs():
        job_id = request.args.get("job_id", type=int)
        logs = get_logs(db_path, job_id=job_id)
        return jsonify({"logs": logs})

    return app


if __name__ == "__main__":
    cfg = load_config()
    application = create_app(cfg)
    application.run(
        host=cfg.get("server_host", "127.0.0.1"),
        port=cfg.get("server_port", 5000),
    )
