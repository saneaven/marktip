"""Opt-in URI policy for link href / image src.

Issue #2 — `[click](javascript:alert(1))` is valid Markdown, so refusing it by default
would be wrong for a general-purpose converter.
But a consumer that stores the output and renders it later has to refuse it at the write
boundary, and doing that in Python costs more than the entire conversion.

The policy is off by default and applies to *both* write boundaries: an editor submits an
AST via from_dict, agents and imports submit Markdown strings via from_markdown.
An option that only existed on from_dict would leave the parser path open.

Rejecting an ASCII control character is the one part that is unconditional — see
test_control_characters_* below for why it cannot sit behind the option.
"""

import pytest

import marktip as tm


def doc(*blocks):
    return {"type": "doc", "content": list(blocks)}


def link(href, text="x"):
    node = {"type": "text", "text": text, "marks": [{"type": "link", "attrs": {"href": href}}]}
    return {"type": "paragraph", "content": [node]}


def image(src):
    return {"type": "paragraph", "content": [{"type": "image", "attrs": {"src": src, "alt": ""}}]}


# Where a violation is reported, for each of the two shapes above.
LINK_PATH = "content[0].content[0].marks[0]"
IMAGE_PATH = "content[0].content[0]"


def code_for(ast, **options):
    """The .code from converting `ast`, or None when it is accepted."""
    try:
        tm.from_dict(ast, **options).to_markdown()
    except tm.MarktipError as err:
        return err.code
    return None


# ── the default: nothing changes for anyone not asking for it ────────────────


@pytest.mark.parametrize("href", ["javascript:alert(1)", "data:text/html,<script>", "vbscript:msgbox"])
def test_dangerous_schemes_still_convert_when_no_policy_is_set(href):
    # marktip is a converter, not a sanitizer. Refusing these by default would be wrong.
    assert code_for(doc(link(href))) is None
    assert tm.from_markdown(f"[x]({href})").to_dict() is not None


def test_the_default_preserves_the_destination_verbatim():
    markdown = "[x](javascript:alert(1))"
    href = tm.from_markdown(markdown).to_dict()["content"][0]["content"][0]["marks"][0]["attrs"]["href"]
    assert href == "javascript:alert(1)"


# ── the scheme allowlist ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "href, expected",
    [
        ("https://example.com", None),
        ("HTTPS://example.com", None),  # scheme comparison is case-insensitive
        ("HtTpS://example.com", None),
        ("http://example.com", "disallowed_scheme"),
        ("javascript:alert(1)", "disallowed_scheme"),
        ("JavaScript:alert(1)", "disallowed_scheme"),  # ...which is the point of it
        ("mailto:a@b.c", "disallowed_scheme"),
    ],
)
def test_allowlist_restricts_link_schemes(href, expected):
    assert code_for(doc(link(href)), link_schemes=("https",)) == expected


def test_allowlist_entries_are_normalized_like_the_values_they_match():
    assert code_for(doc(link("https://a")), link_schemes=("HTTPS",)) is None


def test_empty_allowlist_rejects_every_absolute_reference():
    # () is meaningfully different from None: it allows no scheme at all.
    assert code_for(doc(link("https://a")), link_schemes=()) == "disallowed_scheme"
    assert code_for(doc(link("/foo")), link_schemes=()) is None  # ...but relative is a separate axis


def test_links_and_images_are_governed_separately():
    # The asymmetry the issue argues is common: http/mailto for links, https only for images.
    options = {"link_schemes": ("https", "mailto"), "image_schemes": ("https",)}
    assert code_for(doc(link("mailto:a@b.c")), **options) is None
    assert code_for(doc(image("mailto:a@b.c")), **options) == "disallowed_scheme"
    assert code_for(doc(image("https://cdn/x.png")), **options) is None


def test_image_inside_a_link_is_checked_on_both_the_mark_and_the_node():
    node = {"type": "image", "attrs": {"src": "http://cdn/x.png", "alt": ""}}
    node["marks"] = [{"type": "link", "attrs": {"href": "http://example.com"}}]
    ast = doc({"type": "paragraph", "content": [node]})

    assert code_for(ast, link_schemes=("https",)) == "disallowed_scheme"
    assert code_for(ast, image_schemes=("https",)) == "disallowed_scheme"
    assert code_for(ast) is None


def test_a_missing_href_or_src_is_still_accepted():
    # Unchanged promise: the serializer substitutes a default rather than failing.
    bare_link = {"type": "paragraph", "content": [{"type": "text", "text": "x", "marks": [{"type": "link"}]}]}
    bare_image = {"type": "paragraph", "content": [{"type": "image", "attrs": {"alt": ""}}]}

    assert code_for(doc(bare_link), link_schemes=(), link_relative="reject") is None
    assert code_for(doc(bare_image), image_schemes=(), image_relative="reject") is None


