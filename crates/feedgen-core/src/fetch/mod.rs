//! SSRF 対策付きの取得層 (docs/specs/ssrf.md)。
//!
//! RED 段階のスタブ。実装は仕様 S-1〜S-10 に従って後続のコミットで書く。

use std::future::Future;
use std::io;
use std::net::IpAddr;
use std::time::Duration;

use url::Url;

use crate::error::Result;

/// 応答本文の上限 (S-6)。
pub const MAX_BYTES: usize = 2 * 1024 * 1024;
/// リダイレクトの上限 (S-5)。
pub const MAX_REDIRECTS: usize = 5;
/// 1 リクエストあたりの締切 (S-6)。
pub const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);
/// リダイレクトを含む全体の締切 (S-6)。
pub const TOTAL_TIMEOUT: Duration = Duration::from_secs(45);
/// 内部アドレス・解決失敗・解決結果が空のときに返す共通の文面 (S-9)。
pub const DENIED: &str = "このアドレスへのアクセスは許可されていません";

/// 取得の上限値。本番は [`Limits::default`] のみ使う。
#[derive(Debug, Clone, Copy)]
pub struct Limits {
    pub max_bytes: usize,
    pub request_timeout: Duration,
    pub total_timeout: Duration,
}

impl Default for Limits {
    fn default() -> Self {
        Self {
            max_bytes: MAX_BYTES,
            request_timeout: REQUEST_TIMEOUT,
            total_timeout: TOTAL_TIMEOUT,
        }
    }
}

/// URL 文字列を検査し、解析済みの `Url` を返す (S-2、S-3)。
pub fn check_url(_raw: &str) -> Result<Url> {
    todo!("S-2, S-3")
}

/// 公開アドレスかどうか (S-4)。
pub fn is_public_ip(_ip: IpAddr) -> bool {
    todo!("S-4")
}

/// 名前解決の抽象。テストでは固定表に差し替える。
pub trait Lookup: Send + Sync {
    fn lookup(&self, host: &str) -> impl Future<Output = io::Result<Vec<IpAddr>>> + Send;
}

/// OS の名前解決を使う本番用の実装。
pub struct SystemLookup;

impl Lookup for SystemLookup {
    fn lookup(&self, _host: &str) -> impl Future<Output = io::Result<Vec<IpAddr>>> + Send {
        // 未実装 (S-4: tokio::net::lookup_host を使う)
        async move { Err(io::Error::other("未実装")) }
    }
}

/// 対応する HTTP メソッド (S-1)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Method {
    Get,
    Head,
}

/// 取得結果。
#[derive(Debug)]
pub struct Fetched {
    pub status: u16,
    pub body: Vec<u8>,
    pub final_url: Url,
}

/// SSRF 対策付きの取得器。
pub struct SafeFetcher<L: Lookup = SystemLookup> {
    #[allow(dead_code)]
    lookup: L,
    #[allow(dead_code)]
    limits: Limits,
    /// テストでだけ、検査を通すアドレスを足せる (S-10: 本番には存在しない)。
    #[cfg(test)]
    #[allow(dead_code)]
    allow: Vec<IpAddr>,
}

impl SafeFetcher<SystemLookup> {
    /// 本番用。ポリシーも上限も引数に取らない (S-10)。
    pub fn new() -> Self {
        Self {
            lookup: SystemLookup,
            limits: Limits::default(),
            #[cfg(test)]
            allow: Vec::new(),
        }
    }
}

impl Default for SafeFetcher<SystemLookup> {
    fn default() -> Self {
        Self::new()
    }
}

impl<L: Lookup> SafeFetcher<L> {
    /// テスト用の差し込み口。名前解決、許可アドレス、上限を差し替える。
    #[cfg(test)]
    pub(crate) fn for_test(lookup: L, allow: Vec<IpAddr>, limits: Limits) -> Self {
        Self {
            lookup,
            limits,
            allow,
        }
    }

    /// 検査を通した上で取得する (S-1〜S-8)。
    pub async fn fetch(&self, _method: Method, _url: &str) -> Result<Fetched> {
        todo!("S-1〜S-8")
    }
}

#[cfg(test)]
mod test_server;
#[cfg(test)]
mod tests;
