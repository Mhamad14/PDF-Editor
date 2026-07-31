from flask import Flask, render_template, request, send_file
import fitz  # PyMuPDF
import os
import io
import base64
import json
import math
from PIL import Image

app = Flask(__name__)

# --- PLATE STORAGE ---
PLATES_FILE = os.path.join(os.path.dirname(__file__), 'plates.json')

def flatten_page_to_image(doc, page_index=0, dpi=300):
    """
    Rasterize an entire page to a single image, then replace the page
    with a new page containing only that image. This removes all text
    objects, fonts, and layered content — output looks identical to
    the original image-based PDF structure.
    Also cleans background noise/off-white tints so whiteout boxes blend seamlessly.
    """
    page = doc[page_index]
    page_rect = page.rect
    
    # Rasterize the full page at high DPI
    pix = page.get_pixmap(dpi=dpi, alpha=False)
    img_data = pix.tobytes("png")
    
    # Clean background noise so near-white pixels become pure #ffffff
    try:
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        lut = [255 if i >= 230 else i for i in range(256)]
        cleaned_img = img.point(lut * 3)
        img_buffer = io.BytesIO()
        cleaned_img.save(img_buffer, format="PNG")
        img_data = img_buffer.getvalue()
    except Exception as e:
        print(f"Error cleaning background: {e}")
    
    # Delete the old page and insert a fresh one with same dimensions
    doc.delete_page(page_index)
    new_page = doc.new_page(pno=page_index, width=page_rect.width, height=page_rect.height)
    
    # Insert the rasterized image as a single full-page image
    new_page.insert_image(new_page.rect, stream=img_data)
    
    return new_page

def load_plates():
    if not os.path.exists(PLATES_FILE):
        return []
    try:
        with open(PLATES_FILE, 'r') as f:
            return json.load(f)
    except:
        return []

def save_plate_to_db(plate):
    plates = load_plates()
    if plate not in plates:
        plates.append(plate)
        with open(PLATES_FILE, 'w') as f:
            json.dump(plates, f)
        return True
    return False

@app.route('/health')
def health():
    return 'OK', 200

@app.route('/check_plate', methods=['GET'])
def check_plate():
    plate = request.args.get('plate', '').strip()
    if not plate:
        return {'exists': False}
    plates = load_plates()
    return {'exists': plate in plates}

@app.route('/save_plate', methods=['POST'])
def save_plate_route():
    data = request.json
    plate = data.get('plate', '').strip()
    if plate:
        save_plate_to_db(plate)
        return {'success': True}
    return {'success': False}, 400

# ... (rest of the file)

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

def extract_pdf_data(pdf_document):
    """Extract all relevant data from the PDF document"""
    text = ''
    for page_num in range(len(pdf_document)):
        text += pdf_document[page_num].get_text() + '\n'
    
    import re
    plate_number = ''
    date_range = ''
    marke = ''
    model = ''
    stealnumber = ''
    art = ''
    forste_gang = ''
    
    # 1. Plate Number
    plate_patterns = [
        r'Prøvemærke\s+nummer\s+(\d+)',
        r'A:\s*Prøvemærke\s+nummer\s+(\d+)',
        r'[Pp]røvemærke\s*:?\s*(\d+)',
    ]
    for pattern in plate_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            plate_number = match.group(1)
            break
            
    # 2. Date Range
    date_match = re.search(r'(\d{1,2}-\d{1,2}-\d{4})\s*til\s*(\d{1,2})-(\d{1,2})-(\d{4})', text, re.IGNORECASE)
    if date_match:
        left_date = date_match.group(1)
        right_year = date_match.group(4)
        date_range = f"{left_date} til ??-??-{right_year}"
        
    # 3. Vehicle Details
    m_match = re.search(r'Mærke\s*:?\s*([^\n\r]+)', text, re.IGNORECASE)
    if m_match: marke = m_match.group(1).strip()
    
    model_match = re.search(r'Model\s*:?\s*([^\n\r]+)', text, re.IGNORECASE)
    if model_match: model = model_match.group(1).strip()
    
    s_match = re.search(r'(?:Stelnr|Stelnummer|W\s*\d)\s*:?\s*([^\n\r]+)', text, re.IGNORECASE)
    if s_match: stealnumber = s_match.group(1).strip()
    
    art_match = re.search(r'Art\s*:?\s*([^\n\r]+)', text, re.IGNORECASE)
    if art_match: art = art_match.group(1).strip()
    
    # Relaxed search for Main PDF template specifically
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    if len(lines) >= 10:
        if not marke: marke = lines[7] if 'MERCEDES' in lines[7].upper() else marke
        if not model:
            # Look for keywords in the whole text
            for kw in ['Sættevogn', 'Krone', 'Schmitz']:
                if kw.lower() in text.lower():
                    model = kw
                    break
        if not stealnumber and (len(lines[6]) > 10 or lines[6].startswith('W')): 
            stealnumber = lines[6]
        if not art: 
            # Check lines 8-10 for keywords
            for l in lines[8:11]:
                if any(x in l for x in ['Varebil', 'Lastbil', 'Personbil', 'Sættevogn']):
                    art = l
                    break

    fg_match = re.search(r'(?:1\.\s*gang|Første\s*gang)\s*:?\s*(\d{1,2}-\d{1,2}-\d{4})', text, re.IGNORECASE)
    if fg_match: forste_gang = fg_match.group(1).strip()
    
    # Fallbacks for Template UI satisfaction
    return {
        'plate_number': plate_number or '5000000',
        'date_range': date_range or '01-01-2026 til 07-01-2026',
        'marke': marke or 'MERCEDES-BENZ',
        'model': model or 'Sprinter',
        'stealnumber': stealnumber or 'W1V9076351P472890',
        'art': art or 'Varebil',
        'forste_gang': forste_gang or '01-01-2020'
    }