def test_a_null_href_or_src_is_the_missing_one_not_an_empty_string():
    # Issue #4: Tiptap declares `default: null` for both,
    # so from_dict drops the key rather than coercing it to "".
    # Before 0.6.0 a null reached the policy as a present reference carrying no scheme,
    # and "reject" refused a document the editor produces.
    assert code_for(doc(link(None)), link_schemes=(), link_relative="reject") is None
    assert code_for(doc(image(None)), image_schemes=(), image_relative="reject") is None

    # An href that is present and empty is still a reference, and still refused.
    assert code_for(doc(link("")), link_relative="reject") == "disallowed_relative_url"


def test_non_link_marks_and_non_image_nodes_are_left_alone():
    node = {"type": "text", "text": "x", "marks": [{"type": "bold"}, {"type": "code"}]}
    ast = doc({"type": "paragraph", "content": [node], "attrs": {"href": "javascript:alert(1)"}})
    assert code_for(ast, link_schemes=("https",)) is None


# ── relative references ──────────────────────────────────────────────────────

RELATIVE_CASES = [
    # href                 allow  path_only              reject
    ("/foo", None, None, "disallowed_relative_url"),
    ("#anchor", None, None, "disallowed_relative_url"),
    ("./x.png", None, None, "disallowed_relative_url"),
    ("", None, None, "disallowed_relative_url"),
    ("//evil.com/x", None, "disallowed_relative_url", "disallowed_relative_url"),
    # Browsers fold backslashes into slashes for special schemes,
    # so these leave the origin exactly like "//evil.com/x" does.
    ("\\\\evil.com/x", None, "disallowed_relative_url", "disallowed_relative_url"),
    ("/\\evil.com/x", None, "disallowed_relative_url", "disallowed_relative_url"),
    ("https://example.com", None, None, None),
]


@pytest.mark.parametrize("href, allow, path_only, reject", RELATIVE_CASES)
def test_relative_policy_governs_scheme_less_references(href, allow, path_only, reject):
    assert code_for(doc(link(href)), link_relative="allow") == allow
    assert code_for(doc(link(href)), link_relative="path_only") == path_only
    assert code_for(doc(link(href)), link_relative="reject") == reject


def test_relative_policy_applies_without_a_scheme_allowlist():
    # The two axes are independent: "must be absolute, any scheme" is expressible.
    assert code_for(doc(link("javascript:alert(1)")), link_relative="reject") is None
    assert code_for(doc(link("/foo")), link_relative="reject") == "disallowed_relative_url"


def test_relative_policy_is_separate_for_links_and_images():
    options = {"link_relative": "allow", "image_relative": "reject"}
    assert code_for(doc(link("#anchor")), **options) is None
    assert code_for(doc(image("./x.png")), **options) == "disallowed_relative_url"


# ── control characters: unconditional ────────────────────────────────────────


@pytest.mark.parametrize("href", ["https://a\x01b", "https://a\x00b", "https://a\x7fb", "https://a\nb"])
def test_control_characters_are_rejected_with_no_options_set(href):
    # Changed in 0.5.0. A control character is never valid in a URI unencoded,
    # so this does not wait for the consumer to opt in.
    assert code_for(doc(link(href))) == "invalid_uri_char"
    assert code_for(doc(image(href))) == "invalid_uri_char"


def test_control_characters_cannot_be_used_to_smuggle_a_scheme():
    # The reason it cannot sit behind the option:
    # browsers strip tab/LF/CR before reading the scheme,
    # so "java\tscript:" is a javascript URL to a renderer.
    # If it were merely stored, an https-only allowlist would be a false promise.
    for href in ["java\tscript:alert(1)", "java\nscript:alert(1)", "java\rscript:alert(1)"]:
        assert code_for(doc(link(href)), link_schemes=("https",)) == "invalid_uri_char"


def test_a_leading_space_does_not_hide_the_scheme():
    assert code_for(doc(link(" javascript:alert(1)")), link_schemes=("https",)) == "disallowed_scheme"
    assert code_for(doc(link("   //evil.com/x")), link_relative="path_only") == "disallowed_relative_url"


# ── entity references ────────────────────────────────────────────────────────
#
# MD4C hands MD_TEXT_ENTITY substrings through verbatim,
# so an encoded scheme reaches the AST intact,
# and only becomes executable once a consumer renders it into an HTML attribute.
# The check therefore runs on the decoded form.


