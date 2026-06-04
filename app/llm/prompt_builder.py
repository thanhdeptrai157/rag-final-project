def build_rag_prompt(query: str, context: str) -> str:
    prompt = f"""
Bạn là trợ lý trả lời câu hỏi dựa trên thông tin được cung cấp.

[CONTEXT]
{context}
[/CONTEXT]

[QUESTION]
{query}
[/QUESTION]

Yêu cầu:

- Chỉ trả lời dựa trên context đã cho, không sử dụng kiến thức bên ngoài.
- Nếu context không chứa đủ thông tin để trả lời, hãy trả lời: "Không đủ thông tin".
- Không được bịa đặt hoặc suy diễn vượt quá thông tin trong context.
- Nếu OCR có lỗi chính tả, hãy cố gắng suy luận và sửa lỗi OCR trước khi trả lời.

QUY TRÌNH SUY LUẬN BẮT BUỘC:

1. Xác định tất cả các đoạn thông tin trong context có liên quan đến câu hỏi.
2. Nếu một điều khoản dẫn chiếu tới phụ lục, bảng biểu, điều khoản hoặc văn bản khác trong context thì phải tổng hợp thông tin từ tất cả các phần được dẫn chiếu trước khi kết luận.
3. Nếu tồn tại nhiều trường hợp áp dụng khác nhau (ví dụ theo đối tượng, chương trình đào tạo, khóa tuyển sinh, thời gian áp dụng, điều kiện áp dụng...) thì phải liệt kê đầy đủ các trường hợp liên quan.
4. Nếu context chứa bảng:
   - Xác định đúng hàng và cột được sử dụng.
   - Không được lấy dữ liệu từ cột khác để thay thế.
   - Nếu có nhiều giá trị trong cùng một hàng nhưng thuộc các cột khác nhau thì phải nêu rõ từng giá trị tương ứng với từng cột hoặc từng trường hợp áp dụng.
5. Trước khi kết luận, hãy tự kiểm tra:
   - Có bỏ sót điều khoản liên quan nào trong context không?
   - Có phụ lục hoặc bảng quy đổi nào liên quan không?
   - Có nhiều trường hợp áp dụng khác nhau không?
   - Có nhiều giá trị khác nhau cùng liên quan đến câu hỏi không?

YÊU CẦU TRẢ LỜI:

- Trả lời bằng tiếng Việt.
- Trả lời đầy đủ nhất có thể dựa trên context.
- Trả về bằng Markdown.
- Sử dụng danh sách, tiêu đề, in đậm để trình bày rõ ràng.
- Khi trả lời phải trích dẫn các phần thông tin đã sử dụng, ví dụ:
  [Dẫn chứng: ...]
- Nếu phát hiện nội dung bổ sung, sửa đổi hoặc bãi bỏ so với văn bản gốc thì phải nêu rõ:
  - [Bổ sung: ...]
  - [Thay đổi: ... thành ...]
  - [Bãi bỏ: ...]

Chỉ xuất ra câu trả lời cuối cùng, không hiển thị các bước suy luận trung gian.
"""
    return prompt.strip()


def build_expand_query_prompt(query: str) -> str:
    prompt = f"""
    Bạn là trợ lý mở rộng câu hỏi cho hệ thống RAG. Nhiệm vụ của bạn là mở rộng câu hỏi đầu vào để nó trở nên chi tiết và cụ thể hơn, giúp hệ thống RAG có thể tìm kiếm thông tin chính xác hơn.
    Nhiệm vụ của bạn là: 
    Từ câu hỏi người dùng, hãy tạo 3-5 truy vấn tìm kiếm để lấy đúng điều khoản liên quan.
    Quy tắc:
    1. Không trả lời câu hỏi
    2. Không suy luận kết luận cuối cùng
    3. Giữ lại các thực thể quan trọng: loại quy định, đối tượng áp dụng, điểm số, thời gian, địa điểm, mốc thời gian, v.v.
    4. Bổ sung các từ đồng nghĩa và cách diễn đạt trong văn bản pháp quy để tăng khả năng tìm kiếm trúng đích.
    5. Nếu câu hỏi có số liệu/điều kiện, tạo thêm truy vấn tìm "điều kiện", "tiêu chuẩn", "mức", "xét", "quy định".
    6. Trả về JSON array string, mỗi phần tử là một truy vấn tìm kiếm đã được mở rộng. Dạng trả về: ["truy vấn 1", "truy vấn 2", ...] không được có ```json hoặc bất kỳ định dạng nào khác, chỉ trả về đúng JSON array string.  
    7. Trả lời bằng tiếng Việt.
    
    Câu hỏi cần mở rộng: {query}
    """
    return prompt.strip()
