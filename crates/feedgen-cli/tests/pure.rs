//! 引数・設定・URL 生成 (docs/specs/api.md C-1、C-2、C-4)。

use clap::Parser;
use feedgen_cli::Args;
use feedgen_cli::config::{FileConfig, load_config, parse_config};
use feedgen_cli::settings::resolve;
use feedgen_cli::url_gen::{UrlParams, generate_api_url};

fn args(extra: &[&str]) -> Args {
    let mut all = vec!["feedgen", "https://example.com/"];
    all.extend_from_slice(extra);
    Args::try_parse_from(all).unwrap()
}

// --- 引数 ---

#[test]
fn args_parse_all_options() {
    let parsed = args(&[
        "-o",
        "out.xml",
        "-c",
        "c.yaml",
        "--max-items",
        "7",
        "--user-agent",
        "ua",
        "--use-feed",
        "--feed-first",
        "--generate-url",
        "--api-host",
        "api.example.com",
    ]);
    assert_eq!(parsed.url, "https://example.com/");
    assert_eq!(parsed.output.unwrap().to_str(), Some("out.xml"));
    assert_eq!(parsed.config.unwrap().to_str(), Some("c.yaml"));
    assert_eq!(parsed.max_items, Some(7));
    assert_eq!(parsed.user_agent.as_deref(), Some("ua"));
    assert!(parsed.use_feed && parsed.feed_first && parsed.generate_url);
    assert_eq!(parsed.api_host.as_deref(), Some("api.example.com"));
}

#[test]
fn args_reject_out_of_range_and_unsupported_options() {
    let base = ["feedgen", "https://example.com/"];
    for bad in [
        vec!["--max-items", "0"],
        vec!["--max-items", "101"],
        vec!["--translate"],
        vec!["--decode-google-news"],
        vec!["--google-news-interval", "1"],
    ] {
        let mut all = base.to_vec();
        all.extend(bad.clone());
        assert!(Args::try_parse_from(all).is_err(), "{bad:?}");
    }
    assert!(Args::try_parse_from(["feedgen"]).is_err(), "URL は必須");
}

// --- 設定ファイル ---

#[test]
fn config_reads_known_keys() {
    let loaded =
        parse_config("max_items: 5\nuser_agent: ua/1\napi_base_url: https://api.example.com\n")
            .unwrap();
    assert_eq!(
        loaded.config,
        FileConfig {
            max_items: Some(5),
            user_agent: Some("ua/1".to_string()),
            api_base_url: Some("https://api.example.com".to_string()),
        }
    );
    assert!(loaded.warnings.is_empty());
}

#[test]
fn config_unknown_keys_warn_but_do_not_fail() {
    let loaded =
        parse_config("max_items: 5\ninstagram:\n  max_post: 3\nyoutube_api_key: x\n").unwrap();
    assert_eq!(loaded.config.max_items, Some(5));
    assert_eq!(loaded.warnings.len(), 2);
    let joined = loaded.warnings.join("\n");
    assert!(joined.contains("instagram") && joined.contains("youtube_api_key"));
}

#[test]
fn config_empty_file_is_empty_config() {
    let loaded = parse_config("").unwrap();
    assert_eq!(loaded.config, FileConfig::default());
}

#[test]
fn config_invalid_yaml_or_wrong_type_is_error() {
    assert!(parse_config("max_items: [unclosed").is_err());
    assert!(parse_config("max_items: many\n").is_err());
}

#[test]
fn load_config_explicit_missing_is_error() {
    let dir = tempfile::tempdir().unwrap();
    assert!(load_config(Some(&dir.path().join("none.yaml")), dir.path()).is_err());
}

#[test]
fn load_config_defaults_to_cwd_config_yaml_and_tolerates_absence() {
    let dir = tempfile::tempdir().unwrap();
    assert_eq!(
        load_config(None, dir.path()).unwrap().config,
        FileConfig::default()
    );
    std::fs::write(dir.path().join("config.yaml"), "max_items: 9\n").unwrap();
    assert_eq!(
        load_config(None, dir.path()).unwrap().config.max_items,
        Some(9)
    );
}

#[test]
fn load_config_does_not_search_parent_directories() {
    let dir = tempfile::tempdir().unwrap();
    std::fs::write(dir.path().join("config.yaml"), "max_items: 9\n").unwrap();
    let child = dir.path().join("child");
    std::fs::create_dir(&child).unwrap();
    assert_eq!(load_config(None, &child).unwrap().config.max_items, None);
}

