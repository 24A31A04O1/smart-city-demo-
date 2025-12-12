
import os
import socket


from uuid import uuid4
from flask import jsonify
from werkzeug.utils import secure_filename
from flask import Flask, render_template, request, flash, redirect, url_for, session

from supabase_client import supabase  # your Supabase service key client

app = Flask(__name__)  # ✅ fixed typo
app.secret_key = "super-secret-key"  # ⚠ Change in production

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
MAX_IMAGES = 5
STORAGE_BUCKET = "user_uploads"

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------- Home ----------------
@app.route("/")
def home():
    return render_template("index.html")

# ---------------- Register ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        try:
            resp = supabase.auth.sign_up({"email": email, "password": password})
            user = resp.user
            if not user:
                flash("❌ Registration failed. Try again.")
                return render_template("register.html")
            flash("✅ Registration successful! Please verify your email before login.")
            return redirect(url_for("login"))
        except Exception as e:
            flash(f"❌ Registration error: {e}")
    return render_template("register.html")

# ---------------- Login ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        try:
            resp = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user = resp.user
            if not user:
                flash("❌ Invalid credentials")
                return render_template("login.html")
            if not user.email_confirmed_at:
                flash("⚠ Please verify your email before logging in")
                return render_template("login.html")
            session["user_id"] = user.id
            existing = supabase.table("user_profiles").select("*").eq("user_id", user.id).execute()
            if not existing.data:
                return redirect(url_for("profile"))
            return redirect(url_for("dashboard"))
        except Exception as e:
            flash(f"❌ Login error: {e}")
    return render_template("login.html")

# ---------------- Profile Setup ----------------
@app.route("/profile", methods=["GET", "POST"])
def profile():
    user_id = session.get("user_id")
    if not user_id:
        flash("⚠ Please log in first")
        return redirect(url_for("login"))

    # Fetch dropdown data
    districts = supabase.table("districts").select("id, name").order("name").execute().data
    constituencies = supabase.table("constituencies").select("id, name, district_id").order("name").execute().data
    departments = supabase.table("departments").select("id, name").order("name").execute().data

    # Load saved profile if exists
    result = supabase.table("user_profiles").select("*").eq("user_id", user_id).execute()
    saved = result.data[0] if result.data else None

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip()
        phone_number = request.form.get("phone_number", "").strip()
        state = request.form.get("state", "").strip()
        district_id = request.form.get("district_id", "").strip()
        constituency_id = request.form.get("constituency_id", "").strip()
        department_id = request.form.get("department_id", "").strip()

        supabase.table("user_profiles").upsert({
            "user_id": user_id,
            "full_name": full_name,
            "email": email,
            "phone_number": phone_number,
            "state": state,
            "district_id": district_id,
            "constituency_id": constituency_id,
            
        }).execute()

        return redirect(url_for("dashboard"))

    return render_template("profile.html",
                           districts=districts,
                           constituencies=constituencies,
                           departments=departments,
                           saved=saved)
# ---------------- Dashboard ----------------
@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")
    if not user_id:
        flash("⚠ Please log in first")
        return redirect(url_for("login"))

    return render_template("dashboard.html")
@app.route("/logout")
def logout():
    session.pop("user_id", None)
    flash("✅ You have been logged out.")
    return redirect(url_for("login"))


# ---------------- Submit a New Issue ----------------
MAX_BYTES_PER_IMAGE = 5 * 1024 * 1024  # 5 MB