@app.route('/render_page', methods=['POST'])
def render_page():
    if 'pdf_file' not in request.files:
        return 'No file uploaded', 400
    file = request.files['pdf_file']
    if file.filename == '':
        return 'No file selected', 400
    
    try:
        pdf_bytes = file.read()
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(pdf_document) > 0:
            page = pdf_document[0]
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            img_b64 = base64.b64encode(img_data).decode('utf-8')
            
            data = extract_pdf_data(pdf_document)
            data['image'] = img_b64
            data['width'] = page.rect.width
            data['height'] = page.rect.height
            
            return data
    except Exception as e:
        return str(e), 500
    return 'Error processing PDF', 500

@app.route('/render_main_template', methods=['POST'])
def render_main_template():
    """Render main.pdf for calibration preview and extract text"""
    template_path = os.path.join(os.path.dirname(__file__), 'main.pdf')
    
    if not os.path.exists(template_path):
        return 'main.pdf not found', 404
        
    try:
        pdf_document = fitz.open(template_path)
        if len(pdf_document) > 0:
            page = pdf_document[0]
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            img_b64 = base64.b64encode(img_data).decode('utf-8')
            
            data = extract_pdf_data(pdf_document)
            data['image'] = img_b64
            data['width'] = page.rect.width
            data['height'] = page.rect.height
            
            return data
    except Exception as e:
        return str(e), 500
    return 'Error processing main template PDF', 500

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
    
    # Default coordinates for each template type
    big_defaults = {
        'un': {'x0': 57, 'y0': 31, 'x1': 804, 'y1': 203, 'off_x': 0, 'off_y': 0},
        'dn': {'x0': 57, 'y0': 321, 'x1': 804, 'y1': 481, 'off_x': 0, 'off_y': 0},
        'ul': {'x0': 72, 'y0': 225, 'x1': 176, 'y1': 259, 'off_x': 0, 'off_y': 0},
        'ur': {'x0': 666, 'y0': 225, 'x1': 777, 'y1': 259, 'off_x': 0, 'off_y': 0},
        'dl': {'x0': 72, 'y0': 514, 'x1': 176, 'y1': 545, 'off_x': 0, 'off_y': 0},
        'dr': {'x0': 666, 'y0': 513, 'x1': 777, 'y1': 550, 'off_x': 0, 'off_y': 0},
        'number_fontsize': 188, 'date_fontsize': 31
    }
    small_defaults = {
        'un': {'x0': 43, 'y0': 115, 'x1': 529, 'y1': 219, 'off_x': 0, 'off_y': 0},
        'dn': {'x0': 0, 'y0': 0, 'x1': 0, 'y1': 0, 'off_x': 0, 'off_y': 0},
        'ul': {'x0': 46, 'y0': 281, 'x1': 151, 'y1': 309, 'off_x': 0, 'off_y': 0},
        'ur': {'x0': 431, 'y0': 276, 'x1': 538, 'y1': 309, 'off_x': 0, 'off_y': 0},
        'dl': {'x0': 0, 'y0': 0, 'x1': 0, 'y1': 0, 'off_x': 0, 'off_y': 0},
        'dr': {'x0': 0, 'y0': 0, 'x1': 0, 'y1': 0, 'off_x': 0, 'off_y': 0},
        'number_fontsize': 121, 'date_fontsize': 31
    }
    defaults = big_defaults if template_type == 'big' else small_defaults
    
    # Get font sizes with defaults
    number_fontsize = float(request.form.get('number_fontsize', 0)) or defaults['number_fontsize']
    date_fontsize = float(request.form.get('date_fontsize', 0)) or defaults['date_fontsize']
    
    # Get coordinates for each area with defaults
    def get_coords(prefix):
        area_defaults = defaults.get(prefix, {'x0': 0, 'y0': 0, 'x1': 100, 'y1': 50, 'off_x': 0, 'off_y': 0})
        return {
            'x0': float(request.form.get(f'{prefix}_x0', 0)) or area_defaults['x0'],
            'y0': float(request.form.get(f'{prefix}_y0', 0)) or area_defaults['y0'],
            'x1': float(request.form.get(f'{prefix}_x1', 0)) or area_defaults['x1'],
            'y1': float(request.form.get(f'{prefix}_y1', 0)) or area_defaults['y1'],
            'off_x': float(request.form.get(f'{prefix}_off_x', 0)),
            'off_y': float(request.form.get(f'{prefix}_off_y', 0))
        }
    
    un_coords = get_coords('un')  # Up Number
    dn_coords = get_coords('dn')  # Down Number
    ul_coords = get_coords('ul')  # Up-Left Date
    ur_coords = get_coords('ur')  # Up-Right Date
    dl_coords = get_coords('dl')  # Down-Left Date
    dr_coords = get_coords('dr')  # Down-Right Date
    
    # Check if template file exists
    if not os.path.exists(template_path):
        return f'Template file not found: {template_file}', 404
    
    try:
        pdf_document = fitz.open(template_path)
        if len(pdf_document) == 0:
            return 'Template PDF is empty', 500
        
        page = pdf_document[0]
        
        # Preserve original metadata to avoid detection
        original_metadata = pdf_document.metadata.copy() if pdf_document.metadata else {}
        
        # Revert to original font for template as requested
        font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'arial-unicode-digits.ttf')
        template_font = fitz.Font(fontfile=font_path)
        
        template_color = (0, 0, 0)  # Black text
        
        # Collect all text items
        text_items = []
        
        def queue_text_replacement(text, coords, fontsize):
            if not text.strip():
                return
            # Draw white rectangle to cover original content
            rect = fitz.Rect(coords['x0'], coords['y0'], coords['x1'], coords['y1'])
            page.draw_rect(rect, color=None, fill=(1, 1, 1))
            
            # Queue the text for adding
            text_x = coords['x0'] + 5 + coords['off_x']
            text_y = coords['y0'] + 5 + (fontsize * 0.8) + coords['off_y']
            text_items.append((text, text_x, text_y, fontsize))
        
        # Queue text replacements based on template type
        if template_type == 'big':
            # Big template: 6 areas
            queue_text_replacement(plate_number, un_coords, number_fontsize)
            queue_text_replacement(plate_number, dn_coords, number_fontsize)
            queue_text_replacement(left_date, ul_coords, date_fontsize)
            queue_text_replacement(right_date, ur_coords, date_fontsize)
            queue_text_replacement(left_date, dl_coords, date_fontsize)
            queue_text_replacement(right_date, dr_coords, date_fontsize)
        else:
            # Small template: 3 areas
            queue_text_replacement(plate_number, un_coords, number_fontsize)
            queue_text_replacement(left_date, ul_coords, date_fontsize)
            queue_text_replacement(right_date, ur_coords, date_fontsize)
        
        # Add replacement text using TextWriter
        for text, tx, ty, fs in text_items:
            tw = fitz.TextWriter(page.rect)
            tw.append(fitz.Point(tx, ty), text, font=template_font, fontsize=fs)
            tw.write_text(page, color=template_color)
        
        # Flatten entire page to a single image (removes all text/fonts — matches original structure)
        flatten_page_to_image(pdf_document, page_index=0)
        
        # Restore original metadata
        pdf_document.set_metadata(original_metadata)
        
        # Save to buffer with full cleanup
        output_buffer = io.BytesIO()
        pdf_document.save(output_buffer, garbage=4, deflate=True, clean=True)
        output_buffer.seek(0)
        
        default_filename = f'template_{template_type}_{plate_number or "output"}.pdf'
        desired_filename = request.form.get('desired_filename', default_filename)
        return send_file(
            output_buffer,
            as_attachment=True,
            download_name=desired_filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        import traceback
        print(f"Template generation error: {e}")
        traceback.print_exc()
        return f'Error generating template: {str(e)}', 500


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        action = request.form.get('action', 'download') # download or preview

        # Try to get uploaded file or fallback to main.pdf
        pdf_document = None
        if 'pdf_file' in request.files and request.files['pdf_file'].filename != '':
            file = request.files['pdf_file']
            pdf_document = fitz.open(stream=file.read(), filetype="pdf")
        else:
            main_tpl_path = os.path.join(os.path.dirname(__file__), 'main.pdf')
            if os.path.exists(main_tpl_path):
                pdf_document = fitz.open(main_tpl_path)
            else:
                return 'No file uploaded and main.pdf not found', 400

        top_name = request.form.get('top_name', '')
        second_section = request.form.get('second_section', '')
        marke = request.form.get('marke', '')
        model = request.form.get('model', '')
        stealnumber = request.form.get('stealnumber', '')
        art = request.form.get('art', '')
        forste_gang = request.form.get('forste_gang', '')
        plate_number = request.form.get('plate_number', '')

        # Get coordinates for all areas (r1-r7)
        areas = {}
        try:
            for i in range(1, 8):
                prefix = f'r{i}'
                areas[prefix] = {
                    'x0': float(request.form.get(f'{prefix}_x0', 0)),
                    'y0': float(request.form.get(f'{prefix}_y0', 0)),
                    'x1': float(request.form.get(f'{prefix}_x1', 0)),
                    'y1': float(request.form.get(f'{prefix}_y1', 0)),
                    'off_x': float(request.form.get(f'{prefix}_off_x', 0)),
                    'off_y': float(request.form.get(f'{prefix}_off_y', 0))
                }
            
            # Add r8 (Plate Number)
            areas['r8'] = {
                'x0': float(request.form.get('r8_x0', 0)),
                'y0': float(request.form.get('r8_y0', 0)),
                'x1': float(request.form.get('r8_x1', 0)),
                'y1': float(request.form.get('r8_y1', 0)),
                'off_x': float(request.form.get('r8_off_x', 0)),
                'off_y': float(request.form.get('r8_off_y', 0))
            }
            
            # Font sizes
            fontsize_top = float(request.form.get('main_top_fontsize', 14))
            fontsize_date = float(request.form.get('main_date_fontsize', 11))
            fontsize_vehicle = float(request.form.get('main_vehicle_fontsize', 11))
            fontsize_forste = float(request.form.get('main_forste_fontsize', 11))
        except ValueError:
            # Basic fallback
            fontsize_top, fontsize_date, fontsize_vehicle, fontsize_forste = 14, 11, 11, 11

        if pdf_document and len(pdf_document) > 0:
            page = pdf_document[0]

            # Preserve original metadata to avoid detection
            original_metadata = pdf_document.metadata.copy() if pdf_document.metadata else {}

            # Use Times New Roman as requested
            font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'times.ttf')
            custom_color = (0, 0, 0)
            
            if os.path.exists(font_path):
                custom_font = fitz.Font(fontfile=font_path)
            else:
                custom_font = fitz.Font("tiro")  # Builtin Times-Roman fallback

            # Color codes - Pure black (#000000) for all text fields
            color_name = (0, 0, 0)  # #000000 Pure Black
            color_body = (0, 0, 0)  # #000000 Pure Black for Marke, Model, and all body fields

            # Collect all text items
            main_text_items = []

            def queue_main_text(text, prefix, fontsize, text_color, is_multiline=False):
                if not text or not text.strip():
                    return
                coords = areas.get(prefix)
                if not coords or coords['x1'] == 0:
                    return
                
                # Draw white rectangle to cover original content
                rect = fitz.Rect(coords['x0'], coords['y0'], coords['x1'], coords['y1'])
                page.draw_rect(rect, color=None, fill=(1, 1, 1))
                
                # Queue the text for adding
                main_text_items.append((text, coords, fontsize, text_color, is_multiline))

            # Queue all fields
            queue_main_text(top_name, 'r1', fontsize_top, color_name, is_multiline=True)
            queue_main_text(second_section, 'r2', fontsize_date, color_body)
            queue_main_text(marke, 'r3', fontsize_vehicle, color_body)
            queue_main_text(model, 'r4', fontsize_vehicle, color_body)
            queue_main_text(stealnumber, 'r5', fontsize_vehicle, color_body)
            queue_main_text(art, 'r6', fontsize_vehicle, color_body)
            queue_main_text(forste_gang, 'r7', fontsize_forste, color_body)
            queue_main_text(plate_number, 'r8', fontsize_vehicle, color_body)

            # Add replacement text using TextWriter
            for text, coords, fontsize, text_color, is_multiline in main_text_items:
                tw = fitz.TextWriter(page.rect)
                if is_multiline:
                    line_height = fontsize * 1.2
                    lines = [l.strip() for l in text.split('\n') if l.strip()]
                    y_pos = coords['y0'] + 5 + fontsize + coords['off_y']
                    for line in lines:
                        x_pos = coords['x0'] + 5 + coords['off_x']
                        tw.append(fitz.Point(x_pos, y_pos), line, font=custom_font, fontsize=fontsize)
                        y_pos += line_height
                else:
                    x_pos = coords['x0'] + 5 + coords['off_x']
                    y_pos = coords['y0'] + 5 + (fontsize * 0.8) + coords['off_y']
                    tw.append(fitz.Point(x_pos, y_pos), text, font=custom_font, fontsize=fontsize)
                tw.write_text(page, color=text_color)

            # Flatten entire page to a single image (removes all text/fonts — matches original)
            flatten_page_to_image(pdf_document, page_index=0)

            # Restore original metadata
            pdf_document.set_metadata(original_metadata)

            if action == 'preview':
                preview_page = pdf_document[0]  # get fresh reference after flatten
                pix = preview_page.get_pixmap()
                img_data = pix.tobytes("png")
                img_b64 = base64.b64encode(img_data).decode('utf-8')
                return render_template('index.html', preview_image=img_b64)

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
                
                # Revert to original font for template
                font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'arial-unicode-digits.ttf')
                print(f"DEBUG: Loading font from {font_path}")
                template_font = fitz.Font(fontfile=font_path)
                
                template_color = (0, 0, 0)  # Black text
                # Get font sizes from form (user editable)
                try:
                    number_fontsize = float(request.form.get('tpl_number_fontsize', 63))
                    date_fontsize = float(request.form.get('tpl_date_fontsize', 10))
                except ValueError:
                    number_fontsize = 63
                    date_fontsize = 10
                
                # Preserve original metadata
                original_tpl_metadata = template_doc.metadata.copy() if template_doc.metadata else {}

                # Collect text items
                tpl_text_items = []
                
                def queue_template_text(text, x0, y0, x1, y1, off_x, off_y, fontsize):
                    if text.strip():
                        # Draw white rectangle to cover original content
                        rect = fitz.Rect(x0, y0, x1, y1)
                        template_page.draw_rect(rect, color=None, fill=(1, 1, 1))
                        text_x = x0 + off_x
                        text_y = y0 + off_y + fontsize
                        tpl_text_items.append((text, text_x, text_y, fontsize))
                
                # Queue all 6 text areas
                queue_template_text(tpl_up_number, tpl_un_x0, tpl_un_y0, tpl_un_x1, tpl_un_y1, tpl_un_off_x, tpl_un_off_y, number_fontsize)
                queue_template_text(tpl_down_number, tpl_dn_x0, tpl_dn_y0, tpl_dn_x1, tpl_dn_y1, tpl_dn_off_x, tpl_dn_off_y, number_fontsize)
                queue_template_text(tpl_upleft_date, tpl_ul_x0, tpl_ul_y0, tpl_ul_x1, tpl_ul_y1, tpl_ul_off_x, tpl_ul_off_y, date_fontsize)
                queue_template_text(tpl_upright_date, tpl_ur_x0, tpl_ur_y0, tpl_ur_x1, tpl_ur_y1, tpl_ur_off_x, tpl_ur_off_y, date_fontsize)
                queue_template_text(tpl_downleft_date, tpl_dl_x0, tpl_dl_y0, tpl_dl_x1, tpl_dl_y1, tpl_dl_off_x, tpl_dl_off_y, date_fontsize)
                queue_template_text(tpl_downright_date, tpl_dr_x0, tpl_dr_y0, tpl_dr_x1, tpl_dr_y1, tpl_dr_off_x, tpl_dr_off_y, date_fontsize)

                # Add replacement text using TextWriter
                for text, tx, ty, fs in tpl_text_items:
                    tw = fitz.TextWriter(template_page.rect)
                    tw.append(fitz.Point(tx, ty), text, font=template_font, fontsize=fs)
                    tw.write_text(template_page, color=template_color)

                # Flatten entire page to a single image
                flatten_page_to_image(template_doc, page_index=0)

                # Restore original metadata
                template_doc.set_metadata(original_tpl_metadata)
            
            # Save template to buffer with full cleanup
            template_buffer = io.BytesIO()
            template_doc.save(template_buffer, garbage=4, deflate=True, clean=True)
            template_buffer.seek(0)
            
            tpl_desired_filename = request.form.get('desired_filename', 'template_output.pdf')
            return send_file(
                template_buffer,
                as_attachment=True,
                download_name=tpl_desired_filename,
                mimetype='application/pdf'
            )

        # Handle signature PDF generation
        if action == 'download_signature':
            return generate_signature_pdf(request)

        # Save to buffer with full cleanup
        output_buffer = io.BytesIO()
        pdf_document.save(output_buffer, garbage=4, deflate=True, clean=True)
        output_buffer.seek(0)
        
        main_desired_filename = request.form.get('desired_filename', 'edited_output.pdf')
        return send_file(
            output_buffer,
            as_attachment=True,
            download_name=main_desired_filename,
            mimetype='application/pdf'
        )

    return render_template('index.html')

