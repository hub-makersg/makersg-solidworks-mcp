# Định dạng spec

Một mẫu đèn gồm hai file YAML:

- **template**: thiết kế dùng chung, có khối `params` khai báo các tham số có tên cùng giá trị mặc định;
- **order** (đơn hàng): `order_id` và các giá trị `params` cần ghi đè.

Đơn hàng chỉ được ghi đè tham số đã khai báo trong template. Khoá lạ bị từ chối kèm tên khoá.

Mọi chuỗi trong template có thể chứa `{tên}`:

- Nếu cả chuỗi chỉ là `{tên}`, nó lấy nguyên giá trị của tham số (số hoặc chữ).
- Nếu sau khi thay thế chuỗi chỉ còn phép tính số, nó được tính thành số. Ví dụ `"{width} + 20"`.
- Các trường hợp còn lại giữ nguyên là chữ. Ví dụ `"LAMP {label}"`.

Đơn vị là mm. Kích thước là **kích thước ngoài sau khi gập**.

## Mức đèn (lamp)

| Khoá | Ý nghĩa |
|---|---|
| `name` | Tên mẫu |
| `material` | `stainless`, `steel` hoặc `aluminium` |
| `thickness` | Độ dày tấm |
| `shop` | Tên xưởng (khoá bảng K), mặc định `default` |
| `die_v` | Độ mở cối V của xưởng; bỏ trống thì giả định 6 × độ dày |
| `coat_um` | Độ dày sơn tĩnh điện mỗi mặt (µm), mặc định 80 |
| `parts` | Danh sách part tôn |
| `printed_parts` | Chi tiết in 3D tham số (tuỳ chọn) |

## Part

Mỗi part là một hộp: đáy chữ nhật `width × depth`, có thể có các vách `front`, `back`, `left`, `right` gập lên. Part không có vách là một tấm phẳng.

```yaml
- name: shade
  width: 200
  depth: 200
  walls:
    front: {height: 80, lip: 8}            # mép gập vào trong 8 mm
    back:  {height: 80, hem: {length: 8}}  # open hem, chiều dài phần gập lại 8 mm
    left:  {height: 80}
  holes:    [{face: base, x: 0, y: 0, d: 40}]
  patterns: [{face: left, kind: hex, size: 8, web: 2, margin: 6}]
  texts:    [{face: front, text: "{label}", height: 20, y: 40, font: "C:/Windows/Fonts/arialbd.ttf"}]
  artworks: [{face: base, file: logo.svg, width: 60}]
  tabs:     [{wall: left, at: [-50, 50], width: 8}]
  slots:    [{face: base, x: 0, y: 30, tab_width: 8, angle: 90}]
```

### Toạ độ trên mặt

- `base`: gốc ở tâm đáy, `x` hướng về vách phải, `y` hướng về vách sau, nhìn từ phía có vách.
- Vách: nhìn từ **ngoài** hộp, `x` chạy dọc vách (gốc ở giữa vách, tăng sang phải người nhìn), `y` là độ cao tính từ mặt đáy ngoài.

Chữ trên vách đọc đúng khi nhìn từ ngoài hộp.

### Luật gia công được kiểm

Gọi T là độ dày, R là bán kính trong, V là độ mở cối.

- Vách, mép gập, hem ≥ max(4T, V/2 + T + R).
- Lỗ, hoa văn, chữ, khe phải cách bề mặt ngoài của nếp gập một khoảng 2R + 3T, tức cách tiếp tuyến nếp gập ≥ 2T + R. Với mép không có vách thì khoảng cách tối thiểu là T.
- Lỗ, nét chữ, cầu nối, vách giữa các lỗ hoa văn ≥ T.
- Hem kín bị từ chối vì nhiều xưởng chỉ chấn tới 120–130° và hem kín giữ hoá chất tiền xử lý sơn.
- Tab rộng ≥ max(2T, 3.2 mm), dài ≤ 5 × bề rộng. Mặc định tab dài bằng độ dày tấm cắm vào cộng 2 mm.
- Khe = kích thước tab + 0.25 mm + 4 × độ dày sơn.
- Hình DXF/SVG có đảo kín (phần sẽ rơi ra khi cắt) bị từ chối. Hãy thêm cầu nối trong file hình.

## Chi tiết in 3D

```yaml
printed_parts:
  - name: clip
    model: C:/models/clip.SLDPRT
    vars: {ord_width: "{width} / 10"}
```

Trong model, các kích thước cần đổi phải điều khiển bằng biến toàn cục (Equations) có tiền tố `ord_`. Model dùng equations liên kết file ngoài sẽ bị từ chối.
