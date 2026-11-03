//! `validate_user_agent` (docs/specs/api.md A-2)。

use feedgen_core::generator::validate_user_agent;

#[test]
fn accepts_visible_ascii_with_spaces() {
    assert!(validate_user_agent("feedgen-api/1.0").is_ok());
    assert!(validate_user_agent("Mozilla/5.0 (X11; Linux) ~!@#").is_ok());
}

#[test]
fn length_boundaries() {
    assert!(validate_user_agent("a").is_ok());
    assert!(validate_user_agent(&"a".repeat(256)).is_ok());
    assert!(validate_user_agent("").is_err());
    assert!(validate_user_agent(&"a".repeat(257)).is_err());
}

#[test]
fn rejects_control_and_non_ascii() {
    for bad in [
        "a\nb",
        "a\rb",
        "a\0b",
        "a\tb",
        "a\x7fb",
        "日本語",
        "caf\u{e9}",
    ] {
        assert!(validate_user_agent(bad).is_err(), "{bad:?}");
    }
}
