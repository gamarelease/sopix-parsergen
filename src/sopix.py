#!/usr/bin/env python3

import re
import string
import textwrap

import docopt


PARSER_TEMPLATE = \
r"""${__SHEBANG__}

CMD=${__CMD__}${__STRIP_EXT__}
USAGE="${__USAGE_MSG__}"${__HELP__}

# Convenience functions
${__HELPERS__}

# Parse command-line options${__RANDOM_EOL__}
set -- "$@" "${EOL:=$(printf '\1\3\3\7')}"  # end-of-line-marker${__AUX_VARS__}
while [ "$1" != "$EOL" ]; do
	opt="$1"; shift
	case "$opt" in

		#EDIT HERE: defined options
		${__CASES__}
		-h | --help ) ${__ASSERT_NOARG__}printf "%s\n" "${__HELP_VAR__}"; exit 0;;

		# parse remaining arguments as positional
		--) while [ "$1" != "$EOL" ]; do set -- "$@" "$1"; shift; done;;
		# long options: convert "--opt=arg" to "--opt" "arg"
		--[!=]*=*) ${__LONG_OPTION__}
		# invalid or unknown options
		${__BAD_OPTION__}
		# short options: convert "-abc" to "-a" "-bc"
		-?*) ${__SHORT_OPTION__}
		# positional argument, rotate to the end
		*) set -- "$@" "$opt";;
	esac
done; shift  # $EOL

# Set/unset variables${__DEFAULTS__}
unset ${__UNSET_VARS__}
unset -f ${__UNSET_FUNCS__}

${__DEBUG_PRINT__}
"""

HELPERS_FULL = \
r"""assert_arg () {
	if [ "$1" = "$EOL" ] ||
			{ [ "$1" = '--' ] && [ "$2" != "--" ]; } ||
			{ [ "${3%?}" = '-' ] && [ "$3" = "$4" ]; }
		then exit_usage "missing argument for option '$3'"
	fi
}
assert_noarg () {  # for long options only
	if [ "$1" = "$2" ]
		then exit_usage "option '$2' doesn't accept arguments"
	fi
}
exit_error () { printf >&2 "%s:  ERROR: %s\n" "$CMD" "$1"; exit "${2-1}"; }  # default exit status: 1
exit_usage () { printf >&2 "%s:  %s\n%s\n" "$CMD" "$1" "$USAGE"; exit 2; }"""

HELPERS_MINIMAL = \
r"""exit2 () { printf >&2 "%s:  %s: '%s'\n%s\n" "$CMD" "$1" "$2" "$USAGE"; exit 2; }
check () { { [ "$1" != "$EOL" ] && [ "$1" != '--' ]; } || exit2 "missing argument" "$2"; }"""

BAD_OPTION_FULL = \
r"""--*[!-a-z0-9]* | --*--*) exit_usage "invalid option: '$opt'";;
		--[a-z0-9]*[a-z0-9])     exit_usage "unknown long option: '$opt'";;
		-*[!A-Za-z0-9]*)         exit_usage "invalid option: '$opt'";;
		-[A-Za-z0-9])            exit_usage "unknown short option: '$opt'";;"""

BAD_OPTION_MINIMAL = r"""-[A-Za-z0-9] | -*[!A-Za-z0-9]*) exit2 "invalid option" "$opt";;"""

RANDOM_EOL = """
if [ -c /dev/random ]  # try to obtain a random string
	then EOL=$(dd 2>/dev/null if=/dev/random bs=8 count=1 | od -t x8 -A n)
fi  # fall back to a fixed *binary* string if it fails"""

DEBUG_PRINT = \
r"""# Print collected options and arguments
${{__DEBUG_IF__}}for var in {}
	do eval "printf \"%s = '%s'\n\" '$var' \"\${{opt_$var-}}\""
done && printf "\$@ = (%s)\n" "$*"
"""

