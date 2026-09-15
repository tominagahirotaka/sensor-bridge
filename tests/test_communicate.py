"""Tests for mylib/communicate.py: env_set value coercion and the PC<->board
wire-protocol parsing (key=value;key=value;...), including the split('=', 1)
regression that a real LIS3DH handshake broke earlier (its 'func' field's
lambda body contains 'x>=32768', which collides with a naive split('=') )."""
import mylib.communicate as comm


class TestCoerceEnvValue:
    def test_integer(self):
        assert comm._coerce_env_value("5") == 5

    def test_float(self):
        assert comm._coerce_env_value("0.4") == 0.4

    def test_tuple_of_ints_evaluates_as_python(self):
        assert comm._coerce_env_value("(0, 1, 2)") == (0, 1, 2)

    def test_plain_board_name_is_not_python_evaluable(self):
        # "SHT35" raises NameError under eval() (undefined name) -> falls
        # back to the raw string, not a crash.
        assert comm._coerce_env_value("SHT35") == "SHT35"

    def test_comma_separated_raw_strings_become_a_tuple(self):
        assert comm._coerce_env_value("a,b") == ("a", "b")

    def test_trailing_comma_numeric_value_evaluates_as_a_python_tuple_literal(self):
        # ".ini" convention: a single-element list ends with a comma ("20,")
        # so it round-trips as a tuple. For a numeric value this is valid
        # Python syntax on its own (a 1-tuple literal), so eval() succeeds
        # directly -- the NameError fallback below is never reached.
        assert comm._coerce_env_value("20,") == (20,)

    def test_trailing_comma_non_numeric_value_falls_back_to_string_tuple(self):
        # A non-numeric single value (e.g. a sensor_id like "wire0_0x50")
        # is not a valid Python literal, so eval() raises NameError and the
        # comma-fallback path produces a tuple of the raw string(s).
        assert comm._coerce_env_value("wire0_0x50,") == ("wire0_0x50",)

    def test_lambda_expression_with_comparison_operator(self):
        # The real LIS3DH 'func' field: a lambda whose body contains '>=',
        # evaluated as genuine Python (this is why ast.literal_eval can't be
        # used here -- lambdas aren't a literal).
        value = "[ (lambda x:(x-65536 if x>=32768 else x)*0.001,16, 'g') ]"
        result = comm._coerce_env_value(value)
        assert isinstance(result, list)
        fn, bits, unit = result[0]
        assert unit == "g" and bits == 16
        assert fn(100) == 100 * 0.001          # below threshold: unchanged
        assert fn(40000) == (40000 - 65536) * 0.001  # >=32768: wraps to signed


class TestWireProtocolSplitLimit:
    """dict([k.split('=', 1) for k in board_params.split(';')]) -- the exact
    expression used in connect_serial()/init_serial() to parse the board's
    response. Must not choke on a value that itself contains '='."""

    def test_split_with_limit_handles_embedded_equals_sign(self):
        # A miniature but faithful slice of a real LIS3DH handshake response.
        board_params = "odr=5;func=lambda x:x>=32768;fs=0"
        parsed = dict(k.split("=", 1) for k in board_params.split(";"))
        assert parsed == {
            "odr": "5",
            "func": "lambda x:x>=32768",
            "fs": "0",
        }

    def test_naive_split_without_limit_would_have_broken_this(self):
        # Regression guard: demonstrates *why* split('=', 1) is required --
        # the unlimited split('=') this codebase used to use produces a
        # 3-element list for the 'func' entry, which dict() rejects.
        board_params = "func=lambda x:x>=32768"
        naive_parts = board_params.split("=")
        assert len(naive_parts) == 3  # ['func', 'lambda x:x>', '32768']
        limited_parts = board_params.split("=", 1)
        assert len(limited_parts) == 2
