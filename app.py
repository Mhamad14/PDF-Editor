from flask import Flask, render_template, request, send_file
import fitz  # PyMuPDF
import os
import io

import base64

app = Flask(__name__)

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/render_template', methods=['POST'])
def render_template_pdf():
    """Render big.pdf or small.pdf for calibration preview"""
    template_type = request.form.get('template_type', 'big')
    template_file = 'big.pdf' if template_type == 'big' else 'small.pdf'
    template_path = os.path.join(os.path.dirname(__file__), template_file)
    
    try:
        pdf_document = fitz.open(template_path)
        if len(pdf_document) > 0:
            page = pdf_document[0]
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            img_b64 = base64.b64encode(img_data).decode('utf-8')
            return {'image': img_b64, 'width': page.rect.width, 'height': page.rect.height}
    except Exception as e:
        return str(e), 500
    return 'Error processing template PDF', 500

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

@app.route('/generate_template', methods=['POST'])
def generate_template():
    """Generate template PDF with whiteouts and text overlays"""
    template_type = request.form.get('template_type', 'big')
    template_file = 'big.pdf' if template_type == 'big' else 'small.pdf'
    template_path = os.path.join(os.path.dirname(__file__), template_file)
    
    # Get text values
    plate_number = request.form.get('plate_number', '')
    left_date = request.form.get('left_date', '')
    right_date = request.form.get('right_date', '')
    
    # Get font sizes
    number_fontsize = float(request.form.get('number_fontsize', 63 if template_type == 'big' else 121))
    date_fontsize = float(request.form.get('date_fontsize', 10 if template_type == 'big' else 31))
    
    # Get coordinates for each area
    def get_coords(prefix):
        return {
            'x0': float(request.form.get(f'{prefix}_x0', 0)),
            'y0': float(request.form.get(f'{prefix}_y0', 0)),
            'x1': float(request.form.get(f'{prefix}_x1', 100)),
            'y1': float(request.form.get(f'{prefix}_y1', 50)),
            'off_x': float(request.form.get(f'{prefix}_off_x', 0)),
            'off_y': float(request.form.get(f'{prefix}_off_y', 0))
        }
    
    un_coords = get_coords('un')  # Up Number
    dn_coords = get_coords('dn')  # Down Number
    ul_coords = get_coords('ul')  # Up-Left Date
    ur_coords = get_coords('ur')  # Up-Right Date
    dl_coords = get_coords('dl')  # Down-Left Date
    dr_coords = get_coords('dr')  # Down-Right Date
    
    try:
        pdf_document = fitz.open(template_path)
        if len(pdf_document) == 0:
            return 'Template PDF is empty', 500
        
        page = pdf_document[0]
        
        # Load font
        font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'arial-unicode-ms-bold.ttf')
        if os.path.exists(font_path):
            template_font = fitz.Font(fontfile=font_path)
        else:
            template_font = fitz.Font("helv")
        
        template_color = (0, 0, 0)  # Black text
        
        def add_text_with_whiteout(text, coords, fontsize):
            if not text.strip():
                return
            # Whiteout area
            rect = fitz.Rect(coords['x0'], coords['y0'], coords['x1'], coords['y1'])
            page.draw_rect(rect, color=(1,1,1), fill=(1,1,1), stroke_opacity=0)
            
            # Add text - position so top of text is at y0 (baseline is ~80% below top)
            tw = fitz.TextWriter(page.rect)
            text_x = coords['x0'] + coords['off_x']
            text_y = coords['y0'] + coords['off_y'] + (fontsize * 0.8)  # Baseline offset for top alignment
            text_point = fitz.Point(text_x, text_y)
            tw.append(text_point, text, font=template_font, fontsize=fontsize)
            tw.write_text(page, color=template_color)
        
        # Apply text to areas based on template type
        if template_type == 'big':
            # Big template: 6 areas
            add_text_with_whiteout(plate_number, un_coords, number_fontsize)  # Up Number
            add_text_with_whiteout(plate_number, dn_coords, number_fontsize)  # Down Number (same as plate)
            add_text_with_whiteout(left_date, ul_coords, date_fontsize)       # Up-Left Date
            add_text_with_whiteout(right_date, ur_coords, date_fontsize)      # Up-Right Date
            add_text_with_whiteout(left_date, dl_coords, date_fontsize)       # Down-Left Date (same as left)
            add_text_with_whiteout(right_date, dr_coords, date_fontsize)      # Down-Right Date (same as right)
        else:
            # Small template: 3 areas
            add_text_with_whiteout(plate_number, un_coords, number_fontsize)  # Up Number
            add_text_with_whiteout(left_date, ul_coords, date_fontsize)       # Up-Left Date
            add_text_with_whiteout(right_date, ur_coords, date_fontsize)      # Up-Right Date
        
        # Save to buffer
        output_buffer = io.BytesIO()
        pdf_document.save(output_buffer)
        output_buffer.seek(0)
        
        filename = f'template_{template_type}_{plate_number or "output"}.pdf'
        return send_file(
            output_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        return str(e), 500


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

        # Handle template PDF generation
        if action == 'download_template':
            template_type = request.form.get('template_type', 'big')
            template_file = 'big.pdf' if template_type == 'big' else 'small.pdf'
            template_path = os.path.join(os.path.dirname(__file__), template_file)
            
            # Get template text inputs
            tpl_up_number = request.form.get('tpl_up_number', '')
            tpl_down_number = request.form.get('tpl_down_number', '')
            tpl_upleft_date = request.form.get('tpl_upleft_date', '')
            tpl_upright_date = request.form.get('tpl_upright_date', '')
            tpl_downleft_date = request.form.get('tpl_downleft_date', '')
            tpl_downright_date = request.form.get('tpl_downright_date', '')
            
            # Get template coordinates
            try:
                tpl_un_x0 = float(request.form.get('tpl_un_x0', 0))
                tpl_un_y0 = float(request.form.get('tpl_un_y0', 0))
                tpl_un_x1 = float(request.form.get('tpl_un_x1', 100))
                tpl_un_y1 = float(request.form.get('tpl_un_y1', 50))
                tpl_un_off_x = float(request.form.get('tpl_un_off_x', 0))
                tpl_un_off_y = float(request.form.get('tpl_un_off_y', 0))
                
                tpl_dn_x0 = float(request.form.get('tpl_dn_x0', 0))
                tpl_dn_y0 = float(request.form.get('tpl_dn_y0', 0))
                tpl_dn_x1 = float(request.form.get('tpl_dn_x1', 100))
                tpl_dn_y1 = float(request.form.get('tpl_dn_y1', 50))
                tpl_dn_off_x = float(request.form.get('tpl_dn_off_x', 0))
                tpl_dn_off_y = float(request.form.get('tpl_dn_off_y', 0))
                
                tpl_ul_x0 = float(request.form.get('tpl_ul_x0', 0))
                tpl_ul_y0 = float(request.form.get('tpl_ul_y0', 0))
                tpl_ul_x1 = float(request.form.get('tpl_ul_x1', 100))
                tpl_ul_y1 = float(request.form.get('tpl_ul_y1', 50))
                tpl_ul_off_x = float(request.form.get('tpl_ul_off_x', 0))
                tpl_ul_off_y = float(request.form.get('tpl_ul_off_y', 0))
                
                tpl_ur_x0 = float(request.form.get('tpl_ur_x0', 0))
                tpl_ur_y0 = float(request.form.get('tpl_ur_y0', 0))
                tpl_ur_x1 = float(request.form.get('tpl_ur_x1', 100))
                tpl_ur_y1 = float(request.form.get('tpl_ur_y1', 50))
                tpl_ur_off_x = float(request.form.get('tpl_ur_off_x', 0))
                tpl_ur_off_y = float(request.form.get('tpl_ur_off_y', 0))
                
                tpl_dl_x0 = float(request.form.get('tpl_dl_x0', 0))
                tpl_dl_y0 = float(request.form.get('tpl_dl_y0', 0))
                tpl_dl_x1 = float(request.form.get('tpl_dl_x1', 100))
                tpl_dl_y1 = float(request.form.get('tpl_dl_y1', 50))
                tpl_dl_off_x = float(request.form.get('tpl_dl_off_x', 0))
                tpl_dl_off_y = float(request.form.get('tpl_dl_off_y', 0))
                
                tpl_dr_x0 = float(request.form.get('tpl_dr_x0', 0))
                tpl_dr_y0 = float(request.form.get('tpl_dr_y0', 0))
                tpl_dr_x1 = float(request.form.get('tpl_dr_x1', 100))
                tpl_dr_y1 = float(request.form.get('tpl_dr_y1', 50))
                tpl_dr_off_x = float(request.form.get('tpl_dr_off_x', 0))
                tpl_dr_off_y = float(request.form.get('tpl_dr_off_y', 0))
            except ValueError:
                pass
            
            # Open template PDF
            template_doc = fitz.open(template_path)
            if len(template_doc) > 0:
                template_page = template_doc[0]
                
                # Load Arial Unicode font
                arial_font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'arial-unicode-ms-bold.ttf')
                if os.path.exists(arial_font_path):
                    template_font = fitz.Font(fontfile=arial_font_path)
                else:
                    template_font = fitz.Font("helv")
                
                template_color = (0, 0, 0)  # Black text
                # Get font sizes from form (user editable)
                try:
                    number_fontsize = float(request.form.get('tpl_number_fontsize', 63))
                    date_fontsize = float(request.form.get('tpl_date_fontsize', 10))
                except ValueError:
                    number_fontsize = 63
                    date_fontsize = 10
                
                # Helper function to add text at coordinates with whiteout and offsets
                def add_template_text(text, x0, y0, x1, y1, off_x, off_y, fontsize):
                    if text.strip():
                        # Whiteout the area first to hide old content
                        rect = fitz.Rect(x0, y0, x1, y1)
                        template_page.draw_rect(rect, color=(1,1,1), fill=(1,1,1), stroke_opacity=0)
                        
                        # Calculate text position with offsets
                        tw = fitz.TextWriter(template_page.rect)
                        text_x = x0 + off_x
                        text_y = y0 + off_y + fontsize  # baseline is at bottom of text
                        text_point = fitz.Point(text_x, text_y)
                        tw.append(text_point, text, font=template_font, fontsize=fontsize)
                        tw.write_text(template_page, color=template_color)
                
                # Add all 6 text areas with appropriate font sizes and offsets
                add_template_text(tpl_up_number, tpl_un_x0, tpl_un_y0, tpl_un_x1, tpl_un_y1, tpl_un_off_x, tpl_un_off_y, number_fontsize)
                add_template_text(tpl_down_number, tpl_dn_x0, tpl_dn_y0, tpl_dn_x1, tpl_dn_y1, tpl_dn_off_x, tpl_dn_off_y, number_fontsize)
                add_template_text(tpl_upleft_date, tpl_ul_x0, tpl_ul_y0, tpl_ul_x1, tpl_ul_y1, tpl_ul_off_x, tpl_ul_off_y, date_fontsize)
                add_template_text(tpl_upright_date, tpl_ur_x0, tpl_ur_y0, tpl_ur_x1, tpl_ur_y1, tpl_ur_off_x, tpl_ur_off_y, date_fontsize)
                add_template_text(tpl_downleft_date, tpl_dl_x0, tpl_dl_y0, tpl_dl_x1, tpl_dl_y1, tpl_dl_off_x, tpl_dl_off_y, date_fontsize)
                add_template_text(tpl_downright_date, tpl_dr_x0, tpl_dr_y0, tpl_dr_x1, tpl_dr_y1, tpl_dr_off_x, tpl_dr_off_y, date_fontsize)
            
            # Save template to buffer
            template_buffer = io.BytesIO()
            template_doc.save(template_buffer)
            template_buffer.seek(0)
            
            return send_file(
                template_buffer,
                as_attachment=True,
                download_name='template_output.pdf',
                mimetype='application/pdf'
            )

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