def generate_human_signature(name):
    """Generate a realistic human pen signature from the first name"""
    first_name = name.strip().split()[0] if name.strip() else 'Signature'
    font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'caveat.ttf')
    if not os.path.exists(font_path):
        font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'dancing.ttf')
    
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new('RGBA', (450, 160), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype(font_path, 64)
    except Exception:
        font = ImageFont.load_default()
        
    ink_color = (20, 35, 75, 240)  # Dark navy blue pen ink
    draw.text((25, 30), first_name, font=font, fill=ink_color)
    
    # Draw natural pen flourish underline
    try:
        bbox = draw.textbbox((25, 30), first_name, font=font)
        text_width = bbox[2] - bbox[0]
        start_x = 30
        end_x = start_x + text_width + 45
        y_base = bbox[3] - 8
        points = []
        for x in range(int(start_x), int(end_x), 3):
            t = (x - start_x) / (end_x - start_x)
            y = y_base + math.sin(t * math.pi) * 14 + math.sin(t * 3 * math.pi) * 3
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=ink_color, width=3)
    except Exception as e:
        print(f"Error drawing flourish: {e}")
        
    rotated = img.rotate(4, resample=Image.BICUBIC, expand=True)
    return rotated

def process_uploaded_signature(file_bytes, target_ink_color=(16, 30, 66)):
    """
    Advanced Signature Reconstruction Pipeline:
    1. Upsamples image 2x for smooth crisp edges.
    2. Local background illumination subtraction: isolates pen ink from paper color, watermarks & patterns.
    3. Low-sensitivity thresholding + MORPH_CLOSE (7,7) & MORPH_DILATE (3,3): bridges all stroke gaps for 100% solid, connected pen ink.
    4. Aspect-ratio and component filtering: eliminates horizontal scanner lines and isolated specks.
    5. Gaussian anti-aliasing: smooths stroke outlines for clean, professional PDF rendering.
    """
    import cv2
    import numpy as np
    from PIL import Image

    try:
        if isinstance(file_bytes, (bytes, bytearray)):
            nparr = np.frombuffer(file_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        elif isinstance(file_bytes, str):
            img = cv2.imread(file_bytes)
        else:
            img = np.array(Image.open(io.BytesIO(file_bytes)).convert('RGB'))[:, :, ::-1]

        if img is None:
            raise ValueError("Could not decode image bytes")

        # Scale up 2x for smooth crisp edges
        h, w = img.shape[:2]
        high_res_h, high_res_w = int(h * 2), int(w * 2)
        img_large = cv2.resize(img, (high_res_w, high_res_h), interpolation=cv2.INTER_CUBIC)

        # Grayscale
        gray = cv2.cvtColor(img_large, cv2.COLOR_BGR2GRAY)

        # 1. Local background subtraction (handles uneven paper illumination & paper tint)
        bg_est = cv2.GaussianBlur(gray, (51, 51), 0)
        diff = bg_est.astype(np.float32) - gray.astype(np.float32)
        diff = np.clip(diff, 0, 255).astype(np.uint8)

        # 2. Low-sensitivity thresholding to capture 100% of pen ink (even light pen loops)
        otsu_val, _ = cv2.threshold(diff, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh_val = max(otsu_val * 0.45, 5.0)
        _, binary = cv2.threshold(diff, int(thresh_val), 255, cv2.THRESH_BINARY)

        # 3. Morphological Close (7,7) & Dilate (3,3) to bridge any pixel gaps and render 100% solid, continuous pen strokes
        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)
        
        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        bold_strokes = cv2.dilate(closed, kernel_dilate, iterations=1)

        # 4. Component Analysis & Aspect Ratio Filtering (removes horizontal scanner noise lines & specks)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(bold_strokes)
        clean_mask = np.zeros_like(bold_strokes)

        for i in range(1, num_labels):
            area = stats[i, cv2.CC_STAT_AREA]
            cw = stats[i, cv2.CC_STAT_WIDTH]
            ch = stats[i, cv2.CC_STAT_HEIGHT]
            cy = centroids[i][1]

            aspect_ratio = cw / float(ch + 1e-5)
            is_margin = (cy < high_res_h * 0.05) or (cy > high_res_h * 0.95)
            is_scanner_line = (aspect_ratio > 7.0 and ch < 20) or (aspect_ratio < 0.15 and cw < 15)

            if not is_margin and not is_scanner_line and (area >= 400 or (cw >= 80 and ch >= 80)):
                clean_mask[labels == i] = 255

        # 5. Smooth stroke boundaries with Gaussian blur for crisp anti-aliased digital ink
        alpha = cv2.GaussianBlur(clean_mask, (3, 3), 0)

        # 6. Build bold high quality RGBA output
        rgba = np.zeros((high_res_h, high_res_w, 4), dtype=np.uint8)
        rgba[:, :, 0] = target_ink_color[0]
        rgba[:, :, 1] = target_ink_color[1]
        rgba[:, :, 2] = target_ink_color[2]
        rgba[:, :, 3] = alpha

        pil_img = Image.fromarray(rgba, mode='RGBA')
        bbox = pil_img.getbbox()
        if bbox:
            pil_img = pil_img.crop(bbox)
        return pil_img
    except Exception as e:
        print(f"Advanced signature processing failed: {e}, falling back to PIL thresholding")
        img = Image.open(io.BytesIO(file_bytes)).convert('RGBA')
        gray = img.convert('L')
        alpha = gray.point(lambda p: 255 if p < 200 else 0)
        img.putalpha(alpha)
        return img





@app.route('/render_signature_template', methods=['POST'])
def render_signature_template():
    """Render signature_template.pdf preview for live canvas calibration"""
    template_path = os.path.join(os.path.dirname(__file__), 'signature_template.pdf')
    if not os.path.exists(template_path):
        return 'signature_template.pdf not found', 404
        
    try:
        pdf_document = fitz.open(template_path)
        if len(pdf_document) > 0:
            page = pdf_document[0]
            pix = page.get_pixmap()
            img_data = pix.tobytes("png")
            img_b64 = base64.b64encode(img_data).decode('utf-8')
            return {
                'image': img_b64,
                'width': page.rect.width,
                'height': page.rect.height
            }
    except Exception as e:
        return str(e), 500
    return 'Error processing signature template PDF', 500

def process_drawn_signature(base64_data, target_ink_color=(16, 30, 66)):
    """
    Process interactive drawn signature from canvas pad:
    1. Decodes base64 canvas image.
    2. Makes white background 100% transparent.
    3. Recolors drawn pen ink strokes to deep navy (16, 30, 66).
    4. Applies super-sampling anti-aliasing while keeping 100% solid unbroken lines.
    """
    import base64, io
    import cv2
    import numpy as np
    from PIL import Image, ImageFilter
    try:
        if ',' in base64_data:
            base64_data = base64_data.split(',')[1]
        img_bytes = base64.b64decode(base64_data)
        img = Image.open(io.BytesIO(img_bytes)).convert('RGBA')
        
        arr = np.array(img)
        r, g, b, a = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], arr[:, :, 3]
        
        # Identify drawn stroke pixels (dark ink on white canvas)
        is_background = (r > 240) & (g > 240) & (b > 240)
        
        # Create output RGBA array
        out_arr = np.zeros_like(arr)
        
        # Set stroke color
        out_arr[~is_background, 0] = target_ink_color[0]
        out_arr[~is_background, 1] = target_ink_color[1]
        out_arr[~is_background, 2] = target_ink_color[2]
        out_arr[~is_background, 3] = a[~is_background]
        
        out_pil = Image.fromarray(out_arr, mode='RGBA')
        
        # Smooth stroke edges slightly for natural pen rendering
        out_pil = out_pil.filter(ImageFilter.SMOOTH_MORE)
        
        bbox = out_pil.getbbox()
        if bbox:
            out_pil = out_pil.crop(bbox)
        return out_pil
    except Exception as e:
        print(f"Error processing drawn signature pad: {e}")
        return None

