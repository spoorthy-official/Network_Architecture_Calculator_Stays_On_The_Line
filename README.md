# Task 1: Early HTTP/1.1 Calculator Server That Stays on the Line

A pure TCP socket-based HTTP/1.1 calculator server built without external frameworks. It demonstrates **Persistent Connections (`Keep-Alive`)**, **HTTP Message Boundary / Framing Handling**, **Content-Length Framing**, **Chunked Transfer-Encoding parsing**, and **Connection Lifecycle Management**.

---

## 1. Problem Statement & Background

In **HTTP/1.0**, every request required a brand-new TCP connection. The server sent the response and immediately closed the socket (`EOF`). The client knew the response ended simply because the connection closed.

In **Early HTTP/1.1**, connections are **persistent (`Keep-Alive`) by default**:
- The client initiates **1 single TCP handshake**.
- Multiple requests and responses are exchanged sequentially over that **same open socket**.
- **The Core Challenge (Framing Problem)**: Because the socket never closes between requests, the server and client must know exactly where one message ends and the next begins:
  - Header boundaries are identified by the `\r\n\r\n` delimiter.
  - Body boundaries are determined by reading **exactly `Content-Length` bytes** (or parsing chunked transfer encoding). Reading even 1 extra byte corrupts the subsequent request!
  - Responses must explicitly specify `Content-Length: <len>` so the client does not hang waiting for EOF.

---

## 2. Supported Endpoints & HTTP Response Specifications

| Method | Endpoint & Query | Status Code | Response Body | Behavior / Rationale |
|---|---|---|---|---|
| `GET` | `/add?a=2&b=3` | `200 OK` | `5` | Addition ($2 + 3 = 5$) |
| `GET` | `/sub?a=10&b=4` | `200 OK` | `6` | Subtraction ($10 - 4 = 6$) |
| `GET` | `/mul?a=6&b=7` | `200 OK` | `42` | Multiplication ($6 \times 7 = 42$) |
| `GET` | `/div?a=9&b=3` | `200 OK` | `3` | Integer division ($9 / 3 = 3$) |
| `GET` | `/div?a=1&b=0` | `400 Bad Request` | `division by zero` | Division by zero error handling |
| `GET` | `/add?a=x&b=3` | `400 Bad Request` | `a and b must be numbers` | Non-numeric parameter validation |
| `GET` | `/pow?a=2&b=8` | `404 Not Found` | `not found` | Unrecognized route / unsupported operator |
| `POST` | `/add` | `405 Method Not Allowed` | `method not allowed` | Only `GET` requests are allowed |
| `GET` | `/add?a=2&b=3` *(No `Host:`)* | `400 Bad Request` | `missing Host header` | HTTP/1.1 strictly mandates the `Host:` header |

---

## 3. Code Architecture & Technical Implementation

The implementation is located in [`1st_task.py`](1st_task.py).

```
                                  +-----------------------+
                                  |  main()               |
                                  |  socket() -> bind()   |
                                  |  listen() -> accept() |
                                  +-----------+-----------+
                                              |
                                              v (New Connection)
                                  +-----------------------+
                            +---->| handle_connection()   |<----+
                            |     | Persistent loop       |     |
                            |     +-----------+-----------+     |
                            |                 |                 |
                            |                 v                 |
                            |     +-----------------------+     |
                            |     | read_until(\r\n\r\n)  |     |
                            |     +-----------+-----------+     |
                            |                 |                 |
                            |                 v                 |
                            |     +-----------------------+     |
                            |     | Parse Request Line    |     |
                            |     | Validate Host Header  |     |
                            |     +-----------+-----------+     |
                            |                 |                 |
                            |                 v                 |
                            |     +-----------------------+     |
                            |     | compute() Logic       |     |
                            |     +-----------+-----------+     |
                            |                 |                 |
                            |                 v                 |
                            |     +-----------------------+     |
                            |     | build_response()      |     |
                            |     | Content-Length + Body |     |
                            |     +-----------+-----------+     |
                            |                 |                 |
                            +-----------------+-----------------+
                              (Keeps socket open for next req)
```

### Key Functions Breakdown:
1. **`read_until(sock, buf, delimiter)`**:
   - Accumulates bytes from `sock.recv(4096)` into a persistent buffer until the delimiter (e.g., `\r\n\r\n`) is found.
   - Returns the parsed segment (including delimiter) and retains remaining leftover bytes in `buf` for subsequent reads.
2. **`read_exact(sock, buf, n)`**:
   - Reads exactly `n` bytes across TCP chunk boundaries.
   - Crucial for consuming `Content-Length` request bodies without consuming bytes belonging to pipelined requests.
