"""Apply reviewed compatibility fixes to the pinned Sanster renderer checkout."""
import argparse
import ast
from pathlib import Path


def replace_method(source, name, replacement):
    tree = ast.parse(source)
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
    lines = source.splitlines(keepends=True)
    start = min([node.lineno] + [d.lineno for d in node.decorator_list]) - 1
    lines[start:node.end_lineno] = [replacement.lstrip("\n").rstrip() + "\n"]
    return "".join(lines)


def patch(root):
    root = Path(root)
    if root.is_file():
        root = root.parent.parent
    path = root / "textrenderer/renderer.py"
    source = path.read_text()
    # Pillow API failures are deterministic: retrying forever hides the worker
    # exception and leaves the parent waiting without producing usable images.
    source = source.replace("from tenacity import retry\n", "from tenacity import retry, stop_after_attempt\n")
    source = source.replace("    @retry\n", "    @retry(stop=stop_after_attempt(16), reraise=True)\n")
    source = source.replace("        offset = font.getoffset(word)\n", "        offset = font.getbbox(word)[:2]\n")
    source = replace_method(source, "get_word_size", """
    def get_word_size(self, font, word):
        # A glyph bbox is already offset-aware. Do not subtract top twice.
        left, top, right, bottom = font.getbbox(word)
        if not word.strip() or right <= left or bottom <= top:
            raise ValueError("Cannot render empty/inkless text")
        return right - left, bottom - top
""")
    source = replace_method(source, "draw_text_with_random_space", """
    def draw_text_with_random_space(self, draw, font, word, word_color, bg_width, bg_height):
        boxes = [font.getbbox(c) for c in word]
        ink = [box for c, box in zip(word, boxes) if c.strip()]
        if not ink:
            raise ValueError("Cannot render inkless text")
        top, bottom = min(b[1] for b in ink), max(b[3] for b in ink)
        gap = int((bottom - top) * np.random.uniform(self.cfg.random_space.min, self.cfg.random_space.max))
        positions, cursor = [], 0.0
        for c in word:
            positions.append(cursor)
            cursor += font.getlength(c) + gap
        left = math.floor(min(x + b[0] for x, c, b in zip(positions, word, boxes) if c.strip()))
        right = math.ceil(max(x + b[2] for x, c, b in zip(positions, word, boxes) if c.strip()))
        width, height = right - left, bottom - top
        text_x, text_y = (bg_width - width) // 2, (bg_height - height) // 2
        for x, c in zip(positions, word):
            draw.text((text_x + x - left, text_y - top), c, fill=word_color, font=font)
        return text_x, text_y, width, height
""")
    # Seamless branch must compensate for left bearing as the normal branch does.
    source = source.replace("                               0 + seamless_offset // 2,", "                               -offset[0] + seamless_offset // 2,")
    ast.parse(source)
    main = root / "main.py"
    text = main.read_text().replace("from tenacity import retry\n", "from tenacity import retry, stop_after_attempt\n")
    text = text.replace("@retry\n", "@retry(stop=stop_after_attempt(8), reraise=True)\n")
    ast.parse(text)
    path.write_text(source)
    main.write_text(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, nargs="?", default=Path("text_renderer/textrenderer/renderer.py"))
    patch(parser.parse_args().root)
