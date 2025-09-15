import jpype
import jpype.imports
from jpype.types import *
import os
import requests
from datetime import datetime
import cv2
import numpy as np
import tempfile

def start_jvm():
    if not jpype.isJVMStarted():
        lib_dir = r"C:\\Users\\Ayan Banerjee\\OneDrive\\Documents\\GitHub\\PDFBOX_Accessibility\\backend\\lib"
        jars = [
            "pdfbox-3.0.5.jar",
            "fontbox-3.0.5.jar",
            "pdfbox-io-3.0.5.jar",
            "xmpbox-3.0.5.jar",
            "preflight-3.0.5.jar",
            "pdfbox-tools-3.0.5.jar",
            "commons-logging-1.2.jar",
        ]
        classpath = os.pathsep.join([os.path.join(lib_dir, j) for j in jars])
        jpype.startJVM(
            jpype.getDefaultJVMPath(),
            "-ea",
            f"-Djava.class.path={classpath}"
        )

def is_image_blurred(image_path, threshold=100.0):
    """
    Check if an image is blurred using Laplacian variance.
    Lower variance indicates blurrier images.
    threshold: values below this are considered blurry (adjust as needed)
    """
    try:
        # Read the image
        image = cv2.imread(image_path)
        if image is None:
            return False, 0
        
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Compute Laplacian variance
        laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
        
        # Check if image is blurry
        is_blurry = laplacian_var < threshold
        
        return is_blurry, laplacian_var
        
    except Exception as e:
        print(f"Error checking image blur: {e}")
        return False, 0

def grammar_spell_check(text, lang="en-US"):
    """Send text to LanguageTool API for grammar + spelling issues"""
    url = "https://api.languagetool.org/v2/check"
    try:
        response = requests.post(url, data={"text": text, "language": lang})
        matches = response.json().get("matches", [])
        issues = []
        for m in matches:
            msg = m.get("message", "")
            repl = [r["value"] for r in m.get("replacements", [])]
            if repl:
                issues.append(f"{msg} → Suggestion: {', '.join(repl)}")
            else:
                issues.append(msg)
        return issues
    except Exception as e:
        return [f"Grammar/Spelling check failed: {e}"]

def check_page_numbers(document):
    """Check if page numbers exist and are sequential."""
    from org.apache.pdfbox.text import PDFTextStripper
    stripper = PDFTextStripper()
    total_pages = document.getNumberOfPages()

    detected_numbers = []
    issues = []

    for page_num in range(1, total_pages + 1):
        stripper.setStartPage(page_num)
        stripper.setEndPage(page_num)
        text = str(stripper.getText(document))
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        if not lines:
            issues.append(f"Page {page_num}: no text found.")
            continue

        # heuristic: look at last line (footer area)
        candidate = lines[-1]
        digits = "".join(ch for ch in candidate if ch.isdigit())

        if digits.isdigit():
            detected_numbers.append(int(digits))
        else:
            issues.append(f"Page {page_num}: no page number detected.")

    # Check sequence
    if detected_numbers:
        for i in range(1, len(detected_numbers)):
            if detected_numbers[i] != detected_numbers[i - 1] + 1:
                issues.append(
                    f"Page {i+1}: expected {detected_numbers[i-1]+1}, found {detected_numbers[i]}"
                )
    else:
        issues.append("No page numbers detected in document.")

    return issues

