"""
PDF Edit Detection Scanner
Run: python verify_pdf.py <path_to_pdf>

Checks for common signs that a PDF has been edited:
1. Selectable/extractable text (should be none if text is image-based)
2. Leftover annotations (redaction marks, dotted borders)
3. Multiple content streams (layered edits)
4. Metadata mismatches (producer, modification dates)
5. Incremental saves (edit history)
6. Embedded fonts (added by editor)
7. Mixed content types (images + text objects in same area)
"""

import fitz
import sys
import os


def scan_pdf(filepath):
    print(f"\n{'='*60}")
    print(f"  PDF EDIT DETECTION SCAN")
    print(f"  File: {os.path.basename(filepath)}")
    print(f"{'='*60}\n")
    
    doc = fitz.open(filepath)
    issues = []
    warnings = []
    clean = []
    
    # === 1. CHECK METADATA ===
    meta = doc.metadata
    print("[1] METADATA CHECK")
    print(f"    Producer : {meta.get('producer', '(none)')}")
    print(f"    Creator  : {meta.get('creator', '(none)')}")
    print(f"    Created  : {meta.get('creationDate', '(none)')}")
    print(f"    Modified : {meta.get('modDate', '(none)')}")
    
    producer = (meta.get('producer') or '').lower()
    if 'pymupdf' in producer or 'fitz' in producer:
        issues.append("Producer contains 'PyMuPDF/fitz' — reveals editing tool")
    elif 'modified' in producer:
        issues.append("Producer hints at modification")
    else:
        clean.append("Producer looks clean")
    
    if meta.get('modDate') and meta.get('creationDate'):
        if meta['modDate'] != meta['creationDate']:
            warnings.append("ModDate differs from CreationDate — suggests editing")
        else:
            clean.append("ModDate matches CreationDate")
    
    # === 2. CHECK FOR ANNOTATIONS ===
    print(f"\n[2] ANNOTATIONS CHECK")
    for page_num in range(len(doc)):
        page = doc[page_num]
        annots = list(page.annots()) if page.annots() else []
        if annots:
            for annot in annots:
                issues.append(f"Page {page_num+1}: Annotation found — type={annot.type}, subtype={annot.type[1]}")
                print(f"    ⚠ Page {page_num+1}: {annot.type[1]} annotation at {annot.rect}")
        else:
            clean.append(f"Page {page_num+1}: No annotations")
            print(f"    ✓ Page {page_num+1}: No annotations")
    
    # === 3. CHECK FOR EXTRACTABLE TEXT ===
    print(f"\n[3] EXTRACTABLE TEXT CHECK")
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()
        if text:
            # Count text blocks
            blocks = page.get_text("blocks")
            text_blocks = [b for b in blocks if b[6] == 0]  # type 0 = text
            img_blocks = [b for b in blocks if b[6] == 1]   # type 1 = image
            
            print(f"    Page {page_num+1}: {len(text_blocks)} text blocks, {len(img_blocks)} image blocks")
            if text_blocks:
                issues.append(f"Page {page_num+1}: Found {len(text_blocks)} selectable text blocks — should be 0 if original is image-based")
                # Show first few characters of each text block
                for i, b in enumerate(text_blocks[:5]):
                    preview = b[4][:60].replace('\n', ' ')
                    print(f"      Text block {i+1}: [{b[0]:.0f},{b[1]:.0f},{b[2]:.0f},{b[3]:.0f}] \"{preview}\"")
        else:
            clean.append(f"Page {page_num+1}: No extractable text")
            print(f"    ✓ Page {page_num+1}: No extractable text")
    
    # === 4. CHECK CONTENT STREAMS ===
    print(f"\n[4] CONTENT STREAMS CHECK")
    for page_num in range(len(doc)):
        page = doc[page_num]
        xref = page.xref
        # Check for multiple content streams
        contents = doc.xref_get_key(xref, "Contents")
        print(f"    Page {page_num+1}: Contents = {contents[1][:80]}...")
        
    # === 5. CHECK FOR EMBEDDED FONTS ===
    print(f"\n[5] EMBEDDED FONTS CHECK")
    for page_num in range(len(doc)):
        page = doc[page_num]
        fonts = page.get_fonts()
        if fonts:
            print(f"    Page {page_num+1}: {len(fonts)} fonts found")
            for f in fonts:
                fname = f[3] if f[3] else f[4]
                print(f"      Font: {fname} (xref={f[0]}, ext={f[1]})")
                # Check for PyMuPDF-added fonts
                if 'BAAAAA' in str(fname) or 'subset' in str(fname).lower():
                    warnings.append(f"Page {page_num+1}: Subset font '{fname}' — may indicate added text")
        else:
            clean.append(f"Page {page_num+1}: No embedded fonts")
            print(f"    ✓ Page {page_num+1}: No embedded fonts")
    
    # === 6. CHECK FOR IMAGES (our replacements) ===
    print(f"\n[6] IMAGES CHECK")
    for page_num in range(len(doc)):
        page = doc[page_num]
        images = page.get_images()
        print(f"    Page {page_num+1}: {len(images)} images found")
        for i, img in enumerate(images):
            xref = img[0]
            w, h = img[2], img[3]
            print(f"      Image {i+1}: {w}x{h}px (xref={xref})")
    
    # === 7. CHECK FOR INCREMENTAL SAVES ===
    print(f"\n[7] INCREMENTAL SAVE CHECK")
    # Read raw file to check for multiple %%EOF markers
    with open(filepath, 'rb') as f:
        raw = f.read()
    eof_count = raw.count(b'%%EOF')
    if eof_count > 1:
        issues.append(f"Found {eof_count} %%EOF markers — indicates incremental saves (edit history)")
        print(f"    ⚠ {eof_count} %%EOF markers (incremental saves detected)")
    else:
        clean.append("Single %%EOF — no incremental save history")
        print(f"    ✓ Single %%EOF — clean save")
    
    # === 8. CHECK FOR XMP METADATA ===
    print(f"\n[8] XMP METADATA CHECK")
    xmp = doc.get_xml_metadata()
    if xmp and len(xmp) > 10:
        if 'pymupdf' in xmp.lower() or 'fitz' in xmp.lower():
            issues.append("XMP metadata contains PyMuPDF reference")
            print(f"    ⚠ XMP contains PyMuPDF reference")
        else:
            print(f"    XMP metadata present ({len(xmp)} bytes)")
    else:
        print(f"    ✓ No XMP metadata")
    
    # === SUMMARY ===
    print(f"\n{'='*60}")
    print(f"  SCAN RESULTS")
    print(f"{'='*60}")
    
    if issues:
        print(f"\n  ❌ ISSUES ({len(issues)}):")
        for issue in issues:
            print(f"     • {issue}")
    
    if warnings:
        print(f"\n  ⚠ WARNINGS ({len(warnings)}):")
        for w in warnings:
            print(f"     • {w}")
    
    if clean:
        print(f"\n  ✅ CLEAN ({len(clean)}):")
        for c in clean:
            print(f"     • {c}")
    
    if not issues and not warnings:
        print(f"\n  🟢 PDF LOOKS CLEAN — no obvious edit traces detected")
    elif issues:
        print(f"\n  🔴 PDF HAS DETECTABLE EDITS")
    else:
        print(f"\n  🟡 PDF has minor warnings but no critical issues")
    
    print()
    doc.close()
    return len(issues) == 0


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python verify_pdf.py <path_to_pdf>")
        print("       python verify_pdf.py *.pdf  (scan all PDFs)")
        sys.exit(1)
    
    import glob
    files = []
    for arg in sys.argv[1:]:
        files.extend(glob.glob(arg))
    
    if not files:
        print(f"No files found matching: {sys.argv[1:]}")
        sys.exit(1)
    
    for f in files:
        scan_pdf(f)
