# 3.7 Test Case Design — Video Streaming System

## Mục tiêu
Kiểm thử toàn diện hệ thống video streaming với các kịch bản: SD mode, HD mode, PLAY/PAUSE liên tục, và điều kiện mạng bất lợi.

---

## Test Suite 1: Chức năng cơ bản (Basic Functionality)

### TC-1.1: SETUP thành công
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Server đang chạy, Client mới khởi động |
| **Steps** | 1. Mở Client. 2. Nhấn "Setup" |
| **Expected** | - State chuyển từ INIT → READY<br>- Server trả về 200 OK<br>- RTP socket được tạo<br>- Session ID được gán |
| **Verify** | Console hiện "Data sent: SETUP..." và server hiện "processing SETUP" |

### TC-1.2: PLAY thành công
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | SETUP đã thành công (state = READY) |
| **Steps** | 1. Nhấn "Play" |
| **Expected** | - State: READY → PLAYING<br>- Buffer bắt đầu tích lũy frame<br>- Sau 10 frames, video hiển thị<br>- FPS hiện trên console |
| **Verify** | Thấy "[BUFFER] Initial buffering complete (10 frames)" và "[FPS] ..." |

### TC-1.3: PAUSE thành công
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Đang PLAYING |
| **Steps** | 1. Nhấn "Pause" |
| **Expected** | - State: PLAYING → READY<br>- Video dừng hiển thị<br>- Buffer giữ lại frame chưa hiển thị |
| **Verify** | Video dừng, không có lỗi trên console |

### TC-1.4: TEARDOWN thành công
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Đã SETUP (state != INIT) |
| **Steps** | 1. Nhấn "Teardown" |
| **Expected** | - Session summary in ra console<br>- Cache file bị xóa<br>- GUI đóng |
| **Verify** | Xem stats trên console: Total packets, Lost packets, Loss rate |

---

## Test Suite 2: SD Mode (UDP)

### TC-2.1: Streaming SD đầy đủ
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Mode dropdown = "SD (UDP)" |
| **Steps** | 1. Chọn SD (UDP). 2. Setup → Play. 3. Xem toàn bộ video |
| **Expected** | - Transport header: "RTP/UDP"<br>- Video chạy mượt ~20 FPS<br>- Có thể có packet loss nhỏ |
| **Verify** | Console: FPS ~18-20, kiểm tra packet loss stats |

### TC-2.2: SD với packet loss detection
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | SD mode |
| **Steps** | 1. Setup → Play. 2. Quan sát sequence numbers |
| **Expected** | - Sequence numbers tăng liên tục<br>- Nếu có gap → "[PACKET LOSS]" xuất hiện |
| **Verify** | Console log hiện sequence numbers và cảnh báo mất gói (nếu có) |

---

## Test Suite 3: HD Mode (TCP)

### TC-3.1: Streaming HD đầy đủ
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Mode dropdown = "HD (TCP)" |
| **Steps** | 1. Chọn HD (TCP). 2. Setup → Play. 3. Xem toàn bộ video |
| **Expected** | - Transport header: "RTP/TCP"<br>- TCP connection established<br>- 0% packet loss<br>- Video không mất frame |
| **Verify** | Console: "[TCP] RTP data connection established", loss = 0% |

### TC-3.2: HD mode — không mất frame
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | HD mode đang PLAYING |
| **Steps** | 1. Chạy toàn bộ video. 2. Kiểm tra stats khi TEARDOWN |
| **Expected** | - Packet loss = 0<br>- Packet loss rate = 0.00% |
| **Verify** | "[STATS] Packets lost: 0" |

### TC-3.3: Không chuyển mode sau SETUP
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Đã nhấn SETUP |
| **Steps** | 1. Setup. 2. Thử thay đổi dropdown sang mode khác |
| **Expected** | - Dropdown reset về mode hiện tại<br>- Console: "[MODE] Cannot change mode after SETUP" |
| **Verify** | Mode không thay đổi |

---

## Test Suite 4: PLAY/PAUSE liên tục (Stress Test)

### TC-4.1: PLAY → PAUSE → PLAY nhanh
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | SETUP thành công |
| **Steps** | 1. Play. 2. Đợi 2s. 3. Pause. 4. Đợi 1s. 5. Play. 6. Lặp lại 5 lần |
| **Expected** | - Video tiếp tục mượt sau mỗi lần resume<br>- Không crash, không treo<br>- Buffer tái sử dụng frame còn lại |
| **Verify** | Không có exception trên console, video hiển thị liên tục |

