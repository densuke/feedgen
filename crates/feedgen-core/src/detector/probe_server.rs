//! 共通パスの確認 (D-3) のテスト用サーバー。パスごとに、状態・`Content-Type`・遅延を設定でき、
//! 受けたリクエストを記録する。

use std::net::SocketAddr;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};

/// 1 つのパスの応答。
#[derive(Clone)]
pub struct Route {
    pub path: &'static str,
    pub status: u16,
    pub content_type: &'static str,
    pub delay: Duration,
}

impl Route {
    pub fn new(path: &'static str, status: u16, content_type: &'static str) -> Self {
        Self {
            path,
            status,
            content_type,
            delay: Duration::ZERO,
        }
    }

    pub fn delayed(mut self, delay: Duration) -> Self {
        self.delay = delay;
        self
    }
}

pub struct ProbeServer {
    pub addr: SocketAddr,
    requests: Arc<Mutex<Vec<(String, String)>>>,
}

impl ProbeServer {
    /// 受けたリクエスト (メソッド, パス) を、受けた順に返す。
    pub fn requests(&self) -> Vec<(String, String)> {
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

async fn handle(
    mut stream: TcpStream,
    routes: Arc<Vec<Route>>,
    log: Arc<Mutex<Vec<(String, String)>>>,
) {
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
    let mut first = request.lines().next().unwrap_or("").split(' ');
    let method = first.next().unwrap_or("").to_string();
    let path = first.next().unwrap_or("/").to_string();
    log.lock()
        .expect("ロックを取得できない")
        .push((method, path.clone()));

    let route = routes.iter().find(|r| r.path == path);
    if let Some(route) = route {
        tokio::time::sleep(route.delay).await;
    }
    let head = match route {
        Some(route) => format!(
            "HTTP/1.1 {} X\r\nContent-Type: {}\r\nContent-Length: 0\r\n\r\n",
            route.status, route.content_type
        ),
        None => "HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n".to_string(),
    };
    let _ = stream.write_all(head.as_bytes()).await;
}
