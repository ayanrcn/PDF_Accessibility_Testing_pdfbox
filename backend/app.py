from flask import Flask, request, jsonify, send_file
from werkzeug.utils import secure_filename
import os
from pdf_checker import check_pdf_accessibility, update_report_with_contrast
from color_contrast_checker import analyze_pdf_contrast
from flask_cors import CORS
import traceback

app = Flask(__name__)
CORS(app)

UPLOAD_FOLDER = 'uploads'
REPORT_FOLDER = 'reports'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_pdf():
    try:
        if 'pdf' not in request.files:
            return jsonify({"error": "No file part named 'pdf' in request"}), 400

        file = request.files['pdf']
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({"error": "Only PDF files are allowed"}), 400

        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        try:
            # Step 1: Run main accessibility checks
            text_report_path, issues, page_issues, general_issues = check_pdf_accessibility(
                filepath, REPORT_FOLDER, return_issues=True
            )

            # Step 2: Run color contrast checks
            contrast_report_path, contrast_issues = analyze_pdf_contrast(
                filepath, REPORT_FOLDER, return_issues=True
            )

            # Step 3: Update the structured report with contrast issues
            update_report_with_contrast(text_report_path, contrast_issues)

        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": f"PDF analysis failed: {str(e)}"}), 500

        return jsonify({
            "report": os.path.basename(text_report_path),
            "contrast_report": os.path.basename(contrast_report_path)
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>', methods=['GET'])
def download_report(filename):
    full_path = os.path.join(REPORT_FOLDER, filename)
    if not os.path.exists(full_path):
        return jsonify({"error": "Report not found"}), 404
    return send_file(full_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)