@pytest.mark.parametrize(
    "href",
    [
        "&#106;avascript:alert&#40;1&#41;",  # decimal
        "&#x6a;avascript:alert(1)",  # hex
        "&#X6A;avascript:alert(1)",  # uppercase marker
        "&#106;&#97;&#118;&#97;script:x",  # fully encoded
        "javascript&colon;alert(1)",  # named reference for the colon
    ],
)
def test_entity_encoded_schemes_do_not_slip_past_the_allowlist(href):
    assert code_for(doc(link(href)), link_schemes=("https",)) == "disallowed_scheme"


@pytest.mark.parametrize("href", ["java&#09;script:alert(1)", "java&Tab;script:alert(1)"])
def test_entity_encoded_control_characters_are_rejected(href):
    assert code_for(doc(link(href)), link_schemes=("https",)) == "invalid_uri_char"


@pytest.mark.parametrize("padding", [0, 4, 40, 400])
def test_zero_padded_numeric_references_are_decoded_at_any_length(padding):
    # A numeric reference has no length limit,
    # so the terminator cannot be looked for inside a fixed window —
    # a browser reads all of these as 'j'.
    zeros = "0" * padding
    assert code_for(doc(link(f"&#{zeros}106;avascript:x")), link_schemes=("https",)) == "disallowed_scheme"
    assert code_for(doc(link(f"&#x{zeros}6a;avascript:x")), link_schemes=("https",)) == "disallowed_scheme"
    assert code_for(doc(link(f"java&#{zeros}9;script:x")), link_schemes=("https",)) == "invalid_uri_char"


def test_a_long_query_string_without_semicolons_stays_cheap():
    # Guards the scan bound: every '&' used to rescan the tail looking for a ';'.
    href = "https://a?" + "&".join(f"k{i}=v{i}" for i in range(20000))
    assert code_for(doc(link(href)), link_schemes=("https",)) is None


def test_an_overlong_word_between_ampersand_and_semicolon_is_not_an_entity():
    href = "&" + "a" * 200 + ";javascript:alert(1)"
    assert code_for(doc(link(href)), link_schemes=("https",)) is None


@pytest.mark.parametrize(
    "href",
    [
        "https://a?x=1&y=2",  # bare ampersands are ordinary query separators
        "https://a?x=1&amp;y=2",
        "https://example.com/f&ouml;&ouml;",
        "&amp;#106;avascript:alert(1)",  # decoding is single pass, as in a browser
        "&nope;javascript:alert(1)",  # an unknown reference stays literal
        "&#999999999999;https://a",  # out of range -> U+FFFD
        "&#0;https://a",  # NUL -> U+FFFD, not a control character
        "&;https://a",
        "&#;https://a",
        "&https://a",
    ],
)
def test_ampersands_that_are_not_a_scheme_are_left_alone(href):
    assert code_for(doc(link(href)), link_schemes=("https",)) is None


def test_decoding_is_only_for_the_check_and_never_rewrites_the_stored_value():
    href = "https://example.com/f&ouml;&ouml;?x=1&amp;y=2"
    document = tm.from_dict(doc(link(href)), link_schemes=("https",))

    stored = document.to_dict()["content"][0]["content"][0]["marks"][0]["attrs"]["href"]
    assert stored == href
    assert document.to_markdown().strip() == f"[x]({href})"


# ── from_markdown is the same boundary ───────────────────────────────────────


@pytest.mark.parametrize(
    "markdown, code",
    [
        ("[x](javascript:alert(1))", "disallowed_scheme"),
        ("[x](&#106;avascript:alert&#40;1&#41;)", "disallowed_scheme"),
        ("![x](http://cdn/a.png)", "disallowed_scheme"),
        ("<javascript:alert(1)>", "disallowed_scheme"),  # autolinks are link marks too
        ("[x](https://example.com)", None),
        ("![x](https://cdn/a.png)", None),
    ],
)
def test_the_policy_applies_to_parsed_markdown(markdown, code):
    options = {"link_schemes": ("https",), "image_schemes": ("https",)}
    try:
        tm.from_markdown(markdown, **options)
    except tm.MarktipError as err:
        assert err.code == code
    else:
        assert code is None


def test_a_markdown_violation_reports_the_same_fields_as_the_dict_one():
    markdown = "[x](javascript:alert(1))"
    with pytest.raises(tm.InvalidNodeError) as from_md:
        tm.from_markdown(markdown, link_schemes=("https",))
    with pytest.raises(tm.InvalidNodeError) as from_ast:
        tm.from_dict(doc(link("javascript:alert(1)")), link_schemes=("https",))

    assert from_md.value.code == from_ast.value.code
    assert from_md.value.field == from_ast.value.field == "href"
    assert from_md.value.path == from_ast.value.path == LINK_PATH


