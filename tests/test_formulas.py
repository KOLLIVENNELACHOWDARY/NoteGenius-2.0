import pytest

from utils import formulas as fx


@pytest.mark.parametrize("raw,expected", [
    ("v = u + at", "v = u + at"),
    ("E = mc^2", "E = mc^{2}"),
    ("x² + y² = r²", "x^{2} + y^{2} = r^{2}"),
    ("F = G m1 m2 / r^2", r"F = \frac{G m_{1} m_{2}}{r^{2}}"),
    ("KE = 1/2 m v^2", r"KE = \frac{1}{2} m v^{2}"),
    ("s = ut + ½at²", r"s = ut + \frac{1}{2}at^{2}"),
    ("x = (-b ± sqrt(b^2 - 4ac)) / (2a)", r"x = \frac{-b \pm \sqrt{b^{2} - 4ac}}{2a}"),
    ("Force = mass × acceleration", r"\mathrm{Force} = \mathrm{mass} \times \mathrm{acceleration}"),
    ("PE = mgh", "PE = mgh"),
    ("$\\frac{a}{b}$", r"\frac{a}{b}"),
])
def test_plain_text_to_latex(raw, expected):
    assert fx.to_latex(raw) == expected


def test_chemical_equation_is_typeset_with_subscripts():
    latex = fx.to_latex("2H2 + O2 -> 2H2O")
    assert r"\mathrm{2H_{2}}" in latex and r"\rightarrow" in latex


@pytest.mark.parametrize("line", ["v = u + at", "F = ma", "Area of circle = πr²", "Profit = Total Revenue - Total Cost", "2H2 + O2 -> 2H2O", "$$x^2$$"])
def test_equations_are_recognised(line):
    assert fx.looks_like_equation(line)


@pytest.mark.parametrize("line", [
    "Speed is the distance travelled per unit time.", "The speed is constant = fast", "Water boils at 100 degrees.",
    "Visit http://example.com/?a=1", "v = final",
])
def test_sentences_are_not_equations(line):
    assert not fx.looks_like_equation(line)


def test_inline_formula_is_cut_cleanly():
    assert fx.find_inline_formulas("The relation v = u + at holds, and a is constant.") == ["v = u + at"]
    assert fx.find_inline_formulas("Newton's second law states that F = ma where m is mass.") == ["F = ma"]
    assert fx.find_inline_formulas("A quadratic equation has the form ax^2 + bx + c = 0.") == ["ax^2 + bx + c = 0"]


def test_variable_legend():
    got = fx.parse_variables("where v = final velocity, u = initial velocity, a = acceleration and t = time taken")
    assert got == [("v", "final velocity"), ("u", "initial velocity"), ("a", "acceleration"), ("t", "time taken")]


def test_speech():
    assert fx.to_speech("v = u + at") == "v equals u plus a t"
    assert "squared" in fx.to_speech("E = mc^2")
    assert "over" in fx.to_speech("x = (-b ± sqrt(b^2 - 4ac)) / (2a)")


def test_formula_image(tmp_path):
    out = fx.render_png(fx.to_latex("KE = 1/2 m v^2"), str(tmp_path), color="12263F")
    assert out and out[1] > 50 and open(out[0], "rb").read(4) == b"\x89PNG"
