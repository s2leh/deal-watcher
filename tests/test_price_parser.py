from src.amazon_scraper import extract_asin, parse_price


def test_parse_english_price():
    assert parse_price("SAR 1,299.50") == 1299.50


def test_parse_arabic_price():
    assert parse_price("١٬٢٩٩٫٥٠ ر.س.") == 1299.50


def test_extract_asin():
    url = "https://www.amazon.sa/dp/B0ABCDEFGH?ref_=test"
    assert extract_asin(url) == "B0ABCDEFGH"