SNIPPET = {
    'shebang': '''/bin/sh -eu''',
    'cmd': '''"${0##*/}"''',
    'strip_ext': '''; [ "${CMD%.*}" ] && CMD="${CMD%.*}"  # "bin/script.sh" -> "script"''',
    'help': '''\nHELP_MSG="${__HELP_MSG__}"''',
    'helpers': {False: HELPERS_FULL, True: HELPERS_MINIMAL},
    'random_eol': RANDOM_EOL,
    'aux_vars': {
        False: '''\nlong=; short=; val=  # last long/short option/value split\n''',
        True: '',
    },
    'assert_arg': {
        False: '''assert_arg "$1" "$val" "$opt" "$short"; opt_%s="$1"; shift;;''',
        True: '''check "$1" "$opt"; opt_%s="$1"; shift;;''',
    },
    'assert_noarg': {
        False: '''assert_noarg "$opt" "$long"; ''',
        True: '',
    },
    'long_option': {
        False: '''long="${opt%%=*}"; val="${opt#*=}"; set -- "$long" "$val" "$@";;''',
        True: '''set -- "${opt%%=*}" "${opt#*=}" "$@";;''',
    },
    'short_option': {
        False: '''other="${opt#-?}"; short="${opt%$other}"; set -- "$short" "-${other}" "$@";;''',
        True: '''other="${opt#-?}"; set -- "${opt%$other}" "-${other}" "$@";;''',
    },
    'bad_option': {False: BAD_OPTION_FULL, True: BAD_OPTION_MINIMAL},
    'unset_vars': {
        False: '''EOL HELP long opt other short val # CMD USAGE''',
        True: '''CMD EOL USAGE opt other''',
    },
    'unset_funcs': {
        False: '''assert_arg assert_noarg # exit_error exit_usage''',
        True: '''check exit2''',
    },
    'debug_if': '''[ "${SOPIX_DEBUG-}" ] && ''',
    'debug_print': DEBUG_PRINT,
}


