//! コアの呼び出しを差し替えられるようにする trait (api.md 5 章)。

use std::future::Future;

use chrono::{DateTime, FixedOffset};
use feedgen_core::Result;
use feedgen_core::generator::{FeedGenerator, GenerateOptions, Outcome};

pub trait FeedService: Send + Sync + 'static {
    fn generate(
        &self,
        url: &str,
        options: &GenerateOptions,
        now: DateTime<FixedOffset>,
    ) -> impl Future<Output = Result<Outcome>> + Send;
}

impl FeedService for FeedGenerator {
    async fn generate(
        &self,
        url: &str,
        options: &GenerateOptions,
        now: DateTime<FixedOffset>,
    ) -> Result<Outcome> {
        FeedGenerator::generate(self, url, options, now).await
    }
}
