//! テスト用のローカル HTTP サーバー。パスごとに挙動を変え、1 台で複数の関心を通す。

use std::net::SocketAddr;
use std::sync::Arc;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::{TcpListener, TcpStream};

pub struct TestServer {
    pub addr: SocketAddr,
    accepted: Arc<AtomicUsize>,
}

impl TestServer {
    /// これまでに受け付けた接続の数。
    pub fn accepted(&self) -> usize {
        self.accepted.load(Ordering::SeqCst)
    }
}

pub async fn spawn() -> TestServer {
    let listener = TcpListener::bind("127.0.0.1:0")
        .await
        .expect("ローカルサーバーを起動できない");
    let addr = listener.local_addr().expect("アドレスを取得できない");
    let accepted = Arc::new(AtomicUsize::new(0));
    let counter = Arc::clone(&accepted);
    tokio::spawn(async move {
        while let Ok((stream, _)) = listener.accept().await {
            counter.fetch_add(1, Ordering::SeqCst);
            tokio::spawn(handle(stream, addr.port()));
        }
    });
    TestServer { addr, accepted }
}

async fn read_request(stream: &mut TcpStream) -> Option<String> {
    let mut buf = Vec::new();
    let mut chunk = [0u8; 1024];
    loop {
        let n = stream.read(&mut chunk).await.ok()?;
        if n == 0 {
            return None;
        }
        buf.extend_from_slice(&chunk[..n]);
        if buf.windows(4).any(|w| w == b"\r\n\r\n") {
            return Some(String::from_utf8_lossy(&buf).into_owned());
        }
    }
}

async fn send(stream: &mut TcpStream, status: &str, headers: &[&str], body: &[u8]) {
    let mut head = format!("HTTP/1.1 {status}\r\n");
    for header in headers {
        head.push_str(header);
        head.push_str("\r\n");
    }
    head.push_str("\r\n");
    let _ = stream.write_all(head.as_bytes()).await;
    let _ = stream.write_all(body).await;
}

async fn redirect(stream: &mut TcpStream, location: &str) {
    let header = format!("Location: {location}");
    send(stream, "302 Found", &[&header, "Content-Length: 0"], b"").await;
}

async fn handle(mut stream: TcpStream, port: u16) {
    let Some(request) = read_request(&mut stream).await else {
        return;
    };
    let mut lines = request.split("\r\n");
    let mut first = lines.next().unwrap_or("").split(' ');
    let method = first.next().unwrap_or("");
    let path = first.next().unwrap_or("/");
    let accept_encoding = lines
        .find_map(|line| {
            line.to_ascii_lowercase()
                .strip_prefix("accept-encoding:")
                .map(|v| v.trim().to_string())
        })
        .unwrap_or_default();

    match path {
        "/ok" if method == "HEAD" => {
            send(&mut stream, "200 OK", &["Content-Length: 5"], b"").await;
        }
        "/ok" => send(&mut stream, "200 OK", &["Content-Length: 5"], b"hello").await,
        "/echo-ae" => {
            let len = format!("Content-Length: {}", accept_encoding.len());
            send(&mut stream, "200 OK", &[&len], accept_encoding.as_bytes()).await;
        }
        "/gzip" => {
            let headers = ["Content-Encoding: gzip", "Content-Length: 5"];
            send(&mut stream, "200 OK", &headers, b"hello").await;
        }
        "/chunked" => {
            let headers = ["Transfer-Encoding: chunked"];
            send(
                &mut stream,
                "200 OK",
                &headers,
                b"2\r\nhe\r\n3\r\nllo\r\n0\r\n\r\n",
            )
            .await;
        }
        // 巨大な Content-Length を宣言するだけで本文は送らない。早期に拒否されなければ止まる。
        "/big-declared" => {
            send(&mut stream, "200 OK", &["Content-Length: 5000"], b"").await;
            tokio::time::sleep(Duration::from_secs(30)).await;
        }
        // 宣言なしで上限を超える本文をチャンクで送り続ける。
        "/big-stream" => {
            send(&mut stream, "200 OK", &["Transfer-Encoding: chunked"], b"").await;
            let data = "a".repeat(1024);
            for _ in 0..64 {
                let chunk = format!("400\r\n{data}\r\n");
                if stream.write_all(chunk.as_bytes()).await.is_err() {
                    return;
                }
            }
            let _ = stream.write_all(b"0\r\n\r\n").await;
        }
        // 1 バイトずつ遅く返し続ける (slow drip)。
        "/slow" => {
            send(&mut stream, "200 OK", &["Content-Length: 100"], b"").await;
            for _ in 0..100 {
                if stream.write_all(b"a").await.is_err() {
                    return;
                }
                tokio::time::sleep(Duration::from_millis(200)).await;
            }
        }
        "/r-public" => redirect(&mut stream, &format!("http://pub2.test:{port}/ok")).await,
        "/r-rel" => redirect(&mut stream, "/ok").await,
        "/r-10" => redirect(&mut stream, "http://10.0.0.1/").await,
        "/r-meta" => redirect(&mut stream, "http://169.254.169.254/").await,
        "/r-internal-name" => redirect(&mut stream, "http://internal.test/").await,
        "/r-backslash" => redirect(&mut stream, "http://127.0.0.1\\@8.8.8.8/").await,
        "/r-loop" => redirect(&mut stream, "/r-loop").await,
        "/r-noloc" => send(&mut stream, "302 Found", &["Content-Length: 0"], b"").await,
        _ => send(&mut stream, "404 Not Found", &["Content-Length: 0"], b"").await,
    }
}