def generate_parser(docstring,
                    minimal=False,
                    strip_comments=False,
                    expand_tabs=4,
                    shebang="/bin/sh -eu",
                    command=None,
                    keep_command_ext=False,
                    random_eol=False,
                    debug_print=None,
                    ):

    snippets = {}
    parsed_cmd, usage_msg, help_msg, options = _parse_docstring(docstring)

    # Shebang
    if shebang:
        if '\n' in shebang or len(shebang.split()) > 2:
            raise Exception("invalid shebang string: %r" % shebang)
        elif not shebang.startswith('#!'):
            shebang = "#!" + shebang.strip()
    snippets['__SHEBANG__'] = shebang

    # Command name
    resolved_cmd = command or parsed_cmd 
    snippets['__CMD__'] = resolved_cmd or SNIPPET['cmd']
    snippets['__STRIP_EXT__'] = "" if (keep_command_ext or parsed_cmd) else SNIPPET['strip_ext']

    # Usage and help messages
    if resolved_cmd:
        usage_msg = re.sub(r'^(usage:\s+)\S+', '\g<1>$CMD', usage_msg, count=1, flags=re.IGNORECASE)
    snippets['__USAGE_MSG__'] = usage_msg
    if help_msg.strip() == '$USAGE':
        snippets['__HELP__'] = ""
        snippets['__HELP_VAR__'] = "$USAGE"
    else:
        snippets['__HELP__'] = SNIPPET['help']
        snippets['__HELP_MSG__'] = help_msg
        snippets['__HELP_VAR__'] = "$HELP_MSG"

    # Helpers and auxiliary variables
    snippets['__HELPERS__'] = SNIPPET['helpers'][minimal]
    snippets['__AUX_VARS__'] = SNIPPET['aux_vars'][minimal]

    # EOL marker
    snippets['__RANDOM_EOL__'] = SNIPPET['random_eol'] if random_eol else ""

    # Options
    cases = []
    name_default = []
    max_len = max((len(o.long or '') for o in options), default=0)
    for opt in options:
        opt_name = (opt.long or opt.short).lstrip("-").replace("-", "_")
        line = opt.short or "  "
        line += " | " if opt.short and opt.long else "   " if max_len else ""
        line += "{:{width}} ) ".format(opt.long or "", width=max_len)
        if opt.argcount:
            line += SNIPPET['assert_arg'][minimal]
            default_value = '' if opt.value is None else '"%s"' % opt.value.replace('"', r'\"')
        elif opt_name == 'help':
            continue
        else:
            if opt.long:
                line += SNIPPET['assert_noarg'][minimal]
            line += 'opt_%s="true";;'
            default_value = ''
        cases.append(line % opt_name)
        name_default.append((opt_name, default_value))
        # print(f"{line = }")
    snippets['__CASES__'] = textwrap.indent("\n".join(cases), 2 * "\t").lstrip("\t")
    snippets['__ASSERT_NOARG__'] = SNIPPET['assert_noarg'][minimal]
    # print(f"{cases = }\n")

    # Invalid options patterns/messages
    snippets['__LONG_OPTION__'] = SNIPPET['long_option'][minimal]
    snippets['__SHORT_OPTION__'] = SNIPPET['short_option'][minimal]
    snippets['__BAD_OPTION__'] = SNIPPET['bad_option'][minimal]

    # Defaults
    defaults = '\n: "%s"' % '" "'.join('${opt_%s=%s}' % n_d for n_d in name_default)
    snippets['__DEFAULTS__'] = "" if minimal else defaults
    # print(f"{defaults = }\n")

    # Unset
    snippets['__UNSET_VARS__'] = SNIPPET['unset_vars'][minimal]
    snippets['__UNSET_FUNCS__'] = SNIPPET['unset_funcs'][minimal]

    # Debug print
    if debug_print is False:
        printf = ""
    else:
        printf = SNIPPET['debug_print'].format(" ".join(n for n, d in name_default))
    snippets['__DEBUG_IF__'] = SNIPPET['debug_if'] if debug_print is None else ""
    snippets['__DEBUG_PRINT__'] = printf

    # Generate parser
    parser = string.Template(PARSER_TEMPLATE)
    # NOTE: substitute first snippets that are recursive or have identation
    early_snippets = ('__HELP__', '__CASES__', '__HELPERS__', '__RANDOM_EOL__', '__BAD_OPTION__', '__DEBUG_PRINT__')
    parser = parser.safe_substitute(**{k: v for k, v in snippets.items() if k in early_snippets})
    if expand_tabs > 0:
        parser = parser.replace("\t", expand_tabs * " ")
    parser = string.Template(parser).safe_substitute(**snippets)
    if strip_comments:
        parser = re.sub('^[\t ]*# [^A-Z].+\n', '', parser, flags=re.MULTILINE)
        parser = re.sub('  +# .+', '', parser)

    return parser.strip() + "\n"


def _parse_docstring(docstring):
    docopt_doc = docstring
    parsed_cmd = None
    usage_msg = None

    usage_sections = docopt.parse_section('usage:', docopt_doc)
    if len(usage_sections) > 1:
        raise docopt.DocoptLanguageError("""More than one "usage:" (case-insensitive).""")

    # Add "options:" header if it's not present
    if not docopt.parse_section('options:', docopt_doc):
        docopt_doc = re.sub('^[ \t]+-', 'options:\n\\g<0>', docopt_doc, count=1, flags=re.MULTILINE)

    # Add placeholder usage section if it's not present
    placeholder_usage = "Usage:  $CMD [options] [ARGS...]"
    if not usage_sections:
        docopt_doc = placeholder_usage + "\n\n" + docopt_doc
    # Or extract command name from usage section
    else:
        usage_msg = usage_sections[0]
        parsed_cmd = re.search(r'usage:\s+(\S+)', usage_msg, re.IGNORECASE).group(1)
        if parsed_cmd == '$CMD':
            parsed_cmd = None
    # print(f'docopt_doc =\n"""\n{docopt_doc}\n"""')

    # Parse usage patterns
    formal = docopt.formal_usage(usage_msg or placeholder_usage)
    defaults = docopt.parse_defaults(docopt_doc)
    pattern = docopt.parse_pattern(formal, defaults)
    options = pattern.flat(docopt.Option)
    # print(f"{formal = }\n{defaults = }\n{pattern = }\n{options = }\n")

    # Create usage section from options if it's missing
    if usage_msg is None:
        usage_msg = []
        short_flags = {o for o in defaults if o.short and not o.argcount}
        if short_flags:
            usage_msg.append("-" + "".join(sorted(f.short[-1] for f in short_flags)))
        for opt in defaults:
            if opt in short_flags:
                continue
            s = opt.short or opt.long
            if opt.argcount:
                s += "=ARG" if s.startswith('--') else " ARG"
            usage_msg.append(s)
        usage_msg = "Usage:  $CMD [%s] [ARGS...]" % "] [".join(usage_msg)
        help_msg = "$USAGE\n\n" + docstring.strip()
    else:
        help_msg = docstring.replace(usage_msg, "$USAGE").strip()
    # print(f"{usage_msg = }\n")

    options = set(options)
    options.update(defaults)
    options = sorted(options, key=lambda o: (o.long or '', o.short or ''))

    return parsed_cmd, usage_msg, help_msg, options


