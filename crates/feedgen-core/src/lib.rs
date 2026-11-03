//! feedgen-core: URL から RSS 2.0 フィードを生成するコアライブラリ。
//!
//! Rust 版リブート。仕様は docs/rust-reboot-spec.md と docs/specs/ を参照。

pub mod charset;
pub mod detector;
pub mod error;
pub mod fetch;
pub mod generator;
pub mod models;
pub mod parser;

pub use error::{FeedError, Result};
pub use models::{RssFeed, RssItem};
