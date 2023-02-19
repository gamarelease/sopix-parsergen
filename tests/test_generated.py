import os.path
import subprocess
import tempfile
import unittest

if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(sys.path[0]), 'src'))

from sopix import generate_parser, DOC_EXAMPLE

DEFAULT_SHELL = '/bin/sh'

R_SUCCESS = 0
R_ERROR = 1
R_USAGE = 2

INVALID = "invalid"
UNKNOWN_LONG = "unknown long"
UNKNOWN_SHORT = "unknown short"


def debug_output(*, v='', f='', n='Alice', o='', a=''):
    return """\
v = '{v}'
flag = '{f}'
name = '{n}'
only_long = '{o}'
$@ = ({a})
""".format(v=v, f=f, n=n, o=o, a=a)


class TestGeneratedParser(unittest.TestCase):
    _shell = DEFAULT_SHELL

    @classmethod
    def setUpClass(cls):
        cls._testdir = tempfile.TemporaryDirectory()
        cls._parser = os.path.join(cls._testdir.name, 'parser')
        parser_script = generate_parser(DOC_EXAMPLE, debug_print=True)
        with open(cls._parser, 'w') as file:
            file.write(parser_script)

    @classmethod
    def tearDownClass(cls):
        cls._testdir.cleanup()

    @classmethod
    def run_parser(cls, args):
        if isinstance(args, str):
            args = args.split(' ')
        cmd = [cls._shell, '-e', cls._parser] + args
        proc = subprocess.run(cmd, text=True, capture_output=True)
        return proc.returncode, proc.stdout, proc.stderr

    # Correct commands

    def assert_parser_success(self, args, expected_stderr="", **stdout_fields):
        rcode, stdout, stderr = self.run_parser(args)
        self.assertEqual(rcode, R_SUCCESS)
        self.assertEqual(stdout, debug_output(**stdout_fields))
        self.assertEqual(stderr, expected_stderr)

    def test_empty_command(self):
        args = ""
        self.assert_parser_success(args)

    def test_all_short(self):
        args = "-f -v -n Bob"
        self.assert_parser_success(args, v="true", f="true", n="Bob")

    def test_short_condensed(self):
        args = "-fvn Bob"
        self.assert_parser_success(args, v="true", f="true", n="Bob")

    def test_all_long(self):
        args = "--flag --name Bob"
        self.assert_parser_success(args, f="true", n="Bob")

    def test_long_equal(self):
        args = "--name=Bob"
        self.assert_parser_success(args, n="Bob")

    def test_force_positional(self):
        args = "-- -v --not-an-option"
        self.assert_parser_success(args, a="-v --not-an-option")

    def test_intermixed_positional(self):
        args = "spam -v eggs --name Kevin bacon -- without spam --not-an-option"
        self.assert_parser_success(
            args,
            v="true",
            n="Kevin",
            a="spam eggs bacon without spam --not-an-option",
        )

    def test_corner_case_positional(self):
        args = ["", "-"]
        self.assert_parser_success(args, a=" -")

    def test_equal_empty_value(self):
        args = "--name="
        self.assert_parser_success(args, n="")

    def test_double_dash_value(self):
        args = "--name=--"
        self.assert_parser_success(args, n="--")

    def test_repeated(self):
        args = "-vv -fn Bob --flag --name=Charlie"
        self.assert_parser_success(args, v="true", f="true", n="Charlie")

    # Incorrect commands

    def assert_parser_usage(self, args, usage_error_type, bad_opt=None, expected_stdout=""):
        if bad_opt is None:
            bad_opt = args[0] if isinstance(args, list) else args
        rcode, stdout, stderr = self.run_parser(args)
        self.assertEqual(rcode, R_USAGE)
        self.assertEqual(stdout, expected_stdout)
        expected_error = "{} option: '{}'".format(usage_error_type, bad_opt)
        self.assertIn(expected_error, stderr.splitlines()[0])

    def test_unknown_short(self):
        self.assert_parser_usage("-a", UNKNOWN_SHORT)
        self.assert_parser_usage("-A", UNKNOWN_SHORT)
        self.assert_parser_usage("-0", UNKNOWN_SHORT)
        self.assert_parser_usage("-vfa", UNKNOWN_SHORT, bad_opt="-a")

    def test_unknown_long(self):
        self.assert_parser_usage("--nam3", UNKNOWN_LONG)
        self.assert_parser_usage("--non-existent", UNKNOWN_LONG)
        self.assert_parser_usage("--bad=whatever", UNKNOWN_LONG, bad_opt="--bad")

    def test_invalid_short(self):
        self.assert_parser_usage("-?", INVALID)
        self.assert_parser_usage("-bad!", INVALID)
        self.assert_parser_usage("-ba-d", INVALID)
        self.assert_parser_usage("-bad-", INVALID)
        self.assert_parser_usage(["-n Lancelot"], INVALID)  # not split in two parts

    def test_invalid_long(self):
        self.assert_parser_usage("--a", INVALID)  # single character
        self.assert_parser_usage("--ALL-CAPS-NOT-ALLOWED", INVALID)
        self.assert_parser_usage("---", INVALID)
        self.assert_parser_usage("---too-many-dashes", INVALID)
        self.assert_parser_usage("--two--middle--dashes", INVALID)
        self.assert_parser_usage("--trailing-dash-", INVALID)
        self.assert_parser_usage(["--middle space"], INVALID)
        self.assert_parser_usage("--@#$%!-symbols", INVALID)
        self.assert_parser_usage("--BAD-option=indeed", INVALID, bad_opt="--BAD-option")
        self.assert_parser_usage("--=empty", INVALID)

    # Option argument checking

    def assert_parser_usage_arg(self, args, opt, expected_stdout=""):
        rcode, stdout, stderr = self.run_parser(args)
        self.assertEqual(rcode, R_USAGE)
        self.assertEqual(stdout, expected_stdout)
        self.assertIn('argument', stderr)
        self.assertIn("'%s'" % opt, stderr)

    def test_missing_argument(self):
        self.assert_parser_usage_arg("--name", opt="--name")
        self.assert_parser_usage_arg("--name -- Arthur", opt="--name")
        self.assert_parser_usage_arg("-n", opt="-n")
        self.assert_parser_usage_arg("-n --", opt="-n")
        self.assert_parser_usage_arg("-fnv", opt="-n")

    def test_no_argument(self):
        self.assert_parser_usage_arg("--flag=spam", opt="--flag")  # doesn't accept arguments


if __name__ == '__main__':
    if len(sys.argv) > 1:
        TestGeneratedParser._shell = sys.argv.pop()
    unittest.main()
