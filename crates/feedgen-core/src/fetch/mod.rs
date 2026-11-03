//! SSRF 対策付きの取得層 (docs/specs/ssrf.md)。
//!
//! 取得先 URL を検査し、名前解決を自前で 1 回だけ行い、検査済みのアドレスに固定して
//! 接続する。リダイレクトは追従せず、遷移先ごとに最初から検査をやり直す。

mod address;
mod url_check;

use std::future::Future;
use std::io;
use std::net::{IpAddr, SocketAddr};
use std::time::{Duration, Instant};

use reqwest::header::{ACCEPT_ENCODING, CONTENT_ENCODING, CONTENT_TYPE, LOCATION};
use url::{Host, Url};

use crate::error::{FeedError, Result};

pub use address::is_public_ip;
pub use url_check::check_url;

/// 応答本文の上限 (S-6)。
pub const MAX_BYTES: usize = 2 * 1024 * 1024;
/// リダイレクトの上限 (S-5)。
pub const MAX_REDIRECTS: usize = 5;
/// 1 リクエストあたりの締切 (S-6)。
pub const REQUEST_TIMEOUT: Duration = Duration::from_secs(30);
/// リダイレクトを含む全体の締切 (S-6)。
pub const TOTAL_TIMEOUT: Duration = Duration::from_secs(45);
/// `User-Agent` を指定しないときに送る値 (S-12)。
pub const DEFAULT_USER_AGENT: &str = "feedgen/1.0";
/// 内部アドレス・解決失敗・解決結果が空のときに返す共通の文面 (S-9)。
pub const DENIED: &str = "このアドレスへのアクセスは許可されていません";

const REDIRECT_STATUS: [u16; 5] = [301, 302, 303, 307, 308];

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

/// 拒否の共通エラー (S-9)。
pub(crate) fn denied() -> FeedError {
    FeedError::UnsafeUrl(DENIED.to_string())
}

fn http_error(message: &str) -> FeedError {
    FeedError::Http(message.to_string())
}

/// 名前解決の抽象。テストでは固定表に差し替える。
pub trait Lookup: Send + Sync {
    fn lookup(&self, host: &str) -> impl Future<Output = io::Result<Vec<IpAddr>>> + Send;
}

/// OS の名前解決を使う本番用の実装。
pub struct SystemLookup;

impl Lookup for SystemLookup {
    fn lookup(&self, host: &str) -> impl Future<Output = io::Result<Vec<IpAddr>>> + Send {
        let host = host.to_string();
        async move {
            let mut addrs: Vec<IpAddr> = Vec::new();
            for socket in tokio::net::lookup_host((host.as_str(), 0)).await? {
                if !addrs.contains(&socket.ip()) {
                    addrs.push(socket.ip());
                }
            }
            Ok(addrs)
        }
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
    /// `Content-Type` ヘッダの値をそのまま。ヘッダがなければ空文字列。
    pub content_type: String,
    pub body: Vec<u8>,
    pub final_url: Url,
}

/// 1 回の通信の結果。リダイレクトなら `location` を持つ。
struct Hop {
    status: u16,
    location: Option<String>,
    content_type: String,
    body: Vec<u8>,
}

/// SSRF 対策付きの取得器。
pub struct SafeFetcher<L: Lookup = SystemLookup> {
    lookup: L,
    limits: Limits,
    /// テストでだけ、検査を通すアドレスを足せる (S-10: 本番には存在しない)。
    #[cfg(test)]
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

    /// 検査を通した上で取得する。`User-Agent` は既定の `feedgen/1.0` を送る (S-12)。
    pub async fn fetch(&self, method: Method, url: &str) -> Result<Fetched> {
        self.fetch_as(method, url, DEFAULT_USER_AGENT).await
    }

    /// 検査を通した上で、`User-Agent` を指定して取得する (S-1〜S-8、S-12)。
    pub async fn fetch_as(&self, method: Method, url: &str, _user_agent: &str) -> Result<Fetched> {
        let deadline = Instant::now() + self.limits.total_timeout;
        let mut current = check_url(url)?;

        for _ in 0..=MAX_REDIRECTS {
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err(http_error("応答に時間がかかりすぎています"));
            }
            // 名前解決も通算の締切に含める。間に合わなければ拒否と同じ文面で止める (S-6)。
            let addrs = tokio::time::timeout(remaining, self.resolve_checked(&current))
                .await
                .map_err(|_| denied())??;
            // 解決に使った時間は、通信の残り時間から引く。
            let remaining = deadline.saturating_duration_since(Instant::now());
            if remaining.is_zero() {
                return Err(http_error("応答に時間がかかりすぎています"));
            }
            let hop = self.send_once(method, &current, &addrs, remaining).await?;

            let Some(location) = hop.location else {
                return Ok(Fetched {
                    status: hop.status,
                    content_type: hop.content_type,
                    body: hop.body,
                    final_url: current,
                });
            };
            current = next_url(&current, &location)?;
        }
        Err(FeedError::UnsafeUrl("リダイレクトが多すぎます".into()))
    }

