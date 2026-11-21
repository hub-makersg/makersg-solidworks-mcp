# Hiệu chỉnh hệ số K

DXF chỉ ra đúng kích thước sau chấn khi K khớp với cách xưởng chấn. K phụ thuộc vào vật liệu, độ dày và cối chấn, nên mỗi tổ hợp **xưởng + vật liệu + độ dày + độ mở cối V** cần hiệu chỉnh một lần.

## Các bước

1. Nhờ Claude gọi `calibration_coupon` với vật liệu và độ dày (thêm `shop` và `die_v` nếu biết). Tool tạo một thanh chữ L rộng 100 mm, hai cánh 40 mm, có khắc mã vật liệu, và trả về **chiều dài phẳng L**.
2. Gửi `coupon__coupon-*.dxf` cho xưởng. Nhờ xưởng chấn đúng 90° bằng cối sẽ dùng cho hàng thật, nên làm 3 thanh.
3. Đo từng thanh:
   - dùng thước cặp đo hai **cạnh ngoài** A và B (từ mặt ngoài cánh này tới mép xa của cánh kia);
   - mỗi cạnh đo 3 điểm dọc theo nếp gập rồi lấy trung bình;
   - kiểm góc bằng ê-ke: lệch quá 0.5° thì báo xưởng.
4. Gọi `calibration_record` với L và các cặp số đo (A, B). Từ đó các đơn dùng cùng khoá sẽ được ghi "đã hiệu chỉnh".

Công thức:

```
BD = A + B − L
BA = 2·(R + T) − BD
K  = (BA / (π/2) − R) / T
```

R là bán kính trong giả định, xấp xỉ p × V, với p = 0.21 (inox), 0.16 (thép), 0.12 (nhôm). Bảng K luôn lưu K cùng với R đã dùng để tính ra nó.

## Giới hạn

- Hiệu chỉnh chỉ có giá trị với nếp 90°. Nếp ở góc khác và hem 180° luôn được ghi "chưa hiệu chỉnh" trong `summary.md`.
- K tính ra nằm ngoài khoảng 0.25–0.55 thường là do giả định độ mở cối V sai. Hãy hỏi xưởng độ mở cối thật, khai báo `die_v`, rồi hiệu chỉnh lại.
- Kể cả khi K đúng, sai số góc chấn ±1° trên vách cao 50 mm làm mép lệch khoảng 0.9 mm. Tiêu chí ±0.5 mm chỉ áp cho kích thước ngoài đo tại nếp gập.
