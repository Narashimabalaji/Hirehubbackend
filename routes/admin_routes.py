from flask import Blueprint, request, jsonify, send_file
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import tempfile
import requests

admin_bp = Blueprint("adminroute", __name__)

client = MongoClient("mongodb+srv://vijayprabakaran1905:Mongodbhirehub@cluster0.uma8of4.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["job_portal"]

# Fetch jobs by status
@admin_bp.route('/api/fetchjobs', methods=['GET'])
def get_jobs_by_status():
    status = request.args.get("status")
    jobs = []

    hirers = db.hirers.find()
    for hirer in hirers:
        for job in hirer.get("jobposts", []):
            if not status or job.get("status") == status:
                job["hirer_email"] = hirer.get("emailid")
                jobs.append(job)

    return jsonify(jobs), 200


# Approve a job
@admin_bp.route('/approve-job/<job_id>', methods=['POST'])
def approve_job(job_id):
    result = db.hirers.update_one(
        {"jobposts.id": job_id},
        {"$set": {"jobposts.$.status": "approved"}}
    )
    if result.modified_count:
        return jsonify({"message": "Job approved"}), 200
    return jsonify({"error": "Job not found or already approved"}), 404

# Reject a job
@admin_bp.route('/reject-job/<job_id>', methods=['POST'])
def reject_job(job_id):
    reason = request.json.get("reason", "No reason provided.")
    result = db.hirers.update_one(
        {"jobposts.id": job_id},
        {
            "$set": {
                "jobposts.$.status": "rejected",
                "jobposts.$.rejection_reason": reason
            }
        }
    )
    if result.modified_count:
        return jsonify({"message": "Job rejected"}), 200
    return jsonify({"error": "Job not found or already rejected"}), 404


# Admin views a resume
@admin_bp.route('/admin/view_resume', methods=['GET'])
def log_resume_view():
    url = request.args.get("url")
    admin_email = request.args.get("adminEmail")
    job_id = request.args.get("jobId")
    job_title = request.args.get("jobTitle")

    db.logs.insert_one({
        "resume": url,
        "email": admin_email,
        "job_id": job_id,
        "job_title": job_title,
        "action": "viewed",
        "timestamp": datetime.utcnow()
    })

    return jsonify({"resume_url": url})

# Admin downloads a resume
@admin_bp.route('/admin/download_resume', methods=['GET'])
def download_resume():
    url = request.args.get("url")
    admin_email = request.args.get("adminEmail")
    job_id = request.args.get("jobId")
    job_title = request.args.get("jobTitle")

    # Log download
    db.logs.insert_one({
        "resume": url,
        "email": admin_email,
        "job_id": job_id,
        "job_title": job_title,
        "action": "downloaded",
        "timestamp": datetime.utcnow()
    })

    try:
        r = requests.get(url, stream=True)
        r.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(r.content)
            tmp.flush()
            return send_file(tmp.name, as_attachment=True, download_name="resume.pdf")
    except Exception as e:
        return jsonify({"error": f"Failed to download resume: {str(e)}"}), 500

# Get logs for a job
@admin_bp.route('/admin/logs', methods=['GET'])
def get_logs():
    job_id = request.args.get("jobId")
    logs = list(db.logs.find({"job_id": job_id}))
    for log in logs:
        log["_id"] = str(log["_id"])
        log["timestamp"] = log["timestamp"].isoformat()
    return jsonify({"logs": logs}), 200
