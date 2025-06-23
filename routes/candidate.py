from flask import Blueprint, request, jsonify, send_file
from flask_cors import CORS
from models.users import search_jobs
from bson import ObjectId
from datetime import datetime
from werkzeug.utils import secure_filename
import uuid
from pymongo import MongoClient
from supabase import create_client
import tempfile
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import logging

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

candidate_bp = Blueprint("candidate", __name__)

# MongoDB Configuration
try:
    client = MongoClient("mongodb+srv://vijayprabakaran1905:Mongodbhirehub@cluster0.uma8of4.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
    db_jobportal = client["job_portal"]
    jobs_collection = db_jobportal["jobs"]
    resume_stats = db_jobportal["resume_stats"]
    logs_collection = db_jobportal["logs"]
    logger.info("MongoDB connection established")
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {str(e)}")
    raise

# Supabase Configuration
SUPABASE_URL = "https://ravrvsezztusrbnynuhj.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJhdnJ2c2V6enR1c3JibnludWhqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NzQ2MTQ5NCwiZXhwIjoyMDYzMDM3NDk0fQ.anh2MgM_ekIGWgCQvV198GudwpHPxDQcbOh4YffiTVY"
SUPABASE_BUCKET = "resumes"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Email Configuration
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_ADDRESS = "GadgetZoneEcom@gmail.com"
EMAIL_PASSWORD = "icho xyqy mgsu qrdv"

def send_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(EMAIL_HOST, EMAIL_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Email sending failed: {str(e)}")
        return False

@candidate_bp.route("/search", methods=["GET"])
def search():
    try:
        qualification = request.args.get("qualification")
        keywords = request.args.get("keywords")
        logger.debug(f"Search query: qualification={qualification}, keywords={keywords}")

        filters = {}
        if qualification:
            filters["qualification"] = qualification
        if keywords:
            filters["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]

        jobs = search_jobs(filters)
        for job in jobs:
            job["_id"] = str(job["_id"])
        return jsonify(jobs), 200
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@candidate_bp.route("/upload_resume/<job_id>", methods=["POST"])
def upload_resume(job_id):
    try:
        email = request.form.get("email")
        name = request.form.get("name")
        resume_file = request.files.get("resume")
        logger.debug(f"Uploading resume for job_id={job_id}, email={email}, name={name}")

        if not all([email, name, resume_file]):
            return jsonify({"error": "Missing required fields"}), 400

        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            return jsonify({"error": "Job not found"}), 404

        filename = f"{uuid.uuid4()}_{secure_filename(resume_file.filename)}"
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
            resume_file.save(tmp.name)
            temp_file_path = tmp.name

        try:
            supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=filename,
                file=temp_file_path,
                file_options={"content-type": resume_file.mimetype}
            )
        except Exception as upload_error:
            logger.error(f"Supabase upload failed: {str(upload_error)}")
            return jsonify({"error": f"Failed to upload to Supabase: {str(upload_error)}"}), 500
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

        resume_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"

        jobs_collection.update_one(
            {"_id": ObjectId(job_id)},
            {
                "$push": {
                    "applications": {
                        "email": email,
                        "name": name,
                        "resume_url": resume_url,
                        "uploaded_at": datetime.utcnow()
                    }
                }
            }
        )
        logger.info(f"Application stored for job_id={job_id}, resume_url={resume_url}")

        email_body = f"""
Hi {name},

Thank you for applying to the job: {job.get("title", "Unknown Job")}.
Your resume has been successfully submitted.

You can view your resume here: {resume_url}

Best regards,
Hire Hub Team
"""
        send_email(email, "Application Submitted Successfully", email_body)

        return jsonify({
            "message": "Resume uploaded successfully",
            "resume_url": resume_url
        }), 200
    except Exception as e:
        logger.error(f"Upload resume error: {str(e)}")
        return jsonify({"error": str(e)}), 500

def serialize_job(job):
    applications = [
        {
            "email": app.get("email"),
            "name": app.get("name"),
            "resume_url": app.get("resume_url"),
            "uploaded_at": app.get("uploaded_at").isoformat() if isinstance(app.get("uploaded_at"), datetime) else app.get("uploaded_at")
        } for app in job.get("applications", [])
    ]
    return {
        "_id": str(job["_id"]),
        "title": job.get("title"),
        "description": job.get("description"),
        "qualification": job.get("qualification"),
        "category": job.get("category"),
        "keywords": job.get("keywords", []),
        "status": job.get("status"),
        "created_by": job.get("created_by"),
        "created_at": job.get("created_at").isoformat() if isinstance(job.get("created_at"), datetime) else job.get("created_at"),
        "rejection_reason": job.get("rejection_reason", ""),
        "applications": applications
    }

@candidate_bp.route('/api/jobs', methods=['GET'])
def get_all_jobs():
    try:
        status = request.args.get("status")
        query = {"status": status} if status else {}
        logger.debug(f"Fetching jobs with query: {query}")
        jobs = list(jobs_collection.find(query))
        serialized_jobs = [serialize_job(job) for job in jobs]
        return jsonify(serialized_jobs), 200
    except Exception as e:
        logger.error(f"Get jobs error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@candidate_bp.route('/resumes/<job_id>', methods=['GET'])
def get_resumes(job_id):
    try:
        logger.debug(f"Fetching resumes for job_id={job_id}")
        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            return jsonify({"error": "Job not found"}), 404
        applications = job.get("applications", [])
        result = [
            {
                "name": app.get("name"),
                "email": app.get("email"),
                "resume_url": app.get("resume_url"),
                "uploaded_at": app.get("uploaded_at").isoformat() if isinstance(app.get("uploaded_at"), datetime) else app.get("uploaded_at")
            } for app in applications
        ]
        return jsonify({"resumes": result}), 200
    except Exception as e:
        logger.error(f"Get resumes error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@candidate_bp.route("/approve-job/<job_id>", methods=["POST"])
def approve_job(job_id):
    try:
        logger.debug(f"Approving job_id={job_id}")
        result = jobs_collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"status": "approved", "rejection_reason": ""}}
        )
        if result.modified_count == 0:
            return jsonify({"message": "Job not found or already approved"}), 404
        return jsonify({"message": "Job approved"}), 200
    except Exception as e:
        logger.error(f"Approve job error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@candidate_bp.route("/reject_job/<job_id>", methods=["POST"])
def reject_job(job_id):
    try:
        data = request.get_json()
        reason = data.get("reason", "No reason provided")
        logger.debug(f"Rejecting job_id={job_id}, reason={reason}")
        result = jobs_collection.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"status": "rejected", "rejection_reason": reason}}
        )
        if result.modified_count == 0:
            return jsonify({"message": "Job not found or already rejected"}), 404
        return jsonify({"message": "Job rejected"}), 200
    except Exception as e:
        logger.error(f"Reject job error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@candidate_bp.route("/admin/view_resume", methods=["GET"])
def view_resume():
    try:
        resume_url = request.args.get("url")
        admin_email = request.args.get("adminEmail")
        job_id = request.args.get("jobId")
        job_title = request.args.get("jobTitle")
        logger.debug(f"Viewing resume: url={resume_url}, admin_email={admin_email}, job_id={job_id}, job_title={job_title}")

        if not all([resume_url, admin_email, job_id, job_title]):
            logger.warning("Missing required parameters in view_resume")
            return jsonify({"error": "Missing required parameters"}), 400

        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            logger.warning(f"Job not found: job_id={job_id}")
            return jsonify({"error": "Job not found"}), 404

        application = next((app for app in job.get("applications", []) if app["resume_url"] == resume_url), None)
        if not application:
            logger.warning(f"Resume not found for url={resume_url} in job_id={job_id}")
            return jsonify({"error": "Resume not found for this job"}), 404

        logs_collection.insert_one({
            "email": admin_email,
            "job_id": job_id,
            "name": job_title,
            "resume": resume_url,
            "action": "view",
            "timestamp": datetime.utcnow()
        })

        resume_stats.update_one(
            {"resume_url": resume_url, "job_id": job_id},
            {
                "$inc": {"view_count": 1},
                "$setOnInsert": {
                    "resume_name": resume_url.split("/")[-1],
                    "download_count": 0
                }
            },
            upsert=True
        )
        logger.info(f"View logged for resume_url={resume_url}, job_id={job_id}")

        return jsonify({"message": "View logged", "resume_url": resume_url}), 200
    except Exception as e:
        logger.error(f"View resume error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@candidate_bp.route("/admin/download_resume", methods=["GET"])
def download_resume():
    try:
        resume_url = request.args.get("url")
        admin_email = request.args.get("adminEmail")
        job_id = request.args.get("jobId")
        job_title = request.args.get("jobTitle")
        logger.debug(f"Downloading resume: url={resume_url}, admin_email={admin_email}, job_id={job_id}, job_title={job_title}")

        if not all([resume_url, admin_email, job_id, job_title]):
            logger.warning("Missing required parameters in download_resume")
            return jsonify({"error": "Missing required parameters"}), 400

        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            logger.warning(f"Job not found: job_id={job_id}")
            return jsonify({"error": "Job not found"}), 404

        application = next((app for app in job.get("applications", []) if app["resume_url"] == resume_url), None)
        if not application:
            logger.warning(f"Resume not found for url={resume_url} in job_id={job_id}")
            return jsonify({"error": "Resume not found for this job"}), 404

        logs_collection.insert_one({
            "email": admin_email,
            "job_id": job_id,
            "name": job_title,
            "resume": resume_url,
            "action": "download",
            "timestamp": datetime.utcnow()
        })

        resume_stats.update_one(
            {"resume_url": resume_url, "job_id": job_id},
            {
                "$inc": {"download_count": 1},
                "$setOnInsert": {
                    "resume_name": resume_url.split("/")[-1],
                    "view_count": 0
                }
            },
            upsert=True
        )

        r = requests.get(resume_url, stream=True)
        if r.status_code != 200:
            logger.error(f"Failed to download file from {resume_url}: status={r.status_code}")
            return jsonify({"error": "Failed to download file"}), 500

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(r.content)
            tmp.flush()
            logger.info(f"Resume downloaded for resume_url={resume_url}")
            return send_file(
                tmp.name,
                as_attachment=True,
                download_name="resume.pdf",
                mimetype="application/pdf"
            )
    except Exception as e:
        logger.error(f"Download resume error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@candidate_bp.route("/admin/logs", methods=["GET"])
def get_logs():
    try:
        job_id = request.args.get("jobId")
        if not job_id:
            logger.warning("Missing jobId in get_logs")
            return jsonify({"error": "Missing jobId"}), 400

        logger.debug(f"Fetching logs for job_id={job_id}")
        logs = list(logs_collection.find({"job_id": job_id}))
        serialized_logs = [{
            "email": log["email"],
            "job_id": log["job_id"],
            "name": log["name"],
            "resume": log["resume"],
            "action": log["action"],
            "timestamp": log["timestamp"].isoformat() if isinstance(log["timestamp"], datetime) else log["timestamp"]
        } for log in logs]
        return jsonify({"logs": serialized_logs}), 200
    except Exception as e:
        logger.error(f"Get logs error: {str(e)}")
        return jsonify({"error": str(e)}), 500
