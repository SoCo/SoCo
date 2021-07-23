"""Tests for the utils module."""


from soco.utils import deprecated


# Deprecation decorator


def test_deprecation(recwarn):
    @deprecated("0.7")
    def dummy(args):
        """My docs."""
        pass

    @deprecated("0.8", "better_function", "0.12")
    def dummy2(args):
        """My docs."""
        pass

    assert dummy.__doc__ == "My docs.\n\n  .. deprecated:: 0.7\n"
    assert (
        dummy2.__doc__ == "My docs.\n\n  .. deprecated:: 0.8\n\n"
        "     Will be removed in version 0.12.\n"
        "     Use `better_function` instead."
    )
    dummy(3)
    w = recwarn.pop()
    assert str(w.message) == "Call to deprecated function dummy."
    dummy2(4)
    w = recwarn.pop()
    assert (
        str(w.message) == "Call to deprecated function dummy2. Will be "
        "removed in version 0.12. Use "
        "better_function instead."
    )
    assert w.filename
    assert w.lineno