def test_reference_links_are_checked_after_the_definition_is_resolved():
    markdown = "[x][ref]\n\n[ref]: javascript:alert(1)"
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_markdown(markdown, link_schemes=("https",))
    assert excinfo.value.code == "disallowed_scheme"


def test_raw_html_is_not_scanned_and_html_false_is_the_way_to_close_it():
    # A documented non-guarantee: the policy governs link/image nodes, not raw HTML.
    markdown = '<a href="javascript:alert(1)">x</a>'
    accepted = tm.from_markdown(markdown, link_schemes=("https",))
    assert "javascript:alert(1)" in accepted.to_markdown()

    # html=False keeps the same characters but as literal text, not as markup.
    as_text = tm.from_markdown(markdown, link_schemes=("https",), html=False).to_dict()
    assert not any(node["type"].startswith("html") for node in as_text["content"][0]["content"])


# ── the error itself ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "ast, options, code, field, path",
    [
        (doc(link("http://a")), {"link_schemes": ("https",)}, "disallowed_scheme", "href", LINK_PATH),
        (doc(image("http://a")), {"image_schemes": ("https",)}, "disallowed_scheme", "src", IMAGE_PATH),
        (doc(link("/foo")), {"link_relative": "reject"}, "disallowed_relative_url", "href", LINK_PATH),
        (doc(image("//evil/x")), {"image_relative": "path_only"}, "disallowed_relative_url", "src", IMAGE_PATH),
        (doc(link("https://a\x01b")), {}, "invalid_uri_char", "href", LINK_PATH),
    ],
)
def test_violations_carry_code_field_and_path(ast, options, code, field, path):
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, **options)

    err = excinfo.value
    assert err.code == code
    assert err.field == field
    assert err.path == path
    assert err.detail == str(err)
    assert isinstance(err, tm.MarktipError)


def test_the_path_locates_the_violation_in_a_nested_document():
    ast = doc(
        {"type": "paragraph", "content": [{"type": "text", "text": "ok"}]},
        {"type": "blockquote", "content": [link("javascript:alert(1)")]},
    )
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(ast, link_schemes=("https",))
    assert excinfo.value.path == "content[1].content[0].content[0].marks[0]"


def test_the_message_names_the_offending_scheme():
    with pytest.raises(tm.InvalidNodeError) as excinfo:
        tm.from_dict(doc(link("javascript:alert(1)")), link_schemes=("https",))
    assert str(excinfo.value) == "link href scheme 'javascript' is not allowed"


# ── option values are a caller bug, not a malformed document ─────────────────


@pytest.mark.parametrize(
    "options",
    [
        {"link_schemes": 123},
        {"link_schemes": "https"},  # a bare str would silently become {h, t, p, s}
        {"image_schemes": b"https"},
        {"link_schemes": (1,)},
        {"link_schemes": ("https", None)},
        {"link_relative": 1},
        {"image_relative": None},
    ],
)
def test_bad_option_types_raise_typeerror(options):
    # Same carve-out as from_markdown's non-str argument: a caller bug,
    # so it stays outside the hierarchy and `except MarktipError` must not swallow it.
    with pytest.raises(TypeError):
        tm.from_dict(doc(), **options)
    assert not issubclass(TypeError, tm.MarktipError)


@pytest.mark.parametrize(
    "options",
    [
        {"link_schemes": ("https://",)},
        {"link_schemes": ("ht tps",)},
        {"link_schemes": ("https:",)},
        {"link_schemes": ("",)},
        {"link_schemes": ("1https",)},  # a scheme must start with a letter
        {"link_relative": "nope"},
        {"image_relative": "Allow"},
    ],
)
def test_bad_option_values_raise_valueerror(options):
    with pytest.raises(ValueError):
        tm.from_dict(doc(), **options)


def test_options_are_validated_before_the_document_is_walked():
    # A caller bug should surface whatever the document happens to contain.
    with pytest.raises(ValueError):
        tm.from_dict({"type": "not-a-doc"}, link_relative="nope")


def test_options_are_keyword_only():
    with pytest.raises(TypeError):
        tm.from_dict(doc(), ("https",))
    with pytest.raises(TypeError):
        tm.from_markdown("x", False, True, ("https",))


def test_any_iterable_of_str_is_accepted():
    for schemes in [["https"], ("https",), {"https"}, frozenset({"https"}), iter(["https"])]:
        assert code_for(doc(link("http://a")), link_schemes=schemes) == "disallowed_scheme"


def test_duplicate_scheme_entries_are_harmless():
    assert code_for(doc(link("https://a")), link_schemes=("https", "https", "HTTPS")) is None