@app.route("/new_issue", methods=["GET", "POST"])
def new_issue():
    user_id = session.get("user_id")
    if not user_id:
        # For AJAX calls we return JSON so frontend can handle redirects.
        return jsonify({"status": "error", "message": "Not authenticated"}), 401

    # GET: render page with dropdowns
    if request.method == "GET":
        districts = supabase.table("districts").select("id, name").order("name").execute().data
        constituencies = supabase.table("constituencies").select("id, name, district_id").order("name").execute().data
        departments = supabase.table("departments").select("id, name, district_id").order("name").execute().data
        return render_template(
            "new_issue.html",
            districts=districts,
            constituencies=constituencies,
            departments=departments
        )

    # POST: read fields
    district_id = request.form.get("district_id")
    constituency_id = request.form.get("constituency_id")
    department_id = request.form.get("department_id")
    place = request.form.get("place", "").strip()
    address = request.form.get("address", "").strip()
    description = request.form.get("description", "").strip()
    latitude = request.form.get("latitude", "").strip()
    longitude = request.form.get("longitude", "").strip()

    # Basic validation
    if not (place and description and latitude and longitude):
        return jsonify({"status": "error", "message": "Missing required fields (place/description/lat/lng)"}), 400

    try:
        lat_val = float(latitude)
        lng_val = float(longitude)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid latitude/longitude"}), 400

    if not (-90 <= lat_val <= 90 and -180 <= lng_val <= 180):
        return jsonify({"status": "error", "message": "Latitude/longitude out of range"}), 400

    # === Handle image uploads (up to 5) ===
    uploaded_paths = []   # store paths/filenames placed in bucket, e.g. "uuid_filename.jpg"

    try:
        for i in range(1, 6):
            file = request.files.get(f"image{i}")
            if not file:
                continue

            filename_orig = secure_filename(file.filename or "")
            if not filename_orig:
                continue

            # Optional: check mimetype starts with image/
            mimetype = getattr(file, "mimetype", "") or ""
            if not mimetype.startswith("image/"):
                # skip non-image files (or return error if you prefer)
                continue

            # extension check
            if not allowed_file(filename_orig):
                # skip invalid extensions (or return error)
                continue

            content = file.read()
            if not content:
                continue
            if len(content) > MAX_BYTES_PER_IMAGE:
                # cleanup any uploaded files so far
                if uploaded_paths:
                    try:
                        supabase.storage.from_(STORAGE_BUCKET).remove(uploaded_paths)
                    except Exception:
                        pass
                return jsonify({"status":"error","message":"One of the files is too large (max 5MB)"}), 400

            # Unique name and upload
            unique_name = f"{uuid4()}_{filename_orig}"
            path_in_bucket = unique_name  # or "issues/{unique_name}" if you want folder

            # Upload bytes to Supabase storage
            upload_res = supabase.storage.from_(STORAGE_BUCKET).upload(path_in_bucket, content)
            # Some SDKs return error info on upload_res — you can inspect it here if needed.
            # If the SDK returns an error object, check and handle it (example below).
            if getattr(upload_res, "error", None):
                # cleanup and abort
                if uploaded_paths:
                    try:
                        supabase.storage.from_(STORAGE_BUCKET).remove(uploaded_paths)
                    except Exception:
                        pass
                return jsonify({"status":"error","message":"Upload failed","detail":str(upload_res.error)}), 500

            uploaded_paths.append(path_in_bucket)

        # === Insert record into DB with images list ===
        record = {
            "user_id": user_id,
            "district_id": district_id,
            "constituency_id": constituency_id,
            "department_id": department_id,
            "place": place,
            "address": address,
            "description": description,
            "latitude": lat_val,
            "longitude": lng_val,
            "images": uploaded_paths,   # store filenames/paths only
            "status": "Pending",
            "seen_by_department": False,
            "latest_update": None
        }

        resp = supabase.table("problems").insert(record).execute()
        if getattr(resp, "error", None):
            # DB insert failed -> cleanup uploaded files
            if uploaded_paths:
                try:
                    supabase.storage.from_(STORAGE_BUCKET).remove(uploaded_paths)
                except Exception:
                    pass
            return jsonify({"status":"error","message":"DB insert failed","detail":str(resp.error)}), 500

        inserted = resp.data[0] if getattr(resp, "data", None) else None
        return jsonify({"status":"success","message":"Issue created","issue":inserted}), 201

    except Exception as e:
        # Cleanup uploaded files on any unexpected server error
        if uploaded_paths:
            try:
                supabase.storage.from_(STORAGE_BUCKET).remove(uploaded_paths)
            except Exception:
                pass
        print("Error in new_issue POST:", e)
        return jsonify({"status":"error","message":"Server error","detail":str(e)}), 500
