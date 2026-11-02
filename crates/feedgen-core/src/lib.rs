//! feedgen-core: URL から RSS 2.0 フィードを生成するコアライブラリ。
//!
//! Rust 版リブート。仕様は docs/rust-reboot-spec.md と docs/specs/ を参照。

pub mod error;
pub mod fetch;

pub use error::{FeedError, Result};
