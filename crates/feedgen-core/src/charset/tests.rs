//! docs/specs/pipeline.md G-9 のテスト (RED)。表で総当たりする。

use super::decode_html;

/// 「日本語」の Shift_JIS と EUC-JP のバイト列。
const SJIS: &[u8] = &[0x93, 0xFA, 0x96, 0x7B, 0x8C, 0xEA];
const EUC_JP: &[u8] = &[0xC6, 0xFC, 0xCB, 0xDC, 0xB8, 0xEC];

fn with(prefix: &str, tail: &[u8]) -> Vec<u8> {
    let mut body = prefix.as_bytes().to_vec();
    body.extend_from_slice(tail);
    body
}

#[test]
fn utf8_is_the_default() {
    assert_eq!(decode_html("日本語".as_bytes(), ""), "日本語");
    assert_eq!(decode_html("日本語".as_bytes(), "text/html"), "日本語");
    assert_eq!(decode_html(b"", "text/html"), "");
}

#[test]
fn invalid_bytes_become_replacement_characters_instead_of_failing() {
    assert_eq!(decode_html(&[0x66, 0xFF, 0x6F], ""), "f\u{FFFD}o");
}

#[test]
fn bom_wins_over_the_header_and_the_meta() {
    // UTF-8 の BOM は、Content-Type の Shift_JIS より優先し、結果から取り除く
    let utf8 = with("\u{FEFF}日本語", b"");
    assert_eq!(decode_html(&utf8, "text/html; charset=Shift_JIS"), "日本語");

    // UTF-16LE の BOM (FF FE) + 「日本」
    let utf16 = [0xFF, 0xFE, 0xE5, 0x65, 0x2C, 0x67];
    assert_eq!(decode_html(&utf16, "text/html; charset=utf-8"), "日本");
}

