import fitz

doc = fitz.open()
page = doc.new_page()
font = fitz.Font("helv")
full_font = fitz.Font(fontfile="fonts/Helvetica.ttf")

text = "Turkish: Ş ş Ğ ğ ı İ Ö ö Ü ü Ç ç"

# Test Base14
try:
    page.insert_text((50, 50), f"Base14: {text}", fontname="helv", fontsize=12)
    print("Base14: Success")
except Exception as e:
    print(f"Base14: Failed - {e}")

# Test TTF
try:
    page.insert_text((50, 100), f"TTF: {text}", fontfile="fonts/Helvetica.ttf", fontsize=12)
    print("TTF: Success")
except Exception as e:
    print(f"TTF: Failed - {e}")

doc.save("font_test.pdf")
print("Saved font_test.pdf")