# Get departments by district_id (or state_id if that’s how you linked)
@app.route("/departments_by_district/<district_id>")
def departments_by_district(district_id):
    try:
        departments = supabase.table("departments") \
            .select("id, name") \
            .eq("district_id", district_id) \
            .order("name") \
            .execute().data
        return jsonify(departments)
    except Exception as e:
        return jsonify([])
@app.route("/districts")
def get_districts():
    try:
        districts = supabase.table("districts").select("id, name").order("name").execute().data
        return jsonify(districts)
    except Exception as e:
        print("Error fetching districts:", e)
        return jsonify([])
@app.route("/constituencies/<district_id>")
def get_constituencies(district_id):
    try:
        data = supabase.table("constituencies") \
            .select("id, name") \
            .eq("district_id", district_id) \
            .order("name") \
            .execute().data
        return jsonify(data)
    except Exception as e:
        print("Error fetching constituencies:", e)
        return jsonify([])


# ---------------- Submitted Issues ----------------
PUBLIC_BUCKET_URL = "https://rcrbazstbgqfmhzubmrg.supabase.co/storage/v1/object/public/user_uploads/"

@app.route("/submitted_issues")
def submitted_issues():
    user_id = session.get("user_id")
    if not user_id:
        flash("⚠ Please log in first")
        return redirect(url_for("login"))

    try:
        issues = (
            supabase.table("problems")
            .select("*, districts(name), constituencies(name), departments(name)")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
            ).data

        # 🔥 FIX: Build full URLs
        for issue in issues:
            final_urls = []
            if issue.get("images"):
                for filename in issue["images"]:
                    full_url = PUBLIC_BUCKET_URL + filename
                    final_urls.append(full_url)

            issue["images"] = final_urls

        return render_template("submitted_issues.html", issues=issues)

    except Exception as e:
        print("Error fetching submitted issues:", e)
        return render_template("submitted_issues.html", issues=[])

@app.route("/tracking")
def tracking():
    user_id = session.get("user_id")
    if not user_id:
        flash("⚠ Please log in first")
        return redirect(url_for("login"))

    try:
        # Fetch all issues for the user
        issues = supabase.table("problems") \
            .select("""
                id,
                place,
                created_at,
                status,
                seen_by_department,
                latest_update,
                departments(name)
            """) \
            .eq("user_id", user_id) \
            .order("created_at", desc=True) \
            .execute() \
            .data

        # Calculate counts
        pending_count = sum(1 for i in issues if i['status'] == "Pending")
        progress_count = sum(1 for i in issues if i['status'] == "In Progress")
        resolved_count = sum(1 for i in issues if i['status'] == "Resolved")
        not_seen_count = sum(1 for i in issues if not i['seen_by_department'])

        return render_template(
            "tracking.html",
            issues=issues,
            pending_count=pending_count,
            progress_count=progress_count,
            resolved_count=resolved_count,
            not_seen_count=not_seen_count
        )

    except Exception as e:
        print("Error fetching issues for tracking:", e)
        return render_template(
            "tracking.html",
            issues=[],
            pending_count=0,
            progress_count=0,
            resolved_count=0,
            not_seen_count=0
        )


# ---------------- Run App ----------------
if __name__ == "__main__":
    print(f"Local: http://127.0.0.1:5000\nNetwork: http://{socket.gethostbyname(socket.gethostname())}:5000")
    app.run("0.0.0.0", 5000, debug=True)
