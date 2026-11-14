//! `resolve_admin` (docs/specs/admin.md M-1)。

use feedgen_server::admin::resolve_admin;

#[test]
fn disabled_by_default() {
    assert!(!resolve_admin(false, None));
}

#[test]
fn argument_enables_regardless_of_env() {
    for env in [None, Some(""), Some("0"), Some("false"), Some("1")] {
        assert!(resolve_admin(true, env), "{env:?}");
    }
}

#[test]
fn env_one_or_true_enables_case_insensitively() {
    for value in ["1", "true", "TRUE", "True", "tRuE"] {
        assert!(resolve_admin(false, Some(value)), "{value}");
    }
}

#[test]
fn other_env_values_do_not_enable() {
    for value in [
        "", "0", "false", "FALSE", "yes", "on", "2", " 1", "1 ", "true ",
    ] {
        assert!(!resolve_admin(false, Some(value)), "{value:?}");
    }
}
