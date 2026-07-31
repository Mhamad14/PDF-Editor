import io
import urllib.request
import fitz
from PIL import Image, ImageDraw

img = Image.new('RGBA', (600, 180), (255, 255, 255, 255))
draw = ImageDraw.Draw(img)
points = [(50, 100), (70, 50), (90, 130), (110, 80), (140, 110), (170, 75), (200, 120), (260, 65), (320, 105), (420, 85)]
draw.line(points, fill=(18, 32, 70, 255), width=4, joint='curve')
draw.line([(40, 135), (440, 138)], fill=(18, 32, 70, 255), width=3)

buf = io.BytesIO()
img.save(buf, format='PNG')
import base64
b64_str = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode('utf-8')

base_url = 'http://127.0.0.1:5000'
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
body = bytearray()

fields = {
    'action': 'download_signature',
    'sig_days': '7',
    'sig_start_date': '15-08-2026',
    'sig_vin': 'YS2S4X20005639312',
    'sig_full_name': 'Mhamad Aras',
    'sig_akr': '44994054',
    'sig_drawn_data': b64_str,
    'desired_filename': 'new_defaults_signature.pdf'
}

for k, v in fields.items():
    body.extend(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode('utf-8'))
body.extend(f'--{boundary}--\r\n'.encode('utf-8'))

req = urllib.request.Request(f'{base_url}/generate_signature', data=bytes(body))
req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')

res = urllib.request.urlopen(req)
pdf_bytes = res.read()

doc = fitz.open(stream=pdf_bytes, filetype='pdf')
page = doc[0]
pix = page.get_pixmap()
pix.save('verify_new_defaults_pdf.png')
print('Generated PDF size:', len(pdf_bytes), 'Saved verify_new_defaults_pdf.png')
