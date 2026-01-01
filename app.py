import os
import io
import zipfile
import pandas as pd
import pytesseract
from flask import Flask, render_template, request, send_file
from PIL import Image, ImageDraw, ImageFont

# WINDOWS ONLY: Path to your Tesseract executable
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

app = Flask(__name__)

def find_placeholder_and_style(image, placeholder_text):
    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
    
    words = [text.lower().strip() for text in data['text']]
    search_words = placeholder_text.lower().split()
    
    for i in range(len(words) - len(search_words) + 1):
        if words[i:i+len(search_words)] == search_words:
            # 1. Get the extreme boundaries of the phrase
            left = data['left'][i]
            top = min(data['top'][i:i+len(search_words)])
            # Calculate right by taking the left of the last word + its width
            last_word_idx = i + len(search_words) - 1
            right = data['left'][last_word_idx] + data['width'][last_word_idx]
            bottom = max([data['top'][j] + data['height'][j] for j in range(i, i+len(search_words))])
            
            width = right - left
            height = bottom - top
            
            center_x = left + (width // 2)
            center_y = top + (height // 2)
            
            # Use the detected height for font size
            detected_font_size = int(height * 1.2)
            
            # Sample background color slightly away from the text to avoid "ink" colors
            bg_color = image.getpixel((left, top - 10))
            
            # --- THE FIX: ADD PADDING ---
            # We expand the rectangle by 15 pixels in every direction to ensure 
            # no "ghost letters" remain.
            padding = 15 
            mask_box = (left - padding, top - padding, right + padding, bottom + padding)
            
            return center_x, center_y, detected_font_size, bg_color, mask_box
            
    return None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data_file = request.files.get("file")
        template_file = request.files.get("template")
        placeholder = request.form.get("placeholder", "enter your name")

        if not data_file or not template_file:
            return "Files missing", 400

        df = pd.read_csv(data_file) if data_file.filename.endswith(".csv") else pd.read_excel(data_file)
        template_img = Image.open(template_file).convert("RGB")
        
        result = find_placeholder_and_style(template_img, placeholder)
        if not result:
            return f"Error: Could not find '{placeholder}' on the certificate.", 400
        
        x, y, f_size, bg_color, mask_box = result

        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            for _, row in df.iterrows():
                name = str(row[0]).strip()
                img_copy = template_img.copy()
                draw = ImageDraw.Draw(img_copy)

                # 1. Erase the placeholder with a padded rectangle
                draw.rectangle(mask_box, fill=bg_color)

                # 2. Load Font
                try:
                    font = ImageFont.truetype("arial.ttf", f_size)
                except:
                    font = ImageFont.load_default()

                # 3. Draw name
                draw.text((x, y), name, fill="black", font=font, anchor="mm")

                pdf_buffer = io.BytesIO()
                img_copy.save(pdf_buffer, format="PDF")
                zf.writestr(f"{name}.pdf", pdf_buffer.getvalue())

        memory_file.seek(0)
        return send_file(memory_file, download_name="certificates.zip", as_attachment=True)

    except Exception as e:
        return f"System Error: {str(e)}", 500

if __name__ == "__main__":
    app.run(debug=True)