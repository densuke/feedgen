//! テスト用のローカルのサイト用サーバー。パスごとに、状態・`Content-Type`・本文・遅延・リダイレクト先を
//! 設定でき、受けたリクエスト (メソッド、パス、`User-Agent`) を記録する。
//!
//! 共通パスの確認 (detector.md D-3) と、`generate` (pipeline.md) のテストで使う。

use std::io;
use std::net::{IpAddr, SocketAddr};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};

use crate::fetch::{Limits, Lookup, SafeFetcher};

/// 1 つのパスの応答。
#[derive(Clone)]
pub struct Route {
    pub path: &'static str,
    pub status: u16,
    pub content_type: &'static str,
    pub delay: Duration,
    pub body: Vec<u8>,
    pub location: Option<String>,
}

impl Route {
    pub fn new(path: &'static str, status: u16, content_type: &'static str) -> Self {
        Self {
            path,
            status,
            content_type,
            delay: Duration::ZERO,
            body: Vec::new(),
            location: None,
        }
    }

    /// 本文を持つ 200 の応答。
    pub fn page(path: &'static str, content_type: &'static str, body: impl Into<Vec<u8>>) -> Self {
        Self::new(path, 200, content_type).with_body(body)
    }

    /// `Location` つきの 302。
    pub fn redirect(path: &'static str, to: impl Into<String>) -> Self {
        let mut route = Self::new(path, 302, "");
        route.location = Some(to.into());
        route
    }

    pub fn with_body(mut self, body: impl Into<Vec<u8>>) -> Self {
        self.body = body.into();
        self
    }

    pub fn delayed(mut self, delay: Duration) -> Self {
        self.delay = delay;
        self
    }
}

/// (メソッド, パス, User-Agent)
type Logged = (String, String, String);

pub struct ProbeServer {
    pub addr: SocketAddr,
    requests: Arc<Mutex<Vec<Logged>>>,
}

impl ProbeServer {
    /// 受けたリクエスト (メソッド, パス) を、受けた順に返す。
    pub fn requests(&self) -> Vec<(String, String)> {
        self.logged()
            .into_iter()
            .map(|(method, path, _)| (method, path))
            .collect()
    }

    /// 受けたリクエストの `User-Agent` を、受けた順に返す (ヘッダがなければ空文字列)。
    pub fn user_agents(&self) -> Vec<String> {
        self.logged().into_iter().map(|(_, _, ua)| ua).collect()
    }

    fn logged(&self) -> Vec<Logged> {
        self.requests.lock().expect("ロックを取得できない").clone()
    }
}

/// 設定にないパスは、`Content-Type` なしの 404 を返す。
pub async fn spawn(routes: Vec<Route>) -> ProbeServer {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("ローカルサーバーを起動できない");
    let addr = listener.local_addr().expect("アドレスを取得できない");
    let requests = Arc::new(Mutex::new(Vec::new()));
    let log = Arc::clone(&requests);
    let routes = Arc::new(routes);
    tokio::spawn(async move {
        while let Ok((stream, _)) = listener.accept().await {
            tokio::spawn(handle(stream, Arc::clone(&routes), Arc::clone(&log)));
        }
    });
    ProbeServer { addr, requests }
}

async fn handle(mut stream: TcpStream, routes: Arc<Vec<Route>>, log: Arc<Mutex<Vec<Logged>>>) {
    let mut buf = Vec::new();
    let mut chunk = [0u8; 1024];
    loop {
        let Ok(n) = stream.read(&mut chunk).await else {
            return;
        };
        if n == 0 {
            return;
        }
        buf.extend_from_slice(&chunk[..n]);
        if buf.windows(4).any(|w| w == b"\r\n\r\n") {
            break;
        }
    }
    let request = String::from_utf8_lossy(&buf);
    let mut lines = request.split("\r\n");
    let mut first = lines.next().unwrap_or("").split(' ');
    let method = first.next().unwrap_or("").to_string();
    let path = first.next().unwrap_or("/").to_string();
    let user_agent = lines
        .filter_map(|line| line.split_once(':'))
        .find(|(name, _)| name.eq_ignore_ascii_case("user-agent"))
        .map(|(_, value)| value.trim().to_string())
        .unwrap_or_default();
    log.lock()
        .expect("ロックを取得できない")
        .push((method.clone(), path.clone(), user_agent));

    let route = routes.iter().find(|r| r.path == path);
    if let Some(route) = route {
        tokio::time::sleep(route.delay).await;
    }
    let (head, body) = match route {
        Some(route) => {
            let mut head = format!(
                "HTTP/1.1 {} X\r\nContent-Type: {}\r\nContent-Length: {}\r\n",
                route.status,
                route.content_type,
                route.body.len()
            );
            if let Some(location) = &route.location {
                head.push_str(&format!("Location: {location}\r\n"));
            }
            head.push_str("\r\n");
            (head, route.body.clone())
        }
        None => (
            "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n".to_string(),
            Vec::new(),
        ),
    };
    let _ = stream.write_all(head.as_bytes()).await;
    // HEAD には本文を付けない (Content-Length は GET と同じ値)。
    if method != "HEAD" {
        let _ = stream.write_all(&body).await;
    }
}

// ---- 取得器の共通の道具 (detector と generator のテストで使う) ----

/// どの名前でも 127.0.0.1 に解決する。
pub struct LocalLookup;

impl Lookup for LocalLookup {
    async fn lookup(&self, _host: &str) -> io::Result<Vec<IpAddr>> {
        Ok(vec![IpAddr::from([127, 0, 0, 1])])
    }
}

/// 127.0.0.1 だけを通す取得器 (ポートの制限も外れる)。
pub fn lenient_fetcher() -> SafeFetcher<LocalLookup> {
    SafeFetcher::for_test(
        LocalLookup,
        vec![IpAddr::from([127, 0, 0, 1])],
        Limits::default(),
    )
}

/// 127.0.0.1 を通さない取得器 (別のアドレスだけを許可するので、ポートの制限は外れ、IP の検査で拒否される)。
pub fn refusing_fetcher() -> SafeFetcher<LocalLookup> {
    SafeFetcher::for_test(
        LocalLookup,
        vec![IpAddr::from([10, 0, 0, 9])],
        Limits::default(),
    )
}

/// サーバーの URL (`http://site.test:<port><path>`)。
pub fn site_url(server: &ProbeServer, path: &str) -> String {
    format!("http://site.test:{}{path}", server.addr.port())
}