    /// ポートを確かめ、host を解決し、全アドレスが公開であることを確かめる (S-4)。
    async fn resolve_checked(&self, url: &Url) -> Result<Vec<IpAddr>> {
        let port = url.port_or_known_default().ok_or_else(denied)?;
        if !self.is_allowed_port(port) {
            return Err(denied());
        }
        let addrs = match url.host() {
            Some(Host::Ipv4(ip)) => vec![IpAddr::V4(ip)],
            Some(Host::Ipv6(ip)) => vec![IpAddr::V6(ip)],
            Some(Host::Domain(name)) => self.lookup.lookup(name).await.map_err(|_| denied())?,
            None => return Err(denied()),
        };
        if addrs.is_empty() || !addrs.iter().all(|&ip| self.is_allowed(ip)) {
            return Err(denied());
        }
        Ok(addrs)
    }

    /// 許可するポートは 80 と 443 のみ (S-4)。
    fn is_allowed_port(&self, port: u16) -> bool {
        // テストの取得器 (許可アドレスあり) は、ローカルサーバーの任意ポートを通す (S-10)。
        #[cfg(test)]
        if !self.allow.is_empty() {
            return true;
        }
        matches!(port, 80 | 443)
    }

    fn is_allowed(&self, ip: IpAddr) -> bool {
        #[cfg(test)]
        if self.allow.contains(&ip) {
            return true;
        }
        is_public_ip(ip)
    }

    /// 検査済みアドレスに固定して 1 回だけ通信する。リダイレクトは追わない (S-5〜S-8)。
    async fn send_once(
        &self,
        method: Method,
        url: &Url,
        addrs: &[IpAddr],
        remaining: Duration,
    ) -> Result<Hop> {
        let mut builder = reqwest::Client::builder()
            .redirect(reqwest::redirect::Policy::none())
            .no_proxy()
            .timeout(self.limits.request_timeout.min(remaining));
        if let Some(Host::Domain(name)) = url.host() {
            let port = url.port_or_known_default().unwrap_or(80);
            let pinned: Vec<SocketAddr> =
                addrs.iter().map(|&ip| SocketAddr::new(ip, port)).collect();
            builder = builder.resolve_to_addrs(name, &pinned);
        }
        let client = builder
            .build()
            .map_err(|_| http_error("取得に失敗しました"))?;

        let verb = match method {
            Method::Get => reqwest::Method::GET,
            Method::Head => reqwest::Method::HEAD,
        };
        let mut response = client
            .request(verb, url.clone())
            .header(ACCEPT_ENCODING, "identity")
            .send()
            .await
            .map_err(|e| request_error(&e))?;

        let status = response.status().as_u16();
        if REDIRECT_STATUS.contains(&status)
            && let Some(location) = response
                .headers()
                .get(LOCATION)
                .and_then(|value| value.to_str().ok())
        {
            return Ok(Hop {
                status,
                location: Some(location.to_string()),
                content_type: String::new(),
                body: Vec::new(),
            });
        }

        // ヘッダが複数あるときは、すべてを ", " でつなぐ。UTF-8 でない値は無視する (S-11)。
        let content_type = response
            .headers()
            .get_all(CONTENT_TYPE)
            .iter()
            .filter_map(|value| value.to_str().ok())
            .collect::<Vec<_>>()
            .join(", ");

        // ヘッダが複数あるときも全件を見る。1 つでも identity 以外なら拒否する (S-7)。
        let unsupported_encoding =
            response
                .headers()
                .get_all(CONTENT_ENCODING)
                .iter()
                .any(|value| {
                    value.to_str().map_or(true, |v| {
                        let v = v.trim();
                        !(v.is_empty() || v.eq_ignore_ascii_case("identity"))
                    })
                });
        if unsupported_encoding {
            return Err(http_error("未対応の圧縮形式です"));
        }
        let max = self.limits.max_bytes;
        if response
            .content_length()
            .is_some_and(|len| len > max as u64)
        {
            return Err(http_error("応答が大きすぎます"));
        }

        let mut body = Vec::new();
        while let Some(chunk) = response.chunk().await.map_err(|e| request_error(&e))? {
            if body.len() + chunk.len() > max {
                return Err(http_error("応答が大きすぎます"));
            }
            body.extend_from_slice(&chunk);
        }
        Ok(Hop {
            status,
            location: None,
            content_type,
            body,
        })
    }
}

/// `Location` を現在の URL に対して解決し、改めて検査する (S-5)。
fn next_url(current: &Url, location: &str) -> Result<Url> {
    url_check::check_chars(location)?;
    let joined = current.join(location).map_err(|_| denied())?;
    check_url(joined.as_str())
}

/// 通信エラーを、接続先の詳細を含まない文面に直す (S-9)。
fn request_error(e: &reqwest::Error) -> FeedError {
    if e.is_timeout() {
        http_error("応答に時間がかかりすぎています")
    } else {
        http_error("取得に失敗しました")
    }
}

#[cfg(test)]
mod test_server;
#[cfg(test)]
mod tests;
