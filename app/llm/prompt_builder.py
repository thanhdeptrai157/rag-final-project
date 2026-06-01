def build_rag_prompt(query: str, context: str) -> str:
    prompt = f"""
    Bạn là trợ lý trả lời câu hỏi dựa trên thông tin được cung cấp. Hãy sử dụng thông tin trong phần "Context" để trả lời câu hỏi một cách chính xác và đầy đủ nhất.
    [CONTEXT]
    {context}
    [/CONTEXT]
    [QUESTION]
    {query}
    [/QUESTION]
    Yêu cầu: 
    - Chỉ trả lời dựa trên context đã cho, không sử dụng kiến thức bên ngoài.
    - Nếu context không chứa đủ thông tin để trả lời, hãy trả lời "Không đủ thông tin".
    - Trả lời không được bịa đặt thông tin. Trả lài dài nhất có thể dựa trên context.
    - Khi trả lời, hãy trích dẫn phần thông tin trong context đã sử dụng để trả lời, ví dụ: [Dẫn chứng: <content>]. 
    - Khi trả lời, nếu văn bản có bổ sung, thay đổi, bãi bỏ so với văn bản gốc, hãy chỉ ra rõ ràng và trích dẫn phần văn bản gốc đã được bổ sung, thay đổi, bãi bỏ đó. Nêu rõ ra thay đổi điều gì, từ cái gì thành cái gì, bổ sung thêm gì, bãi bỏ cái gì. Ví dụ: [Bổ sung: <content>], [Thay đổi: <content> thành <content>], [Bãi bỏ: <content>].
    - Trả lời bằng tiếng Việt.
    - Trả về bằng markdown, sử dụng các thẻ như **bold** để nhấn mạnh thông tin quan trọng, sử dụng gạch đầu dòng hoặc số để liệt kê nếu cần thiết. Phải thụt lề hợp lý để dễ đọc. nếu có công thức toán học, hãy sử dụng định dạng LaTeX.
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
    6. Trả về JSON array string, mỗi phần tử là một truy vấn tìm kiếm đã được mở rộng. Dạng trả về: ["truy vấn 1", "truy vấn 2", ...]
    7. Trả lời bằng tiếng Việt.
    
    Câu hỏi cần mở rộng: {query}
    """
    return prompt.strip()
