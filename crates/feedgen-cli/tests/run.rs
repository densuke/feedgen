//! `run` (docs/specs/api.md C-1、C-3、C-4)。通信せず、偽の `FeedSource` を差し込む。

use std::sync::Mutex;

use chrono::{DateTime, FixedOffset};
use clap::Parser;
use feedgen_cli::Args;
use feedgen_cli::run::{FeedSource, run};
use feedgen_core::detector::{FeedInfo, FeedKind};
use feedgen_core::generator::{GenerateOptions, Outcome};
use feedgen_core::models::RssFeed;
use feedgen_core::{FeedError, Result};

struct Fake {
    make: Box<dyn Fn() -> Result<Outcome>>,
    seen: Mutex<Vec<(String, GenerateOptions)>>,
}

impl Fake {
    fn new(make: impl Fn() -> Result<Outcome> + 'static) -> Self {
        Self {
            make: Box::new(make),
            seen: Mutex::new(Vec::new()),
        }
    }
}

impl FeedSource for Fake {
    async fn generate(
        &self,
        url: &str,
        options: &GenerateOptions,
        _now: DateTime<FixedOffset>,
    ) -> Result<Outcome> {
        self.seen
            .lock()
            .unwrap()
            .push((url.to_string(), options.clone()));
        (self.make)()
    }
}

fn now() -> DateTime<FixedOffset> {
    DateTime::parse_from_rfc3339("2026-11-03T12:00:00+00:00").unwrap()
}

fn feed(detected: Vec<FeedInfo>) -> Result<Outcome> {
    Ok(Outcome::Generated {
        feed: RssFeed {
            title: "タイトル".to_string(),
            description: "d".to_string(),
            link: "https://example.com/".to_string(),
            items: vec![],
        },
        detected,
    })
}

fn args(extra: &[&str]) -> Args {
    let mut all = vec!["feedgen", "https://example.com/"];
    all.extend_from_slice(extra);
    Args::try_parse_from(all).unwrap()
}

fn empty_dir() -> tempfile::TempDir {
    tempfile::tempdir().unwrap()
}

#[tokio::test]
async fn generated_feed_goes_to_stdout() {
    let dir = empty_dir();
    let source = Fake::new(|| feed(vec![]));
    let report = run(&args(&[]), dir.path(), &source, now()).await;
    assert_eq!(report.exit_code, 0);
    let out = String::from_utf8(report.stdout).unwrap();
    assert!(out.contains("<rss") && out.contains("タイトル"));
    assert!(report.stderr.is_empty());
}

#[tokio::test]
async fn proxied_body_is_written_byte_for_byte() {
    let dir = empty_dir();
    let raw = vec![0xff, 0xfe, 0x00, b'<'];
    let body = raw.clone();
    let source = Fake::new(move || {
        Ok(Outcome::Proxied {
            body: body.clone(),
            content_type: "application/rss+xml".to_string(),
            source_url: "https://example.com/feed".to_string(),
        })
    });
    let report = run(&args(&[]), dir.path(), &source, now()).await;
    assert_eq!(report.exit_code, 0);
    assert_eq!(report.stdout, raw);
}

#[tokio::test]
async fn output_file_is_written_and_stdout_stays_empty() {
    let dir = empty_dir();
    let out_path = dir.path().join("out.xml");
    let source = Fake::new(|| feed(vec![]));
    let report = run(
        &args(&["-o", out_path.to_str().unwrap()]),
        dir.path(),
        &source,
        now(),
    )
    .await;
    assert_eq!(report.exit_code, 0);
    assert!(report.stdout.is_empty());
    assert!(report.stderr.contains("出力しました"));
    assert!(std::fs::read_to_string(&out_path).unwrap().contains("<rss"));
}

#[tokio::test]
async fn unwritable_output_is_exit_1() {
    let dir = empty_dir();
    let bad = dir.path().join("no-such-dir").join("out.xml");
    let source = Fake::new(|| feed(vec![]));
    let report = run(
        &args(&["-o", bad.to_str().unwrap()]),
        dir.path(),
        &source,
        now(),
    )
    .await;
    assert_eq!(report.exit_code, 1);
    assert!(!report.stderr.is_empty());
}

#[tokio::test]
async fn core_error_is_exit_1_with_message_on_stderr_only() {
    let dir = empty_dir();
    let source = Fake::new(|| Err(FeedError::Http("HTTP取得エラー: boom".to_string())));
    let report = run(&args(&[]), dir.path(), &source, now()).await;
    assert_eq!(report.exit_code, 1);
    assert!(report.stdout.is_empty());
    assert!(report.stderr.contains("boom"));
}

