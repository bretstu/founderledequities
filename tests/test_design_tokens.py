"""THE DESIGN HAS ONE SOURCE (design b, 2026-09-29).

index.html's stylesheet is lifted into site.css and every page links it,
so the tokens (one :root), the faces (one @font-face block) and the
colours (names, never hex) live in one place. Months of iteration had
left six copies of the token block, four self-hosted families and forty
hex colours written past the tokens; these pins keep that from growing
back. A deliberate exception updates the pin with a dated comment.
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# every hand-written template that becomes a page (built pages are not
# here: the builder copies them from these)
TEMPLATES = ["index.html", "company.html", "tape.html", "companies.html",
             "about.html", "alerts.html", "404.html", "universe.html", "terms.html"]


def _read(name):
    return open(os.path.join(ROOT, name), encoding="utf-8").read()


def _styles(page):
    """every <style> block of a template, joined"""
    return "\n".join(re.findall(r"<style>(.*?)</style>", page, re.S))


def test_one_root_block_and_it_is_index_htmls():
    for name in TEMPLATES:
        n = _styles(_read(name)).count(":root{")
        if name == "index.html":
            assert n == 1, "index.html carries the one :root; site.css is built from it"
        else:
            assert n == 0, f"{name} carries its own :root; the tokens are index.html's"


def test_the_faces_are_declared_once_and_are_inter_and_plex_mono():
    for name in TEMPLATES:
        page = _read(name)
        if name == "index.html":
            faces = re.findall(r'@font-face\{font-family:"([^"]+)"', page)
            assert sorted(set(faces)) == ["IBM Plex Mono", "Inter"], faces
        else:
            assert "@font-face" not in page, f"{name} declares a face; site.css has them"
        assert "fonts.googleapis.com" not in page, f"{name} fetches a third-party font"
        for retired in ("Fraunces", "Bricolage", "Hanken"):
            assert retired not in page, f"{name} still names the retired face {retired}"
    fonts = sorted(f for f in os.listdir(os.path.join(ROOT, "fonts")) if f.endswith(".woff2"))
    assert fonts == ["inter.woff2", "plexmono-medium.woff2", "plexmono.woff2"], fonts


def test_no_colour_is_written_in_hex_outside_the_tokens():
    """a colour with no name in :root does not exist on the site. #fff and
    #000 are allowed: white is a surface, not a colour choice."""
    page = _read("index.html")
    css = _styles(page)
    a = css.index(":root{")
    b = css.index("\n}\n", a)
    outside = css[:a] + css[b:]
    hexes = {h.lower() for h in re.findall(r"#[0-9A-Fa-f]{3,6}\b", outside)}
    assert hexes <= {"#fff", "#ffffff", "#000"}, sorted(hexes)
    for name in ["company.html", "tape.html", "companies.html"]:
        hexes = {h.lower() for h in re.findall(r"#[0-9A-Fa-f]{3,6}\b", _styles(_read(name)))}
        assert hexes <= {"#fff", "#ffffff", "#000"}, (name, sorted(hexes))


def test_the_display_face_is_retired():
    """one sans; a heading is the same face at 700. --disp would silently
    resolve to nothing and fall back to the browser's serif."""
    for name in TEMPLATES + ["ops/build_company_pages.py", "assets/company-page.js"]:
        assert "var(--disp)" not in _read(name), f"{name} still asks for the display face"


def test_the_kind_chip_has_one_rule():
    """the tape, the home strip and the company record share .kind from
    site.css; company.html carried a second copy once."""
    assert ".kind.bought{" in _styles(_read("index.html"))
    assert ".kind.bought" not in _styles(_read("company.html"))


def test_type_sizes_come_from_the_scale():
    """seven named sizes below a headline (slice 2, 2026-09-29); a headline is a
    clamp of its own, and the few fixed display sizes above 27px stay literal."""
    for name in TEMPLATES:
        css = _styles(_read(name))
        loose = [m for m in re.findall(r"font-size:(\d+(?:\.\d+)?)px", css) if float(m) < 27]
        # the one literal: the kind chip is 10px so COMPENSATION fits the tape's fixed column
        assert loose in ([], ["10"]), (name, loose)
    assert "--fs-m:" in _styles(_read("index.html"))


def test_every_class_the_stylesheet_defines_is_used_somewhere():
    """A RULE WITH NO ELEMENT IS DEBT (2026-10-07). The review that day found 64
    classes from retired features (the paid tier's locks and seals, the sign-in
    modal, the old home tape, the sparkline) still styled in index.html's sheet.
    A class the stylesheet defines must appear in a template, the builder, or a
    script; a comment does not count. Deliberate exceptions go in ALLOW with a
    dated reason."""
    import glob
    page = _read("index.html")
    css = _styles(page)
    nocomment = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    classes = sorted(set(re.findall(r"\.([a-zA-Z_][\w-]*)", nocomment)))
    files = ([n for n in TEMPLATES if n != "index.html"] + ["_harness.js"]
             + glob.glob(os.path.join(ROOT, "assets", "*.js")) + glob.glob(os.path.join(ROOT, "ops", "*.py"))
             + glob.glob(os.path.join(ROOT, "fle", "*.py")))
    corpus = re.sub(r"<style>.*?</style>", "", page, flags=re.S) + "\n" + "\n".join(
        open(f if os.path.isabs(f) else os.path.join(ROOT, f), encoding="utf-8", errors="ignore").read() for f in files)
    ALLOW = set()
    dead = [c for c in classes if c not in ALLOW and re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(c), corpus) is None]
    assert not dead, dead
