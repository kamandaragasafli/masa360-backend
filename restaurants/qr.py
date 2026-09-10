"""Masa QR generasiya və toplu PDF."""

from __future__ import annotations

import io
from pathlib import Path

import qrcode
from django.core.files.base import ContentFile
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


def generate_table_qr_image(url: str, design: str = 'simple', logo_path=None, title: str = ''):
    qr = qrcode.QRCode(version=None, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white').convert('RGB')

    if design != 'branded':
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        return buf.getvalue()

    # Çərçivəli / loqolu
    pad = 40
    footer_h = 70
    header_h = 56
    size = qr_img.size[0]
    canvas_w = size + pad * 2
    canvas_h = size + pad * 2 + header_h + footer_h
    canvas_img = Image.new('RGB', (canvas_w, canvas_h), 'white')
    draw = ImageDraw.Draw(canvas_img)

    # border
    draw.rectangle(
        [8, 8, canvas_w - 9, canvas_h - 9],
        outline='#d94a2b',
        width=3,
    )

    try:
        font = ImageFont.truetype('arial.ttf', 22)
        font_sm = ImageFont.truetype('arial.ttf', 14)
    except OSError:
        font = ImageFont.load_default()
        font_sm = font

    title_text = title or 'Menyu'
    draw.text((pad, 22), title_text, fill='#1c1c1e', font=font)

    if logo_path and Path(logo_path).exists():
        try:
            logo = Image.open(logo_path).convert('RGBA')
            logo.thumbnail((44, 44))
            canvas_img.paste(logo, (canvas_w - pad - logo.size[0], 16), logo)
        except Exception:
            pass

    canvas_img.paste(qr_img, (pad, header_h + pad // 2))
    draw.text(
        (pad, canvas_h - 48),
        'Skan edin — sifariş verin',
        fill='#8b8d97',
        font=font_sm,
    )

    buf = io.BytesIO()
    canvas_img.save(buf, format='PNG')
    return buf.getvalue()


def save_table_qr(table, restaurant) -> str:
    url = restaurant.table_menu_url(table.number)
    logo_path = restaurant.logo.path if restaurant.logo else None
    png = generate_table_qr_image(
        url,
        design=restaurant.qr_design,
        logo_path=logo_path,
        title=f'Masa {table.number}',
    )
    filename = f'table-{restaurant.slug}-{table.number}.png'
    table.qr_code.save(filename, ContentFile(png), save=True)
    return url


def build_qr_pdf(tables, restaurant) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4

    cols, rows = 2, 2
    cell_w = page_w / cols
    cell_h = page_h / rows
    margin = 8 * mm

    for idx, table in enumerate(tables):
        if idx > 0 and idx % (cols * rows) == 0:
            c.showPage()

        slot = idx % (cols * rows)
        col = slot % cols
        row = slot // cols
        x0 = col * cell_w
        y0 = page_h - (row + 1) * cell_h

        # kəsim xətləri
        c.setStrokeColorRGB(0.8, 0.8, 0.82)
        c.setDash(3, 3)
        c.rect(x0 + margin / 2, y0 + margin / 2, cell_w - margin, cell_h - margin)
        c.setDash()

        url = restaurant.table_menu_url(table.number)
        logo_path = restaurant.logo.path if restaurant.logo else None
        png = generate_table_qr_image(
            url,
            design=restaurant.qr_design,
            logo_path=logo_path,
            title=f'Masa {table.number}',
        )
        img_buf = io.BytesIO(png)
        img_size = min(cell_w, cell_h) - 28 * mm
        img_x = x0 + (cell_w - img_size) / 2
        img_y = y0 + (cell_h - img_size) / 2 - 4 * mm
        c.drawImage(
            __pil_reader(img_buf),
            img_x,
            img_y,
            width=img_size,
            height=img_size,
            preserveAspectRatio=True,
            mask='auto',
        )
        c.setFillColorRGB(0.11, 0.11, 0.12)
        c.setFont('Helvetica-Bold', 12)
        c.drawCentredString(x0 + cell_w / 2, y0 + cell_h - 14 * mm, f'Masa {table.number}')

    c.save()
    return buf.getvalue()


def __pil_reader(buf):
    from reportlab.lib.utils import ImageReader

    buf.seek(0)
    return ImageReader(buf)
