import fitz  # PyMuPDF
import os
import math

def calculate_contrast_ratio(color1, color2):
    """Calculate contrast ratio between two RGB colors (0-1 range)."""
    def get_luminance(color):
        r, g, b = color
        # Convert to linear RGB
        r = r if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
        g = g if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
        b = b if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    l1 = get_luminance(color1)
    l2 = get_luminance(color2)
    
    lighter = max(l1, l2)
    darker = min(l1, l2)
    
    return (lighter + 0.05) / (darker + 0.05)

def rgb_from_int(color_int):
    """Convert integer color to RGB values (0-1 range)."""
    if color_int == 0:
        return (0, 0, 0)  # black
    
    r = ((color_int >> 16) & 0xFF) / 255.0
    g = ((color_int >> 8) & 0xFF) / 255.0
    b = (color_int & 0xFF) / 255.0
    return (r, g, b)

def analyze_pdf_contrast(pdf_path, report_folder, return_issues=False):
    """Check color contrast in a PDF using proper contrast ratio calculation."""
    doc = fitz.open(pdf_path)
    issues = []

    # HTML report filename
    contrast_report_filename = os.path.basename(pdf_path).replace(".pdf", "_contrast.html")
    contrast_report_path = os.path.join(report_folder, contrast_report_filename)

    html_content = ["<html><head><title>Color Contrast Report</title>"]
    html_content.append("<style>body { font-family: Arial, sans-serif; margin: 20px; }")
    html_content.append(".issue { background-color: #fff3f3; padding: 10px; margin: 5px; border-left: 4px solid #ff6b6b; }")
    html_content.append(".good { background-color: #f3fff3; padding: 10px; margin: 5px; border-left: 4px solid #6bff6b; }")
    html_content.append("</style></head><body>")
    html_content.append(f"<h2>Color Contrast Report for {os.path.basename(pdf_path)}</h2>")

    for page_num in range(len(doc)):
        page = doc[page_num]
        
        # Assume white background for contrast calculation
        background_color = (1, 1, 1)  # white background
        
        text_instances = page.get_text("dict")["blocks"]

        for block in text_instances:
            if "lines" in block:
                for line in block["lines"]:
                    for span in line["spans"]:
                        text = span["text"].strip()
                        if not text:
                            continue
                        
                        # Get text color
                        color_int = span.get("color", 0)
                        text_color = rgb_from_int(color_int)
                        
                        # Calculate contrast ratio
                        contrast_ratio = calculate_contrast_ratio(text_color, background_color)
                        
                        font_size = span.get("size", 0)
                        
                        # WCAG guidelines
                        if font_size >= 18 or (font_size >= 14 and span.get("flags", 0) & 2):  # bold or large text
                            min_ratio = 3.0
                            text_type = "large"
                        else:
                            min_ratio = 4.5
                            text_type = "normal"
                        
                        if contrast_ratio < min_ratio:
                            # Convert RGB to hex for display
                            r_hex = int(text_color[0] * 255)
                            g_hex = int(text_color[1] * 255)
                            b_hex = int(text_color[2] * 255)
                            hex_color = f"#{r_hex:02x}{g_hex:02x}{b_hex:02x}"
                            
                            issue = (f"Page {page_num+1}: Text '{text[:30]}{'...' if len(text) > 30 else ''}' "
                                    f"has low contrast ratio {contrast_ratio:.2f}:1 "
                                    f"(needs {min_ratio}:1 for {text_type} text, color: {hex_color}, size: {font_size:.1f}pt)")
                            issues.append(issue)
                            
                            # Add to HTML with color preview
                            html_content.append(f'<div class="issue">')
                            html_content.append(f'<strong>Page {page_num+1}:</strong> Low contrast text')
                            html_content.append(f'<div style="margin: 5px 0; padding: 5px; background-color: white;">')
                            html_content.append(f'<span style="color: {hex_color}; font-size: {font_size}pt; background-color: white; padding: 2px 5px; border: 1px solid #ccc;">')
                            html_content.append(f'Preview: {text[:50]}{"..." if len(text) > 50 else ""}')
                            html_content.append(f'</span>')
                            html_content.append(f'</div>')
                            html_content.append(f'Contrast ratio: {contrast_ratio:.2f}:1 (needs {min_ratio}:1 for {text_type} text)')
                            html_content.append(f'</div>')

    if not issues:
        no_issue_msg = "✅ No color contrast issues found."
        issues.append(no_issue_msg)
        html_content.append(f'<div class="good">{no_issue_msg}</div>')

    html_content.append("</body></html>")

    with open(contrast_report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_content))

    doc.close()

    if return_issues:
        return contrast_report_path, issues
    else:
        return contrast_report_path