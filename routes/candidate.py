from flask import Blueprint, request, jsonify
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
from flask import send_file

candidate_bp = Blueprint("candidate", __name__)

client = MongoClient("mongodb+srv://vijayprabakaran1905:Mongodbhirehub@cluster0.uma8of4.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db_jobportal = client["job_portal"]
jobs_collection = db_jobportal["jobs"]
resume_stats = db_jobportal["resume_stats"]
SUPABASE_URL="https://ravrvsezztusrbnynuhj.supabase.co"
SUPABASE_KEY="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJhdnJ2c2V6enR1c3JibnludWhqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0NzQ2MTQ5NCwiZXhwIjoyMDYzMDM3NDk0fQ.anh2MgM_ekIGWgCQvV198GudwpHPxDQcbOh4YffiTVY"
SUPABASE_BUCKET="resumes"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

EMAIL_HOST="smtp.gmail.com"
EMAIL_PORT=587
EMAIL_ADDRESS="GadgetZoneEcom@gmail.com"
EMAIL_PASSWORD="icho xyqy mgsu qrdv"



def send_email(to_email, subject, body):
    from_email = EMAIL_ADDRESS
    password = EMAIL_PASSWORD
    host = EMAIL_HOST
    port = EMAIL_PORT

    msg = MIMEMultipart()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(host, port)
        server.starttls()
        server.login(from_email, password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email sending failed: {e}")
        return False


@candidate_bp.route("/search", methods=["GET"])
def search():
    qualification = request.args.get("qualification")
    keywords = request.args.get("keywords")  # changed from 'keyword' to 'keywords'

    filters = {}

    if qualification:
        filters["qualification"] = qualification  # keep as comma-separated string, your search_jobs will split

    if keywords:
        # convert comma-separated keywords string into list
        filters["keywords"] = [k.strip() for k in keywords.split(",") if k.strip()]

    jobs = search_jobs(filters)

    for job in jobs:
        job["_id"] = str(job["_id"])  # Convert ObjectId to string

    return jsonify(jobs)



@candidate_bp.route("/upload_resume/<job_id>", methods=["POST"])
def upload_resume(job_id):
    try:
        email = request.form.get("email")
        name = request.form.get("name")
        resume_file = request.files.get("resume")

        if not all([email, name, resume_file]):
            return jsonify({"error": "Missing required fields"}), 400

        # Check if job exists
        job = db_jobportal.jobs.find_one({"_id": ObjectId(job_id)})
        if not job:
            return jsonify({"error": "Job not found"}), 404

        # Generate secure filename
        filename = f"{uuid.uuid4()}_{secure_filename(resume_file.filename)}"

        # Save resume to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as tmp:
            resume_file.save(tmp.name)
            temp_file_path = tmp.name

        # Upload to Supabase
        try:
            supabase.storage.from_(SUPABASE_BUCKET).upload(
                path=filename,
                file=temp_file_path,
                file_options={"content-type": resume_file.mimetype}
            )
        except Exception as upload_error:
            return jsonify({"error": f"Failed to upload to Supabase: {str(upload_error)}"}), 500
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

        resume_url = f"{SUPABASE_URL}/storage/v1/object/public/{SUPABASE_BUCKET}/{filename}"

        # Store application
        db_jobportal.applications.insert_one({
            "job_id": str(job_id),
            "email": email,
            "name": name,
            "resume_url": resume_url,
            "uploaded_at": datetime.utcnow()
        })

        # Send email
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
        return jsonify({"error": str(e)}), 500

# Serialize job for frontend
def serialize_job(job):
    return {
        "id": str(job["_id"]),
        "title": job.get("title"),
        "description": job.get("description"),
        "qualification": job.get("qualification"),
        "category": job.get("category"),
        "keywords": job.get("keywords", []),
        "status": job.get("status"),
        "created_by": job.get("created_by"),
        "created_at": job.get("created_at").isoformat() if isinstance(job.get("created_at"), datetime) else job.get("created_at"),
    }

@candidate_bp.route('/api/jobs', methods=['GET'])
def get_all_jobs():
    try:
        status = request.args.get("status")
        query = {}
        if status:
            query["status"] = status

        jobs = list(db_jobportal.jobs.find(query))
        serialized_jobs = [serialize_job(job) for job in jobs]
        return jsonify(serialized_jobs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route('/resumes/<job_id>', methods=['GET'])
def get_resumes(job_id):
    try:
        applications = db_jobportal.applications.find({"job_id": str(job_id)})
        result = [{
            "name": app.get("name"),
            "email": app.get("email"),
            "resume_url": app.get("resume_url"),
            "uploaded_at": app.get("uploaded_at").isoformat() if isinstance(app.get("uploaded_at"), datetime) else app.get("uploaded_at")
        } for app in applications]

        return jsonify({"resumes": result}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route("/approve-job/<job_id>", methods=["POST"])
def approve_job(job_id):
    try:
        result = db_jobportal.jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"status": "approved"}}
        )
        if result.modified_count == 0:
            return jsonify({"message": "Job not found or already approved"}), 404
        return jsonify({"message": "Job approved"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route("/reject_job/<job_id>", methods=["POST"])
def reject_job(job_id):
    try:
        data = request.get_json()
        reason = data.get("reason", "No reason provided")
        result = db_jobportal.jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"status": "rejected", "rejection_reason": reason}}
        )
        if result.modified_count == 0:
            return jsonify({"message": "Job not found or already rejected"}), 404
        return jsonify({"message": "Job rejected"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route("/admin/view_resume", methods=["GET"])
def view_resume():
    try:
        resume_url = request.args.get("url")
        admin_email = request.args.get("adminEmail")
        job_id = request.args.get("jobId")
        job_title = request.args.get("jobTitle")

        if not resume_url:
            return jsonify({"error": "Missing resume URL"}), 400

        db_jobportal.logs.insert_one({
            "adminEmail": admin_email,
            "jobId": job_id,
            "jobTitle": job_title,
            "resumeUrl": resume_url,
            "action": "view",
            "timestamp": datetime.utcnow().isoformat()
        })

        resume_stats.update_one(
            {"resumeUrl": resume_url},
            {
                "$inc": {"view_count": 1},
                "$setOnInsert": {
                    "jobId": job_id,
                    "resumeUrl": resume_url,
                    "resumeName": resume_url.split("/")[-1],
                    "download_count": 0
                }
            },
            upsert=True
        )

        return jsonify({"message": "View logged"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route("/admin/download_resume", methods=["GET"])
def download_resume():
    try:
        resume_url = request.args.get("url")
        admin_email = request.args.get("adminEmail")
        job_id = request.args.get("jobId")
        job_title = request.args.get("jobTitle")

        if not resume_url:
            return jsonify({"error": "Missing resume URL"}), 400

        db_jobportal.logs.insert_one({
            "adminEmail": admin_email,
            "jobId": job_id,
            "jobTitle": job_title,
            "resumeUrl": resume_url,
            "action": "download",
            "timestamp": datetime.utcnow().isoformat()
        })

        resume_stats.update_one(
            {"resumeUrl": resume_url},
            {
                "$inc": {"download_count": 1},
                "$setOnInsert": {
                    "jobId": job_id,
                    "resumeUrl": resume_url,
                    "resumeName": resume_url.split("/")[-1],
                    "view_count": 0
                }
            },
            upsert=True
        )

        r = requests.get(resume_url, stream=True)
        if r.status_code != 200:
            return jsonify({"error": "Failed to download file"}), 500

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(r.content)
            tmp.flush()
            return send_file(tmp.name, as_attachment=True, download_name="resume.pdf")

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route("/admin/resume_stats", methods=["GET"])
def get_resume_stats():
    try:
        job_id = request.args.get("jobId")
        if not job_id:
            return jsonify({"error": "Missing jobId"}), 400

        stats = list(resume_stats.find({"jobId": job_id}, {"_id": 0}))
        return jsonify({"stats": stats}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
