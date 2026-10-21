"""Screenshot handling: numbering the elements on the image, and encoding it."""

from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from android_mcp.tree import Element

# Distinct, readable against both light and dark screens. Elements take them in turn.
PALETTE = (
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#008080",
    "#9a6324",
    "#800000",
    "#808000",
    "#000075",
)


def annotate(image: Image.Image, elements: list[Element]) -> Image.Image:
    """Return a copy of ``image`` with each element boxed and numbered by its index.

    The number sits on a coloured tab above the top-right corner of the box, which keeps it off
    the element's own content.
    """
    annotated = image.convert("RGB")
    draw = ImageDraw.Draw(annotated)
    font_size = max(14, round(annotated.width / 60))  # legible at phone resolutions
    font = ImageFont.load_default(size=font_size)

    for index, element in enumerate(elements):
        color = PALETTE[index % len(PALETTE)]
        bounds = element.bounds
        draw.rectangle(
            (bounds.left, bounds.top, bounds.right, bounds.bottom), outline=color, width=2
        )

        label = str(index)
        label_width = draw.textlength(label, font=font) + 4
        label_x = max(0, bounds.right - label_width)
        label_y = max(0, bounds.top - font_size - 4)
        draw.rectangle(
            (label_x, label_y, label_x + label_width, label_y + font_size + 4), fill=color
        )
        draw.text((label_x + 2, label_y + 2), label, fill="white", font=font)
    return annotated


def to_png(image: Image.Image, *, quantize: bool = False) -> bytes:
    """Encode ``image`` as PNG.

    Args:
        image: The image to encode.
        quantize: Reduce it to a 256-colour palette first. The file is several times smaller, at
            the cost of colour detail, which cuts what an agent spends reading the image.
    """
    if quantize:
        image = image.convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=quantize)
    return buffer.getvalue()


def render(
    png: bytes, elements: list[Element], *, annotate_elements: bool, quantize: bool
) -> bytes:
    """Turn a raw screenshot into what is sent back, re-encoding it only if it has to change."""
    annotating = annotate_elements and bool(elements)
    if not annotating and not quantize:
        return png
    image = Image.open(BytesIO(png))
    if annotating:
        image = annotate(image, elements)
    return to_png(image, quantize=quantize)