def check_pdf_accessibility(pdf_path, report_folder=None, return_issues=False):
    start_jvm()

    from java.io import File
    from org.apache.pdfbox import Loader
    from org.apache.pdfbox.pdmodel.graphics.image import PDImageXObject
    from org.apache.pdfbox.pdmodel import PDDocumentCatalog
    from org.apache.pdfbox.pdmodel.documentinterchange.logicalstructure import (
        PDStructureTreeRoot,
        PDStructureElement,
        PDMarkedContentReference,
    )
    from org.apache.pdfbox.text import PDFTextStripper
    from org.apache.pdfbox.pdmodel.interactive.form import PDAcroForm, PDField
    from org.apache.pdfbox.pdmodel.interactive.documentnavigation.outline import PDDocumentOutline

    document = Loader.loadPDF(File(pdf_path))
    total_pages = document.getNumberOfPages()

    # Page-specific issue tracking
    page_issues = {i+1: {
        'alt_text': [],
        'tagging': [],
        'reading_order': [],
        'form_fields': [],
        'grammar': [],
        'contrast': [],  # Will be populated later
        'image_quality': []  # New: for blur detection
    } for i in range(total_pages)}

    general_issues = {
        'navigation': [],
        'page_numbers': [],
        'language': []
    }

    # Grammar + spelling check
    stripper = PDFTextStripper()
    pdf_text = str(stripper.getText(document))
    if pdf_text.strip():
        grammar_issues = grammar_spell_check(pdf_text, "en-US")
        # Distribute grammar issues to appropriate pages (simplified)
        for issue in grammar_issues:
            for page_num in range(1, total_pages + 1):
                page_issues[page_num]['grammar'].append(issue)

    # Alt text and image quality check
    pages = document.getPages().iterator()
    page_num = 1
    while pages.hasNext():
        page = pages.next()
        resources = page.getResources()
        xobjects = resources.getXObjectNames()
        for name in xobjects:
            xobject = resources.getXObject(name)
            if isinstance(xobject, PDImageXObject):
                # Check for alt text
                alt = xobject.getCOSObject().getItem("Alt")
                if alt is None:
                    page_issues[page_num]['alt_text'].append(f"Image '{name}' missing alt text")
                
                # Check for blurry images
                try:
                    # Extract image to temporary file for blur detection
                    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                        temp_path = temp_file.name
                    
                    # Convert PDFBox image to bytes and save
                    buffered_image = xobject.getImage()
                    from javax.imageio import ImageIO
                    from java.io import File as JavaFile
                    ImageIO.write(buffered_image, "png", JavaFile(temp_path))
                    
                    # Check if image is blurry
                    is_blurry, blur_score = is_image_blurred(temp_path)
                    if is_blurry:
                        page_issues[page_num]['image_quality'].append(
                            f"Image '{name}' appears blurry (sharpness score: {blur_score:.2f})"
                        )
                    
                    # Clean up temporary file
                    os.unlink(temp_path)
                    
                except Exception as e:
                    print(f"Error processing image quality for {name}: {e}")
                    # Continue with other images even if one fails
        page_num += 1

    # Tagging structure check
    catalog = document.getDocumentCatalog()
    struct_tree = catalog.getStructureTreeRoot()

    if struct_tree is None:
        for page_num in range(1, total_pages + 1):
            page_issues[page_num]['tagging'].append("Missing /StructTreeRoot — PDF is not tagged.")
    else:
        kids = struct_tree.getKids()
        if kids is None or kids.size() == 0:
            for page_num in range(1, total_pages + 1):
                page_issues[page_num]['tagging'].append("StructTreeRoot exists but contains no child elements.")
        else:
            def check_structure_element(element, tag_path="Root"):
                local_issues = []
                kids = element.getKids()
                if kids is None or kids.size() == 0:
                    local_issues.append(f"{tag_path}: has no children (possibly untagged content).")
                    return local_issues

                has_mcid = False
                for i in range(kids.size()):
                    kid = kids.get(i)
                    if isinstance(kid, PDMarkedContentReference):
                        has_mcid = True
                        mcid = kid.getMCID()
                        if mcid == -1:
                            local_issues.append(f"{tag_path}: contains invalid MCID.")
                    elif isinstance(kid, PDStructureElement):
                        local_issues.extend(check_structure_element(kid, f"{tag_path} -> {kid.getStructureType()}"))

                if not has_mcid:
                    local_issues.append(f"{tag_path}: contains no MCID references.")

                return local_issues

            for i in range(kids.size()):
                el = kids.get(i)
                if isinstance(el, PDStructureElement):
                    tagging_issues = check_structure_element(el, f"Tag[{i}]({el.getStructureType()})")
                    for page_num in range(1, total_pages + 1):
                        page_issues[page_num]['tagging'].extend(tagging_issues)

    # Reading order check
    def extract_visual_order(doc):
        stripper = PDFTextStripper()
        stripper.setSortByPosition(True)
        text = stripper.getText(doc)
        text_py = str(text)
        return [line.strip() for line in text_py.splitlines() if line.strip()]

    def extract_tagged_order(element, collected=None):
        if collected is None:
            collected = []
        kids = element.getKids()
        if kids is not None:
            for i in range(kids.size()):
                kid = kids.get(i)
                if isinstance(kid, PDStructureElement):
                    extract_tagged_order(kid, collected)
                else:
                    try:
                        txt = str(kid.toString()).strip()
                        if txt:
                            collected.append(txt)
                    except Exception:
                        pass
        return collected

    visual_order = extract_visual_order(document)
    tagged_order = []
    if struct_tree is not None:
        kids = struct_tree.getKids()
        if kids is not None:
            for i in range(kids.size()):
                el = kids.get(i)
                tagged_order.extend(extract_tagged_order(el))

    if not tagged_order:
        for page_num in range(1, total_pages + 1):
            page_issues[page_num]['reading_order'].append("No tagged text found — reading order unavailable.")
    elif not visual_order:
        for page_num in range(1, total_pages + 1):
            page_issues[page_num]['reading_order'].append("No visual text extracted.")
    else:
        mismatches = 0
        for i, txt in enumerate(tagged_order):
            if i < len(visual_order):
                if txt not in visual_order[i]:
                    mismatches += 1
        if mismatches > len(tagged_order) * 0.3:
            for page_num in range(1, total_pages + 1):
                page_issues[page_num]['reading_order'].append("Possible reading order issue: tagged order diverges from visual order.")

    # Form field labeling
    acro_form = catalog.getAcroForm()
    if acro_form is not None:
        fields = acro_form.getFields()
        for i in range(fields.size()):
            field = fields.get(i)
            if not field.getAlternateFieldName() and not field.getPartialName():
                # Distribute form field issues to appropriate pages (simplified)
                for page_num in range(1, total_pages + 1):
                    page_issues[page_num]['form_fields'].append(f"Form field {i} missing label/tooltip.")

    # Navigation checks
    outline = catalog.getDocumentOutline()
    if outline is None:
        general_issues['navigation'].append("No bookmarks/outline found — navigation aid missing.")

    lang = catalog.getLanguage()
    if lang is None:
        general_issues['language'].append("No document language set (/Lang missing).")

    if not catalog.getMarkInfo() or not catalog.getMarkInfo().isMarked():
        general_issues['navigation'].append("Document not marked as tagged (MarkInfo missing or false).")

    # Page number checks
    page_number_issues = check_page_numbers(document)
    general_issues['page_numbers'].extend(page_number_issues)

    document.close()

    # Generate structured report
    base_filename = os.path.splitext(os.path.basename(pdf_path))[0]
    report_filename = f"{base_filename}_report.txt"
    report_path = os.path.join(report_folder, report_filename)

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Accessibility Compliance Report\n\n")
        f.write("## Document Overview\n")
        f.write(f"This report evaluates the accessibility compliance of a {total_pages}-page PDF document ")
        f.write("based on WCAG and PDF/UA standards. The document is assessed for navigability, ")
        f.write("understandability, and usability by all users, including those using assistive technologies.\n\n")
        f.write(f"Report generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        f.write("## Page-by-Page Analysis\n\n")

        for page_num in range(1, total_pages + 1):
            f.write(f"### Page {page_num}\n\n")

            # 1. Proper Tagging Structure
            f.write("#### 1. Proper Tagging Structure\n")
            if page_issues[page_num]['tagging']:
                f.write("- **Issues Detected**: " + "; ".join(page_issues[page_num]['tagging']) + "\n")
                f.write("- **Recommendation**: Implement a proper tagging structure with semantic elements.\n")
            else:
                f.write("- **Issues Detected**: No tagging issues detected.\n")
                f.write("- **Recommendation**: N/A\n")
            f.write("\n")

            # 2. Logical Reading Order
            f.write("#### 2. Logical Reading Order\n")
            if page_issues[page_num]['reading_order']:
                f.write("- **Issues Detected**: " + "; ".join(page_issues[page_num]['reading_order']) + "\n")
                f.write("- **Recommendation**: Establish a logical reading order that follows natural document flow.\n")
            else:
                f.write("- **Issues Detected**: Reading order appears correct.\n")
                f.write("- **Recommendation**: N/A\n")
            f.write("\n")

            # 3. Alt Text for Images
            f.write("#### 3. Alt Text for Images\n")
            if page_issues[page_num]['alt_text']:
                f.write("- **Issues Detected**: " + "; ".join(page_issues[page_num]['alt_text']) + "\n")
                f.write("- **Recommendation**: Provide descriptive alt text for all images.\n")
            else:
                f.write("- **Issues Detected**: No images or all images have proper alt text.\n")
                f.write("- **Recommendation**: N/A\n")
            f.write("\n")

            # 4. Image Quality and Clarity
            f.write("#### 4. Image Quality and Clarity\n")
            if page_issues[page_num]['image_quality']:
                f.write("- **Issues Detected**: " + "; ".join(page_issues[page_num]['image_quality']) + "\n")
                f.write("- **Recommendation**: Replace blurry images with higher quality versions for better readability.\n")
            else:
                f.write("- **Issues Detected**: No image quality issues detected.\n")
                f.write("- **Recommendation**: N/A\n")
            f.write("\n")

            # 5. Color Contrast and Font Legibility
            f.write("#### 5. Color Contrast and Font Legibility\n")
            if page_issues[page_num]['contrast']:
                f.write("- **Issues Detected**: " + "; ".join(page_issues[page_num]['contrast']) + "\n")
                f.write("- **Recommendation**: Ensure text contrast meets WCAG standards (4.5:1 for normal text, 3:1 for large text).\n")
            else:
                f.write("- **Issues Detected**: No contrast issues detected.\n")
                f.write("- **Recommendation**: N/A\n")
            f.write("\n")

            # 6. Form Field Labeling and Navigation
            f.write("#### 6. Form Field Labeling and Navigation\n")
            if page_issues[page_num]['form_fields']:
                f.write("- **Issues Detected**: " + "; ".join(page_issues[page_num]['form_fields']) + "\n")
                f.write("- **Recommendation**: Label form fields clearly and ensure keyboard accessibility.\n")
            else:
                f.write("- **Issues Detected**: No form fields or all form fields properly labeled.\n")
                f.write("- **Recommendation**: N/A\n")
            f.write("\n")

            # 7. Grammar and Spelling Checks
            f.write("#### 7. Grammar and Spelling Checks\n")
            if page_issues[page_num]['grammar']:
                f.write("- **Issues Detected**: " + "; ".join(page_issues[page_num]['grammar'][:3]) + "\n")
                f.write("- **Recommendation**: Use grammar tools to correct language errors.\n")
            else:
                f.write("- **Issues Detected**: No grammatical issues detected.\n")
                f.write("- **Recommendation**: N/A\n")
            f.write("\n")

        # General Recommendations
        f.write("## General Recommendations\n\n")
        f.write("- **Semantic Structure**: Implement comprehensive tagging throughout the document\n")
        f.write("- **Reading Order**: Define logical reading order for all pages\n")
        f.write("- **Alt Text**: Ensure descriptive alt text for all images\n")
        f.write("- **Image Quality**: Replace blurry or low-quality images\n")
        f.write("- **Grammar**: Use grammar tools to correct language errors\n")
        f.write("- **Navigation**: Add bookmarks and proper document structure\n")
        f.write("- **Page Numbers**: Implement sequential page numbering\n")
        f.write("- **Language**: Set document language property\n\n")

        f.write("## Conclusion\n")
        f.write("The document requires improvements to meet accessibility standards. ")
        f.write("Implementing the recommended changes will enhance usability and accessibility for all users.\n")

    # Return both structured data and report path
    all_issues = []
    for page_num in range(1, total_pages + 1):
        all_issues.extend(page_issues[page_num]['alt_text'])
        all_issues.extend(page_issues[page_num]['tagging'])
        all_issues.extend(page_issues[page_num]['reading_order'])
        all_issues.extend(page_issues[page_num]['form_fields'])
        all_issues.extend(page_issues[page_num]['grammar'])
        all_issues.extend(page_issues[page_num]['contrast'])
        all_issues.extend(page_issues[page_num]['image_quality'])
    
    all_issues.extend(general_issues['navigation'])
    all_issues.extend(general_issues['page_numbers'])
    all_issues.extend(general_issues['language'])

    return report_path, all_issues, page_issues, general_issues

def update_report_with_contrast(text_report_path, contrast_issues):
    """Update the structured report with color contrast issues"""
    
    # Parse contrast issues by page
    contrast_by_page = {}
    for issue in contrast_issues:
        if "Page " in issue and ":" in issue:
            # Extract page number from issue string
            page_part = issue.split("Page ")[1].split(":")[0]
            try:
                page_num = int(page_part)
                if page_num not in contrast_by_page:
                    contrast_by_page[page_num] = []
                contrast_by_page[page_num].append(issue)
            except ValueError:
                continue
    
    # If no contrast issues found, return early
    if not contrast_by_page:
        return
    
    # Read the existing report
    with open(text_report_path, "r", encoding="utf-8") as f:
        report_content = f.read()
    
    # Update contrast sections for each page
    for page_num in contrast_by_page:
        # Create new contrast section
        new_contrast_section = f"#### 5. Color Contrast and Font Legibility\n"
        new_contrast_section += "- **Issues Detected**: " + "; ".join(contrast_by_page[page_num]) + "\n"
        new_contrast_section += "- **Recommendation**: Ensure text contrast meets WCAG standards (4.5:1 for normal text, 3:1 for large text).\n\n"
        
        # Find the page section
        page_header = f"### Page {page_num}\n\n"
        page_start = report_content.find(page_header)
        if page_start != -1:
            page_end = report_content.find("### Page", page_start + len(page_header))
            if page_end == -1:
                page_end = len(report_content)
            
            page_content = report_content[page_start:page_end]
            
            # Replace the existing contrast section
            old_contrast_pattern = "#### 5. Color Contrast and Font Legibility\n- **Issues Detected**: No contrast issues detected.\n- **Recommendation**: N/A\n\n"
            if old_contrast_pattern in page_content:
                page_content = page_content.replace(old_contrast_pattern, new_contrast_section)
            else:
                # If pattern not found, try to insert after section 4
                alt_pattern = "#### 4. Image Quality and Clarity\n"
                alt_pos = page_content.find(alt_pattern)
                if alt_pos != -1:
                    section_end = page_content.find("####", alt_pos + len(alt_pattern))
                    if section_end != -1:
                        page_content = page_content[:section_end] + new_contrast_section + page_content[section_end:]
            
            # Update the report content
            report_content = report_content[:page_start] + page_content + report_content[page_end:]
    
    # Write the updated report
    with open(text_report_path, "w", encoding="utf-8") as f:
        f.write(report_content)