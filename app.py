import os
from flask import Flask, request, render_template
from PIL import Image, ImageOps, ImageFilter
import io, base64

app = Flask(__name__)
LUTS_FOLDER = "./luts"

# --- Palette Loader ---
def load_palette(file_stream):
    colors = []
    try:
        lines = file_stream.read().decode("utf-8").splitlines()
    except UnicodeDecodeError:
        file_stream.seek(0)
        lines = file_stream.read().decode("iso-8859-1").splitlines()
    for line in lines:
        line = line.strip()
        if not line or line.startswith(";"):
            continue
        if line.startswith("FF") or line.startswith("#"):
            hex_color = line[-6:]
            colors.append(tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4)))
    return colors

# --- Palette Image for Pillow ---
def make_palette_image(palette):
    palette_data = []
    for r, g, b in palette:
        palette_data.extend([r, g, b])
    palette_data.extend([0, 0, 0] * (256 - len(palette)))
    pal_img = Image.new("P", (1, 1))
    pal_img.putpalette(palette_data)
    return pal_img

# --- Apply Filter ---
def apply_filter(img, palette, pixel_scale=1.0, use_dither=False, use_outlines=False):
    if pixel_scale < 1.0:
        w, h = img.size
        img = img.resize((int(w * pixel_scale), int(h * pixel_scale)), Image.NEAREST)
        img = img.resize((w, h), Image.NEAREST)
    pal_img = make_palette_image(palette)
    dither_mode = Image.FLOYDSTEINBERG if use_dither else Image.NONE
    result = img.convert("RGB").quantize(palette=pal_img, dither=dither_mode).convert("RGB")
    if use_outlines:
        edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
        edges = ImageOps.invert(edges).point(lambda x: 0 if x < 128 else 255, mode="1")
        edges = edges.convert("L")
        result.paste((0, 0, 0), mask=edges)
    return result

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def index():
    result_img_b64 = None
    download_name = "filtered.png"
    original_img_b64 = None
    lut_files = [f for f in os.listdir(LUTS_FOLDER) if f.lower().endswith(".txt")]

    if request.method == "POST":
        pixel_scale = float(request.form.get("pixel_scale", 1.0))
        use_dither = "dither" in request.form
        use_outlines = "outlines" in request.form

        # Either a newly uploaded image or previously stored base64
        if "image" in request.files and request.files["image"].filename != "":
            image_file = request.files["image"]
            img = Image.open(image_file.stream)
            # Store original image base64
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            original_img_b64 = base64.b64encode(buf.read()).decode("utf-8")
            original_filename = image_file.filename
        elif "original_img" in request.form and request.form["original_img"]:
            original_img_b64 = request.form["original_img"]
            img_data = base64.b64decode(original_img_b64)
            img = Image.open(io.BytesIO(img_data))
            original_filename = request.form.get("original_filename", "filtered.png")
        else:
            img = None
            original_filename = "filtered.png"

        if img:
            uploaded_palette = request.files.get("palette")
            selected_lut = request.form.get("lut_select")

            # Determine palette
            if uploaded_palette and uploaded_palette.filename != "":
                palette = load_palette(uploaded_palette.stream)
            elif selected_lut:
                lut_path = os.path.join(LUTS_FOLDER, selected_lut)
                with open(lut_path, "rb") as f:
                    palette = load_palette(f)
            else:
                palette = None

            if palette:
                result = apply_filter(img, palette, pixel_scale, use_dither, use_outlines)
                buf = io.BytesIO()
                result.save(buf, format="PNG")
                buf.seek(0)
                result_img_b64 = base64.b64encode(buf.read()).decode("utf-8")

                # Append _filtered to original filename
                name, ext = os.path.splitext(original_filename)
                download_name = f"{name}_filtered{ext}"

    return render_template(
        "index.html",
        result_img_b64=result_img_b64,
        download_name=download_name,
        original_img_b64=original_img_b64,
        lut_files=lut_files
    )