3. **`read_chunked_body(sock, buf)`**:
   - Implements chunked Transfer-Encoding parsing (hex chunk size -> chunk data -> trailing CRLF -> terminating 0 chunk).
4. **`compute(path)`**:
   - Extracts route and query parameters (`urllib.parse`), validates numeric inputs, performs arithmetic, and returns the status code and text.
5. **`build_response(status, body_text, keep_alive=True)`**:
   - Formats a compliant HTTP/1.1 response:
     ```http
     HTTP/1.1 200 OK\r\n
     Content-Length: 1\r\n
     Content-Type: text/plain\r\n
     Connection: keep-alive\r\n
     \r\n
     5
     ```
6. **`handle_connection(conn, addr)`**:
   - Sets an idle timeout (30 seconds).
   - Loops continuously over incoming requests on the same connection until the client explicitly disconnects, sends `Connection: close`, or times out.

---

## 4. How to Run & Verify

### Step 1: Start the Server
Open a terminal and run:
```bash
python3 1st_task.py
```
**Expected Output:**
```
listening on 0.0.0.0:8080
```

---

### Step 2: Automated Verification (Single Persistent TCP Socket Test)
In a second terminal, execute the automated test suite:
```bash
python3 test_task1.py
```

**What this test validates:**
1. Connects using `socket.create_connection(("localhost", 8080))`.
2. Sends all 8 test cases sequentially across the **exact same TCP socket**.
3. Asserts the status code, `Content-Length`, and body response for every request.
4. Asserts that the server **keeps the socket open** across all requests.
5. Tests the missing `Host` header error condition.

**Expected Test Output:**
```
Connecting to localhost:8080 over a single TCP socket...

---> Sending: GET /add?a=2&b=3 HTTP/1.1
<--- Received Status: HTTP/1.1 200 OK
<--- Received Body: 5

---> Sending: GET /sub?a=10&b=4 HTTP/1.1
<--- Received Status: HTTP/1.1 200 OK
<--- Received Body: 6

---> Sending: GET /mul?a=6&b=7 HTTP/1.1
<--- Received Status: HTTP/1.1 200 OK
<--- Received Body: 42

---> Sending: GET /div?a=9&b=3 HTTP/1.1
<--- Received Status: HTTP/1.1 200 OK
<--- Received Body: 3

---> Sending: GET /div?a=1&b=0 HTTP/1.1
<--- Received Status: HTTP/1.1 400 Bad Request
<--- Received Body: division by zero

---> Sending: GET /add?a=x&b=3 HTTP/1.1
<--- Received Status: HTTP/1.1 400 Bad Request
<--- Received Body: a and b must be numbers

---> Sending: GET /pow?a=2&b=8 HTTP/1.1
<--- Received Status: HTTP/1.1 404 Not Found
<--- Received Body: not found

---> Sending: POST /add HTTP/1.1
<--- Received Status: HTTP/1.1 405 Method Not Allowed
<--- Received Body: method not allowed

---> Sending request with missing Host header...
<--- Final Response:
HTTP/1.1 400 Bad Request
Content-Length: 19
Content-Type: text/plain
Connection: close

missing Host header

ALL TASK 1 TESTS PASSED SUCCESSFULLY ON A SINGLE PERSISTENT TCP SOCKET!
```

---

### Step 3: Manual Verification Using `curl`

You can also test individual endpoints directly via standard HTTP tools:

```bash
# 1. Addition -> 200 OK (5)
curl -i "http://localhost:8080/add?a=2&b=3"

# 2. Subtraction -> 200 OK (6)
curl -i "http://localhost:8080/sub?a=10&b=4"

# 3. Multiplication -> 200 OK (42)
curl -i "http://localhost:8080/mul?a=6&b=7"

# 4. Division -> 200 OK (3)
curl -i "http://localhost:8080/div?a=9&b=3"

# 5. Division by Zero -> 400 Bad Request
curl -i "http://localhost:8080/div?a=1&b=0"

# 6. Invalid parameters -> 400 Bad Request
curl -i "http://localhost:8080/add?a=x&b=3"

# 7. Unknown Endpoint -> 404 Not Found
curl -i "http://localhost:8080/pow?a=2&b=8"

# 8. POST Method -> 405 Method Not Allowed
curl -i -X POST "http://localhost:8080/add"
```

---

### Step 4: Verify Persistent Connection with Netcat / Raw Telnet
To manually confirm that the server doesn't close the connection after the first response:

```bash
nc localhost 8080
```
Paste the following block and press Enter:
```http
GET /add?a=2&b=3 HTTP/1.1
Host: localhost

GET /mul?a=6&b=7 HTTP/1.1
Host: localhost

```
**Observation**: Both responses (`5` and `42`) will be returned immediately, and the prompt will remain open waiting for further commands.
