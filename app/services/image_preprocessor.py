"""
Image Preprocessing Pipeline — enterprise-grade scan enhancement.

Used by EnterpriseOCREngine before passing images to Tesseract.
Techniques used by Big-4 document-intelligence platforms:
  1. Grayscale conversion
  2. Upscaling to 300 DPI equivalent (if image is small)
  3. Denoising via median filter
  4. Deskewing via projection-profile rotation search
  5. Adaptive contrast enhancement (CLAHE-style via ImageOps)
  6. Otsu-style binarization

All operations are pure-Pillow so no OpenCV dependency is required.
"""

from __future__ import annotations
from PIL import Image, ImageFilter, ImageOps, ImageEnhance
from loguru import logger

TARGET_DPI         = 300
DESKEW_ANGLE_RANGE = 10
DESKEW_STEPS       = 40


def _to_grayscale(img: Image.Image) -> Image.Image:
    return img.convert("L")


def _upscale_if_small(img: Image.Image, min_width: int = 1200) -> Image.Image:
    w, h = img.size
    if w < min_width:
        scale    = min_width / w
        new_size = (int(w * scale), int(h * scale))
        img      = img.resize(new_size, Image.LANCZOS)
        logger.debug(f"Upscaled from {w}x{h} -> {new_size[0]}x{new_size[1]}")
    return img


def _denoise(img: Image.Image) -> Image.Image:
    return img.filter(ImageFilter.MedianFilter(size=3))


def _projection_score(img: Image.Image) -> float:
    pixels   = list(img.getdata())
    w, h     = img.size
    rows     = [pixels[y * w:(y + 1) * w] for y in range(h)]
    row_sums = [sum(p < 128 for p in row) for row in rows]
    if not row_sums:
        return 0.0
    mean     = sum(row_sums) / len(row_sums)
    variance = sum((s - mean) ** 2 for s in row_sums) / len(row_sums)
    return variance


def _deskew(img: Image.Image) -> Image.Image:
    best_score = -1.0
    best_angle = 0.0
    step       = (DESKEW_ANGLE_RANGE * 2) / DESKEW_STEPS

    for i in range(DESKEW_STEPS + 1):
        angle   = -DESKEW_ANGLE_RANGE + i * step
        rotated = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=255)
        score   = _projection_score(rotated)
        if score > best_score:
            best_score = score
            best_angle = angle

    if abs(best_angle) > 0.3:
        logger.debug(f"Deskew: rotating {best_angle:.1f} degrees")
        img = img.rotate(best_angle, resample=Image.BICUBIC, expand=True, fillcolor=255)
    return img


def _enhance_contrast(img: Image.Image) -> Image.Image:
    img = ImageOps.autocontrast(img, cutoff=2)
    img = ImageEnhance.Sharpness(img).enhance(1.5)
    return img


def _binarize(img: Image.Image) -> Image.Image:
    hist  = img.histogram()
    total = sum(hist)
    if total == 0:
        return img.convert("1")

    sum_all = sum(i * hist[i] for i in range(256))
    sum_bg  = 0
    w_bg    = 0
    best_thresh = 0
    best_var    = 0.0

    for t in range(256):
        w_bg   += hist[t]
        w_fg    = total - w_bg
        if w_bg == 0 or w_fg == 0:
            continue
        sum_bg  += t * hist[t]
        mean_bg  = sum_bg / w_bg
        mean_fg  = (sum_all - sum_bg) / w_fg
        var      = w_bg * w_fg * (mean_bg - mean_fg) ** 2
        if var > best_var:
            best_var    = var
            best_thresh = t

    return img.point(lambda p: 255 if p >= best_thresh else 0, "L")


def preprocess_for_ocr(img: Image.Image, *, deskew: bool = True) -> Image.Image:
    """
    Full preprocessing pipeline. Returns an enhanced grayscale PIL.Image
    ready to be passed to pytesseract.
    Steps: grayscale -> upscale -> denoise -> deskew -> contrast -> binarize
    """
    img = _to_grayscale(img)
    img = _upscale_if_small(img)
    img = _denoise(img)
    if deskew:
        img = _deskew(img)
    img = _enhance_contrast(img)
    img = _binarize(img)
    return img
