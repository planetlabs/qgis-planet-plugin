def test_import_planet():
    try:
        import planet  # noqa: F401

        assert True
    except ImportError:
        assert False
