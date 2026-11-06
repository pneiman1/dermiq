"""The UI-role triplets must agree with the hex tokens they mirror.

tokens.css carries each brand colour twice: as hex (read by chartTokens.ts and
scripts/check-contrast.mjs) and as an HSL triplet (read by Tailwind, which
cannot inject an alpha channel into a hex custom property). Two representations
of one colour is a drift risk, and this is the test that makes it safe.

The teal this app served until the rename was exactly this class of failure — a
second colour definition nobody was comparing against the first.
"""
from __future__ import annotations

import colorsys
import re
from pathlib import Path

import pytest

TOKENS = Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles" / "tokens.css"

#: UI role -> the hex token it must equal. Roles with no brand equivalent
#: (card, muted, the hover fill) are free and not listed.
MIRRORS = {
    "--ui-background": "--surface-1",
    "--ui-foreground": "--text-primary",
    "--ui-muted-foreground": "--text-secondary",
    "--ui-primary": "--accent",
    "--ui-ring": "--accent",
    "--ui-destructive": "--status-critical",
}

#: Roles with no brand equivalent, listed so their absence above is a decision
#: rather than an oversight. --ui-border is NOT --chart-grid: they coincide in
#: the light theme and diverge in the dark one, where the border is deliberately
#: a step lighter than the chart grid so a card edge stays visible against it.
FREE_ROLES = {
    "--ui-card", "--ui-card-foreground", "--ui-popover", "--ui-popover-foreground",
    "--ui-muted", "--ui-accent", "--ui-accent-foreground", "--ui-border",
    "--ui-input", "--ui-primary-foreground", "--ui-destructive-foreground",
    "--radius",
}


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*[\s\S]*?\*/", "", css)


def _scopes() -> list[dict[str, str]]:
    """Each colour scope's declarations, by brace matching rather than by
    indentation — the scopes in this file are nested to different depths."""
    css = _strip_comments(TOKENS.read_text())
    out = []
    # Every block whose selector mentions :root. Matching the selector text
    # itself is brittle — :root:where(:not([data-theme="light"])) has nested
    # parentheses that a [^)]* class truncates — so this walks the braces and
    # looks backwards at the selector instead.
    for i, ch in enumerate(css):
        if ch != "{":
            continue
        # The selector is the text since the previous brace of EITHER kind. Using
        # only the previous "}" swept up the enclosing "@media (...) {" for the
        # nested dark scope, and the "@" test then skipped it — so the OS-preference
        # theme went unchecked while the test reported success on two scopes.
        sel_start = max(css.rfind("}", 0, i), css.rfind("{", 0, i)) + 1
        selector = css[sel_start:i]
        if ":root" not in selector or selector.lstrip().startswith("@"):
            continue
        depth, j = 1, i + 1
        while depth and j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
            j += 1
        body = css[i + 1 : j - 1]
        decls = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;]+);", body))
        if decls:
            out.append(decls)
    return out


def _hex_to_triplet(hx: str) -> tuple[float, float, float]:
    hx = hx.strip().lstrip("#")
    r, g, b = (int(hx[i : i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h * 360, s * 100, l * 100


def _parse_triplet(v: str) -> tuple[float, float, float]:
    m = re.match(r"\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*$", v)
    assert m, f"not an HSL triplet: {v!r}"
    return float(m.group(1)), float(m.group(2)), float(m.group(3))


def test_tokens_file_has_three_colour_scopes():
    """:root, the OS-preference dark scope, and the in-app toggle. If one is
    missing, a theme silently falls back to the other's values."""
    scopes = _scopes()
    assert len(scopes) == 3, f"expected 3 colour scopes, found {len(scopes)}"


@pytest.mark.parametrize("role,brand", sorted(MIRRORS.items()))
def test_ui_triplet_matches_the_hex_token_it_mirrors(role, brand):
    for n, decls in enumerate(_scopes()):
        if role not in decls or brand not in decls:
            continue
        want = _hex_to_triplet(decls[brand])
        got = _parse_triplet(decls[role])
        # Triplets are written rounded to whole numbers, so a unit of slack per
        # channel. Anything larger is a different colour.
        for axis, w, g in zip("HSL", want, got):
            assert abs(w - g) <= 1.5, (
                f"scope {n}: {role} = {decls[role].strip()!r} does not match "
                f"{brand} = {decls[brand].strip()!r} on {axis} "
                f"(want {w:.1f}, got {g:.1f})"
            )


def test_every_mirrored_role_is_accounted_for():
    """Each --ui-* role is either mirrored onto a brand token or explicitly
    free. A role in neither set is one nobody decided about."""
    roles = {k for s in _scopes() for k in s if k.startswith("--ui-")} | {"--radius"}
    unaccounted = sorted(roles - set(MIRRORS) - FREE_ROLES)
    assert not unaccounted, f"roles in neither MIRRORS nor FREE_ROLES: {unaccounted}"


def test_every_ui_role_is_defined_in_every_dark_scope():
    """A role defined in :root but missing from a dark scope inherits the light
    value, which is how half-themed dark modes happen."""
    scopes = _scopes()
    light = {k for k in scopes[0] if k.startswith("--ui-")}
    for n, decls in enumerate(scopes[1:], start=1):
        present = {k for k in decls if k.startswith("--ui-")}
        missing = sorted(light - present - {"--radius"})
        assert not missing, f"dark scope {n} is missing {len(missing)} role(s): {missing}"


def test_the_two_themes_do_not_share_an_accent():
    """An inverted accent is what produces an identical value in both themes."""
    scopes = _scopes()
    accents = [s["--accent"].strip().lower() for s in scopes if "--accent" in s]
    assert len(set(accents)) >= 2, f"both themes use the same accent: {accents}"


def test_no_blue_family_tailwind_utility_in_any_component():
    """The source half of the gate. scripts/check-theme.mjs covers the built
    bundle, which is the half that actually caught this; this one keeps the
    source honest so the failure is cheap to diagnose."""
    src = TOKENS.resolve().parents[1]
    pattern = re.compile(
        r"(?<![\w-])(?:bg|text|border|ring|from|to|via|fill|stroke|divide|outline"
        r"|shadow|decoration|accent|caret|placeholder)-"
        r"(?:blue|indigo|sky|cyan|teal|slate|violet|purple)-\d{2,3}(?![\w-])"
    )
    offenders = []
    for path in src.rglob("*.tsx"):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(src)}:{n}")
    assert not offenders, f"blue-family Tailwind utilities: {offenders}"
