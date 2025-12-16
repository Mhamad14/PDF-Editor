from flask import Flask, render_template, request, send_file
import fitz  # PyMuPDF
import os
import io

import base64

app = Flask(__name__)

@app.route('/render_page', methods=['POST'])
def render_page():
    if 'pdf_file' not in request.files:
        return 'No file uploaded', 400
    file = request.files['pdf_file']
    if file.filename == '':
        return 'No file selected', 400
    
    try:
        pdf_document = fitz.open(stream=file.read(), filetype="pdf")
        if len(pdf_document) > 0:
            page = pdf_document[0]
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            img_b64 = base64.b64encode(img_data).decode('utf-8')
            return {'image': img_b64, 'width': page.rect.width, 'height': page.rect.height}
    except Exception as e:
        return str(e), 500
    return 'Error processing PDF', 500


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        action = request.form.get('action', 'download') # download or preview

        if 'pdf_file' not in request.files:
            return 'No file uploaded', 400
        
        file = request.files['pdf_file']
        if file.filename == '':
            return 'No file selected', 400

        top_name = request.form.get('top_name', '')
        second_section = request.form.get('second_section', '')

        # Get dynamic coordinates
        try:
            r1_x0 = float(request.form.get('r1_x0', 100))
            r1_y0 = float(request.form.get('r1_y0', 50))
            r1_x1 = float(request.form.get('r1_x1', 550))
            r1_y1 = float(request.form.get('r1_y1', 150))
            
            # offsets
            r1_off_x = float(request.form.get('r1_off_x', 0))
            r1_off_y = float(request.form.get('r1_off_y', 0))
            
            r2_x0 = float(request.form.get('r2_x0', 250))
            r2_y0 = float(request.form.get('r2_y0', 520))
            r2_x1 = float(request.form.get('r2_x1', 500))
            r2_y1 = float(request.form.get('r2_y1', 560))
            
            # offsets
            r2_off_x = float(request.form.get('r2_off_x', 0))
            r2_off_y = float(request.form.get('r2_off_y', 0))
            
        except ValueError:
            # Fallback if invalid numbers
            r1_x0, r1_y0, r1_x1, r1_y1 = 100, 50, 550, 150
            r1_off_x, r1_off_y = 0, 0
            r2_x0, r2_y0, r2_x1, r2_y1 = 250, 520, 500, 560
            r2_off_x, r2_off_y = 0, 0


        # Open PDF from memory
        pdf_document = fitz.open(stream=file.read(), filetype="pdf")

        if len(pdf_document) > 0:
            page = pdf_document[0]  # Edit ONLY page 1

            # Register Custom Font with full Unicode support
            font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'HelveticaNowMicro-Regular.ttf')
            
            custom_color = (20/255, 20/255, 60/255)
            
            # Create Font object for proper Unicode support
            if os.path.exists(font_path):
                custom_font = fitz.Font(fontfile=font_path)
            else:
                custom_font = fitz.Font("helv")

            # Area 1: Top Name (Long text) - BIGGER FONT (14pt)
            if top_name:
                # Whiteout Box - simple fill, no stroke
                rect_whiteout1 = fitz.Rect(r1_x0, r1_y0, r1_x1, r1_y1)
                page.draw_rect(rect_whiteout1, color=(1,1,1), fill=(1,1,1), stroke_opacity=0)
                
                # Use TextWriter for proper Unicode rendering - handle multiline
                tw = fitz.TextWriter(page.rect)
                fontsize_name = 14  # Bigger font for name
                line_height = fontsize_name * 1.2  # Line spacing
                
                # Split text by newlines and write each line
                lines = top_name.split('\n')
                y_pos = r1_y0 + r1_off_y + fontsize_name + 2  # Starting Y position
                
                for line in lines:
                    if line.strip():  # Only write non-empty lines
                        text_point = fitz.Point(r1_x0 + r1_off_x + 5, y_pos)
                        tw.append(text_point, line, font=custom_font, fontsize=fontsize_name)
                    y_pos += line_height
                    
                tw.write_text(page, color=custom_color)

            # Area 2: Second Section (Date) - FONT (11pt)
            if second_section:
                # Whiteout Box - simple fill, no stroke
                rect_whiteout2 = fitz.Rect(r2_x0, r2_y0, r2_x1, r2_y1)
                page.draw_rect(rect_whiteout2, color=(1,1,1), fill=(1,1,1), stroke_opacity=0)
                
                # Use TextWriter for proper Unicode rendering
                tw2 = fitz.TextWriter(page.rect)
                fontsize_date = 11  # Date font size
                text_point2 = fitz.Point(r2_x0 + r2_off_x + 5, r2_y0 + r2_off_y + fontsize_date + 2)
                tw2.append(text_point2, second_section, font=custom_font, fontsize=fontsize_date)
                tw2.write_text(page, color=custom_color)

            if action == 'preview':
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")
                img_b64 = base64.b64encode(img_data).decode('utf-8')
                return render_template('index.html', preview_image=img_b64, 
                                       top_name=top_name, second_section=second_section,
                                       r1_x0=r1_x0, r1_y0=r1_y0, r1_x1=r1_x1, r1_y1=r1_y1,
                                       r1_off_x=r1_off_x, r1_off_y=r1_off_y,
                                       r2_x0=r2_x0, r2_y0=r2_y0, r2_x1=r2_x1, r2_y1=r2_y1,
                                       r2_off_x=r2_off_x, r2_off_y=r2_off_y)

        # Save to buffer
        output_buffer = io.BytesIO()
        pdf_document.save(output_buffer)
        output_buffer.seek(0)
        
        return send_file(
            output_buffer,
            as_attachment=True,
            download_name='edited_output.pdf',
            mimetype='application/pdf'
        )

    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
