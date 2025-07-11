# chatgroq.py

from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from pymongo import MongoClient
import fitz  # PyMuPDF
import os
import requests
import re
from dotenv import load_dotenv
from langdetect import detect
from flask import Response, stream_with_context
from openai import OpenAI


chatgroq_bp = Blueprint("chatgroq", __name__)


# --- Config ---
GROQ_API_KEY = "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"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL_NAME = "llama3-70b-8192"

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# --- MongoDB ---
client = MongoClient("mongodb+srv://vijayprabakaran1905:Mongodbhirehub@cluster0.uma8of4.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["job_portal"]
jobs_collection = db.hirers

# --- Utilities ---

def extract_text_from_pdf(filepath):
    doc = fitz.open(filepath)
    text = ""
    for page in doc:
        text += page.get_text()
    return text.strip()

def fetch_jobs_matching(text_input=None, filters=None):
    query = {"status": "approved"}
    matched_jobs = []

    for hirer in jobs_collection.find():
        for job in hirer.get("jobposts", []):
            # Match status
            if job.get("status") != "approved":
                continue

            # --- FILTER-BASED SEARCH ---
            if filters:
                match = True
                if "qualification" in filters and filters["qualification"]:
                    qualifications = [q.strip().lower() for q in filters["qualification"].split(",")]
                    if job.get("qualification", "").lower() not in qualifications:
                        match = False
                if "keywords" in filters and filters["keywords"]:
                    if not any(kw.lower() in [k.lower() for k in job.get("keywords", [])] for kw in filters["keywords"]):
                        match = False
                if "category" in filters and filters["category"]:
                    if job.get("category", "").lower() != filters["category"].lower():
                        match = False
                if "title" in filters and filters["title"]:
                    if filters["title"].lower() not in job.get("title", "").lower():
                        match = False
                if match:
                    matched_jobs.append(job)

            # --- TEXT-BASED SEARCH (e.g., from resume or question) ---
            elif text_input:
                text_input = text_input.lower()
                combined = (
                    job.get("title", "") + " " +
                    job.get("description", "") + " " +
                    job.get("qualification", "") + " " +
                    " ".join(job.get("keywords", []))
                ).lower()

                if any(word in combined for word in text_input.split()):
                    matched_jobs.append(job)

    return matched_jobs[:10]  # Limit to 10




def build_prompt(user_question, resume_text=None, job_list=None):
    try:
        detected_lang = detect(user_question)
    except:
        detected_lang = "en"  # fallback to English if detection fails

    system_msg = (
        "You are a helpful AI assistant. "
        "Only use the provided job listings from the database to answer the user's question. "
        "Do not make up any job openings or qualifications. "
    )

    # Only switch language if it's not English
    if detected_lang != "en":
        system_msg += (
            f"Respond in {detected_lang.upper()} only if the user's question is in that language. "
            f"Otherwise, respond in English."
        )
    else:
        system_msg += "Respond in English."

    resume_section = f"User Resume:\n{resume_text}" if resume_text else "No resume provided."

    if job_list:
        jobs_info = "\n".join(
            [
                f"{i+1}. Title: {job.get('title')}\n"
                f"   Company: {job.get('company_name', 'Unknown')}\n"
                f"   Qualification Required: {job.get('qualification', 'N/A')}\n"
                f"   Description: {job.get('description', 'N/A')}\n"
                for i, job in enumerate(job_list)
            ]
        )
    else:
        jobs_info = "No job matches found in the database."

    user_prompt = (
        f"{resume_section}\n\n"
        f"Available Job Listings:\n{jobs_info}\n\n"
        f"User Question: {user_question}\n\n"
        f"Answer based only on the listings above. "
        f"If any job matches the user's qualification, mention them clearly. "
        f"Do not say no jobs exist unless the job list is empty."
    )

    return [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_prompt}
    ]
def chat_with_groq(messages):
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.7
    }

    response = requests.post(GROQ_API_URL, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        print("Groq API Error:", response.text)
        return "Sorry, I couldn't get a response from the AI."

# --- Routes ---

@chatgroq_bp.route("/chat", methods=["POST"])
def chat():
    data = request.json
    question = data.get("question", "").strip()
    filters = data.get("filters", {})

    if not question:
        return jsonify({"error": "Question is required."}), 400

    jobs = fetch_jobs_matching(text_input=question, filters=filters)
    prompt = build_prompt(question, resume_text=None, job_list=jobs)
    ai_response = chat_with_groq(prompt)

    return jsonify({
        "matched_jobs": [job.get("title") for job in jobs],
        "response": ai_response
    })




@chatgroq_bp.route("/upload_resume_and_chat", methods=["POST"])
def upload_resume_and_chat():
    question = request.form.get("question", "").strip()
    if not question:
        return jsonify({"error": "Question is required."}), 400

    if 'resume' not in request.files:
        return jsonify({"error": "No resume file uploaded."}), 400

    resume_file = request.files['resume']
    filename = secure_filename(resume_file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    resume_file.save(filepath)

    resume_text = extract_text_from_pdf(filepath)
    jobs = fetch_jobs_matching(resume_text)
    prompt = build_prompt(question, resume_text, jobs)
    ai_response = chat_with_groq(prompt)

    return jsonify({
        "matched_jobs": [job.get("title") for job in jobs],
        "response": ai_response
    })


@chatgroq_bp.route("/generatedescription", methods=["POST"])
def job_description_generation():
    try:
        data = request.json

        # Safely convert inputs to string
        title = str(data.get("title", "")).strip()
        category = str(data.get("category", "")).strip()
        experience = str(data.get("experience", "")).strip()

        # Handle keywords which might be a list or string
        raw_keywords = data.get("keywords", [])
        if isinstance(raw_keywords, list):
            keywords = ", ".join(map(str, raw_keywords)).strip()
        else:
            keywords = str(raw_keywords).strip()

        # Basic validation
        if not title or not category or not experience or not keywords:
            return jsonify({"error": "All fields are required."}), 400

        # Prompt construction
        prompt = f"""
You are an expert HR content writer. Write a clear, engaging, and inclusive job description for the following role:

- **Job Title:** {title}
- **Category/Department:** {category}
- **Experience Required:** {experience}
- **Keywords/Skills:** {keywords}

Format the output in clean, structured Markdown with these sections:

### Job Title  
{title}

### Department  
{category}

### About the Role  
Write a brief overview of the position, its mission, and its value to the organization.

### Responsibilities  
Use action-oriented bullet points tailored to the experience level and keywords provided.

### Required Qualifications  
Based on the experience and keywords, include technical and soft skills in bullets.

### Benefits  
Include a short placeholder section of benefits.

### Equal Opportunity Statement  
Add a standard, inclusive EEO message.

Use inclusive and professional tone.
        """

        # LLaMA-3 Groq setup
        api_key = "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"
        api_base = "https://api.groq.com/openai/v1"
        model = "llama3-70b-8192"

        client = OpenAI(api_key=api_key, base_url=api_base)

        # Streaming response from Groq
        stream = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant who writes high-quality job descriptions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000,
            stream=True
        )

        # Accumulate content from stream
        full_response = ""
        for chunk in stream:
            content = getattr(chunk.choices[0].delta, "content", None)
            if content:
                full_response += content

        return jsonify({"description": full_response})

    except Exception as e:
        return jsonify({"error": f"Failed to generate description: {str(e)}"}), 500
