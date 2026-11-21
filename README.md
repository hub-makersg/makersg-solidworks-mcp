# swlamp-mcp

MCP server mã nguồn mở để Claude thiết kế đèn decor bằng tôn (cắt laser, chấn) trên SolidWorks 2025. Claude viết bản mô tả (spec) YAML cho một mẫu đèn. Với mỗi đơn hàng, server dựng part sheet metal trong SolidWorks đang mở và tạo một thư mục riêng cho đơn, gồm:

- DXF phẳng cho xưởng (`CUT`, `BEND_UP`, `BEND_DOWN`, đơn vị mm);
- file SLDPRT, 3MF, STL;
- ảnh xem trước;
- bản tóm tắt.

*English: an open-source MCP server that lets Claude design flat-pack sheet-metal decor lamps in SolidWorks 2025, from a YAML spec to a per-order folder of shop-ready flat DXF (CUT / BEND_UP / BEND_DOWN), SLDPRT, 3MF and STL. Windows only.*

## Làm được gì

- Hộp hoặc khay từ 0 đến 4 vách. Mỗi vách có thể có mép gập vào trong hoặc open hem. Không có vách nào thì part là một tấm phẳng (nắp, đế).
- Lỗ tròn, hoa văn lưới hoặc lục giác, hình DXF/SVG cắt xuyên.
- Chữ khắc cắt xuyên. Lõi của các chữ có vòng kín như O, A, D được tự nối cầu nên không rơi ra.
- Khớp tab-slot giữa các tấm để lắp không cần hàn. Khe được nới theo độ dày sơn tĩnh điện.
- Mỗi đơn chỉ đổi tham số (kích thước, chữ, hoa văn). Template không bao giờ bị sửa.
- Chi tiết in 3D: bạn tự dựng model tham số có biến toàn cục `ord_*`. MCP sao chép model, đổi biến theo đơn rồi xuất 3MF/STL.
- Hiệu chỉnh hệ số K bằng thanh thử chữ L. K được lưu theo xưởng, vật liệu, độ dày và độ mở cối V.
- DXF chỉ được giao khi cả hai cổng kiểm đều đạt:
  - part SolidWorks dựng ra khớp kích thước ngoài trong spec trong 0.05 mm;
  - flat pattern của SolidWorks khớp file DXF trong 0.05 mm.

Phiên bản đã kiểm: **SolidWorks 2025 SP5** (bản desktop), Windows 10, Python 3.11. Phiên bản SW khác chưa kiểm; nếu bạn chạy được hoặc gặp lỗi, hãy báo lại.

## Cài đặt

Yêu cầu: Windows, SolidWorks 2025 có license, [uv](https://docs.astral.sh/uv/).

```powershell
git clone <repo> swlamp-mcp
cd swlamp-mcp
uv sync
uv run swlamp-mcp --prepare   # tạo sẵn wrapper COM cho SolidWorks 2025
```

Đăng ký với Claude Code:

```powershell
claude mcp add --transport stdio swlamp --scope user -- uv run --directory C:\duong\dan\swlamp-mcp swlamp-mcp
```

Với Claude Desktop, thêm vào `claude_desktop_config.json`:

```json
{ "mcpServers": { "swlamp": { "command": "uv", "args": ["run", "--directory", "C:\\duong\\dan\\swlamp-mcp", "swlamp-mcp"] } } }
```

Mở SolidWorks trước khi gọi tool. MCP không tự khởi động SolidWorks.

## Dùng thử

1. Mở SolidWorks 2025.
2. Nhờ Claude: "Kiểm `examples/box4-inox08.template.yaml` rồi chạy đơn `examples/order-300.yaml`".
3. Kết quả nằm trong `Documents\swlamp-orders\o300\`. Đọc `summary.md` trước khi gửi xưởng.

| Tool | Việc |
|---|---|
| `sw_status` | Kiểm tra SolidWorks đang chạy |
| `validate_spec` | Kiểm luật gia công, tính bản phẳng (không cần SW) |
| `preview_flat` | Ảnh bản phẳng dự đoán (không cần SW) |
| `run_order` | Dựng và xuất trọn một đơn |
| `screenshot`, `measure` | Xem và đo part đang mở |
| `calibration_coupon`, `calibration_record`, `k_table` | Hiệu chỉnh hệ số K |
| `export_mesh` | Xuất 3MF/STL part đang mở |

Tool `run_script` (chạy Python tuỳ ý trong SolidWorks) chỉ xuất hiện khi đặt biến môi trường `SWLAMP_ENABLE_SCRIPT=1`.

Biến môi trường khác:

- `SWLAMP_OUTPUT_DIR`: nơi tạo thư mục đơn.
- `SWLAMP_CONFIG_DIR`: nơi lưu bảng K, mặc định `%APPDATA%\swlamp`.

## Trước khi gia công thật

Khi chưa hiệu chỉnh, K chỉ là giá trị tạm, và `summary.md` ghi rõ "K chưa hiệu chỉnh". Làm theo [docs/calibration.md](docs/calibration.md) cho từng cặp xưởng + vật liệu + độ dày.

- Tiêu chí ±0.5 mm áp cho kích thước ngoài đi qua tối đa 2 nếp gập, đo tại nếp gập.
- Hiệu chỉnh chỉ có giá trị với nếp 90°. Hem 180° luôn ghi là chưa hiệu chỉnh.

Định dạng spec: [docs/spec-format.md](docs/spec-format.md).

## Phát triển

```powershell
uv run ruff check
uv run pytest -m "not sw"   # không cần SolidWorks
uv run pytest -m sw          # cần SolidWorks 2025 đang mở; khoảng 10 phút
```

## Ghi công

Dự án tham khảo ý tưởng (không sao chép mã) từ các repo MIT sau:

- [soheil-mp/solidworks-mcp](https://github.com/soheil-mp/solidworks-mcp): đặt tên tool sheet metal;
- [aryesil/SolidworksMCP](https://github.com/aryesil/SolidworksMCP): xuất flat pattern;
- [hjbaard/SolidWorks-MCP](https://github.com/hjbaard/SolidWorks-MCP): lớp COM Python với early binding và luồng STA.

Quy tắc gia công lấy từ hướng dẫn công khai của Protolabs, Hubs, SendCutSend và TheFabricator.

Giấy phép: MIT.