# Wrapper script

doc = """SOPIX: Simple Option Parser In POSIX

Generate an option parser in pure POSIX shell code for bash, dash, ksh, zsh, etc.

Usage:  sopix [-msrk] [-t NUM] [-b STRING] [-c CMD] [-d | -D] [INPUT]
        sopix (--example | --full-example)
        sopix (-h | --help | --version)

Global options:
  -m, --minimal                 minimalistic version (implies -s)
  -s, --strip-comments          don't inlude comments from generated code
  -t NUM, --expand-tabs=NUM     number of indentation spaces (-1 means "keep tabs") [default: {t}]

More options:
  -b STRING, --shebang=STRING   shebang string (an empty string disables it) [default: {b}]
  -c CMD, --command=CMD         use CMD as a hardcoded command name (implies -k)
  -k, --keep-command-ext        keep the command name file extension in the usage message
  -r, --random-eol              use runtime-generated random string for "end-of-loop" marker
  -d, --debug-print             leave debug printing code unconditional
  -D, --no-debug-print          don't include debug printing code

Authors:
  leogama @ github
"""

DOC_EXAMPLE = """\
This is brief description of what the program does.

  -h, --help            show this message
  -f, --flag            do stuff differently
  -n TEXT, --name=TEXT  use TEXT as name [default: Alice]
  --only-long           option without short version
  -v                    verbose mode
"""


if __name__ == '__main__':
    import sys
    import inspect
    from contextlib import closing

    par = inspect.signature(generate_parser).parameters
    doc = doc.format(t=par['expand_tabs'].default, b=par['shebang'].default)
    arg = docopt.docopt(doc, version="0.1.0").items()
    arg = {k.lstrip('-').replace('-', '_'): v for k, v in arg}

    # Validate options
    try:
        arg['expand_tabs'] = int(arg['expand_tabs'])
    except ValueError:
        print("sipox:  ERROR: the option '--expand-tabs' expects an integer value", file=sys.stderr)
        sys.exit(2)

    # Coupled options
    if arg['example']:
        arg['minimal'] = True
        arg['shebang'] = ""
        arg['keep_command_ext'] = True
    arg['strip_comments'] |= arg['minimal']
    arg['keep_command_ext'] |= (arg['command'] is not None)

    # Input
    if arg['example'] or arg['full_example']:
        arg['debug_print'] = True
        docstring = DOC_EXAMPLE
    else:
        input_file = open(arg['INPUT']) if arg['INPUT'] is not None else sys.stdin
        with closing(input_file) as file:
            docstring = file.read()

    # Output
    parser = generate_parser(
        docstring,
        arg['minimal'],
        arg['strip_comments'],
        arg['expand_tabs'],
        arg['shebang'],
        arg['command'],
        arg['keep_command_ext'],
        arg['random_eol'],
        arg['debug_print'] or (False if arg['no_debug_print'] else None)
    )
    print(parser, end="")
