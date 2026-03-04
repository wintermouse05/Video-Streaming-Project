# 3.8 Final Report — Video Streaming with RTSP and RTP

## Mục lục
1. [Kiến trúc hệ thống](#1-kiến-trúc-hệ-thống)
2. [RTSP Flow](#2-rtsp-flow)
3. [RTP Header Breakdown](#3-rtp-header-breakdown)
4. [Fragmentation](#4-fragmentation)
5. [TCP Encapsulation (HD Mode)](#5-tcp-encapsulation-hd-mode)
6. [Các tính năng nâng cao](#6-các-tính-năng-nâng-cao)
7. [Benchmark](#7-benchmark)
8. [Hướng dẫn chạy](#8-hướng-dẫn-chạy)

---

## 1. Kiến trúc hệ thống

### 1.1 Tổng quan

```
┌──────────────────┐          RTSP (TCP)           ┌──────────────────┐
│                  │ ◄──────────────────────────► │                  │
│     CLIENT       │      Control Channel          │     SERVER       │
│                  │                                │                  │
│  ClientLauncher  │    RTP/UDP (SD) hoặc           │  Server.py       │
│  Client.py       │    RTP/TCP (HD)                │  ServerWorker.py │
│                  │ ◄────────────────────────────  │                  │
│  RtpPacket.py    │      Data Channel              │  RtpPacket.py    │
│                  │                                │  VideoStream.py  │
└──────────────────┘                                └──────────────────┘
```

### 1.2 Các module

| Module           | Vai trò                                           |
|------------------|---------------------------------------------------|
| **Server.py**    | Lắng nghe kết nối RTSP từ client                  |
| **ServerWorker.py** | Xử lý RTSP request, gửi RTP packets           |
| **Client.py**    | GUI, gửi RTSP request, nhận/hiển thị video        |
| **ClientLauncher.py** | Khởi tạo Client, UI chọn SD/HD mode         |
| **RtpPacket.py** | Encode/Decode RTP packet (header + payload)       |
| **VideoStream.py** | Đọc frame từ file .Mjpeg                       |

### 1.3 Hai kênh truyền thông

```
┌─────────────────────────────────────────────────────────┐
│  Control Channel: RTSP over TCP (port 554 or custom)    │
│  ─ SETUP, PLAY, PAUSE, TEARDOWN                        │
│  ─ Reliable, ordered delivery                           │
├─────────────────────────────────────────────────────────┤
│  Data Channel: RTP over UDP (SD) or TCP (HD)            │
│  ─ Video frames encapsulated in RTP packets             │
│  ─ SD: Fast, low latency, may lose packets              │
│  ─ HD: Reliable, no packet loss, higher latency         │
└─────────────────────────────────────────────────────────┘
```

---

## 2. RTSP Flow

### 2.1 State Diagram

```
     ┌──────┐
     │ INIT │
     └──┬───┘
        │ SETUP (200 OK)
        ▼
     ┌──────┐
  ┌─►│READY │◄─────────────┐
  │  └──┬───┘              │
  │     │ PLAY (200 OK)    │ PAUSE (200 OK)
  │     ▼                  │
  │  ┌───────┐             │
  │  │PLAYING│─────────────┘
  │  └───┬───┘
  │      │ TEARDOWN (200 OK)
  │      ▼
  │  ┌──────┐
  └──│ INIT │
     └──────┘
```

### 2.2 RTSP Message Exchange

#### SETUP
```
Client → Server:
  SETUP movie.Mjpeg RTSP/1.0
  CSeq: 1
  Transport: RTP/UDP; client_port= 25000     ← SD mode
  -- hoặc --
  Transport: RTP/TCP; client_port= 25000     ← HD mode

Server → Client:
  RTSP/1.0 200 OK
  CSeq: 1
  Session: 123456
```

**Xử lý phía Client:**
1. Tạo TCP connection đến server (RTSP control)
2. Gửi SETUP request với Transport header
3. Parse response: lấy Session ID
4. Mở RTP port:
   - SD: UDP socket, bind port
   - HD: TCP server socket, listen on port

**Xử lý phía Server:**
1. Nhận SETUP, mở VideoStream
2. Parse Transport header → xác định mode (UDP/TCP) và port
3. Tạo Session ID, gửi 200 OK

#### PLAY
```
Client → Server:
  PLAY movie.Mjpeg RTSP/1.0
  CSeq: 2
  Session: 123456

Server → Client:
  RTSP/1.0 200 OK
  CSeq: 2
  Session: 123456
```

**Xử lý:**
1. Server tạo RTP socket:
   - SD: UDP datagram socket
   - HD: TCP connect đến client RTP port
2. Server bắt đầu thread `sendRtp()`: đọc frame → packetize → gửi mỗi 50ms
3. Client bắt đầu thread `listenRtp()`: nhận packet → decode → buffer
4. Client bắt đầu display loop: đọc từ buffer → hiển thị

#### PAUSE
```
Client → Server:
  PAUSE movie.Mjpeg RTSP/1.0
  CSeq: 3
  Session: 123456
```
- Server: set event → sendRtp thread dừng
- Client: set playEvent → listenRtp thread dừng, display loop dừng

#### TEARDOWN
```
Client → Server:
  TEARDOWN movie.Mjpeg RTSP/1.0
  CSeq: 4
  Session: 123456
```
- In session stats (total packets, lost packets, loss rate)
- Đóng tất cả socket
- Xóa cache file

---

## 3. RTP Header Breakdown

### 3.1 Cấu trúc RTP Header (12 bytes)

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|V=2|P|X|  CC   |M|     PT      |       Sequence Number         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                           Timestamp                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                             SSRC                              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                          Payload...                           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### 3.2 Chi tiết các trường

| Trường | Bits | Vị trí | Giá trị | Mô tả |
|--------|------|--------|---------|-------|
| **V** (Version) | 2 | Byte 0, bit 6-7 | `2` | RTP version 2 |
| **P** (Padding) | 1 | Byte 0, bit 5 | `0` | Không có padding |
| **X** (Extension) | 1 | Byte 0, bit 4 | `0` | Không có extension header |
| **CC** | 4 | Byte 0, bit 0-3 | `0` | Số Contributing Sources = 0 |
| **M** (Marker) | 1 | Byte 1, bit 7 | `0` | Không đánh dấu |
| **PT** (Payload Type) | 7 | Byte 1, bit 0-6 | `26` | MJPEG payload type |
| **Sequence Number** | 16 | Byte 2-3 | `frameNbr` | Số thứ tự frame (big-endian) |
| **Timestamp** | 32 | Byte 4-7 | `int(time())` | Unix timestamp (big-endian) |
| **SSRC** | 32 | Byte 8-11 | `0` | Source identifier |

### 3.3 Encode Implementation

```python
def encode(self, version, padding, extension, cc, seqnum, marker, pt, ssrc, payload):
    timestamp = int(time())
    header = bytearray(12)
    
    header[0] = (version << 6) | (padding << 5) | (extension << 4) | cc  # V|P|X|CC
    header[1] = (marker << 7) | pt                                        # M|PT
    header[2] = (seqnum >> 8) & 0xFF                                      # Seq (high)
    header[3] = seqnum & 0xFF                                              # Seq (low)
    header[4] = (timestamp >> 24) & 0xFF                                   # Timestamp
    header[5] = (timestamp >> 16) & 0xFF
    header[6] = (timestamp >> 8) & 0xFF
    header[7] = timestamp & 0xFF
    header[8] = (ssrc >> 24) & 0xFF                                        # SSRC
    header[9] = (ssrc >> 16) & 0xFF
    header[10] = (ssrc >> 8) & 0xFF
    header[11] = ssrc & 0xFF
    
    self.header = header
    self.payload = payload
```

### 3.4 Ví dụ packet thực tế

Giả sử frame #1, timestamp = 1709654400, SSRC = 0:
```
Byte 0:  10 00 0000 = 0x80  (V=2, P=0, X=0, CC=0)
Byte 1:  0 0011010 = 0x1A   (M=0, PT=26)
Byte 2:  0x00               (SeqNum high = 0)
Byte 3:  0x01               (SeqNum low = 1)
Byte 4-7: Timestamp (big-endian)
Byte 8-11: 0x00000000       (SSRC = 0)
Byte 12+: JPEG frame data
```

---

## 4. Fragmentation

### 4.1 UDP Fragmentation

Trong SD mode (RTP/UDP):
- Mỗi RTP packet chứa **một JPEG frame hoàn chỉnh**
- Kích thước frame MJPEG thường từ vài KB đến vài chục KB
- Nếu packet > MTU (thường 1500 bytes), **IP layer tự động fragment**
- Vấn đề: nếu bất kỳ fragment nào mất → toàn bộ packet bị discard

```
┌──────────────┐     IP Fragmentation      ┌──────────┐
│  RTP Packet  │  ──────────────────────►  │ Fragment 1│
│  (30KB)      │                            │ Fragment 2│
│              │                            │ Fragment 3│
│              │                            │ ...       │
│              │                            │ Fragment N│
└──────────────┘                            └──────────┘
```

### 4.2 Tại sao đây là vấn đề?

- UDP không có cơ chế retransmission
- Mất 1 IP fragment → mất toàn bộ frame
- Trên mạng congested: tỷ lệ mất frame tăng exponentially với kích thước frame
- **Giải pháp**: Application-level fragmentation (chia frame thành nhiều RTP packet nhỏ) — không implement trong lab này

### 4.3 So sánh

| Aspect | UDP (No App Fragmentation) | TCP |
|--------|---------------------------|-----|
| Fragmentation | IP layer | TCP stream (no fragmentation issue) |
| Lost fragment | Entire frame lost | TCP retransmits |
| Overhead | Low | Higher (ACK, retransmit) |

---

## 5. TCP Encapsulation (HD Mode)

### 5.1 Tại sao cần TCP cho HD?

- HD video = frame lớn hơn → nhiều IP fragment → nguy cơ mất gói cao hơn
- TCP cung cấp:
  - **Reliable delivery**: đảm bảo mọi byte đến đích
  - **In-order delivery**: frame đến đúng thứ tự
  - **Flow control**: tránh overwhelm receiver
  - **Congestion control**: thích ứng với bandwidth mạng

### 5.2 TCP Framing Protocol

Vì TCP là byte stream (không có ranh giới message), cần **length prefix** để xác định ranh giới mỗi RTP packet:

```
┌──────────────────────────────────────────┐
│  4 bytes (Big-Endian)  │   N bytes       │
│  Length = N            │   RTP Packet    │
│                        │  (Header+Data)  │
└──────────────────────────────────────────┘
```

### 5.3 Server gửi (ServerWorker.py)

```python
# TCP: gửi với length prefix
packet = self.makeRtp(data, frameNumber)
lengthPrefix = struct.pack('>I', len(packet))    # 4 bytes, big-endian
self.clientInfo['rtpSocket'].sendall(lengthPrefix + packet)
```

### 5.4 Client nhận (Client.py)

```python
# TCP: đọc length prefix rồi đọc data
lengthBytes = self.recvExact(self.rtpSocket, 4)     # Đọc 4 bytes
length = struct.unpack('>I', lengthBytes)[0]         # Parse length
data = self.recvExact(self.rtpSocket, length)        # Đọc RTP packet
```

### 5.5 Xử lý timeout trong recvExact

```python
def recvExact(self, sock, n):
    """Đọc chính xác n bytes, xử lý timeout và stop condition."""
    data = b''
    while len(data) < n:
        if self.playEvent.isSet() or self.teardownAcked == 1:
            return None        # Dừng khi PAUSE/TEARDOWN
        try:
            chunk = sock.recv(n - len(data))
            if not chunk:
                return None    # Connection closed
            data += chunk
        except socket.timeout:
            continue           # Retry on timeout
    return data
```

### 5.6 TCP Connection Lifecycle

```
SETUP:
  Client → TCP Listen on RTP port
  
PLAY (first time):
  Server → TCP Connect to Client RTP port
  Client → Accept connection
  ── Data flows ──
  
PAUSE:
  Server → Stop sending (event.set())
  Client → Stop receiving (playEvent.set())
  ── Connection stays open ──
  
PLAY (resume):
  Server → Resume sending on SAME connection
  Client → Resume receiving on SAME connection
  
TEARDOWN:
  Both → Close TCP connection
```

---

## 6. Các tính năng nâng cao

### 6.1 Frame Buffer Queue (3.1)

**Mục đích**: Giảm jitter bằng cách buffer N frame trước khi hiển thị.

```
Receive Thread:  ──► [Frame Buffer (deque)] ──► Display Loop
                     │ frame1 │ frame2 │ ... │ frameN │
```

- Buffer size: 10 frames (configurable via `BUFFER_SIZE`)
- Khi PLAY: đợi buffer đủ 10 frame mới bắt đầu hiển thị
- Display loop chạy via `tkinter.after(50ms)` (~20 FPS)

### 6.2 Jitter Handling (3.2)

- Nếu buffer rỗng khi cần hiển thị frame → **buffer underrun**
- Tạm dừng hiển thị, đợi buffer nạp thêm frame
- Khi buffer đủ frame → tự động resume
- Console log: `[JITTER] Buffer underrun - pausing display temporarily`

### 6.3 FPS Monitor (3.4)

- Đếm số frame hiển thị trong mỗi giây
- In ra console mỗi giây: `[FPS] 19.8 frames/sec | Buffer: 8 | Lost: 0`
- Reset counter mỗi giây

### 6.4 Packet Loss Detection (3.5)

- Theo dõi expected sequence number
- Nếu nhận seq > expected → phát hiện gap → log mất gói
- Per-packet log: `[PACKET LOSS] Lost 2 packet(s): expected seq 45, got 47`
- Session summary khi TEARDOWN:
  ```
  [STATS] Session Summary (SD mode - UDP):
    Total packets received: 500
    Packets lost: 3
    Packet loss rate: 0.60%
  ```

### 6.5 SD/HD Mode UI (3.3)

- Dropdown Combobox trong ClientLauncher: "SD (UDP)" / "HD (TCP)"
- Có thể chọn trước khi nhấn SETUP
- Sau SETUP, không cho phép đổi mode
- Mode ảnh hưởng:
  - Transport header trong SETUP request
  - Loại socket (UDP vs TCP) cho RTP data
  - Server sending mechanism

---

## 7. Benchmark

(Xem chi tiết tại [benchmark_report.md](benchmark_report.md))

### Tóm tắt

| Metric | SD (UDP) | HD (TCP) |
|--------|----------|----------|
| FPS | 18-20 | 18-20 |
| Latency | ~1-5ms | ~5-15ms |
| Packet Loss | 0-5% | 0% |
| Jitter | Có thể cao | Thấp |
| Reliability | Không đảm bảo | 100% |

**Kết luận**: 
- SD (UDP) phù hợp cho real-time streaming khi chấp nhận mất frame
- HD (TCP) phù hợp khi cần chất lượng video đầy đủ không mất frame

---

## 8. Hướng dẫn chạy

### 8.1 Yêu cầu
- Python 3.x
- Thư viện: Pillow (`pip install Pillow`), tkinter (có sẵn)

### 8.2 Khởi động Server
```bash
python Server.py 5540
```

### 8.3 Khởi động Client
```bash
python ClientLauncher.py 127.0.0.1 5540 25000 movie.Mjpeg
```

### 8.4 Sử dụng
1. **Chọn mode**: SD (UDP) hoặc HD (TCP) trong dropdown
2. **Setup**: Nhấn nút Setup → thiết lập session
3. **Play**: Nhấn nút Play → video bắt đầu (sau buffering)
4. **Pause**: Nhấn nút Pause → tạm dừng
5. **Teardown**: Nhấn nút Teardown → kết thúc, xem stats

### 8.5 Console Output mẫu

```
[MODE] Selected: SD (UDP)

Data sent:
SETUP movie.Mjpeg RTSP/1.0
CSeq: 1
Transport: RTP/UDP; client_port= 25000

Current Seq Num: 1
Current Seq Num: 2
...
[BUFFER] Initial buffering complete (10 frames)
[FPS] 19.5 frames/sec | Buffer: 8 | Lost: 0
[FPS] 20.0 frames/sec | Buffer: 10 | Lost: 0
...
==================================================
[STATS] Session Summary (SD mode - UDP):
  Total packets received: 500
  Packets lost: 2
  Packet loss rate: 0.40%
==================================================
```

---

## Phụ lục

### A. File format (.Mjpeg)
- Mỗi frame bắt đầu bằng 5 bytes chứa frame length (ASCII)
- Tiếp theo là JPEG data với kích thước đã chỉ định
- Ví dụ: `04523` + 4523 bytes JPEG data

### B. Cấu trúc project
```
Video-Streaming-Project/
├── Server.py              # RTSP server entry point
├── ServerWorker.py        # Xử lý RTSP + gửi RTP
├── Client.py              # RTSP client + nhận/hiển thị video
├── ClientLauncher.py      # Khởi tạo client + SD/HD UI
├── RtpPacket.py           # RTP packet encode/decode
├── VideoStream.py         # Đọc .Mjpeg file
├── movie.Mjpeg            # Sample video file
├── benchmark_report.md    # Báo cáo benchmark (3.6)
├── test_cases.md          # Thiết kế test case (3.7)
├── final_report.md        # Báo cáo tổng kết (3.8)
└── task.txt               # Mô tả bài tập
```
