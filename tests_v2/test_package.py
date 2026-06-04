def test_package_import_and_version():
    import deep6v2

    assert isinstance(deep6v2.__version__, str)
    assert deep6v2.__version__.strip()
