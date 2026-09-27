"""
Early HTTP/1.1 calculator server.
No framework -- just a raw socket. Handles persistent (keep-alive)
connections, arbitrary pipelined GET requests on the same connection,
Content-Length / chunked body framing, and Connection: close / idle
timeout behaviour.

Run:
    python3 server11.py            # listens on 0.0.0.0:8080

Test:
    curl "http://localhost:8080/add?a=2&b=3"
"""

import socket
from urllib.parse import urlparse, parse_qs

HOST = "0.0.0.0"
PORT = 8080
IDLE_TIMEOUT = 30  # seconds, stretch: defensible idle timeout

STATUS_TEXT = {
    200: "200 OK",
    400: "400 Bad Request",
    404: "404 Not Found",
    405: "405 Method Not Allowed",
}


def read_until(sock, buf, delimiter):
    """Read from sock, appending to buf, until delimiter is seen.
    Returns (head_including_delimiter, remainder) or (None, buf) on EOF."""
    while delimiter not in buf:
        data = sock.recv(4096)
        if not data:
            return None, buf
        buf += data
    idx = buf.index(delimiter) + len(delimiter)
    return buf[:idx], buf[idx:]


def read_exact(sock, buf, n):
    """Read exactly n bytes (across recv boundaries). May return short on EOF."""
    while len(buf) < n:
        data = sock.recv(4096)
        if not data:
            break
        buf += data
    return buf[:n], buf[n:]


def read_chunked_body(sock, buf):
    """Stretch: parse a chunked Transfer-Encoding request body."""
    body = b""
    while True:
        size_line, buf = read_until(sock, buf, b"\r\n")
        if size_line is None:
            break
        size_str = size_line.strip().split(b";")[0]
        try:
            size = int(size_str, 16)
        except ValueError:
            break
        if size == 0:
            # consume optional trailer headers + final CRLF
            _, buf = read_until(sock, buf, b"\r\n\r\n")
            break
        chunk, buf = read_exact(sock, buf, size)
        body += chunk
        _, buf = read_until(sock, buf, b"\r\n")  # trailing CRLF after chunk
    return body, buf


def build_response(status, body_text, keep_alive=True):
    body_bytes = body_text.encode()
    headers = [
        f"HTTP/1.1 {STATUS_TEXT.get(status, str(status))}",
        f"Content-Length: {len(body_bytes)}",
        "Content-Type: text/plain",
        f"Connection: {'keep-alive' if keep_alive else 'close'}",
    ]
    head = "\r\n".join(headers) + "\r\n\r\n"
    return head.encode() + body_bytes


def compute(path):
    parsed = urlparse(path)
    route = parsed.path
    qs = parse_qs(parsed.query)

    if route not in ("/add", "/sub", "/mul", "/div"):
        return 404, "not found"

    if "a" not in qs or "b" not in qs:
        return 400, "missing a or b"

    try:
        a = float(qs["a"][0])
        b = float(qs["b"][0])
    except (ValueError, IndexError):
        return 400, "a and b must be numbers"

    if route == "/add":
        result = a + b
    elif route == "/sub":
        result = a - b
    elif route == "/mul":
        result = a * b
    else:  # /div
        if b == 0:
            return 400, "division by zero"
        result = a / b

    if result == int(result):
        result = int(result)
    return 200, str(result)


def handle_connection(conn, addr):
    conn.settimeout(IDLE_TIMEOUT)
    buf = b""
    keep_alive = True
    try:
        while keep_alive:
            try:
                head, buf = read_until(conn, buf, b"\r\n\r\n")
            except socket.timeout:
                break  # stretch: idle timeout closes the connection cleanly
            if head is None:
                break  # client closed the socket

            lines = head.split(b"\r\n")
            request_line = lines[0].decode(errors="replace")
            header_lines = lines[1:-2]  # drop the blank terminator pair

            parts = request_line.split(" ")
            if len(parts) != 3:
                conn.sendall(build_response(400, "bad request line", keep_alive=False))
                break
            method, path, version = parts

            headers = {}
            for hl in header_lines:
                if b":" in hl:
                    k, v = hl.split(b":", 1)
                    headers[k.strip().lower().decode()] = v.strip().decode()

            content_length = int(headers.get("content-length", 0) or 0)
            transfer_encoding = headers.get("transfer-encoding", "").lower()

            if transfer_encoding == "chunked":
                _, buf = read_chunked_body(conn, buf)
            elif content_length > 0:
                _, buf = read_exact(conn, buf, content_length)

            conn_header = headers.get("connection", "").lower()
            if version.strip() == "HTTP/1.0":
                keep_alive = conn_header == "keep-alive"
            else:
                keep_alive = conn_header != "close"  # stretch: honour Connection: close

            if "host" not in headers:
                conn.sendall(build_response(400, "missing Host header", keep_alive=False))
                break

            if method != "GET":
                conn.sendall(build_response(405, "method not allowed", keep_alive=keep_alive))
                if not keep_alive:
                    break
                continue

            status, text = compute(path)
            conn.sendall(build_response(status, text, keep_alive=keep_alive))
    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        conn.close()


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    print(f"listening on {HOST}:{PORT}")
    try:
        while True:
            conn, addr = srv.accept()
            handle_connection(conn, addr)  # one connection at a time, requests answered in order
    except KeyboardInterrupt:
        pass
    finally:
        srv.close()


if __name__ == "__main__":
    main()