//! `encode_title` (A-7) と `resolve_bind` (A-8)。

use feedgen_server::headers::encode_title;
use feedgen_server::listen::resolve_bind;

#[test]
fn ascii_title_is_unchanged() {
    assert_eq!(encode_title("Site Feed"), "Site Feed");
}

#[test]
fn japanese_is_percent_encoded_per_utf8_byte() {
    assert_eq!(encode_title("日本"), "%E6%97%A5%E6%9C%AC");
    assert_eq!(encode_title("A日B"), "A%E6%97%A5B");
}

#[test]
fn control_characters_are_removed() {
    assert_eq!(encode_title("a\r\nb\tc\0d\x7fe"), "abcde");
}

#[test]
fn percent_sign_itself_is_kept_as_is() {
    // 可視 ASCII はそのまま。受け手が二重に復号しない前提は、仕様に書かない。
    assert_eq!(encode_title("100%"), "100%");
}

#[test]
fn truncated_to_200_chars_before_encoding() {
    assert_eq!(encode_title(&"a".repeat(300)), "a".repeat(200));
    assert_eq!(encode_title(&"日".repeat(300)), "%E6%97%A5".repeat(200));
}

#[test]
fn output_is_always_a_valid_header_value() {
    let encoded = encode_title("悪い\u{1F600}タイトル\u{0}\n");
    assert!(
        encoded.bytes().all(|b| (0x20..0x7f).contains(&b)),
        "{encoded}"
    );
}

#[test]
fn bind_defaults() {
    assert_eq!(
        resolve_bind(None, None, None, None).unwrap().to_string(),
        "127.0.0.1:8000"
    );
}

#[test]
fn bind_precedence_arg_over_env_over_default() {
    let addr = resolve_bind(Some("0.0.0.0"), Some(9000), Some("10.0.0.1"), Some("7000")).unwrap();
    assert_eq!(addr.to_string(), "0.0.0.0:9000");
    let addr = resolve_bind(None, None, Some("10.0.0.1"), Some("7000")).unwrap();
    assert_eq!(addr.to_string(), "10.0.0.1:7000");
    let addr = resolve_bind(None, Some(9001), Some("10.0.0.1"), None).unwrap();
    assert_eq!(addr.to_string(), "10.0.0.1:9001");
}

#[test]
fn bind_ipv6_host() {
    let addr = resolve_bind(Some("::1"), Some(8080), None, None).unwrap();
    assert_eq!(addr.to_string(), "[::1]:8080");
}

#[test]
fn bind_rejects_invalid_values() {
    assert!(resolve_bind(Some("not a host"), None, None, None).is_err());
    assert!(resolve_bind(None, None, Some("bad host"), None).is_err());
    assert!(resolve_bind(None, None, None, Some("abc")).is_err());
    assert!(resolve_bind(None, None, None, Some("70000")).is_err());
}
