import os
import tempfile
from flask import Flask, request, render_template, send_from_directory
from PIL import Image, ImageOps, ImageFilter
import io, base64

app = Flask(__name__)

# --- Folders ---
LUTS_FOLDER = os.path.join(os.path.dirname(__file__), "luts")
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "pixel_art_uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Max upload size ---
app.config['MAX_CONTENT_LENGTH'] = 1024 * 1024 * 1024  # 1 GB

# --- Palette Loader ---
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

# --- Palette Image ---
def make_palette_image(palette):
    palette_data = []
    for r, g, b in palette:
        palette_data.extend([r, g, b])
    palette_data.extend([0, 0, 0] * (256 - len(palette)))
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(palette_data)
    return pal_img

# --- Apply Filter ---
def apply_filter(img, palette, use_dither=False, use_outlines=False):
    pal_img = make_palette_image(palette)
    dither_mode = Image.FLOYDSTEINBERG if use_dither else Image.NONE
    result = img.convert("RGB").quantize(palette=pal_img, dither=dither_mode).convert("RGB")
    if use_outlines:
        edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
        edges = ImageOps.invert(edges).point(lambda x: 0 if x < 128 else 255, mode="1")
        edges = edges.convert("L")
        result.paste((0, 0, 0), mask=edges)
    return result

# --- Serve stored images for preview ---
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# --- Main Route ---
@app.route("/", methods=["GET", "POST"])
def index():
    result_img_b64 = None
    download_name = "filtered.png"
    lut_files = [f for f in os.listdir(LUTS_FOLDER) if f.lower().endswith(".txt")]
    img = None
    original_filename = None

    if request.method == "POST":
        # Pixel scale 1-100%
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
                # --- Apply filter ---
                result = apply_filter(img, palette, use_dither=use_dither, use_outlines=use_outlines)

                buf = io.BytesIO()
                result.save(buf, format="PNG")
                buf.seek(0)
                result_img_b64 = base64.b64encode(buf.read()).decode("utf-8")

                name, ext = os.path.splitext(original_filename)
                download_name = f"{name}_filtered{ext}"

    return render_template(
        "index.html",
        result_img_b64=result_img_b64,
        download_name=download_name,
        lut_files=lut_files,
        stored_image=original_filename  # Pass filename for slider preview
    )
