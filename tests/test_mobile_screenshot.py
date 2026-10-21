"""Tests for screenshot handling: numbering elements on the image, and encoding it."""

import io

import pytest
from PIL import Image

from android_mcp.mobile import screenshot
from android_mcp.tree import Bounds, Element


def _element(left, top, right, bottom, name="x"):
    return Element(name, "android.widget.Button", "", Bounds(left, top, right, bottom))


def _png(image):
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _white(width=300, height=500):
    return Image.new("RGB", (width, height), "white")


def _gradient(width=300, height=500):
    """An image with thousands of colours, which a 256-colour palette must lose."""
    image = Image.new("RGB", (width, height))
    image.putdata([(x % 256, y % 256, (x * y) % 256) for y in range(height) for x in range(width)])
    return image


@pytest.mark.unit
class TestAnnotate:
    """Tests for annotate."""

    def test_draws_a_box_around_the_element(self):
        """The edges of the element's bounds are drawn in its colour; the inside is untouched."""
        annotated = screenshot.annotate(_white(), [_element(50, 200, 250, 400)])

        color = screenshot.PALETTE[0]
        assert annotated.getpixel((50, 300)) == _rgb(color)  # left edge
        assert annotated.getpixel((250, 300)) == _rgb(color)  # right edge
        assert annotated.getpixel((150, 200)) == _rgb(color)  # top edge
        assert annotated.getpixel((150, 400)) == _rgb(color)  # bottom edge
        assert annotated.getpixel((150, 300)) == (255, 255, 255)  # inside

    def test_numbers_sit_on_a_tab_above_the_top_right_corner(self):
        """The label's background fills the strip above the box, ending at its right edge."""
        annotated = screenshot.annotate(_white(), [_element(50, 200, 250, 400)])

        assert annotated.getpixel((249, 190)) == _rgb(screenshot.PALETTE[0])
        assert annotated.getpixel((100, 190)) == (255, 255, 255)  # tab does not span the box

    def test_each_element_gets_its_own_colour(self):
        """Neighbours are told apart; colours repeat only after the palette runs out."""
        elements = [_element(10 + 20 * i, 100, 25 + 20 * i, 200) for i in range(12)]

        annotated = screenshot.annotate(_white(400, 300), elements)

        for index in (0, 1, 2, 10, 11):
            assert annotated.getpixel((10 + 20 * index, 150)) == _rgb(
                screenshot.PALETTE[index % len(screenshot.PALETTE)]
            )

    def test_does_not_modify_the_original(self):
        """The input image is left as it was."""
        original = _white()

        screenshot.annotate(original, [_element(50, 200, 250, 400)])

        assert original.getpixel((50, 300)) == (255, 255, 255)

    def test_accepts_images_with_an_alpha_channel(self):
        """Screenshots may be RGBA; the result is plain RGB."""
        annotated = screenshot.annotate(
            Image.new("RGBA", (300, 500), "white"), [_element(1, 1, 9, 9)]
        )

        assert annotated.mode == "RGB"

    def test_element_at_the_top_edge_keeps_its_number_on_screen(self):
        """A tab that would be above the image is clamped to it instead of vanishing."""
        annotated = screenshot.annotate(_white(), [_element(50, 0, 250, 100)])

        assert annotated.getpixel((249, 1)) == _rgb(screenshot.PALETTE[0])

    def test_element_partly_off_screen_does_not_raise(self):
        """Bounds that run past the image are drawn as far as they go."""
        screenshot.annotate(_white(), [_element(-40, -40, 900, 900)])

    def test_no_elements_returns_an_equal_image(self):
        """With nothing to draw the pixels are unchanged."""
        assert screenshot.annotate(_white(), []).tobytes() == _white().tobytes()


def _rgb(hex_color):
    return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))


@pytest.mark.unit
class TestToPng:
    """Tests for to_png."""

    def test_round_trips_pixels(self):
        """Unquantized encoding loses nothing."""
        image = _gradient()

        assert Image.open(io.BytesIO(screenshot.to_png(image))).tobytes() == image.tobytes()

    def test_quantize_is_smaller_and_uses_a_palette(self):
        """256 colours cost far fewer bytes than millions, and keep the size."""
        image = _gradient()

        plain = screenshot.to_png(image)
        small = screenshot.to_png(image, quantize=True)
        result = Image.open(io.BytesIO(small))

        assert len(small) < len(plain)
        assert result.mode == "P"
        assert result.size == image.size
        assert len(result.getcolors(maxcolors=300)) <= 256

    def test_quantize_accepts_rgba(self):
        """An alpha channel does not stop quantizing."""
        image = Image.new("RGBA", (50, 50), (10, 20, 30, 255))

        assert Image.open(io.BytesIO(screenshot.to_png(image, quantize=True))).size == (50, 50)


@pytest.mark.unit
class TestRender:
    """Tests for render."""

    def test_untouched_when_nothing_is_asked_for(self):
        """The device's own PNG is returned as the very same bytes."""
        png = _png(_gradient())

        assert (
            screenshot.render(png, [_element(1, 1, 9, 9)], annotate_elements=False, quantize=False)
            is png
        )

    def test_untouched_when_there_is_nothing_to_annotate(self):
        """Annotation asked for but no elements: no pointless re-encode."""
        png = _png(_gradient())

        assert screenshot.render(png, [], annotate_elements=True, quantize=False) is png

    def test_annotated(self):
        """With elements, the result is a different image with the box drawn."""
        png = _png(_white())

        result = screenshot.render(
            png, [_element(50, 200, 250, 400)], annotate_elements=True, quantize=False
        )

        assert result != png
        assert Image.open(io.BytesIO(result)).convert("RGB").getpixel((50, 300)) == _rgb(
            screenshot.PALETTE[0]
        )

    def test_quantized_without_annotation(self):
        """Quantizing works on its own."""
        png = _png(_gradient())

        result = screenshot.render(png, [], annotate_elements=False, quantize=True)

        assert Image.open(io.BytesIO(result)).mode == "P"
        assert len(result) < len(png)

    def test_annotated_and_quantized(self):
        """Both together: boxes drawn, then reduced to a palette."""
        result = screenshot.render(
            _png(_white()), [_element(50, 200, 250, 400)], annotate_elements=True, quantize=True
        )

        assert Image.open(io.BytesIO(result)).mode == "P"