### TC-4.2: PLAY → PAUSE ngay lập tức
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | SETUP thành công |
| **Steps** | 1. Play. 2. Ngay lập tức Pause (< 0.5s). 3. Play lại |
| **Expected** | - Không crash<br>- Video tiếp tục bình thường |
| **Verify** | Không có lỗi trên console |

### TC-4.3: PAUSE khi buffer đang load
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Vừa nhấn PLAY, buffer chưa đủ 10 frames |
| **Steps** | 1. Play. 2. Pause trong lúc buffer đang tải |
| **Expected** | - Buffering dừng<br>- Không crash |
| **Verify** | Khi Play lại, buffer tải tiếp và hiển thị bình thường |

---

## Test Suite 5: Frame Buffer & Jitter (3.1 + 3.2)

### TC-5.1: Initial buffering
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Mới nhấn PLAY |
| **Steps** | 1. Play. 2. Quan sát thời gian trước khi video hiển thị |
| **Expected** | - Video không hiển thị ngay<br>- Đợi đủ 10 frames mới hiển thị<br>- Console: "[BUFFER] Initial buffering complete" |
| **Verify** | Có delay ~0.5s trước khi video bắt đầu |

### TC-5.2: Buffer underrun (jitter handling)
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | Video đang chạy |
| **Steps** | 1. Trong trường hợp buffer hết frame (mạng chậm) |
| **Expected** | - Console: "[JITTER] Buffer underrun - pausing display temporarily"<br>- Video tạm dừng<br>- Tự động tiếp tục khi buffer đủ frame |
| **Verify** | Video không giật mạnh, tạm dừng mượt |

---

## Test Suite 6: FPS Monitor (3.4)

### TC-6.1: FPS output
| Mục | Chi tiết |
|-----|---------|
| **Steps** | 1. Setup → Play. 2. Quan sát console mỗi giây |
| **Expected** | - Mỗi giây in: "[FPS] X.X frames/sec \| Buffer: Y \| Lost: Z"<br>- FPS ~18-20 |
| **Verify** | FPS update mỗi giây, giá trị hợp lý |

---

## Test Suite 7: Packet Loss Detection (3.5)

### TC-7.1: Phát hiện packet loss (UDP)
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | SD (UDP) mode |
| **Steps** | 1. Play toàn bộ video. 2. Xem stats khi Teardown |
| **Expected** | - Nếu có gap trong seq num → "[PACKET LOSS] Lost X packet(s)"<br>- Stats summary cuối session |
| **Verify** | Console log chính xác số packet mất |

### TC-7.2: Không mất packet (TCP)
| Mục | Chi tiết |
|-----|---------|
| **Precondition** | HD (TCP) mode |
| **Steps** | 1. Play toàn bộ video. 2. Xem stats khi Teardown |
| **Expected** | - Không có "[PACKET LOSS]" message<br>- Loss rate = 0.00% |
| **Verify** | Stats: "Packets lost: 0" |

---

## Test Suite 8: Edge Cases & Error Handling

### TC-8.1: File không tồn tại
| Mục | Chi tiết |
|-----|---------|
| **Steps** | 1. Khởi động client với file không tồn tại: `python ClientLauncher.py 127.0.0.1 5540 25000 nonexist.Mjpeg` |
| **Expected** | - Server trả về 404<br>- Client xử lý lỗi |

### TC-8.2: Server không chạy
| Mục | Chi tiết |
|-----|---------|
| **Steps** | 1. Khởi động client khi server chưa start |
| **Expected** | - Connection Failed warning dialog |

### TC-8.3: Đóng cửa sổ khi đang play
| Mục | Chi tiết |
|-----|---------|
| **Steps** | 1. Play video. 2. Nhấn nút X (close window) |
| **Expected** | - Dialog "Are you sure you want to quit?"<br>- Cancel → tiếp tục play<br>- OK → teardown + close |

---

## Tổng kết kết quả test

| Test Suite | Số TC | Pass | Fail | Notes |
|-----------|-------|------|------|-------|
| Basic Functionality | 4 | - | - | |
| SD Mode (UDP) | 2 | - | - | |
| HD Mode (TCP) | 3 | - | - | |
| PLAY/PAUSE Stress | 3 | - | - | |
| Buffer & Jitter | 2 | - | - | |
| FPS Monitor | 1 | - | - | |
| Packet Loss | 2 | - | - | |
| Edge Cases | 3 | - | - | |
| **Total** | **20** | - | - | |

> Điền kết quả Pass/Fail sau khi thực hiện test trên môi trường thực tế.