// --- 統合 ---

#[test]
fn settings_precedence_args_over_file_over_default() {
    let file = FileConfig {
        max_items: Some(30),
        user_agent: Some("file-ua".to_string()),
        api_base_url: Some("https://file.example".to_string()),
    };
    let from_file = resolve(&args(&[]), &file).unwrap();
    assert_eq!(from_file.options.max_items, 30);
    assert_eq!(from_file.options.user_agent, "file-ua");
    assert_eq!(from_file.api_host.as_deref(), Some("https://file.example"));

    let from_args = resolve(
        &args(&[
            "--max-items",
            "3",
            "--user-agent",
            "arg-ua",
            "--api-host",
            "arg.example",
        ]),
        &file,
    )
    .unwrap();
    assert_eq!(from_args.options.max_items, 3);
    assert_eq!(from_args.options.user_agent, "arg-ua");
    assert_eq!(from_args.api_host.as_deref(), Some("arg.example"));

    let defaults = resolve(&args(&[]), &FileConfig::default()).unwrap();
    assert_eq!(defaults.options.max_items, 20);
    assert_eq!(defaults.options.user_agent, "feedgen/1.0");
    assert!(defaults.api_host.is_none());
}

#[test]
fn settings_flags_pass_through() {
    let settings = resolve(
        &args(&["--use-feed", "--feed-first"]),
        &FileConfig::default(),
    )
    .unwrap();
    assert!(settings.options.use_feed && settings.options.feed_first);
}

#[test]
fn settings_validate_values_from_the_file_too() {
    let bad_ua = FileConfig {
        user_agent: Some("日本語".to_string()),
        ..Default::default()
    };
    assert!(resolve(&args(&[]), &bad_ua).is_err());
    for bad in [0, 101] {
        let file = FileConfig {
            max_items: Some(bad),
            ..Default::default()
        };
        assert!(resolve(&args(&[]), &file).is_err(), "{bad}");
    }
    assert!(resolve(&args(&["--user-agent", "a\nb"]), &FileConfig::default()).is_err());
}

// --- URL 生成 (Python の URLGenerator と同じ形) ---

#[test]
fn url_minimal() {
    assert_eq!(
        generate_api_url(
            "https://api.example.com",
            "https://example.com/",
            &UrlParams::default()
        )
        .unwrap(),
        "https://api.example.com/feed?url=https%3A%2F%2Fexample.com%2F"
    );
}

#[test]
fn url_host_is_normalized() {
    let expect = "https://api.example.com/feed?url=x";
    for host in [
        "api.example.com",
        "https://api.example.com",
        "https://api.example.com/",
        "https://api.example.com///",
    ] {
        assert_eq!(
            generate_api_url(host, "x", &UrlParams::default()).unwrap(),
            expect,
            "{host}"
        );
    }
    assert_eq!(
        generate_api_url("http://localhost:8000", "x", &UrlParams::default()).unwrap(),
        "http://localhost:8000/feed?url=x"
    );
}

#[test]
fn url_invalid_host_is_error() {
    for host in ["", "   ", "https://", "https:///path"] {
        assert!(
            generate_api_url(host, "x", &UrlParams::default()).is_err(),
            "{host:?}"
        );
    }
}

#[test]
fn url_param_order_and_encoding_match_python_urlencode() {
    let params = UrlParams {
        max_items: Some(5),
        use_feed: true,
        feed_first: true,
        user_agent: Some("my agent/1.0 ~x".to_string()),
    };
    assert_eq!(
        generate_api_url("https://a.example", "https://e.com/p?q=1&r=日", &params).unwrap(),
        "https://a.example/feed?url=https%3A%2F%2Fe.com%2Fp%3Fq%3D1%26r%3D%E6%97%A5\
         &max_items=5&use_feed=true&feed_first=true&user_agent=my+agent%2F1.0+~x"
    );
}

#[test]
fn url_false_flags_are_omitted() {
    let params = UrlParams {
        max_items: Some(1),
        ..Default::default()
    };
    assert_eq!(
        generate_api_url("https://a.example", "x", &params).unwrap(),
        "https://a.example/feed?url=x&max_items=1"
    );
}
