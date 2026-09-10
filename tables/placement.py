"""Plan üzərində masa yerləşdirmə — toqquşma olmadan."""


def _bbox(pos_x, pos_y, width, height, pad=1.5):
    hw, hh = width / 2 + pad, height / 2 + pad
    return (pos_x - hw, pos_y - hh, pos_x + hw, pos_y + hh)


def _overlaps(a, b):
    return not (a[2] <= b[0] or a[0] >= b[2] or a[3] <= b[1] or a[1] >= b[3])


def find_free_position(existing, width, height, margin=10):
    """
    existing: [{pos_x, pos_y, width, height}, ...]
    Qaytarır: (pos_x, pos_y) — mərkəz koordinatları (%).
    """
    occupied = [
        _bbox(
            float(t['pos_x']),
            float(t['pos_y']),
            float(t.get('width') or 12),
            float(t.get('height') or 12),
        )
        for t in existing
    ]

    # Grid üzrə boş yer axtar (soldan-sağa, yuxarıdan-aşağı)
    step_x = max(8.0, width * 0.85)
    step_y = max(8.0, height * 0.85)
    x_start = margin + width / 2
    y_start = margin + height / 2
    x_end = 100 - margin - width / 2
    y_end = 100 - margin - height / 2

    y = y_start
    while y <= y_end + 0.01:
        x = x_start
        while x <= x_end + 0.01:
            candidate = _bbox(x, y, width, height)
            if not any(_overlaps(candidate, box) for box in occupied):
                return round(x, 1), round(y, 1)
            x += step_x
        y += step_y

    # Heç yer tapılmadı — sağ aşağı küncə, bir az ofset
    return (
        round(min(90, x_end), 1),
        round(min(90, y_end), 1),
    )