#[test]
fn charset_in_the_content_type_is_used_with_any_label_and_case() {
    for label in [
        "Shift_JIS",
        "shift_jis",
        "SHIFT_JIS",
        "x-sjis",
        "windows-31j",
        "sjis",
    ] {
        let content_type = format!("text/html; charset={label}");
        assert_eq!(decode_html(SJIS, &content_type), "日本語", "{label}");
    }
    // 引用符、パラメータ名の大文字小文字、ほかのパラメータ
    assert_eq!(
        decode_html(SJIS, r#"text/html; charset="Shift_JIS""#),
        "日本語"
    );
    assert_eq!(
        decode_html(EUC_JP, "text/html; Charset=EUC-JP; x=y"),
        "日本語"
    );
    assert_eq!(
        decode_html(EUC_JP, "text/html;x=y;charset=euc-jp"),
        "日本語"
    );
}

#[test]
fn content_type_wins_over_the_meta() {
    let body = with(r#"<meta charset="utf-8">"#, SJIS);
    assert_eq!(
        decode_html(&body, "text/html; charset=Shift_JIS"),
        r#"<meta charset="utf-8">日本語"#
    );
}

#[test]
fn meta_charset_is_used_when_the_header_has_none() {
    let metas = [
        r#"<meta charset="Shift_JIS">"#,
        "<meta charset=Shift_JIS>",
        "<meta charset='shift_jis'>",
        r#"<meta http-equiv="Content-Type" content="text/html; charset=Shift_JIS">"#,
        r#"<META CHARSET="SHIFT_JIS">"#,
        r#"<html><head><meta name="viewport" content="x"><meta charset="x-sjis"></head>"#,
    ];
    for meta in metas {
        let decoded = decode_html(&with(meta, SJIS), "text/html");
        assert!(decoded.ends_with("日本語"), "{meta}: {decoded}");
    }
}

#[test]
fn meta_after_the_first_1024_bytes_is_ignored() {
    let padding = " ".repeat(1100);
    let body = with(&format!(r#"{padding}<meta charset="Shift_JIS">"#), SJIS);
    let decoded = decode_html(&body, "text/html");
    assert!(!decoded.contains("日本語"), "{decoded}");
    assert!(
        decoded.contains('\u{FFFD}'),
        "UTF-8 として読み、不正なバイトは置き換える"
    );
}

#[test]
fn unknown_labels_are_skipped_and_fall_back_in_order() {
    // Content-Type の charset が未知 → meta に進む
    let body = with(r#"<meta charset="Shift_JIS">"#, SJIS);
    assert!(decode_html(&body, "text/html; charset=x-unknown").ends_with("日本語"));
    // meta の charset も未知 → UTF-8
    assert_eq!(
        decode_html("日本語".as_bytes(), "text/html; charset=x-unknown"),
        "日本語"
    );
    let unknown_meta = with(r#"<meta charset="x-unknown">日本語"#, b"");
    assert!(decode_html(&unknown_meta, "").ends_with("日本語"));
}

#[test]
fn labels_that_encoding_rs_maps_to_replacement_are_treated_as_unknown() {
    // iso-2022-kr や hz-gb-2312 は replacement。使うと、本文全体が U+FFFD 1 文字になる。
    let meta = decode_html(
        br#"<meta charset="iso-2022-kr"><h2>hello</h2>"#,
        "text/html",
    );
    assert!(meta.contains("hello"), "{meta}");
    assert_eq!(
        decode_html(b"hello", "text/html; charset=hz-gb-2312"),
        "hello"
    );
    // 未知として扱うので、次の手段 (meta) に進む
    let body = with(r#"<meta charset="Shift_JIS">"#, SJIS);
    assert!(decode_html(&body, "text/html; charset=iso-2022-kr").ends_with("日本語"));
}

#[test]
fn a_meta_pointing_at_utf16_is_read_as_utf8() {
    // ASCII 互換の本文を UTF-16 として読むと文字化けする。meta が UTF-16 を指すときは UTF-8 とみなす。
    for label in ["utf-16", "utf-16le", "utf-16be"] {
        let body = format!(r#"<meta charset="{label}">日本語"#);
        let decoded = decode_html(body.as_bytes(), "text/html");
        assert!(decoded.ends_with("日本語"), "{label}: {decoded}");
    }
}

#[test]
fn meta_charset_is_read_only_as_an_attribute_of_a_real_meta_tag() {
    // 拾わないもの。Shift_JIS の本文を、誤って Shift_JIS として読めば日本語になるが、
    // 正しく無視すれば UTF-8 として読み、日本語にならない。
    let ignored = [
        r#"<metadata charset="shift_jis">"#,
        r#"<!-- <meta charset="shift_jis"> -->"#,
        r#"<meta name="description" content="fix charset=shift_jis here">"#,
        r#"<meta data-charset="shift_jis">"#,
    ];
    for head in ignored {
        let decoded = decode_html(&with(head, SJIS), "text/html");
        assert!(!decoded.contains("日本語"), "{head}: {decoded}");
    }
    // 本物の charset 属性は、別の属性名や、未知のラベルや、コメントの後ろにあっても拾う
    let found = [
        r#"<meta data-charset="utf-8" charset="shift_jis">"#,
        r#"<meta data-charset="foo" charset="shift_jis">"#,
        r#"<meta charset="x-unknown"><meta charset="shift_jis">"#,
        r#"<!-- c --><meta charset="shift_jis">"#,
    ];
    for head in found {
        let decoded = decode_html(&with(head, SJIS), "text/html");
        assert!(decoded.ends_with("日本語"), "{head}: {decoded}");
    }
}

#[test]
fn single_quotes_around_the_header_charset_are_removed() {
    assert_eq!(
        decode_html(SJIS, "text/html; charset='Shift_JIS'"),
        "日本語"
    );
}

#[test]
fn malformed_meta_fragments_never_panic_or_loop() {
    // 決まった疑似乱数 (LCG) で、`<meta` の周辺の断片を組み合わせた入力を作り、panic と無限ループがないことを確かめる。
    let pieces: [&[u8]; 18] = [
        b"<",
        b">",
        b"<meta",
        b"<META ",
        b"charset",
        b"=",
        b"\"",
        b"'",
        b" ",
        b"/",
        b"<!--",
        b"-->",
        b"http-equiv",
        b"content",
        b"shift_jis",
        b";",
        b"\xFF\xFE",
        b"\xE3\x81",
    ];
    let mut state: u64 = 0x2545_F491_4F6C_DD1D;
    let mut next = move || {
        state = state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        (state >> 33) as usize
    };
    for _ in 0..5000 {
        let mut body = Vec::new();
        for _ in 0..(next() % 40) {
            body.extend_from_slice(pieces[next() % pieces.len()]);
        }
        if next() % 4 == 0 {
            body.extend(std::iter::repeat_n(b'x', next() % 2000)); // 1024 バイトの境界をまたぐ
        }
        let content_type = [
            "",
            "text/html",
            "text/html; charset=",
            "text/html; charset='",
        ][next() % 4];
        let _ = decode_html(&body, content_type);
    }
}