#[tokio::test]
async fn feed_first_prints_first_candidate_to_stderr_not_stdout() {
    let dir = empty_dir();
    let source = Fake::new(|| {
        feed(vec![FeedInfo {
            url: "https://example.com/atom.xml".to_string(),
            title: "新着".to_string(),
            kind: FeedKind::Atom,
        }])
    });
    let report = run(&args(&["--feed-first"]), dir.path(), &source, now()).await;
    assert_eq!(report.exit_code, 0);
    assert!(
        report
            .stderr
            .contains("既存フィード: Atom https://example.com/atom.xml (新着)"),
        "{}",
        report.stderr
    );
    assert!(
        !String::from_utf8(report.stdout)
            .unwrap()
            .contains("既存フィード")
    );
}

#[tokio::test]
async fn options_reach_the_source_with_config_file_applied() {
    let dir = empty_dir();
    std::fs::write(
        dir.path().join("config.yaml"),
        "max_items: 7\nuser_agent: file-ua\n",
    )
    .unwrap();
    let source = Fake::new(|| feed(vec![]));
    run(
        &args(&["--use-feed", "--user-agent", "arg-ua"]),
        dir.path(),
        &source,
        now(),
    )
    .await;
    let seen = source.seen.lock().unwrap();
    assert_eq!(seen[0].0, "https://example.com/");
    assert_eq!(seen[0].1.max_items, 7);
    assert_eq!(seen[0].1.user_agent, "arg-ua");
    assert!(seen[0].1.use_feed);
}

#[tokio::test]
async fn unknown_config_keys_warn_on_stderr_and_continue() {
    let dir = empty_dir();
    std::fs::write(
        dir.path().join("config.yaml"),
        "instagram:\n  max_post: 1\n",
    )
    .unwrap();
    let source = Fake::new(|| feed(vec![]));
    let report = run(&args(&[]), dir.path(), &source, now()).await;
    assert_eq!(report.exit_code, 0);
    assert!(report.stderr.contains("instagram"));
}

#[tokio::test]
async fn broken_or_missing_explicit_config_is_exit_1_without_fetching() {
    let dir = empty_dir();
    let source = Fake::new(|| feed(vec![]));
    let missing = dir.path().join("none.yaml");
    let report = run(
        &args(&["-c", missing.to_str().unwrap()]),
        dir.path(),
        &source,
        now(),
    )
    .await;
    assert_eq!(report.exit_code, 1);
    std::fs::write(dir.path().join("config.yaml"), "max_items: [").unwrap();
    let report = run(&args(&[]), dir.path(), &source, now()).await;
    assert_eq!(report.exit_code, 1);
    assert!(source.seen.lock().unwrap().is_empty());
}

#[tokio::test]
async fn invalid_user_agent_is_exit_1_without_fetching() {
    let dir = empty_dir();
    let source = Fake::new(|| feed(vec![]));
    let report = run(
        &args(&["--user-agent", "日本語"]),
        dir.path(),
        &source,
        now(),
    )
    .await;
    assert_eq!(report.exit_code, 1);
    assert!(source.seen.lock().unwrap().is_empty());
}

#[tokio::test]
async fn generate_url_prints_the_api_url_without_fetching() {
    let dir = empty_dir();
    let source = Fake::new(|| feed(vec![]));
    let report = run(
        &args(&[
            "--generate-url",
            "--api-host",
            "api.example.com",
            "--max-items",
            "5",
            "--use-feed",
        ]),
        dir.path(),
        &source,
        now(),
    )
    .await;
    assert_eq!(report.exit_code, 0);
    assert_eq!(
        String::from_utf8(report.stdout).unwrap().trim_end(),
        "https://api.example.com/feed?url=https%3A%2F%2Fexample.com%2F&max_items=5&use_feed=true"
    );
    assert!(source.seen.lock().unwrap().is_empty());
}

#[tokio::test]
async fn generate_url_uses_api_base_url_from_config_and_requires_a_host() {
    let dir = empty_dir();
    let source = Fake::new(|| feed(vec![]));
    let report = run(&args(&["--generate-url"]), dir.path(), &source, now()).await;
    assert_eq!(report.exit_code, 1, "ホストなしはエラー");

    std::fs::write(
        dir.path().join("config.yaml"),
        "api_base_url: https://cfg.example/\n",
    )
    .unwrap();
    let report = run(&args(&["--generate-url"]), dir.path(), &source, now()).await;
    assert_eq!(report.exit_code, 0);
    assert!(
        String::from_utf8(report.stdout)
            .unwrap()
            .starts_with("https://cfg.example/feed?url=")
    );
}

#[tokio::test]
async fn generate_url_can_write_to_a_file() {
    let dir = empty_dir();
    let out_path = dir.path().join("url.txt");
    let source = Fake::new(|| feed(vec![]));
    let report = run(
        &args(&[
            "--generate-url",
            "--api-host",
            "a.example",
            "-o",
            out_path.to_str().unwrap(),
        ]),
        dir.path(),
        &source,
        now(),
    )
    .await;
    assert_eq!(report.exit_code, 0);
    assert!(
        std::fs::read_to_string(&out_path)
            .unwrap()
            .starts_with("https://a.example/feed?url=")
    );
}
