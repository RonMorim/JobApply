import pytest
from backend.scrapers.parsing_engine import ParsingEngine

def test_parse_html():
    html = "<html><body><h1>Hello</h1></body></html>"
    soup = ParsingEngine.parse_html(html)
    assert soup.find("h1").text == "Hello"

def test_extract_text_by_selector():
    html = "<html><body><h1 class='title'>Job Title  </h1></body></html>"
    soup = ParsingEngine.parse_html(html)
    text = ParsingEngine.extract_text_by_selector(soup, ".title")
    assert text == "Job Title"
    
    # Missing selector
    assert ParsingEngine.extract_text_by_selector(soup, ".missing") is None

def test_extract_all_texts_by_selector():
    html = "<html><body><ul><li>One</li><li> Two </li></ul></body></html>"
    soup = ParsingEngine.parse_html(html)
    texts = ParsingEngine.extract_all_texts_by_selector(soup, "li")
    assert texts == ["One", "Two"]

def test_clean_html():
    html = "<html><style>body { color: red; }</style><body><p>Hello  <b>World</b></p><script>alert(1)</script></body></html>"
    cleaned = ParsingEngine.clean_html(html)
    assert cleaned == "Hello World"

def test_extract_json_metadata():
    data = {
        "job": {
            "title": "Software Engineer",
            "location": {
                "name": "Tel Aviv"
            }
        },
        "id": "123"
    }
    
    schema = {
        "title": ["job", "title"],
        "location": ["job", "location", "name"],
        "id": ["id"],
        "missing": ["job", "missing_field"]
    }
    
    extracted = ParsingEngine.extract_json_metadata(data, schema)

    assert extracted["title"] == "Software Engineer"
    assert extracted["location"] == "Tel Aviv"
    assert extracted["id"] == "123"
    assert extracted["missing"] is None


def test_extract_json_metadata_list_indices():
    # ATS payloads nest objects in arrays (Lever "lists", Greenhouse "offices")
    data = {
        "offices": [{"name": "Tel Aviv"}, {"name": "Berlin"}],
        "lists":   [{"text": "Requirements", "content": "<li>5+ years</li>"}],
    }
    schema = {
        "first_office":  ["offices", 0, "name"],
        "last_office":   ["offices", -1, "name"],
        "req_heading":   ["lists", 0, "text"],
        "out_of_range":  ["offices", 5, "name"],
        "not_a_list":    ["lists", 0, "text", 0],
    }
    extracted = ParsingEngine.extract_json_metadata(data, schema)
    assert extracted["first_office"] == "Tel Aviv"
    assert extracted["last_office"] == "Berlin"
    assert extracted["req_heading"] == "Requirements"
    assert extracted["out_of_range"] is None
    assert extracted["not_a_list"] is None


def test_html_to_text_preserves_lines_and_unescapes_entities():
    # Entity-encoded markup, as shipped by some Greenhouse/Lever payloads
    encoded = "&lt;div&gt;&lt;p&gt;First line&lt;/p&gt;&lt;p&gt;Second line&lt;/p&gt;&lt;/div&gt;"
    text = ParsingEngine.html_to_text(encoded)
    assert "First line" in text and "Second line" in text
    assert "<" not in text                      # no tags leaked verbatim
    assert "\n" in text                         # line structure preserved

    # Hebrew content survives untouched (Israeli-market requirement)
    hebrew = "<p>דרוש מנהל מוצר</p><p>Requirements: Python</p>"
    text = ParsingEngine.html_to_text(hebrew)
    assert "דרוש מנהל מוצר" in text
    assert "Requirements: Python" in text

    assert ParsingEngine.html_to_text("") == ""