def generate_signature_pdf(req):
    """Generate Signature / Power of Attorney PDF with text overlay and signature"""
    template_path = os.path.join(os.path.dirname(__file__), 'signature_template.pdf')
    if not os.path.exists(template_path):
        return 'Signature template file not found', 404
        
    sig_days = req.form.get('sig_days', '')
    sig_start_date = req.form.get('sig_start_date', '')
    sig_vin = req.form.get('sig_vin', '')
    sig_full_name = req.form.get('sig_full_name', '')
    sig_akr = req.form.get('sig_akr', '')
    
    # Bounding boxes and offsets for fields
    sig_defaults = {
        'sig_days': {'x0': 205, 'y0': 353, 'x1': 517, 'y1': 373, 'off_x': 0, 'off_y': -4},
        'sig_start_date': {'x0': 205, 'y0': 378, 'x1': 515, 'y1': 400, 'off_x': 0, 'off_y': -3.5},
        'sig_vin': {'x0': 146, 'y0': 447, 'x1': 484, 'y1': 469, 'off_x': 0, 'off_y': -3},
        'sig_full_name': {'x0': 150, 'y0': 490, 'x1': 515, 'y1': 511, 'off_x': 0, 'off_y': -3},
        'sig_akr': {'x0': 140, 'y0': 574, 'x1': 338, 'y1': 594, 'off_x': 0, 'off_y': -3},
        'sig_signature': {'x0': 180, 'y0': 715, 'x1': 440, 'y1': 835, 'off_x': 0, 'off_y': 0}
    }
    
    def get_sig_coords(prefix):
        d = sig_defaults.get(prefix, {'x0': 0, 'y0': 0, 'x1': 100, 'y1': 50, 'off_x': 0, 'off_y': 0})
        off_x_val = req.form.get(f'{prefix}_off_x', '').strip()
        off_y_val = req.form.get(f'{prefix}_off_y', '').strip()
        return {
            'x0': float(req.form.get(f'{prefix}_x0', 0)) or d['x0'],
            'y0': float(req.form.get(f'{prefix}_y0', 0)) or d['y0'],
            'x1': float(req.form.get(f'{prefix}_x1', 0)) or d['x1'],
            'y1': float(req.form.get(f'{prefix}_y1', 0)) or d['y1'],
            'off_x': float(off_x_val) if off_x_val != '' else d['off_x'],
            'off_y': float(off_y_val) if off_y_val != '' else d['off_y']
        }
        
    coords = {k: get_sig_coords(k) for k in sig_defaults}
    
    try:
        body_fontsize = float(req.form.get('sig_body_fontsize', 14))
    except ValueError:
        body_fontsize = 14

    try:
        pdf_document = fitz.open(template_path)
        if len(pdf_document) == 0:
            return 'Signature template PDF is empty', 500
            
        page = pdf_document[0]
        original_metadata = pdf_document.metadata.copy() if pdf_document.metadata else {}
        
        font_path = os.path.join(os.path.dirname(__file__), 'fonts', 'times.ttf')
        if os.path.exists(font_path):
            times_font = fitz.Font(fontfile=font_path)
        else:
            times_font = fitz.Font("tiro")
            
        text_fields = [
            (sig_days, coords['sig_days']),
            (sig_start_date, coords['sig_start_date']),
            (sig_vin, coords['sig_vin']),
            (sig_full_name, coords['sig_full_name']),
            (sig_akr, coords['sig_akr']),
        ]
        
        for text, c in text_fields:
            if text and text.strip():
                rect = fitz.Rect(c['x0'], c['y0'], c['x1'], c['y1'])
                page.draw_rect(rect, color=None, fill=(1, 1, 1))
                tx = c['x0'] + 5 + c['off_x']
                ty = c['y0'] + 5 + (body_fontsize * 0.8) + c['off_y']
                tw = fitz.TextWriter(page.rect)
                tw.append(fitz.Point(tx, ty), text, font=times_font, fontsize=body_fontsize)
                tw.write_text(page, color=(0, 0, 0))

        # Handle signature rendering (drawn pad -> uploaded photo -> auto-generated human signature)
        sig_c = coords['sig_signature']
        sig_rect = fitz.Rect(sig_c['x0'] + sig_c['off_x'], sig_c['y0'] + sig_c['off_y'], sig_c['x1'] + sig_c['off_x'], sig_c['y1'] + sig_c['off_y'])
        
        sig_img = None
        
        # 1. Check if user drew signature on pad
        sig_drawn_data = req.form.get('sig_drawn_data', '').strip()
        if sig_drawn_data:
            try:
                sig_img = process_drawn_signature(sig_drawn_data)
            except Exception as e:
                print(f"Drawn signature processing failed: {e}")
                
        # 2. Check if user uploaded a signature photo
        if sig_img is None and 'sig_image' in req.files and req.files['sig_image'].filename != '':
            try:
                sig_img = process_uploaded_signature(req.files['sig_image'].read())
            except Exception as e:
                print(f"Uploaded signature processing failed: {e}")
                
        # 3. Fallback: Auto-generate human cursive pen signature from First Name
        if sig_img is None:
            sig_img = generate_human_signature(sig_full_name)
            
        # Draw signature image onto PDF page (with white background rect under signature box)
        if sig_img:
            page.draw_rect(sig_rect, color=None, fill=(1, 1, 1))
            buf = io.BytesIO()
            sig_img.save(buf, format='PNG')
            page.insert_image(sig_rect, stream=buf.getvalue())
            
        flatten_page_to_image(pdf_document, page_index=0)
        pdf_document.set_metadata(original_metadata)
        
        output_buffer = io.BytesIO()
        pdf_document.save(output_buffer, garbage=4, deflate=True, clean=True)
        output_buffer.seek(0)
        
        desired_filename = req.form.get('desired_filename', 'power_of_attorney.pdf')
        return send_file(
            output_buffer,
            as_attachment=True,
            download_name=desired_filename,
            mimetype='application/pdf'
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f'Error generating signature PDF: {str(e)}', 500

@app.route('/generate_signature', methods=['POST'])
def generate_signature_route():
    return generate_signature_pdf(request)

if __name__ == '__main__':
    app.run(debug=True)

