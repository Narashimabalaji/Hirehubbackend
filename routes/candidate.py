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

candidate_bp = Blueprint("candidate", __name__)

client = MongoClient("mongodb+srv://vijayprabakaran1905:Mongodbhirehub@cluster0.uma8of4.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db_jobportal = client["job_portal"]
jobs_collection = db_jobportal["jobs"]
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

        # Find job inside jobposts array
        hirer_doc = db_jobportal.hirers.find_one({
            "jobposts.id": job_id
        })

        if not hirer_doc:
            return jsonify({"error": "Job not found"}), 404

        # Extract job post if needed
        job = next((j for j in hirer_doc["jobposts"] if j["id"] == job_id), None)
        if not job:
            return jsonify({"error": "Job not found inside hirer"}), 404

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

        # Optionally log/save resume application
        application_data = {
            "job_id": job_id,
            "job_title": job.get("title", ""),
            "name": name,
            "email": email,
            "resume_url": resume_url,
            "uploaded_at": datetime.utcnow()
        }

        db_jobportal.applications.insert_one(application_data)
       
        # Send confirmation email
        email_body = f"""
        Hi {name},
        
        Thank you for applying to the job: {job.get("title", "Unknown Job")}.
        Your resume has been successfully submitted.
        
        You can view your resume here: {resume_url}
        
        Best regards,
        Hire Hub Team
        """
        
        try:
            send_email(email, "Application Submitted Successfully", email_body)
        except Exception as e:
            print(f"Email sending failed: {e}")
        
        # Return success after everything
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
        "salary":job.get("salary"),
        "location":job.get("location"),
        "company":job.company("company"),
        "hireremailid":job.get("hireremailid"),
        "hirername":job.get("hirername"),
        "keywords": job.get("keywords", []),
        "status": job.get("status"),
        "created_by": job.get("created_by"),
        "created_at": job.get("created_at").isoformat() if isinstance(job.get("created_at"), datetime) else job.get("created_at"),
    }

# Get all approved jobs
@candidate_bp.route('/api/jobs', methods=['GET'])
def get_all_jobs():
    try:
        hirers = db_jobportal.hirers.find()
        approved_jobs = []

        for hirer in hirers:
            jobposts = hirer.get("jobposts", [])
            for job in jobposts:
                if job.get("status") == "approved":
                    # Optional: Add hirer's email or name if needed
                    job["hirer_email"] = hirer["emailid"]
                    approved_jobs.append(job)

        return jsonify(approved_jobs), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Get resumes for a specific job
@candidate_bp.route('/resumes/<job_id>', methods=['GET'])
def get_resumes(job_id):
    try:
        print(f"Fetching resumes for job ID: {job_id}")  # Add this
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

def serialize_jobs(job):
    return {
        "id": str(job.get("id")),
        "title": job.get("title"),
        "description": job.get("description"),
        "qualification": job.get("qualification"),
        "category": job.get("category"),
        "salary": job.get("salary"),
        "location": job.get("location"),
        "company": job.get("company_name"),  # corrected key from your DB
        "hireremailid": job.get("hireremailid"),
        "hirername": job.get("hirername"),
        "keywords": job.get("keywords", []),
        "status": job.get("status"),
        "created_by": job.get("created_by", ""),  # fallback if missing
        "created_at": (
            job.get("created_at").isoformat()
            if isinstance(job.get("created_at"), datetime)
            else job.get("created_at")
        ),
    }

@candidate_bp.route('/particularjob/<string:job_id>', methods=['GET'])
def get_job_by_id(job_id):
    try:
        # Search through all hirers
        hirers = db_jobportal.hirers.find()

        for hirer in hirers:
            jobposts = hirer.get("jobposts", [])
            for job in jobposts:
                if str(job.get("id")) == job_id:
                    # Add hirer data to the job for response
                    job["hireremailid"] = hirer.get("emailid")
                    job["hirername"] = hirer.get("name", "")
                    return jsonify(serialize_jobs(job)), 200

        return jsonify({"error": "Job not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route('/posted/hirer_jobs', methods=['POST'])
def get_jobs_by_hirer_email():
    try:
        data = request.get_json()
        email = data.get("emailid")

        if not email:
            return jsonify({"error": "Missing emailid in request"}), 400

        hirer = db_jobportal.hirers.find_one({"emailid": email})
        if not hirer:
            return jsonify({"error": "No hirer found with that email"}), 404

        jobposts = hirer.get("jobposts", [])

        # Add hirer info to each job for frontend
        job_data = []
        for job in jobposts:
            job["hireremailid"] = hirer.get("emailid")
            job["hirername"] = hirer.get("name", "")
            job_data.append(serialize_jobs(job))

        return jsonify(job_data), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@candidate_bp.route('/save_job', methods=['POST'])
def save_job_for_user():
    try:
        data = request.get_json()
        email = data.get("emailid")
        job_id = data.get("job_id")

        if not email or not job_id:
            return jsonify({"error": "Missing emailid or job_id"}), 400

        user = db_jobportal.users.find_one({"Emailid": email, "userType": "seeker"})
        if not user:
            return jsonify({"error": "User not found or not a seeker"}), 404

        # Add job ID if not already in saved list
        db_jobportal.users.update_one(
            {"Emailid": email},
            {"$addToSet": {"saved_jobs": job_id}}
        )

        return jsonify({"message": "Job saved successfully"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route('/unsave_job', methods=['POST'])
def unsave_job():
    try:
        data = request.get_json()
        email = data.get("emailid")
        job_id = data.get("job_id")

        if not email or not job_id:
            return jsonify({"error": "Missing emailid or job_id"}), 400

        result = db_jobportal.users.update_one(
            {"Emailid": email},
            {"$pull": {"saved_jobs": job_id}}
        )

        return jsonify({"message": "Job removed from saved list"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@candidate_bp.route('/saved_jobs/<string:email>', methods=['GET'])
def get_saved_jobs(email):
    try:
        # 1. Find seeker user by email
        user = db_jobportal.users.find_one({"Emailid": email, "userType": "seeker"})
        if not user:
            return jsonify({"error": "User not found or not a seeker"}), 404

        saved_ids = user.get("saved_jobs", [])
        if not saved_ids:
            return jsonify([]), 200  # No saved jobs

        # 2. Go through hirers and match jobs
        saved_jobs = []
        hirers = db_jobportal.hirers.find()

        for hirer in hirers:
            for job in hirer.get("jobposts", []):
                if str(job.get("id")) in saved_ids:
                    # Attach hirer info
                    job["hireremailid"] = hirer.get("emailid")
                    job["hirername"] = hirer.get("name", "")
                    saved_jobs.append(serialize_jobs(job))  # Use your serializer

        return jsonify(saved_jobs), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500









