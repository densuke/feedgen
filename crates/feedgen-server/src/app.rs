//! axum の Router (api.md A-1〜A-6)。

use std::sync::Arc;
use std::time::Duration;

use axum::Router;

use crate::service::FeedService;

/// 構成値。本番は 60 秒と 32 件。テストでは短い値を差し込む。
#[derive(Debug, Clone)]
pub struct AppConfig {
    pub timeout: Duration,
    pub max_concurrent: usize,
}

impl Default for AppConfig {
    fn default() -> Self {
        Self {
            timeout: Duration::from_secs(60),
            max_concurrent: 32,
        }
    }
}

pub fn router<S: FeedService>(service: Arc<S>, config: AppConfig) -> Router {
    let _ = (service, config);
    todo!("api.md A-1")
}
