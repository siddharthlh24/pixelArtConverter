from flask import Flask, request, render_template, send_from_directory, url_for
import os, tempfile
from PIL import Image, ImageFilter

app = Flask(__name__)

LUTS_FOLDER = os.path.join(os.path.dirname(__file__), "luts")
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "pixel_art_uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1 GB

def load_palette(file_stream):
    import re
    colors = []
    try:
        lines = file_stream.read().decode("utf-8").splitlines()
    except UnicodeDecodeError:
        file_stream.seek(0)
        lines = file_stream.read().decode("iso-8859-1").splitlines()

    hex_pattern = re.compile(r'[0-9A-Fa-f]{6}$')
    for line in lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("FF") or line.startswith("#"):
            hex_color = line[-6:]
            if not hex_pattern.match(hex_color):
                continue
            colors.append(tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4)))
    return colors

def make_palette_image(palette):
    palette_data = []
    for r, g, b in palette:
        palette_data.extend([r, g, b])
    palette_data.extend([0, 0, 0] * (256 - len(palette)))
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(palette_data)
    return pal_img

def apply_filter(img, palette, use_dither=False, use_outlines=False):
    pal_img = make_palette_image(palette)
    dither_mode = Image.FLOYDSTEINBERG if use_dither else Image.NONE
    
    result = img.convert("RGB").quantize(palette=pal_img, dither=dither_mode).convert("RGB")

    if use_outlines:
        edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
        edges = edges.point(lambda x: 255 if x > 40 else 0, mode="1")
        edges = edges.filter(ImageFilter.MaxFilter(3))
        result.paste((0, 0, 0), mask=edges)

    return result

@app.route("/", methods=["GET", "POST"])
def index():
    download_name = "filtered.png"
    img = None
    original_filename = None
    preview_img_url = None
    result_img_url = None

    # --- Load all LUTs with full color arrays ---
    lut_files = []
    for lut_file in os.listdir(LUTS_FOLDER):
        if lut_file.lower().endswith(".txt"):
            lut_path = os.path.join(LUTS_FOLDER, lut_file)
            with open(lut_path, "rb") as f:
                palette = load_palette(f)
            if palette:
                colors = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in palette]
                lut_files.append({"name": lut_file, "colors": colors})

    if request.method == "POST":
        pixel_scale = float(request.form.get("pixel_scale", 100))
        scale_factor = max(min(pixel_scale, 100), 1) / 100.0
        use_dither = "dither" in request.form
        use_outlines = "outlines" in request.form

        # --- Load image ---
        uploaded_img = request.files.get("image")
        stored_image = request.form.get("stored_image")

        if uploaded_img and uploaded_img.filename != "":
            original_filename = uploaded_img.filename
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], original_filename)
            uploaded_img.save(temp_path)
            img = Image.open(temp_path)
        elif stored_image:
            temp_path = os.path.join(app.config['UPLOAD_FOLDER'], stored_image)
            if os.path.exists(temp_path):
                img = Image.open(temp_path)
                original_filename = stored_image

        if img:
            # --- Apply pixel scale ---
            w, h = img.size
            if scale_factor < 1.0:
                img = img.resize((int(w * scale_factor), int(h * scale_factor)), Image.NEAREST)
                img = img.resize((w, h), Image.NEAREST)

            # --- Load palette ---
            uploaded_palette = request.files.get("palette")
            selected_lut = request.form.get("lut_select")

            if uploaded_palette and uploaded_palette.filename != "":
                palette = load_palette(uploaded_palette.stream)
            elif selected_lut:
                lut_path = os.path.join(LUTS_FOLDER, selected_lut)
                with open(lut_path, "rb") as f:
                    palette = load_palette(f)
            else:
                palette = None

            if palette:
                result = apply_filter(img, palette, use_dither=use_dither, use_outlines=use_outlines)

                name, _ = os.path.splitext(original_filename)
                output_filename = f"{name}_filtered.jpg"
                output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

                # Save full-resolution image
                result = result.convert("RGB")
                result.save(output_path, "JPEG", quality=90, progressive=True)

                # --- Create thumbnail for preview ---
                preview = result.copy()
                preview.thumbnail((512, 512), Image.LANCZOS)
                preview_filename = f"{name}_filtered_preview.jpg"
                preview_path = os.path.join(app.config['UPLOAD_FOLDER'], preview_filename)
                preview.save(preview_path, "JPEG", quality=70, progressive=True)

                # URLs for template
                result_img_url = url_for('uploaded_file', filename=output_filename)
                preview_img_url = url_for('uploaded_file', filename=preview_filename)
                download_name = output_filename

    return render_template(
        "index.html",
        download_name=download_name,
        lut_files=lut_files,
        stored_image=original_filename,
        preview_img_url=preview_img_url,
        result_img_url=result_img_url
    )
