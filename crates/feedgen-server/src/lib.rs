//! feedgen の Web API (docs/specs/api.md)。コアの `generate` を呼ぶだけの薄い層。

pub mod admin;
pub mod app;
pub mod headers;
pub mod listen;
pub mod query;
pub mod service;

pub use app::{AppConfig, router};
pub use service::FeedService;
